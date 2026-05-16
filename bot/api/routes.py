from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from bot.api.schemas import TradingViewAlert, WebhookResponse, AlertType
from bot.config.settings import get_settings
from bot.config.logging_config import logger
from bot.db.session import get_db
from bot.db.models import Signal, SignalStatus
import json
import uuid

settings = get_settings()
router = APIRouter()


def _validate_secret(alert: TradingViewAlert):
    if alert.secret != settings.webhook_secret:
        logger.warning("Webhook received with invalid secret — rejected.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret.",
        )


def _handle_alert(alert: TradingViewAlert) -> str:
    """
    Core dispatch logic — runs in background after webhook returns 200.
    Returns the signal_id created or updated.
    """
    signal_id = str(uuid.uuid4())

    with get_db() as db:

        if alert.alert_type == AlertType.ZONE_IDENTIFIED:
            logger.info(f"[{alert.symbol}] Zone identified: {alert.setup_type} "
                        f"zone={alert.zone_bottom}–{alert.zone_top} "
                        f"fib={alert.fib_level} trend={alert.trend}")

            signal = Signal(
                id=uuid.UUID(signal_id),
                symbol=alert.symbol,
                setup_type=alert.setup_type or "UNKNOWN",
                zone_top=alert.zone_top or 0.0,
                zone_bottom=alert.zone_bottom or 0.0,
                fib_high=alert.fib_high or 0.0,
                fib_low=alert.fib_low or 0.0,
                fib_level_entry=alert.fib_level or "0.618",
                trend_4h=alert.trend,
                status=SignalStatus.PENDING,
                raw_payload=json.dumps(alert.model_dump()),
            )
            db.add(signal)

        elif alert.alert_type == AlertType.PRICE_IN_ZONE:
            logger.info(f"[{alert.symbol}] Price entered zone at {alert.close}")
            # Find the most recent pending signal for this symbol
            signal = (
                db.query(Signal)
                .filter(Signal.symbol == alert.symbol, Signal.status == SignalStatus.PENDING)
                .order_by(Signal.detected_at.desc())
                .first()
            )
            if signal:
                signal.status = SignalStatus.TRIGGERED
                from datetime import datetime, timezone
                signal.triggered_at = datetime.now(timezone.utc)
                signal_id = str(signal.id)
                logger.info(f"Signal {signal_id} updated to TRIGGERED")
            else:
                logger.warning(f"[{alert.symbol}] Price in zone but no pending signal found.")

        elif alert.alert_type == AlertType.ENTRY_SIGNAL:
            logger.info(f"[{alert.symbol}] Entry signal! Pattern={alert.pattern} "
                        f"RSI={alert.rsi} MACD={alert.macd_line}")

            signal = (
                db.query(Signal)
                .filter(Signal.symbol == alert.symbol, Signal.status == SignalStatus.TRIGGERED)
                .order_by(Signal.detected_at.desc())
                .first()
            )
            if signal:
                signal.status = SignalStatus.CONFIRMED
                signal.rsi_ok = (alert.rsi is not None and alert.rsi < 50)
                signal.macd_ok = (
                    alert.macd_line is not None and
                    alert.macd_signal is not None and
                    alert.macd_line > alert.macd_signal
                )
                signal.pattern_5m = alert.pattern
                from datetime import datetime, timezone
                signal.confirmed_at = datetime.now(timezone.utc)
                signal_id = str(signal.id)
                logger.info(f"Signal {signal_id} CONFIRMED — dispatching to risk + execution")

                # TODO: publish to Kafka → risk manager → order executor
                # kafka_producer.publish("trade_signals", signal)

            else:
                logger.warning(f"[{alert.symbol}] Entry signal but no triggered signal found.")

        elif alert.alert_type == AlertType.ZONE_INVALIDATED:
            logger.info(f"[{alert.symbol}] Zone invalidated — expiring pending signals.")
            db.query(Signal).filter(
                Signal.symbol == alert.symbol,
                Signal.status.in_([SignalStatus.PENDING, SignalStatus.TRIGGERED])
            ).update({"status": SignalStatus.EXPIRED})

    return signal_id


@router.post("/webhook", response_model=WebhookResponse, status_code=status.HTTP_200_OK)
async def receive_alert(alert: TradingViewAlert, background_tasks: BackgroundTasks):
    """
    TradingView sends a POST here when a Pine Script alert fires.
    We validate the secret, return 200 immediately, then process in the background.
    """
    _validate_secret(alert)
    logger.info(f"Webhook received: {alert.alert_type} for {alert.symbol}")

    background_tasks.add_task(_handle_alert, alert)

    return WebhookResponse(
        status="received",
        message=f"Alert {alert.alert_type} queued for processing.",
    )