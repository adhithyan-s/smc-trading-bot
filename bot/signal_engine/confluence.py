import pandas as pd
from dataclasses import dataclass
from bot.signal_engine.timeframe_4h import analyse_4h, Analysis4H
from bot.signal_engine.timeframe_1h import analyse_1h, Analysis1H
from bot.signal_engine.timeframe_15m import analyse_15m, Analysis15M
from bot.signal_engine.timeframe_5m import analyse_5m, Analysis5M
from bot.config.logging_config import logger


@dataclass
class TradeSignal:
    """
    Final output of the confluence engine.
    If is_valid=True, the risk manager picks this up and sizes the trade.
    """
    is_valid: bool

    # Setup context
    symbol: str
    direction: str           # "bullish" | "bearish"
    setup_type: str          # "OB+FVG" | "FVG" | "OB"

    # Price levels
    entry_price: float
    zone_top: float
    zone_bottom: float
    swing_high: float
    swing_low: float

    # Entry trigger
    pattern: str | None
    atr: float

    # Confluence details
    trend_4h: str
    rsi_value: float
    macd_line: float
    macd_signal: float
    confluence_score: int    # 0–4

    # Fib context
    fib_zone_top: float
    fib_zone_bottom: float

    # Rejection reason (when is_valid=False)
    rejection_reason: str = ""


def run_confluence(
    symbol: str,
    df_4h: pd.DataFrame,
    df_1h: pd.DataFrame,
    df_15m: pd.DataFrame,
    df_5m: pd.DataFrame,
) -> TradeSignal:
    """
    Runs the full multi-timeframe SMC confluence check.

    Pipeline:
      4H -> trend + swing H/L + Fib zone
      1H -> OB/FVG detection inside Fib zone
      15M -> price in zone + RSI + MACD confirmation
      5M -> candle pattern entry trigger

    Each stage gates the next. If any stage fails, returns is_valid=False
    with a reason so we can see exactly where the signal broke down.

    Args:
        symbol: e.g. "SOLUSDT"
        df_4h, df_1h, df_15m, df_5m: OHLCV DataFrames for each timeframe,
            columns = [open, high, low, close, volume], index = datetime ascending

    Returns:
        TradeSignal
    """
    def _reject(reason: str) -> TradeSignal:
        logger.info(f"[{symbol}] Signal rejected: {reason}")
        return TradeSignal(
            is_valid=False, symbol=symbol, direction="", setup_type="",
            entry_price=0, zone_top=0, zone_bottom=0,
            swing_high=0, swing_low=0, pattern=None, atr=0,
            trend_4h="", rsi_value=0, macd_line=0, macd_signal=0,
            confluence_score=0, fib_zone_top=0, fib_zone_bottom=0,
            rejection_reason=reason,
        )

    logger.info(f"[{symbol}] Running confluence engine...")

    # --- Stage 1: 4H ---
    a4h: Analysis4H = analyse_4h(df_4h)
    if not a4h.is_valid:
        return _reject(f"4H trend is '{a4h.trend}' - not tradeable")

    # --- Stage 2: 1H ---
    a1h: Analysis1H = analyse_1h(df_1h, a4h)
    if not a1h.is_valid:
        return _reject("No OB/FVG setup found inside Fib 38.2%-61.8% zone on 1H")

    # --- Stage 3: 15M ---
    a15m: Analysis15M = analyse_15m(df_15m, a1h)
    if not a15m.is_valid:
        return _reject(
            f"15M confluence failed - in_zone={a15m.price_in_zone} "
            f"rsi={a15m.rsi_value:.1f} macd_ok={a15m.macd_ok}"
        )

    # --- Stage 4: 5M ---
    a5m: Analysis5M = analyse_5m(df_5m, a15m)
    if not a5m.is_valid:
        return _reject("No valid candle pattern on 5M entry candle")

    # --- All stages passed ---
    setup = a1h.best_setup
    signal = TradeSignal(
        is_valid = True,
        symbol = symbol,
        direction = a4h.trend,
        setup_type = setup.setup_type,
        entry_price = a5m.entry_price,
        zone_top = setup.zone_top,
        zone_bottom = setup.zone_bottom,
        swing_high = a4h.swing_high,
        swing_low = a4h.swing_low,
        pattern = a5m.pattern,
        atr = a5m.atr,
        trend_4h = a4h.trend,
        rsi_value = a15m.rsi_value,
        macd_line = a15m.macd_line,
        macd_signal = a15m.macd_signal,
        confluence_score = a15m.confluence_score,
        fib_zone_top = a4h.fib_zone_top,
        fib_zone_bottom = a4h.fib_zone_bottom,
    )

    logger.info(
        f"[{symbol}] SIGNAL CONFIRMED | "
        f"{signal.direction} {signal.setup_type} | "
        f"Entry: {signal.entry_price:.4f} | "
        f"Zone: {signal.zone_bottom:.4f}–{signal.zone_top:.4f} | "
        f"Pattern: {signal.pattern} | "
        f"Confluence: {signal.confluence_score}/4"
    )

    return signal