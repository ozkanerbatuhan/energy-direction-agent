"""
engine.py — Türkiye şebekesi saatlik açık / fazla yön tahmini.

Hedef büyüklük EPİAŞ'ın gerçekleşen net dengeleme talimatıdır (YAL − YAT):
    Net > 0  →  AÇIK (DEFICIT)   — TEİAŞ yük aldırdı
    Net < 0  →  FAZLA (SURPLUS)  — TEİAŞ yük attırdı
Yön ve açık olasılığı app/model.py'deki lojistik regresyondan gelir (model.json yoksa
son BASELINE_DAYS günün aynı saatindeki net ortalamasına düşer). Fiziksel sapma ve arıza
yalnız bilgi amaçlı.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.model import build_series, features, load_model, predict_proba

logger = logging.getLogger(__name__)

TZ_ISTANBUL = ZoneInfo("Europe/Istanbul")

# Tahmin tabanı: kaç günün aynı saati ortalanır (backtest: 7 gün en iyi)
BASELINE_DAYS = 7


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


def _find_string(items: list[dict] | None, hour_key: str, fields: list[str]) -> str | None:
    """
    EPİAŞ API'sinden dönen item listesi içinde, belirtilen saate
    ait olan kaydın değerini string olarak arar ve döndürür.
    """
    if not items:
        return None

    for item in items:
        date_str = item.get("date") or item.get("tarih") or ""
        if date_str[:13] == hour_key:
            for f in fields:
                val = item.get(f)
                if val is not None:
                    return str(val).strip()
    return None


def _non_solar(items: list[dict] | None, hour_key: str, total_fields: list[str], sun_fields: list[str]) -> float | None:
    """
    Toplam üretimden güneşi düşer.

    Gerçek zamanlı üretim yalnız sayacı anlık okunan (lisanslı) GES'leri içerir (~3 GW),
    KGÜP ise lisanssız GES dahil tüm güneşi (~15-19 GW). İkisi doğrudan çıkarılırsa
    öğlen güneş eğrisi kadar sahte "açık" doğar; karşılaştırma güneşsiz yapılır.
    """
    total = _find_value(items, hour_key, total_fields)
    if total is None:
        return None
    sun = _find_value(items, hour_key, sun_fields) or 0.0
    return total - sun


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
                    "realtimeGenerationList", "loadEstimationPlanList", "dppList",
                    "interimMcpList", "systemMarginalPriceList", "orderSummaryDownList",
                    "orderSummaryUpList", "systemDirectionList"):
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


def calculate_daily_forecast(raw_data: dict, target_date: str = None) -> dict | None:
    """
    24 saatlik sistem yönü tahmini.

    Her saat için açık olasılığı p = lojistik regresyon (app/model.py), "şimdi"den
    o saate kadar geçen ufukla (k) bilinebilecek veriyle. Bar değeri:
        forecast_delta_mw = (2p − 1) × son 7 günün bu saatteki ortalama |net|
    Yön modelden, büyüklük geçmişten. Ay ay ileri yürüyen test (May–Eki 2026):
    %65 yön isabeti; 7 günlük net ortalaması %60, eski fiziksel formül ~%47-52.
    """
    logger.info("Net talimat tabanlı yön tahmini başlatılıyor...")

    if target_date:
        now = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=TZ_ISTANBUL)
    else:
        now = datetime.now(tz=TZ_ISTANBUL)

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = today_start.strftime("%Y-%m-%d")

    load_items = _extract_items(raw_data.get("load_estimation"))
    cons_items = _extract_items(raw_data.get("realtime_consumption"))
    gen_items  = _extract_items(raw_data.get("realtime_generation"))
    dpp_items  = _extract_items(raw_data.get("dpp"))
    outages    = raw_data.get("outages")

    finance_raw = raw_data.get("finance", {}) or {}
    yal_items = _extract_items(finance_raw.get("yal"))
    sys_dir_items = _extract_items(finance_raw.get("system_direction"))

    def net_at(key: str) -> float | None:
        return _find_value(yal_items, key, ["net"])

    def physical_at(key: str) -> float | None:
        """Güneş hariç fiziksel sapma: (Tüketim − LEP) − (Üretim − KGÜP)."""
        r_cons = _find_value(cons_items, key, ["consumption", "value"])
        e_cons = _find_value(load_items, key, ["lep", "llesValue", "value"])
        r_gen  = _non_solar(gen_items, key, ["total", "value"], ["sun"])
        d_gen  = _non_solar(dpp_items, key, ["toplam", "total", "value"], ["gunes"])
        if None in (r_cons, e_cons, r_gen, d_gen):
            return None
        return (r_cons - e_cons) - (r_gen - d_gen)

    past_days = [today_start - timedelta(days=d) for d in range(1, BASELINE_DAYS + 1)]
    baselines_mw: dict[str, float] = {}
    magnitudes_mw: dict[str, float] = {}
    baseline_counts: dict[str, int] = {}
    for h in range(24):
        hour_str = f"{h:02d}"
        keys = [d.strftime("%Y-%m-%d") + f"T{hour_str}" for d in past_days]
        vals = [net_at(k) for k in keys if _find_string(sys_dir_items, k, ["systemDirection"])]
        vals = [v for v in vals if v is not None]
        baselines_mw[hour_str] = sum(vals) / len(vals) if vals else 0.0
        magnitudes_mw[hour_str] = sum(abs(v) for v in vals) / len(vals) if vals else 0.0
        baseline_counts[hour_str] = len(vals)

    # Lojistik regresyon (app/model.py). Yoksa 7 günlük ortalamaya düşülür.
    model = load_model()
    S = build_series({
        "ptf": _extract_items(finance_raw.get("k_ptf")),
        "smf": _extract_items(finance_raw.get("smf")),
        "load_estimation": load_items,
        "realtime_consumption": cons_items,
        "realtime_generation": gen_items,
        "dpp": dpp_items,
        "yal": yal_items,
        "system_direction": sys_dir_items,
    }) if model else None
    # "Şimdi": bugün için içinde bulunulan saat; geçmiş bir gün için gün sonu (her saat 1 saat önceden)
    now_hour = (now if not target_date else today_start + timedelta(days=1)).replace(
        minute=0, second=0, microsecond=0, tzinfo=None)

    hourly_predictions = []
    for h in range(24):
        hour_str = f"{h:02d}"
        t_key = f"{today_str}T{hour_str}"

        base = baselines_mw[hour_str]
        # EPİAŞ yayınlamadığı saatler için net=0 döndürüyor; gerçekleşen sayılması için yön de yayınlanmış olmalı
        epias_dir = _find_string(sys_dir_items, t_key, ["systemDirection"])
        realized = net_at(t_key) if epias_dir else None
        physical = physical_at(t_key)
        outage = _calculate_outage_mw(outages, t_key)
        lep_val = _find_value(load_items, t_key, ["lep", "llesValue", "value"])
        dpp_val = _find_value(dpp_items, t_key, ["toplam", "total", "value"])

        reason = f"Son {baseline_counts[hour_str]} gün bu saat: ort. {abs(round(base))} MWh " + (
            "açık" if base > 0 else "fazla" if base < 0 else "denge")

        prob = None
        horizon = None
        missing = None
        forecast = base
        if model:
            t = today_start.replace(tzinfo=None) + timedelta(hours=h)
            horizon = max(1, int((t - now_hour).total_seconds() // 3600))
            prob, missing = predict_proba(model, features(S, t, horizon))
            # Yön modelden, büyüklük son 7 günün bu saatteki ortalama |net|'inden
            forecast = (2 * prob - 1) * magnitudes_mw[hour_str]
            reason = f"Açık olasılığı %{round(prob * 100)} ({horizon} sa önceden) | " + reason

        hourly_predictions.append({
            "hour": t_key,
            "is_forecast": realized is None,
            "forecast_delta_mw": round(forecast, 2),
            "forecast_direction": _get_direction(forecast),
            "deficit_probability": round(prob, 4) if prob is not None else None,
            "realized_delta_mw": round(realized, 2) if realized is not None else None,
            "realized_direction": epias_dir,
            "physical_delta_mw": round(physical, 2) if physical is not None else None,
            "outage_mw": outage,
            "lep_mw": round(lep_val, 2) if lep_val is not None else None,
            "dpp_mw": round(dpp_val, 2) if dpp_val is not None else None,
            "plan_delta_mw": round(lep_val - dpp_val, 2) if lep_val is not None and dpp_val is not None else None,
            "reason_parts": {
                "baseline_mw": round(base, 2),
                "baseline_days": baseline_counts[hour_str],
                "probability": round(prob, 4) if prob is not None else None,
                "horizon_h": horizon,
                "missing_features": missing,
                "physical_mw": round(physical, 2) if physical is not None else None,
                "outage_mw": round(outage, 2),
            },
            "reasoning": reason,
        })

    return {
        "model": {"type": model["type"], "trained_at": model["trained_at"],
                  "walk_forward_accuracy": model["walk_forward"]["model"]} if model else None,
        "historical_baselines_mw": {k: round(v, 2) for k, v in baselines_mw.items()},
        "hourly_predictions": hourly_predictions,
        "calculated_at": now.isoformat()
    }
