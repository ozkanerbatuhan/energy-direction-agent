"""
fetcher.py — EPİAŞ Şeffaflık Platformu veri çekme modülü.

Dört farklı API uç noktasından bugüne ait verileri çeker:
  1. Tahmini Tüketim (Load Estimation Plan)
  2. Gerçekleşen Tüketim (Realtime Consumption)
  3. Gerçekleşen Üretim (Realtime Generation)
  4. Arızalar / Kesintiler (Planlı + Plansız)

urllib3 kullanır (eptr2 referansıyla uyumlu — httpx EPİAŞ ile
"Server disconnected" hatası verdiği için değiştirildi).
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import urllib3

from app.auth import get_current_tgt
from app.config import (
    EPIAS_BASE_URL,
    EPIAS_LOAD_ESTIMATION_PATH,
    EPIAS_PLANNED_OUTAGE_PATH,
    EPIAS_REALTIME_CONSUMPTION_PATH,
    EPIAS_REALTIME_GENERATION_PATH,
    EPIAS_UNPLANNED_OUTAGE_PATH,
    EPIAS_DPP_PATH,
    EPIAS_KPTF_PATH,
    EPIAS_SMF_PATH,
    EPIAS_YAT_PATH,
    EPIAS_YAL_PATH,
    EPIAS_SYSTEM_DIRECTION_PATH,
)

logger = logging.getLogger(__name__)

# Türkiye saat dilimi
TZ_ISTANBUL = ZoneInfo("Europe/Istanbul")

# Retry ayarları
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # saniye


def _fetch_range(target_date: str = None) -> tuple[str, str]:
    """
    Geçmiş 3 günlük veriyi de kapsayacak biçimde
    (target_date - 3 days) ile (target_date) arasındaki başlangıç ve bitiş saatlerini
    EPİAŞ'ın beklediği T00:00:00+03:00 formatında döndürür.
    """
    if target_date:
        now = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=TZ_ISTANBUL)
    else:
        now = datetime.now(tz=TZ_ISTANBUL)
        
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    past_start = day_start - timedelta(days=3)
    
    fmt = "%Y-%m-%dT%H:%M:%S%z"
    start_raw = past_start.strftime(fmt)
    end_raw = day_start.strftime(fmt)
    
    # +0300 → +03:00
    start_str = start_raw[:-2] + ":" + start_raw[-2:]
    end_str = end_raw[:-2] + ":" + end_raw[-2:]
    return start_str, end_str


def _today_period(target_date: str = None) -> str:
    """
    Belirtilen veya bugünün tarihini EPİAŞ period formatında döndürür.
    eptr2 referansıyla: YYYY-MM-DDT00:00:00+03:00
    """
    if target_date:
        now = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=TZ_ISTANBUL)
    else:
        now = datetime.now(tz=TZ_ISTANBUL)
        
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    fmt = "%Y-%m-%dT%H:%M:%S%z"
    raw = day_start.strftime(fmt)
    return raw[:-2] + ":" + raw[-2:]


def _post_sync(url: str, body: dict, tgt: str) -> dict | None:
    """
    EPİAŞ API'sine urllib3 ile senkron POST isteği atar.
    Bağlantı hatalarında retry uygular.
    """
    http = urllib3.PoolManager(cert_reqs="CERT_REQUIRED")
    headers = {
        "Content-Type": "application/json",
        "TGT": tgt,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            res = http.request(
                method="POST",
                url=url,
                body=json.dumps(body),
                headers=headers,
                timeout=60.0,
            )

            if res.status in (200, 201):
                return json.loads(res.data.decode("utf-8"))

            # 4xx/5xx hata — retry etmeden loglayıp dön
            err_text = res.data.decode("utf-8", errors="replace")[:500]
            logger.warning(
                "API yanıt hatası (HTTP %d): %s — %s",
                res.status, url, err_text,
            )
            # 408 / 502 / 503 / 504 gibi sunucu hatalarında tekrar dene
            if res.status in (408, 502, 503, 504) and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                logger.info("Tekrar deneniyor (%d/%d) — %d sn sonra…", attempt, MAX_RETRIES, wait)
                time.sleep(wait)
                continue
            return None

        except Exception as exc:
            wait = RETRY_BACKOFF * attempt
            logger.warning(
                "API bağlantı hatası (deneme %d/%d): %s — %s. %d sn sonra tekrar denenecek…",
                attempt, MAX_RETRIES, url, exc, wait,
            )
            if attempt < MAX_RETRIES:
                time.sleep(wait)

    logger.error("API isteği %d denemede de başarısız oldu: %s", MAX_RETRIES, url)
    return None


async def _post(url: str, body: dict, tgt: str) -> dict | None:
    """Senkron _post_sync'i event loop'u bloklamadan çalıştırır."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _post_sync, url, body, tgt)


