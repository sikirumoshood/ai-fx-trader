from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BasePredictor(ABC):
    """Abstract interface for all prediction models.

    All models must implement predict() so the signal engine
    can swap between Kronos, Moirai, TFT, etc. via config only.
    """

    @abstractmethod
    def predict(self, candles: pd.DataFrame) -> pd.DataFrame:
        """
        Args:
            candles: OHLCV DataFrame with columns [open, high, low, close, volume].
                     Must contain at least as many rows as the model's context window.

        Returns:
            DataFrame with predicted next candle(s): columns [open, high, low, close].
        """
        raise NotImplementedError
