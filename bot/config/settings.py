from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):

    # --- Bybit ---
    bybit_api_key: str
    bybit_api_secret: str
    bybit_testnet: bool = True

    # --- Trading ---
    symbol: str = "SOLUSDT"
    risk_percent: float = 1.5       # % of capital risked per trade
    capital: float = 10000.0        # starting paper capital in USDT
    paper_mode: bool = True         # True = no real orders placed

    # --- Database ---
    postgres_url: str = "postgresql://smcbot:smcbot123@localhost:5432/smcbot"
    postgres_user: str = "smcbot"
    postgres_password: str = "smcbot123"
    postgres_db: str = "smcbot"

    # --- Kafka ---
    kafka_bootstrap_servers: str = "localhost:9092"

    # --- FastAPI webhook ---
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8000
    webhook_secret: str = "changeme"   # TradingView alert secret token

    # --- Logging ---
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()