async def fetch_all_data(target_date: str = None) -> dict:
    """
    Tüm uç noktalardan bugüne veya belirtilen güne ait verileri çeker.

    Returns:
        {
            "load_estimation": {...} | None,
            "realtime_consumption": {...} | None,
            "realtime_generation": {...} | None,
            "outages": {"planned": ..., "unplanned": ...} | None,
            "fetched_at": "ISO timestamp",
            "date_range": {"start": "...", "end": "..."},
        }
    """
    tgt = await get_current_tgt()
    if not tgt:
        logger.error("TGT mevcut değil — veri çekilemiyor.")
        return {}

    start_date, end_date = _fetch_range(target_date)
    period = _today_period(target_date)
    date_body = {"startDate": start_date, "endDate": end_date}
    dpp_body = {"startDate": start_date, "endDate": end_date, "region": "TR1"}
    period_body = {"period": period}

    logger.info("Veri çekiliyor — Tarih: %s", period)

    # 1 — Tahmini Tüketim
    load_est = await _post(
        f"{EPIAS_BASE_URL}{EPIAS_LOAD_ESTIMATION_PATH}",
        date_body,
        tgt,
    )
    logger.info("Tahmini Tüketim: %s", "OK" if load_est else "BAŞARISIZ")

    # 2 — Gerçekleşen Tüketim
    rt_consumption = await _post(
        f"{EPIAS_BASE_URL}{EPIAS_REALTIME_CONSUMPTION_PATH}",
        date_body,
        tgt,
    )
    logger.info("Gerçekleşen Tüketim: %s", "OK" if rt_consumption else "BAŞARISIZ")

    # 3 — Gerçekleşen Üretim
    rt_generation = await _post(
        f"{EPIAS_BASE_URL}{EPIAS_REALTIME_GENERATION_PATH}",
        date_body,
        tgt,
    )
    logger.info("Gerçekleşen Üretim: %s", "OK" if rt_generation else "BAŞARISIZ")

    # 3.5 — Kesinleşmiş Günlük Üretim Planı (KGÜP / DPP)
    dpp = await _post(
        f"{EPIAS_BASE_URL}{EPIAS_DPP_PATH}",
        dpp_body,
        tgt,
    )
    logger.info("Üretim Planı (KGÜP/DPP): %s", "OK" if dpp else "BAŞARISIZ")

    # 4 — Arızalar / Kesintiler (Planlı + Plansız)
    planned_outage = await _post(
        f"{EPIAS_BASE_URL}{EPIAS_PLANNED_OUTAGE_PATH}",
        period_body,
        tgt,
    )
    unplanned_outage = await _post(
        f"{EPIAS_BASE_URL}{EPIAS_UNPLANNED_OUTAGE_PATH}",
        period_body,
        tgt,
    )
    logger.info(
        "Arızalar — Planlı: %s, Plansız: %s",
        "OK" if planned_outage else "BAŞARISIZ",
        "OK" if unplanned_outage else "BAŞARISIZ",
    )

    # 5 — Finansallar ve Dengeleme (Trading Terminal)
    k_ptf = await _post(f"{EPIAS_BASE_URL}{EPIAS_KPTF_PATH}", date_body, tgt)
    smf = await _post(f"{EPIAS_BASE_URL}{EPIAS_SMF_PATH}", date_body, tgt)
    yat = await _post(f"{EPIAS_BASE_URL}{EPIAS_YAT_PATH}", date_body, tgt)
    yal = await _post(f"{EPIAS_BASE_URL}{EPIAS_YAL_PATH}", date_body, tgt)
    sys_dir = await _post(f"{EPIAS_BASE_URL}{EPIAS_SYSTEM_DIRECTION_PATH}", date_body, tgt)
    logger.info("Finansallar (K.PTF / SMF / YAT / YAL / YÖN) Çekildi.")

    now_str = datetime.now(tz=TZ_ISTANBUL).isoformat()

    return {
        "load_estimation": load_est,
        "realtime_consumption": rt_consumption,
        "realtime_generation": rt_generation,
        "outages": {
            "planned": planned_outage,
            "unplanned": unplanned_outage,
        },
        "dpp": dpp,
        "finance": {
            "k_ptf": k_ptf,
            "smf": smf,
            "yat": yat,
            "yal": yal,
            "system_direction": sys_dir
        },
        "fetched_at": now_str,
        "date_range": {"start": start_date, "end": end_date},
    }
