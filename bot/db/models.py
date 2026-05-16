from sqlalchemy import (
    Column, String, Float, Boolean, DateTime,
    Integer, Text, Enum as SAEnum, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timezone
import uuid
import enum


class Base(DeclarativeBase):
    pass


def utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TradeStatus(str, enum.Enum):
    OPEN      = "open"
    CLOSED    = "closed"
    CANCELLED = "cancelled"

class TradeDirection(str, enum.Enum):
    LONG  = "long"
    SHORT = "short"

class SignalStatus(str, enum.Enum):
    PENDING   = "pending"    # waiting for price to reach zone
    TRIGGERED = "triggered"  # price entered zone
    CONFIRMED = "confirmed"  # all TF confluence met → order placed
    EXPIRED   = "expired"    # zone invalidated


# ---------------------------------------------------------------------------
# Trades — one row per completed or open trade
# ---------------------------------------------------------------------------

class Trade(Base):
    __tablename__ = "trades"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol          = Column(String(20), nullable=False, index=True)
    direction       = Column(SAEnum(TradeDirection), nullable=False)
    status          = Column(SAEnum(TradeStatus), nullable=False, default=TradeStatus.OPEN)

    # Price levels
    entry_price     = Column(Float, nullable=False)
    stop_loss       = Column(Float, nullable=False)
    take_profit_1   = Column(Float, nullable=True)   # first TP target
    take_profit_2   = Column(Float, nullable=True)   # second TP / structure high
    exit_price      = Column(Float, nullable=True)

    # Sizing
    position_size   = Column(Float, nullable=False)  # in base currency (e.g. SOL)
    capital_at_risk = Column(Float, nullable=False)  # USDT risked on this trade
    risk_percent    = Column(Float, nullable=False)  # e.g. 1.5

    # P&L
    pnl_usdt        = Column(Float, nullable=True)
    pnl_percent     = Column(Float, nullable=True)
    fees_usdt       = Column(Float, nullable=True, default=0.0)

    # Setup metadata
    setup_type      = Column(String(20), nullable=True)   # e.g. "OB+FVG", "FVG"
    fib_level       = Column(String(10), nullable=True)   # e.g. "0.618"
    timeframe_entry = Column(String(5),  nullable=True)   # e.g. "5m"
    signal_id       = Column(UUID(as_uuid=True), nullable=True)  # FK to signals

    # Exchange
    bybit_order_id  = Column(String(64), nullable=True)
    is_paper        = Column(Boolean, default=True)

    # Timestamps
    opened_at       = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    closed_at       = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_trades_symbol_status", "symbol", "status"),
        Index("ix_trades_opened_at", "opened_at"),
    )

    def __repr__(self):
        return f"<Trade {self.symbol} {self.direction} @ {self.entry_price} [{self.status}]>"


# ---------------------------------------------------------------------------
# Signals — one row per detected SMC setup
# ---------------------------------------------------------------------------

class Signal(Base):
    __tablename__ = "signals"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol          = Column(String(20), nullable=False, index=True)

    # Zone definition
    setup_type      = Column(String(20), nullable=False)  # "OB+FVG" | "FVG"
    zone_top        = Column(Float, nullable=False)
    zone_bottom     = Column(Float, nullable=False)
    fib_high        = Column(Float, nullable=False)
    fib_low         = Column(Float, nullable=False)
    fib_level_entry = Column(String(10), nullable=False)  # "0.382" | "0.618"

    # Confluence flags
    trend_4h        = Column(String(10), nullable=True)   # "bullish" | "bearish"
    ob_confirmed    = Column(Boolean, default=False)
    fvg_confirmed   = Column(Boolean, default=False)
    rsi_ok          = Column(Boolean, default=False)
    macd_ok         = Column(Boolean, default=False)
    pattern_5m      = Column(String(30), nullable=True)   # "engulfing" | "doji"

    # Status
    status          = Column(SAEnum(SignalStatus), default=SignalStatus.PENDING, nullable=False)
    raw_payload     = Column(Text, nullable=True)   # original TradingView webhook JSON

    # Timestamps
    detected_at     = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    triggered_at    = Column(DateTime(timezone=True), nullable=True)
    confirmed_at    = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_signals_symbol_status", "symbol", "status"),
        Index("ix_signals_detected_at", "detected_at"),
    )


# ---------------------------------------------------------------------------
# Performance — daily snapshots for equity curve / drawdown tracking
# ---------------------------------------------------------------------------

class PerformanceSnapshot(Base):
    __tablename__ = "performance"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    date            = Column(DateTime(timezone=True), nullable=False, unique=True, index=True)

    # Capital
    equity          = Column(Float, nullable=False)   # total account value
    daily_pnl       = Column(Float, nullable=False)
    cumulative_pnl  = Column(Float, nullable=False)

    # Trade stats (rolling)
    total_trades    = Column(Integer, default=0)
    winning_trades  = Column(Integer, default=0)
    losing_trades   = Column(Integer, default=0)
    win_rate        = Column(Float, nullable=True)    # 0.0 – 1.0
    avg_rr          = Column(Float, nullable=True)    # average risk:reward achieved
    profit_factor   = Column(Float, nullable=True)    # gross profit / gross loss

    # Drawdown
    peak_equity     = Column(Float, nullable=True)
    drawdown_pct    = Column(Float, nullable=True)    # current drawdown from peak

    created_at      = Column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------------------
# Market data — OHLCV snapshots fetched from Bybit
# ---------------------------------------------------------------------------

class MarketData(Base):
    __tablename__ = "market_data"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    symbol      = Column(String(20), nullable=False)
    timeframe   = Column(String(5),  nullable=False)   # "5m" | "15m" | "1h" | "4h"
    open_time   = Column(DateTime(timezone=True), nullable=False)
    open        = Column(Float, nullable=False)
    high        = Column(Float, nullable=False)
    low         = Column(Float, nullable=False)
    close       = Column(Float, nullable=False)
    volume      = Column(Float, nullable=False)

    __table_args__ = (
        Index("ix_market_data_symbol_tf_time", "symbol", "timeframe", "open_time", unique=True),
    )