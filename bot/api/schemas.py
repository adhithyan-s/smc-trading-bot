from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class AlertType(str, Enum):
    ZONE_IDENTIFIED  = "zone_identified"   # 1H: OB/FVG zone found inside Fib range
    PRICE_IN_ZONE    = "price_in_zone"     # 15M: price entered the zone
    ENTRY_SIGNAL     = "entry_signal"      # 5M: candle pattern confirmed → place trade
    ZONE_INVALIDATED = "zone_invalidated"  # price closed below zone — cancel setup


class TradingViewAlert(BaseModel):
    """
    JSON payload sent by TradingView Pine Script webhook.
    Every field has a default so partial alerts don't crash the server.
    """
    secret: str = Field(..., description="Must match WEBHOOK_SECRET in .env")

    alert_type: AlertType
    symbol: str = Field(default="SOLUSDT")
    timeframe: str = Field(default="")          # "4h" | "1h" | "15m" | "5m"

    # Price data at alert time
    close: float = Field(default=0.0)
    high:  float = Field(default=0.0)
    low:   float = Field(default=0.0)

    # Zone info (populated on zone_identified)
    zone_top:    Optional[float] = None
    zone_bottom: Optional[float] = None
    fib_high:    Optional[float] = None
    fib_low:     Optional[float] = None
    fib_level:   Optional[str]  = None    # "0.382" | "0.500" | "0.618"
    setup_type:  Optional[str]  = None    # "OB+FVG" | "FVG"

    # Trend context (populated on zone_identified)
    trend:       Optional[str]  = None    # "bullish" | "bearish"
    swing_high:  Optional[float] = None
    swing_low:   Optional[float] = None

    # Entry signal (populated on entry_signal)
    pattern:     Optional[str]  = None    # "engulfing" | "doji" | "pin_bar"
    rsi:         Optional[float] = None
    macd_line:   Optional[float] = None
    macd_signal: Optional[float] = None

    class Config:
        use_enum_values = True


class WebhookResponse(BaseModel):
    status: str
    message: str
    signal_id: Optional[str] = None