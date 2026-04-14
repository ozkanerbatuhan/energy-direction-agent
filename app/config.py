"""
config.py — Uygulama ayarları ve sabitler.

.env dosyasından EPIAS_USERNAME / EPIAS_PASSWORD okur.
Tüm EPİAŞ API uç noktaları burada merkezi olarak tanımlıdır.
"""

from pathlib import Path
from pydantic_settings import BaseSettings

# ──────────────────────────────────────────────
# Proje kök dizini (app/ klasörünün bir üst dizini)
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Ortam değişkenlerinden okunan yapılandırma."""

    # EPİAŞ kimlik bilgileri
    EPIAS_USERNAME: str = ""
    EPIAS_PASSWORD: str = ""

    # Yerel JSON veritabanı
    DATA_FILE: str = str(BASE_DIR / "data.json")

    # Zamanlayıcı aralıkları (dakika)
    AUTH_REFRESH_MINUTES: int = 90      # TGT yenileme
    FETCH_INTERVAL_MINUTES: int = 15    # Veri çekme

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"


# Tekil ayar nesnesi — tüm modüller bunu import eder
settings = Settings()


# ──────────────────────────────────────────────
# EPİAŞ API Uç Noktaları  (v2 — electricity-service)
# ──────────────────────────────────────────────
EPIAS_BASE_URL = "https://seffaflik.epias.com.tr"

EPIAS_AUTH_URL = "https://giris.epias.com.tr/cas/v1/tickets"

# Tahmini Tüketim (Load Estimation Plan)
EPIAS_LOAD_ESTIMATION_PATH = "/electricity-service/v1/consumption/data/load-estimation-plan"

# Gerçekleşen Tüketim (Realtime Consumption)
EPIAS_REALTIME_CONSUMPTION_PATH = "/electricity-service/v1/consumption/data/realtime-consumption"

# Gerçekleşen Üretim (Realtime Generation)
EPIAS_REALTIME_GENERATION_PATH = "/electricity-service/v1/generation/data/realtime-generation"

# Kesinleşmiş Günlük Üretim Planı (KGÜP / DPP)
EPIAS_DPP_PATH = "/electricity-service/v1/generation/data/dpp"

# Arızalar / Kesintiler — Planlı ve Plansız
EPIAS_PLANNED_OUTAGE_PATH = "/electricity-service/v1/consumption/data/planned-power-outage-info"
EPIAS_UNPLANNED_OUTAGE_PATH = "/electricity-service/v1/consumption/data/unplanned-power-outage-info"

# K.PTF (Kesinleşmemiş Piyasa Takas Fiyatı)
EPIAS_KPTF_PATH = "/electricity-service/v1/markets/dam/data/interim-mcp"

# SMF (Sistem Marjinal Fiyatı)
EPIAS_SMF_PATH = "/electricity-service/v1/markets/bpm/data/system-marginal-price"

# YAT (Yük Atma)
EPIAS_YAT_PATH = "/electricity-service/v1/markets/bpm/data/order-summary-down"

# YAL (Yük Alma)
EPIAS_YAL_PATH = "/electricity-service/v1/markets/bpm/data/order-summary-up"

# Sistem Yönü
EPIAS_SYSTEM_DIRECTION_PATH = "/electricity-service/v1/markets/bpm/data/system-direction"
