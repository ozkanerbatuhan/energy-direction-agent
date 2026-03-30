"""
engine.py — İş mantığı modülü: Enerji Açık / Fazla ve Gelişmiş Tarihsel Tahminleyici.

Geçmiş (gerçekleşen) saatler için Formül:
    Delta = (Gerçekleşen Tüketim − Tahmini Tüketim)
          − (Gerçekleşen Üretim − KGÜP/DPP Üretimi)
          + (Arıza/Kesinti Kayıp MW)

Gelecek saatler için Tahminleme (Forecasting) Formülü:
    Adım 1: Tarihsel Sapma (Baseline) = Son 3 günün o saate ait sapma ortalaması
    Adım 2: Bugünün Trendi (Momentum) = Bugün gerçekleşen saatlerdeki (Sapma - Baseline) ortalaması
    Tahmini Delta(H) = Baseline(H) + Momentum + Outage(H)

    Delta > 0  →  AÇIK (DEFICIT)
    Delta < 0  →  FAZLA (SURPLUS)
    Delta == 0 →  DENGEDE (BALANCED)
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TZ_ISTANBUL = ZoneInfo("Europe/Istanbul")


def _find_value(items: list[dict] | None, hour_key: str, fields: list[str]) -> float | None:
    """
    EPİAŞ API'sinden dönen item listesi içinde, belirtilen saate
    ait olan kaydın değerini verilen alan adlarıyla arar ve döndürür.
    hour_key: "2026-03-30T14" formundadır.
    """
    if not items:
        return None

    for item in items:
        date_str = item.get("date") or item.get("tarih") or ""
        if date_str[:13] == hour_key:
            for f in fields:
                val = item.get(f)
                if val is not None:
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        pass
    return None


def _extract_items(response: dict | None) -> list[dict]:
    """
    API yanıtından item listesini güvenle çıkarır.
    """
    if not response:
        return []
    body = response.get("body", response)
    if isinstance(body, dict):
        for key in ("items", "plannedPowerOutageList", "unplannedPowerOutageList",
                    "marketMessageList", "content", "realtimeConsumptionList", 
                    "realtimeGenerationList", "loadEstimationPlanList", "dppList"):
            items = body.get(key, [])
            if items:
                return items
        if isinstance(body.get("body"), list):
            return body["body"]
    return []


def _calculate_outage_mw(outages: dict | None, hour_key: str) -> float:
    """
    Arıza/kesinti verilerinden belirtilen saati kapsayan ve aktif olan
    kesintilerin toplam kapasite kaybını (MW) hesaplar.
    """
    if not outages:
        return 0.0

    try:
        hour_start = datetime.strptime(hour_key, "%Y-%m-%dT%H").replace(tzinfo=TZ_ISTANBUL)
    except ValueError:
        return 0.0
    hour_end = hour_start + timedelta(hours=1) - timedelta(seconds=1)

    total_mw = 0.0
    all_items: list[dict] = []
    all_items.extend(_extract_items(outages.get("planned")))
    all_items.extend(_extract_items(outages.get("unplanned")))

    for msg in all_items:
        try:
            capacity_loss = (
                msg.get("powerLoss")
                or msg.get("capacityAtThatTime")
                or msg.get("power")
                or 0
            )
            capacity_loss = float(capacity_loss)
            if capacity_loss <= 0:
                continue

            start_str = (
                msg.get("startDate")
                or msg.get("caseStartDate")
                or msg.get("outageStartDate")
                or ""
            )
            end_str = (
                msg.get("endDate")
                or msg.get("caseEndDate")
                or msg.get("outageEndDate")
                or ""
            )

            if not start_str or not end_str:
                continue

            msg_start = datetime.fromisoformat(start_str)
            msg_end = datetime.fromisoformat(end_str)

            if msg_start <= hour_end and msg_end >= hour_start:
                total_mw += capacity_loss
        except (ValueError, TypeError):
            continue

    return total_mw


def _get_direction(delta: float) -> str:
    if delta > 0:
        return "AÇIK (DEFICIT)"
    elif delta < 0:
        return "FAZLA (SURPLUS)"
    return "DENGEDE (BALANCED)"


def calculate_daily_forecast(raw_data: dict) -> dict | None:
    """
    Tarihsel Baseline (Son 3 gün) ve Günlük Momentum yöntemini 
    kullanarak 24 saatlik güncel Delta tahminlemesi yapar.
    """
    logger.info("KGÜP ve Momentum destekli tahminleme algoritması başlatılıyor...")

    now = datetime.now(tz=TZ_ISTANBUL)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 1. API Listelerini Çıkar
    load_items = _extract_items(raw_data.get("load_estimation"))
    cons_items = _extract_items(raw_data.get("realtime_consumption"))
    gen_items = _extract_items(raw_data.get("realtime_generation"))
    dpp_items  = _extract_items(raw_data.get("dpp"))
    outages    = raw_data.get("outages")

    # ---------------------------------------------------------
    # ADIM 1: Tarihsel Profil (Baseline) Çıkarma
    # ---------------------------------------------------------
    # Bugün haricinde geçmiş 3 günün (today-3, today-2, today-1) 
    # saatlik sapmalarını hesaplayıp ortalamasını (Baseline) buluyoruz.
    past_days = [today_start - timedelta(days=d) for d in range(3, 0, -1)]
    baselines_mw = {}

    for h in range(24):
        hour_str = f"{h:02d}"
        deviations_for_h = []
        
        for p_day in past_days:
            p_key = p_day.strftime("%Y-%m-%d") + f"T{hour_str}"
            
            r_cons = _find_value(cons_items, p_key, ["consumption", "value"])
            e_cons = _find_value(load_items, p_key, ["lep", "llesValue", "value"])
            r_gen  = _find_value(gen_items,  p_key, ["total", "value"])
            d_gen  = _find_value(dpp_items,  p_key, ["toplam", "total", "value"])
            
            # Eğer o saate ait tüm veriler varsa dahil et
            if r_cons is not None and e_cons is not None and r_gen is not None:
                d_gen = d_gen if d_gen is not None else r_gen
                dev = (r_cons - e_cons) - (r_gen - d_gen)
                deviations_for_h.append(dev)
                
        if deviations_for_h:
            avg_dev = sum(deviations_for_h) / len(deviations_for_h)
        else:
            avg_dev = 0.0
            
        baselines_mw[hour_str] = avg_dev

    # ---------------------------------------------------------
    # ADIM 2: Bugünün Sapmaları ve Momentum Hesabı
    # ---------------------------------------------------------
    today_str = today_start.strftime("%Y-%m-%d")
    today_diff_from_baseline = []
    hourly_predictions = []

    for h in range(24):
        hour_str = f"{h:02d}"
        t_key = f"{today_str}T{hour_str}"
        
        r_cons = _find_value(cons_items, t_key, ["consumption", "value"])
        e_cons = _find_value(load_items, t_key, ["lep", "llesValue", "value"])
        r_gen  = _find_value(gen_items,  t_key, ["total", "value"])
        d_gen  = _find_value(dpp_items,  t_key, ["toplam", "total", "value"])
        outage = _calculate_outage_mw(outages, t_key)
        
        e_cons = e_cons or 0.0
        
        if r_cons is not None and r_gen is not None:
            # Gerçekleşen saat
            d_gen = d_gen if d_gen is not None else r_gen
            today_dev = (r_cons - e_cons) - (r_gen - d_gen)
            
            # Formül mantığı: Gerçekleşmiş Delta = T_Dev + Outage
            delta = today_dev + outage
            hourly_predictions.append({
                "hour": t_key,
                "is_forecast": False,
                "delta_mw": round(delta, 2),
                "direction": _get_direction(delta),
                "outage_mw": outage
            })
            
            # Momentumu bulmak için Baseline'dan saptığı farkı kaydet
            base_val = baselines_mw.get(hour_str, 0.0)
            diff = today_dev - base_val
            today_diff_from_baseline.append(diff)
            
        else:
            # Henüz gerçekleşmemiş (Gelecek) saat
            hourly_predictions.append({
                "hour": t_key,
                "is_forecast": True,
                "delta_mw": None, # Adım 3'te dolacak
                "direction": None,
                "outage_mw": outage,
                "_base": baselines_mw.get(hour_str, 0.0)
            })

    # Momentum, bugün gerçekleşen saatlerdeki (Sapma - Baseline) farkların ortalamasıdır.
    today_momentum = 0.0
    if today_diff_from_baseline:
        today_momentum = sum(today_diff_from_baseline) / len(today_diff_from_baseline)

    # ---------------------------------------------------------
    # ADIM 3: Gelecek Saatlerin Tahmini
    # ---------------------------------------------------------
    for p in hourly_predictions:
        if p["is_forecast"]:
            base = p.pop("_base", 0.0)
            # Tahmini Delta = Geçmiş Profil (Baseline) + Güncel Momentum + Gelecek Arızalar
            forecast_delta = base + today_momentum + p["outage_mw"]
            
            p["delta_mw"] = round(forecast_delta, 2)
            p["direction"] = _get_direction(forecast_delta)

    return {
        "historical_baselines_mw": {k: round(v, 2) for k, v in baselines_mw.items()},
        "today_momentum_mw": round(today_momentum, 2),
        "hourly_predictions": hourly_predictions,
        "calculated_at": now.isoformat()
    }
