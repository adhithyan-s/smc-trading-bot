import pandas as pd
from dataclasses import dataclass
from bot.signal_engine.indicators import calculate_atr, detect_candle_pattern
from bot.signal_engine.timeframe_15m import Analysis15M
from bot.config.logging_config import logger


@dataclass
class Analysis5M:
    pattern: str | None       # "engulfing" | "doji" | "pin_bar" | "marubozu" | None
    entry_price: float        # suggested entry (close of trigger candle)
    atr: float                # current ATR value
    is_valid: bool            # True if a valid pattern detected AND 15M confirmed


def analyse_5m(df: pd.DataFrame, analysis_15m: Analysis15M) -> Analysis5M:
    """
    Analyses the 5M chart for a candle pattern entry trigger.

    Only fires if:
    - 15M analysis is valid (price in zone + RSI/MACD confluence)
    - A recognised bullish pattern appears on the last closed candle

    The entry candle is the most recently CLOSED candle (iloc[-2]),
    not the still-forming one (iloc[-1]).

    Args:
        df: 5M OHLCV DataFrame
        analysis_15m: Result from analyse_15m()

    Returns:
        Analysis5M
    """
    empty = Analysis5M(pattern=None, entry_price=0.0, atr=0.0, is_valid=False)

    if not analysis_15m.is_valid:
        logger.info("5M: Skipping - 15M confluence not met.")
        return empty

    if len(df) < 20:
        logger.warning(f"5M: Not enough candles ({len(df)}).")
        return empty

    atr_series = calculate_atr(df["high"], df["low"], df["close"])
    atr_value = float(atr_series.iloc[-1])

    # Use the last CLOSED candle for pattern detection
    trigger_candle = df.iloc[-2]
    pattern = detect_candle_pattern(trigger_candle, atr=atr_value)

    if pattern:
        entry_price = float(trigger_candle["close"])
        logger.info(
            f"5M | Pattern detected: {pattern} | "
            f"Entry: {entry_price:.4f} | ATR: {atr_value:.4f}"
        )
        return Analysis5M(
            pattern = pattern,
            entry_price = entry_price,
            atr = atr_value,
            is_valid = True,
        )
    else:
        logger.info(f"5M | No valid pattern on last closed candle. ATR={atr_value:.4f}")
        return empty