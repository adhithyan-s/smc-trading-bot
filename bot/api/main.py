from fastapi import FastAPI, HTTPException, status
from contextlib import asynccontextmanager
import uvicorn

from bot.api.schemas import TradingViewAlert, WebhookResponse
from bot.api.routes import router
from bot.config.settings import get_settings
from bot.config.logging_config import logger
from bot.db.session import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SMC Trading Bot...")
    init_db()
    logger.info("Database tables verified.")
    logger.info(f"Trading {settings.symbol} | Paper mode: {settings.paper_mode}")
    yield
    logger.info("Shutting down SMC Trading Bot.")


app = FastAPI(
    title="SMC Trading Bot",
    description="Webhook receiver for TradingView Pine Script alerts",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "symbol": settings.symbol, "paper_mode": settings.paper_mode}


if __name__ == "__main__":
    uvicorn.run(
        "bot.api.main:app",
        host=settings.webhook_host,
        port=settings.webhook_port,
        reload=True,
    )