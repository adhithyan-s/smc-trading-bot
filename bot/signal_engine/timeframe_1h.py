import pandas as pd
from dataclasses import dataclass, field
from bot.signal_engine.indicators import find_order_blocks, find_fvgs
from bot.signal_engine.timeframe_4h import Analysis4H
from bot.config.logging_config import logger


@dataclass
class ZoneSetup:
    setup_type: str       # "OB+FVG" | "FVG" | "OB"
    zone_top: float
    zone_bottom: float
    ob: dict = field(default_factory=dict)
    fvg: dict = field(default_factory=dict)
    strength: float = 0.0


@dataclass
class Analysis1H:
    setups: list[ZoneSetup]    # ranked by strength, best first
    best_setup: ZoneSetup | None
    is_valid: bool             # True if at least one setup found in Fib zone


def _is_in_fib_zone(level_top: float, level_bottom: float,
                    zone_top: float, zone_bottom: float,
                    overlap_pct: float = 0.5) -> bool:
    """
    Returns True if a zone overlaps with the Fib golden zone by at least overlap_pct.
    We don't require perfect containment — partial overlap is fine.
    """
    overlap_top = min(level_top, zone_top)
    overlap_bottom = max(level_bottom, zone_bottom)
    if overlap_top <= overlap_bottom:
        return False
    overlap_size = overlap_top - overlap_bottom
    zone_size = level_top - level_bottom
    return (overlap_size / zone_size) >= overlap_pct


def analyse_1h(df: pd.DataFrame, analysis_4h: Analysis4H) -> Analysis1H:
    """
    Analyses the 1H chart to find OB+FVG or FVG setups inside the Fibonacci 38.2%-61.8% golden zone identified on 4H.

    Priority ranking:
    1. OB + FVG overlap -> strongest (institutional confluence)
    2. FVG alone        -> good
    3. OB alone         -> acceptable

    Args:
        df: 1H OHLCV DataFrame
        analysis_4h:  Result from analyse_4h()

    Returns:
        Analysis1H with ranked setups
    """
    if not analysis_4h.is_valid:
        logger.info("1H: Skipping — 4H analysis not valid.")
        return Analysis1H(setups=[], best_setup=None, is_valid=False)

    direction = analysis_4h.trend
    zone_top = analysis_4h.fib_zone_top
    zone_bottom = analysis_4h.fib_zone_bottom

    obs  = find_order_blocks(df, direction=direction, lookback=30)
    fvgs = find_fvgs(df, direction=direction, lookback=30)

    # Filter to only those inside (or overlapping) the Fib golden zone
    obs_in_zone = [ob  for ob  in obs  if _is_in_fib_zone(ob["top"],  ob["bottom"],  zone_top, zone_bottom)]
    fvgs_in_zone = [fvg for fvg in fvgs if _is_in_fib_zone(fvg["top"], fvg["bottom"], zone_top, zone_bottom)]

    logger.info(
        f"1H | OBs in Fib zone: {len(obs_in_zone)} | "
        f"FVGs in Fib zone: {len(fvgs_in_zone)}"
    )

    setups = []

    # --- OB + FVG overlap (strongest setup) ---
    for ob in obs_in_zone:
        for fvg in fvgs_in_zone:
            overlap_top = min(ob["top"],    fvg["top"])
            overlap_bottom = max(ob["bottom"], fvg["bottom"])
            if overlap_top > overlap_bottom:
                combined_strength = ob["strength"] + fvg["size"] * 10
                setups.append(ZoneSetup(
                    setup_type  = "OB+FVG",
                    zone_top = overlap_top,
                    zone_bottom = overlap_bottom,
                    ob = ob,
                    fvg = fvg,
                    strength = round(combined_strength, 3),
                ))

    # --- FVG alone ---
    for fvg in fvgs_in_zone:
        setups.append(ZoneSetup(
            setup_type = "FVG",
            zone_top = fvg["top"],
            zone_bottom = fvg["bottom"],
            fvg = fvg,
            strength = round(fvg["size"] * 10, 3),
        ))

    # --- OB alone (lowest priority) ---
    for ob in obs_in_zone:
        setups.append(ZoneSetup(
            setup_type = "OB",
            zone_top = ob["top"],
            zone_bottom = ob["bottom"],
            ob = ob,
            strength = ob["strength"],
        ))

    # Rank by strength
    setups.sort(key=lambda x: x.strength, reverse=True)
    best = setups[0] if setups else None

    if best:
        logger.info(
            f"1H | Best setup: {best.setup_type} | "
            f"Zone: {best.zone_bottom:.4f}–{best.zone_top:.4f} | "
            f"Strength: {best.strength}"
        )
    else:
        logger.info("1H | No valid setups found in Fib zone.")

    return Analysis1H(
        setups = setups,
        best_setup = best,
        is_valid = best is not None,
    )