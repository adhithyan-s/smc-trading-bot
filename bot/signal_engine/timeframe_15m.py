import pandas as pd
from dataclasses import dataclass
from bot.signal_engine.indicators import calculate_rsi, calculate_macd
from bot.signal_engine.timeframe_1h import Analysis1H, ZoneSetup
from bot.config.logging_config import logger


@dataclass
class Analysis15M:
    price_in_zone: bool       # is current price inside the setup zone?
    price_bouncing: bool      # has price bounced off zone bottom (higher low forming)?
    rsi_value: float
    rsi_ok: bool              # RSI < 50 for bullish (oversold bounce from zone)
    macd_line: float
    macd_signal: float
    macd_ok: bool             # MACD line crossing above signal (momentum shift)
    confluence_score: int     # 0–4: how many conditions are met
    is_valid: bool            # True if price in zone AND at least RSI or MACD confirms


def _check_price_in_zone(current_price: float, zone: ZoneSetup, buffer_pct: float = 0.002) -> bool:
    """
    Returns True if price is inside the zone or within buffer_pct of zone top.
    buffer_pct=0.002 means 0.2% above zone top is still acceptable.
    """
    buffer = zone.zone_top * buffer_pct
    return zone.zone_bottom <= current_price <= (zone.zone_top + buffer)


def _check_price_bouncing(df: pd.DataFrame, zone: ZoneSetup, lookback: int = 3) -> bool:
    """
    Checks if price has touched the zone and is forming a higher low —
    i.e. the last `lookback` lows are rising after touching zone bottom.
    """
    recent_lows = df["low"].iloc[-lookback:]
    touched_zone = any(low <= zone.zone_top for low in recent_lows)
    if not touched_zone:
        return False
    # Higher low: most recent low is higher than the one before
    return float(df["low"].iloc[-1]) > float(df["low"].iloc[-2])


def analyse_15m(df: pd.DataFrame, analysis_1h: Analysis1H) -> Analysis15M:
    """
    Analyses the 15M chart for confluence when price is in the OB/FVG zone.

    Conditions checked:
    1. Price is inside the zone (or just touched it)
    2. Price is bouncing (higher low forming)
    3. RSI < 50 (bullish — not overbought, coming from oversold)
    4. MACD line > signal line (momentum turning bullish)

    At least conditions 1 + one of (3 or 4) required for is_valid = True.

    Args:
        df: 15M OHLCV DataFrame
        analysis_1h: Result from analyse_1h()

    Returns:
        Analysis15M
    """
    empty = Analysis15M(
        price_in_zone=False, price_bouncing=False,
        rsi_value=0, rsi_ok=False,
        macd_line=0, macd_signal=0, macd_ok=False,
        confluence_score=0, is_valid=False,
    )

    if not analysis_1h.is_valid or analysis_1h.best_setup is None:
        logger.info("15M: Skipping — no valid 1H setup.")
        return empty

    if len(df) < 30:
        logger.warning(f"15M: Not enough candles ({len(df)}).")
        return empty

    zone = analysis_1h.best_setup
    current_price = float(df["close"].iloc[-1])

    # --- Condition 1: price in zone ---
    price_in_zone = _check_price_in_zone(current_price, zone)

    # --- Condition 2: bouncing ---
    price_bouncing = _check_price_bouncing(df, zone)

    # --- Condition 3: RSI ---
    rsi_series = calculate_rsi(df["close"])
    rsi_value = float(rsi_series.iloc[-1])
    rsi_ok = rsi_value < 50   # for bullish: not overbought

    # --- Condition 4: MACD ---
    macd_line_s, macd_signal_s, _ = calculate_macd(df["close"])
    macd_line = float(macd_line_s.iloc[-1])
    macd_signal = float(macd_signal_s.iloc[-1])
    macd_ok = macd_line > macd_signal   # momentum flipping bullish

    # Score
    score = sum([price_in_zone, price_bouncing, rsi_ok, macd_ok])
    is_valid = price_in_zone and (rsi_ok or macd_ok)

    logger.info(
        f"15M | Price: {current_price:.4f} | In zone: {price_in_zone} | "
        f"Bouncing: {price_bouncing} | RSI: {rsi_value:.1f} ({rsi_ok}) | "
        f"MACD: {macd_line:.4f} vs {macd_signal:.4f} ({macd_ok}) | "
        f"Score: {score}/4 | Valid: {is_valid}"
    )

    return Analysis15M(
        price_in_zone = price_in_zone,
        price_bouncing = price_bouncing,
        rsi_value = rsi_value,
        rsi_ok = rsi_ok,
        macd_line = macd_line,
        macd_signal = macd_signal,
        macd_ok = macd_ok,
        confluence_score = score,
        is_valid = is_valid,
    )