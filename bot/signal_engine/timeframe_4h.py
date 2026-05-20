import pandas as pd
from dataclasses import dataclass
from bot.signal_engine.indicators import (
    detect_trend,
    find_swing_high,
    find_swing_low,
    calculate_fib_levels,
    get_fib_zone,
)
from bot.config.logging_config import logger


@dataclass
class Analysis4H:
    trend: str               # "bullish" | "bearish" | "ranging"
    swing_high: float
    swing_low: float
    fib_zone_top: float      # 38.2% level
    fib_zone_bottom: float   # 61.8% level
    fib_levels: dict
    is_valid: bool           # False if trend is ranging — skip signal


def analyse_4h(df: pd.DataFrame, lookback: int = 20) -> Analysis4H:
    """
    Analyses the 4H chart to determine:
    1. Current trend direction (bullish/bearish/ranging)
    2. Most recent swing high and swing low
    3. Fibonacci retracement levels from swing H/L
    4. The golden zone (38.2%-61.8%) where we look for OB/FVG

    Args:
        df: OHLCV DataFrame with columns [open, high, low, close, volume]
            Index should be datetime, sorted ascending.
        lookback: number of candles to look back for swing H/L detection.

    Returns:
        Analysis4H dataclass
    """
    if len(df) < max(lookback, 50):
        logger.warning(f"4H: Not enough candles ({len(df)}) for analysis. Need {max(lookback, 50)}.")
        return Analysis4H(
            trend="ranging",
            swing_high=0, swing_low=0,
            fib_zone_top=0, fib_zone_bottom=0,
            fib_levels={}, is_valid=False,
        )

    trend      = detect_trend(df["close"])
    swing_high = find_swing_high(df["high"], lookback=lookback)
    swing_low  = find_swing_low(df["low"],   lookback=lookback)

    if swing_high <= swing_low:
        logger.warning(f"4H: Invalid swing levels — high={swing_high} low={swing_low}")
        return Analysis4H(
            trend=trend,
            swing_high=swing_high, swing_low=swing_low,
            fib_zone_top=0, fib_zone_bottom=0,
            fib_levels={}, is_valid=False,
        )

    fib_levels               = calculate_fib_levels(swing_high, swing_low)
    fib_zone_bottom, fib_zone_top = get_fib_zone(swing_high, swing_low)

    is_valid = trend in ("bullish", "bearish")

    logger.info(
        f"4H Analysis | Trend: {trend} | "
        f"Swing H: {swing_high:.4f} L: {swing_low:.4f} | "
        f"Fib zone: {fib_zone_bottom:.4f}–{fib_zone_top:.4f} | "
        f"Valid: {is_valid}"
    )

    return Analysis4H(
        trend=trend,
        swing_high=swing_high,
        swing_low=swing_low,
        fib_zone_top=fib_zone_top,
        fib_zone_bottom=fib_zone_bottom,
        fib_levels=fib_levels,
        is_valid=is_valid,
    )