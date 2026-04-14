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
from fastapi.middleware.cors import CORSMiddleware

from app.auth import refresh_tgt
from app.scheduler import fetch_and_process, start_scheduler, stop_scheduler
from app.storage import read_data, read_history_cache, write_history_cache
from app.fetcher import fetch_all_data, TZ_ISTANBUL
from app.engine import calculate_daily_forecast
from datetime import datetime

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Endpoint'ler
# ──────────────────────────────────────────────
@app.get("/api/v1/raw-data/{dataset}", tags=["Veri"])
async def get_raw_dataset(dataset: str, date: str | None = None, refresh: bool = False):
    """
    Belirli bir ham veri setini (örneğin 'load_estimation', 'finance' vb.) döndürür.
    İsteğe bağlı ?date=YYYY-MM-DD ile spesifik tarihteki veriyi anlık çeker.
    ?refresh=true ile önbelleği zorla yeniler.
    """
    try:
        if date and date != datetime.now(tz=TZ_ISTANBUL).strftime("%Y-%m-%d"):
            # Tarih belirtilmişse ve bugün değilse, önce önbelleği kontrol et
            logger.info(f"Tarihli (Geçmiş) raw-data isteği: {date} (Refresh: {refresh})")
            
            raw = None
            if not refresh:
                raw = await read_history_cache(date)
            
            if not raw:
                # Önbellekte yoksa API'den çek ve kaydet
                logger.info(f"{date} için API'den taze veri çekiliyor...")
                raw = await fetch_all_data(target_date=date)
                await write_history_cache(date, raw)
        else:
            # Bugün için önbellekten oku
            store = await read_data()
            raw = store.get("raw_data")
        
        if not raw:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "waiting",
                    "message": "Henüz veri çekilmedi veya bulunamadı.",
                },
            )
            
        if dataset not in raw:
            return JSONResponse(
                status_code=404,
                content={"error": f"'{dataset}' adında bir veri seti bulunamadı."}
            )
            
        return raw[dataset]
    except Exception:
        logger.exception(f"raw-data/{dataset} endpoint hatası")
        return JSONResponse(
            status_code=500,
            content={"error": "Veri okunurken bir hata oluştu."},
        )


@app.get("/api/v1/prediction", tags=["Tahmin"])
async def get_prediction(date: str | None = None, refresh: bool = False):
    """
    Hesaplanan son Delta değerini ve Sistem Yönünü döndürür.
    İsteğe bağlı ?date=YYYY-MM-DD ile spesifik tarihin tahminini anlık çeker.
    ?refresh=true ile zorla baştan hesaplar.
    """
    try:
        if date and date != datetime.now(tz=TZ_ISTANBUL).strftime("%Y-%m-%d"):
            # Tarihli özel hesaplama yap, önce önbellek kontrol et
            logger.info(f"Tarihli (Geçmiş) prediction isteği: {date} (Refresh: {refresh})")
            
            raw = None
            if not refresh:
                raw = await read_history_cache(date)
            
            if not raw:
                logger.info(f"{date} için API'den taze tahmin verisi çekiliyor...")
                raw = await fetch_all_data(target_date=date)
                await write_history_cache(date, raw)

            if not raw:
                return JSONResponse(status_code=404, content={"error": "Bu tarih için ham veri bulunamadı."})
            prediction = calculate_daily_forecast(raw, target_date=date)
        else:
            store = await read_data()
            prediction = store.get("prediction")

        if not prediction:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "waiting",
                    "message": "Henüz tahmin hesaplanmadı veya bulunamadı.",
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
