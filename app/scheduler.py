"""
scheduler.py — APScheduler ile arka plan görevleri.

İki periyodik görev tanımlar:
  1. TGT yenileme  → her 90 dakikada bir
  2. Veri çekme + Delta hesaplama → her 15 dakikada bir
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.auth import refresh_tgt
from app.config import settings
from app.engine import calculate_daily_forecast
from app.fetcher import fetch_all_data
from app.storage import read_data, write_data

logger = logging.getLogger(__name__)

# Modül seviyesinde scheduler nesnesi
scheduler = AsyncIOScheduler()


async def fetch_and_process() -> None:
    """
    1. EPİAŞ API'lerinden veri çeker.
    2. Ham veriyi data.json'a yazar.
    3. Delta hesaplar ve sonucu data.json'a ekler.
    """
    logger.info("═" * 50)
    logger.info("Zamanlayıcı: Veri çekme ve işleme başlatılıyor…")

    # 1 — Veri çek
    raw_data = await fetch_all_data()
    if not raw_data:
        logger.warning("Veri çekilemedi — işlem atlanıyor.")
        return

    # 2 — Ham veriyi kaydet
    store = await read_data()
    store["raw_data"] = raw_data
    await write_data(store)

    # 3 — Delta hesapla
    prediction = calculate_daily_forecast(raw_data)
    if prediction:
        store["prediction"] = prediction
        await write_data(store)

    logger.info("Zamanlayıcı: Döngü tamamlandı.")
    logger.info("═" * 50)


def start_scheduler() -> None:
    """
    Zamanlayıcıyı başlatır.
    - TGT yenileme: her AUTH_REFRESH_MINUTES dakikada bir
    - Veri çekme:   her FETCH_INTERVAL_MINUTES dakikada bir
    """
    # Görev 1 — TGT Yenileme
    scheduler.add_job(
        refresh_tgt,
        trigger=IntervalTrigger(minutes=settings.AUTH_REFRESH_MINUTES),
        id="tgt_refresh",
        name="TGT Yenileme",
        replace_existing=True,
    )

    # Görev 2 — Veri Çekme + Delta
    scheduler.add_job(
        fetch_and_process,
        trigger=IntervalTrigger(minutes=settings.FETCH_INTERVAL_MINUTES),
        id="data_fetch",
        name="Veri Çekme & Delta Hesaplama",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Zamanlayıcı başlatıldı — TGT yenileme: %d dk, Veri çekme: %d dk",
        settings.AUTH_REFRESH_MINUTES,
        settings.FETCH_INTERVAL_MINUTES,
    )


def stop_scheduler() -> None:
    """Zamanlayıcıyı düzgün şekilde kapatır."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Zamanlayıcı durduruldu.")
