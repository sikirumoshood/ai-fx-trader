from __future__ import annotations

from functools import lru_cache
from typing import Optional

from config.settings import FINBERT_MODEL

# Lazy imports — avoid loading PyTorch at import time
_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline as hf_pipeline
        _pipeline = hf_pipeline(
            "text-classification",
            model=FINBERT_MODEL,
            tokenizer=FINBERT_MODEL,
            top_k=None,          # return all labels
            device=-1,           # CPU
            truncation=True,
            max_length=512,
        )
    return _pipeline


# ── Label normalisation ───────────────────────────────────────────────────────

# FinBERT outputs: "positive", "negative", "neutral"
_LABEL_MAP = {
    "positive": "BULLISH",
    "negative": "BEARISH",
    "neutral":  "NEUTRAL",
}


# ── Public API ────────────────────────────────────────────────────────────────

def score_headline(headline: str) -> dict:
    """Score a single headline with FinBERT.

    Returns:
        {
            "label":    "BULLISH" | "BEARISH" | "NEUTRAL",
            "score":    float,          # confidence of the winning label
            "raw":      dict[str, float]  # all three label scores
        }
    """
    pipe = _get_pipeline()
    results = pipe(headline)[0]  # list of {label, score}
    raw = {_LABEL_MAP.get(r["label"].lower(), r["label"]): r["score"] for r in results}
    best = max(raw, key=raw.get)
    return {"label": best, "score": raw[best], "raw": raw}


def aggregate_bias(headlines: list[str]) -> tuple[str, float]:
    """Score multiple headlines and return an aggregate bias.

    Returns (bias, confidence) where bias is "BULLISH" | "BEARISH" | "NEUTRAL".
    Confidence is the mean score of the winning label.
    """
    if not headlines:
        return "NEUTRAL", 0.0

    pipe = _get_pipeline()
    totals: dict[str, float] = {"BULLISH": 0.0, "BEARISH": 0.0, "NEUTRAL": 0.0}

    for headline in headlines:
        result = pipe(headline)[0]
        for r in result:
            label = _LABEL_MAP.get(r["label"].lower(), "NEUTRAL")
            totals[label] += r["score"]

    n = len(headlines)
    averages = {k: v / n for k, v in totals.items()}
    bias = max(averages, key=averages.get)

    # Require at least a 5% edge over neutral to call directional bias
    if bias != "NEUTRAL":
        edge = averages[bias] - averages["NEUTRAL"]
        if edge < 0.05:
            bias = "NEUTRAL"

    return bias, round(averages[bias], 3)


def score_events(events: list[dict], pair: str) -> tuple[str, float]:
    """Score economic calendar event names relevant to a pair.

    Uses event name + forecast vs previous as proxy for headline sentiment.
    Returns (bias, confidence).
    """
    headlines = _events_to_headlines(events, pair)
    if not headlines:
        return "NEUTRAL", 0.0
    return aggregate_bias(headlines)


def _events_to_headlines(events: list[dict], pair: str) -> list[str]:
    """Convert calendar event dicts to pseudo-headlines for FinBERT."""
    base = pair[:3].upper()
    quote = pair[3:6].upper()
    relevant_currencies = {base, quote}

    headlines: list[str] = []
    for event in events:
        if event.get("currency") not in relevant_currencies:
            continue
        name = event.get("name", "")
        forecast = event.get("forecast")
        previous = event.get("previous")

        # Build a minimal headline FinBERT can score
        if forecast and previous and forecast != previous:
            headlines.append(
                f"{name}: forecast {forecast}, previous {previous}"
            )
        elif name:
            headlines.append(name)

    return headlines
