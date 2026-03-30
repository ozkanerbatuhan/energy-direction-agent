"""
main.py — FastAPI uygulaması, lifespan ve REST endpoint'leri.

Endpoints:
  GET /api/v1/raw-data    → Son çekilen ham verileri döndürür.
  GET /api/v1/prediction  → Son Delta ve System Direction sonucunu döndürür.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.auth import refresh_tgt
from app.scheduler import fetch_and_process, start_scheduler, stop_scheduler
from app.storage import read_data

# ──────────────────────────────────────────────
# Loglama yapılandırması
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Uygulama başlarken:
      1. İlk TGT'yi al (zorunlu await — token olmadan veri çekilemez)
      2. Zamanlayıcıyı başlat
      3. İlk veri çekme döngüsünü tetikle
    Uygulama kapanırken:
      Zamanlayıcıyı durdur.
    """
    logger.info("🚀 Uygulama başlatılıyor…")

    # 1 — İlk TGT'yi al (token hazır olana kadar bekle)
    logger.info("İlk TGT alınıyor…")
    await refresh_tgt()

    # 2 — Zamanlayıcıyı başlat
    start_scheduler()

    # 3 — İlk veri çekme döngüsünü hemen tetikle
    logger.info("İlk veri çekme döngüsü tetikleniyor…")
    await fetch_and_process()

    logger.info("✅ Uygulama hazır — endpoint'ler aktif.")
    yield

    # Shutdown
    logger.info("Uygulama kapatılıyor…")
    stop_scheduler()
    logger.info("👋 Uygulama durduruldu.")


# ──────────────────────────────────────────────
# FastAPI uygulaması
# ──────────────────────────────────────────────
app = FastAPI(
    title="EPİAŞ Enerji Yön Tahmini API",
    description=(
        "Türkiye enerji piyasasında arz-talep dengesini izleyen "
        "ve enerji açığı/fazlası tahmin eden MVP."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────
# Endpoint'ler
# ──────────────────────────────────────────────
@app.get("/api/v1/raw-data", tags=["Veri"])
async def get_raw_data():
    """
    EPİAŞ API'lerinden çekilen son ham verileri döndürür.
    Henüz veri çekilmemişse bilgi mesajı döner.
    """
    try:
        store = await read_data()
        raw = store.get("raw_data")
        if not raw:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "waiting",
                    "message": "Henüz veri çekilmedi. Zamanlayıcı çalışıyor, lütfen bekleyin.",
                },
            )
        return raw
    except Exception:
        logger.exception("raw-data endpoint hatası")
        return JSONResponse(
            status_code=500,
            content={"error": "Veri okunurken bir hata oluştu."},
        )


@app.get("/api/v1/prediction", tags=["Tahmin"])
async def get_prediction():
    """
    Hesaplanan son Delta değerini ve Sistem Yönünü döndürür.
    Henüz hesaplama yapılmamışsa bilgi mesajı döner.
    """
    try:
        store = await read_data()
        prediction = store.get("prediction")
        if not prediction:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "waiting",
                    "message": "Henüz tahmin hesaplanmadı. Zamanlayıcı çalışıyor, lütfen bekleyin.",
                },
            )
        return prediction
    except Exception:
        logger.exception("prediction endpoint hatası")
        return JSONResponse(
            status_code=500,
            content={"error": "Tahmin okunurken bir hata oluştu."},
        )


@app.get("/", tags=["Sağlık"])
async def health():
    """Basit sağlık kontrolü."""
    return {
        "status": "ok",
        "service": "EPİAŞ Enerji Yön Tahmini API",
        "version": "1.0.0",
    }
