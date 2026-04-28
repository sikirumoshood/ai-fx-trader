from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from model.base import BasePredictor
from config.settings import (
    KRONOS_MODEL, KRONOS_TOKENIZER, KRONOS_DEVICE,
    KRONOS_CONTEXT, KRONOS_PRED_LEN, KRONOS_TEMPERATURE, KRONOS_SAMPLES,
)


class KronosPredictor(BasePredictor):
    """Wrapper around the Kronos foundational time-series model.

    Loads NeoQuasar/Kronos-base (or whichever variant is configured) from
    HuggingFace and exposes a standard predict() interface.

    Lazy-loads on first predict() call so the API server starts instantly
    even when the model weights have not been downloaded yet.
    """

    def __init__(
        self,
        model_id: str = KRONOS_MODEL,
        tokenizer_id: str = KRONOS_TOKENIZER,
        device: str = KRONOS_DEVICE,
        max_context: int = KRONOS_CONTEXT,
        pred_len: int = KRONOS_PRED_LEN,
        temperature: float = KRONOS_TEMPERATURE,
        sample_count: int = KRONOS_SAMPLES,
    ) -> None:
        self.model_id      = model_id
        self.tokenizer_id  = tokenizer_id
        self.device        = device
        self.max_context   = max_context
        self.pred_len      = pred_len
        self.temperature   = temperature
        self.sample_count  = sample_count
        self._predictor    = None   # loaded lazily

    # ── Lazy load ─────────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load Kronos model and tokenizer from HuggingFace.

        Uses the vendored Kronos repo (vendor/Kronos). Because Kronos uses
        'model' as its internal package name — the same name as our own
        model/ package — we temporarily swap sys.modules['model'] so the
        two don't collide.
        """
        import sys, os

        vendor_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "vendor", "Kronos")
        )
        if not os.path.isdir(vendor_root):
            raise ImportError(
                "Kronos vendor directory not found. Run:\n"
                "  git clone https://github.com/shiyu-coder/Kronos.git vendor/Kronos"
            )

        # ── isolate import to avoid model/ name collision ──────────────────
        # Save and remove our model/* entries from sys.modules temporarily
        saved = {k: v for k, v in sys.modules.items()
                 if k == "model" or k.startswith("model.")}
        for k in saved:
            del sys.modules[k]

        if vendor_root not in sys.path:
            sys.path.insert(0, vendor_root)

        try:
            from kronos import Kronos, KronosTokenizer
            from kronos import KronosPredictor as _KronosPredictor
        except Exception as exc:
            raise ImportError(f"Failed to import Kronos from vendor: {exc}") from exc
        finally:
            # Remove vendor from path and Kronos's model/* from sys.modules,
            # then restore our own model package
            if vendor_root in sys.path:
                sys.path.remove(vendor_root)
            for k in list(sys.modules.keys()):
                if k == "model" or k.startswith("model."):
                    del sys.modules[k]
            sys.modules.update(saved)
        # ── end isolation ──────────────────────────────────────────────────

        tokenizer = KronosTokenizer.from_pretrained(self.tokenizer_id)
        model_obj = Kronos.from_pretrained(self.model_id)
        self._predictor = _KronosPredictor(
            model_obj,
            tokenizer,
            device=self.device,
            max_context=self.max_context,
        )

    def is_loaded(self) -> bool:
        return self._predictor is not None

    # ── BasePredictor interface ───────────────────────────────────────────────

    def predict(self, candles: pd.DataFrame, pred_len: Optional[int] = None) -> pd.DataFrame:
        """Predict the next pred_len candles from OHLCV context.

        Args:
            candles: DataFrame with columns [open, high, low, close, volume]
                     and a DatetimeTZDtype 'time' column (UTC).
                     Must have at least 2 rows; max_context rows are used.

        Returns:
            DataFrame with columns [open, high, low, close] for the next
            pred_len candles, indexed 0…pred_len-1.
        """
        if self._predictor is None:
            self._load()

        df = candles.copy()
        if "time" in df.columns:
            df = df.set_index("time")

        # Trim to context window
        if len(df) > self.max_context:
            df = df.iloc[-self.max_context:]

        # Timestamps for the prediction window
        last_time: datetime = df.index[-1]
        if hasattr(last_time, "tzinfo") and last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)

        n = pred_len if pred_len is not None else self.pred_len
        freq = _infer_freq(df)
        x_timestamp = pd.Series(pd.DatetimeIndex(df.index))
        y_timestamp = pd.Series(pd.DatetimeIndex([last_time + freq * (i + 1) for i in range(n)]))

        pred_df = self._predictor.predict(
            df=df[["open", "high", "low", "close", "volume"]],
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=n,
            T=self.temperature,
            top_p=0.9,
            sample_count=self.sample_count,
            verbose=False,
        )

        return pred_df[["open", "high", "low", "close"]].reset_index(drop=True)

    # ── Convenience ───────────────────────────────────────────────────────────

    def predict_next(self, candles: pd.DataFrame) -> dict:
        """Return the immediately next predicted candle as a plain dict."""
        pred = self.predict(candles)
        row = pred.iloc[0]
        return {
            "open":  float(row["open"]),
            "high":  float(row["high"]),
            "low":   float(row["low"]),
            "close": float(row["close"]),
        }

    def estimate_confidence(self, candles: pd.DataFrame) -> float:
        """Estimate directional confidence from a single prediction.

        Uses the magnitude of the predicted move relative to recent volatility
        as a proxy for confidence. Falls back to 0.6 if unavailable.
        """
        try:
            pred = self.predict(candles)
            row = pred.iloc[0]
            predicted_move = abs(row["close"] - row["open"])
            # Normalise by recent ATR (last 14 candles)
            df = candles.copy()
            if "time" in df.columns:
                df = df.set_index("time")
            recent = df.iloc[-14:]
            atr = float((recent["high"] - recent["low"]).mean()) if len(recent) >= 2 else 1e-5
            confidence = min(0.95, 0.5 + 0.5 * (predicted_move / (atr + 1e-8)))
            return round(confidence, 3)
        except Exception:
            return 0.6  # fallback — neutral-ish confidence


# ── Helpers ───────────────────────────────────────────────────────────────────

def _infer_freq(df: pd.DataFrame) -> timedelta:
    """Infer candle frequency from the DataFrame index."""
    if len(df) >= 2:
        delta = df.index[-1] - df.index[-2]
        if isinstance(delta, timedelta):
            return delta
    return timedelta(hours=1)  # fallback to H1
