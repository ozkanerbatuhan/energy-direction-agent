"""
model.py — Sistem yönü (açık / fazla) için lojistik regresyon: özellikler + çıkarım.

Eğitim `scripts/train_model.py` ile yapılır; katsayılar `app/model.json`'a yazılır.
Özellikler burada tek yerde tanımlı — eğitim de çıkarım da `features()`'ı çağırır,
böylece eğitimle canlı arasında özellik kayması olmaz. Saf Python: sklearn gerekmez.

Zaman: EPİAŞ saatleri "YYYY-MM-DDTHH" anahtarıyla, İstanbul yerel saatinde (yaz saati yok).
"""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parent / "model.json"

# Yayın gecikmeleri (9 Eki 2026 ölçümü): yön/SMF/net ~6 sa, gerçek zamanlı tüketim/üretim ~2 sa
PUB_LAG = 6
PHYS_LAG = 2

FEATURES = [
    # gün öncesinden bilinenler
    "hs", "hc", "wkend",
    "ptf", "ptf_dev", "ptf_rank", "ptf_d1", "ptf_n1", "ptf_dmean",
    "lep", "dpp", "dpp_sun", "dpp_wind", "dpp_gas", "dpp_hydro", "dpp_river", "dpp_coal", "dpp_lig",
    "lep_dpp", "gas_dev", "net7",
    # ufka bağlı: k = hedef saat ile "şimdi" arası saat
    "k", "net_last", "net_last3", "smfptf_last", "net_24", "net_168", "acik_168",
    "phys_last", "phys_last3", "wind_dev_last",
]

# EPİAŞ alanı → seri adı
_SOURCES = {
    "ptf": [("price", "ptf")],
    "smf": [("systemMarginalPrice", "smf")],
    "load_estimation": [("lep", "lep")],
    "realtime_consumption": [("consumption", "cons")],
    "realtime_generation": [("total", "gen"), ("sun", "gen_sun"), ("wind", "gen_wind")],
    "dpp": [("toplam", "dpp"), ("gunes", "dpp_sun"), ("ruzgar", "dpp_wind"), ("dogalgaz", "dpp_gas"),
            ("barajli", "dpp_hydro"), ("akarsu", "dpp_river"), ("ithalKomur", "dpp_coal"), ("linyit", "dpp_lig")],
}


def hkey(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H")


def build_series(items_by_source: dict[str, list[dict]]) -> dict[str, dict[str, float]]:
    """
    EPİAŞ item listelerinden saat anahtarlı seriler kurar.
    items_by_source anahtarları: ptf, smf, load_estimation, realtime_consumption,
    realtime_generation, dpp, yal, system_direction.
    Net ve SMF yalnız sistem yönü yayınlanmış saatler için alınır (yayınlanmamış saat net=0 gelir).
    """
    S: dict[str, dict[str, float]] = {}
    for src, fields in _SOURCES.items():
        for _, name in fields:
            S[name] = {}
        for it in items_by_source.get(src) or []:
            k = (it.get("date") or "")[:13]
            for field, name in fields:
                v = it.get(field)
                if v is not None:
                    try:
                        S[name][k] = float(v)
                    except (TypeError, ValueError):
                        pass

    published = {(i.get("date") or "")[:13] for i in items_by_source.get("system_direction") or []
                 if i.get("systemDirection")}
    S["net"] = {}
    for it in items_by_source.get("yal") or []:
        k = (it.get("date") or "")[:13]
        if k in published and it.get("net") is not None:
            S["net"][k] = float(it["net"])
    S["smf"] = {k: v for k, v in S["smf"].items() if k in published}

    S["phys"] = {}
    S["wind_dev"] = {}
    for k in S["cons"]:
        try:
            S["phys"][k] = (S["cons"][k] - S["lep"][k]) - (
                (S["gen"][k] - S["gen_sun"].get(k, 0.0)) - (S["dpp"][k] - S["dpp_sun"].get(k, 0.0)))
        except KeyError:
            pass
        if k in S["gen_wind"] and k in S["dpp_wind"]:
            S["wind_dev"][k] = S["gen_wind"][k] - S["dpp_wind"][k]
    return S


def _day_values(series: dict[str, float], day: str) -> list[float] | None:
    vals = [series.get(f"{day}T{h:02d}") for h in range(24)]
    return None if any(v is None for v in vals) else vals


def _window(series: dict[str, float], end: datetime, n: int) -> list[float] | None:
    """end dahil geriye n saat; eksik varsa None."""
    out = []
    for i in range(n):
        v = series.get(hkey(end - timedelta(hours=i)))
        if v is None:
            return None
        out.append(v)
    return out


def _pct_rank(values: list[float], v: float) -> float:
    """pandas rank(pct=True, method='average') ile aynı."""
    less = sum(1 for x in values if x < v)
    eq = sum(1 for x in values if x == v)
    return (less + (eq + 1) / 2) / len(values)


def features(S: dict[str, dict[str, float]], t: datetime, k: int) -> dict[str, float | None]:
    """Hedef saat t için, t'den k saat önce bilinebilecek bilgiyle özellikler. Eksik olan None."""
    key = hkey(t)
    day = t.strftime("%Y-%m-%d")
    f: dict[str, float | None] = {}
    f["hs"] = math.sin(2 * math.pi * t.hour / 24)
    f["hc"] = math.cos(2 * math.pi * t.hour / 24)
    f["wkend"] = 1.0 if t.weekday() >= 5 else 0.0

    ptf = S["ptf"].get(key)
    ptf_day = _day_values(S["ptf"], day)
    f["ptf"] = ptf
    f["ptf_dmean"] = sum(ptf_day) / 24 if ptf_day else None
    f["ptf_dev"] = ptf - f["ptf_dmean"] if ptf is not None and ptf_day else None
    f["ptf_rank"] = _pct_rank(ptf_day, ptf) if ptf is not None and ptf_day else None
    prev = S["ptf"].get(hkey(t - timedelta(hours=1)))
    nxt = S["ptf"].get(hkey(t + timedelta(hours=1)))
    f["ptf_d1"] = ptf - prev if ptf is not None and prev is not None else None
    f["ptf_n1"] = nxt - ptf if ptf is not None and nxt is not None else None

    for c in ("lep", "dpp", "dpp_sun", "dpp_wind", "dpp_gas", "dpp_hydro", "dpp_river", "dpp_coal", "dpp_lig"):
        f[c] = S[c].get(key)
    f["lep_dpp"] = f["lep"] - f["dpp"] if f["lep"] is not None and f["dpp"] is not None else None
    gas_day = _day_values(S["dpp_gas"], day)
    f["gas_dev"] = f["dpp_gas"] - sum(gas_day) / 24 if gas_day and f["dpp_gas"] is not None else None

    past = [S["net"].get(hkey(t - timedelta(days=d))) for d in range(2, 9)]
    f["net7"] = sum(past) / 7 if all(v is not None for v in past) else None

    f["k"] = float(k)
    t_net = t - timedelta(hours=k + PUB_LAG)
    t_phys = t - timedelta(hours=k + PHYS_LAG)
    w3 = _window(S["net"], t_net, 3)
    w24 = _window(S["net"], t_net, 24)
    w168 = _window(S["net"], t_net, 168)
    f["net_last"] = w3[0] if w3 else S["net"].get(hkey(t_net))
    f["net_last3"] = sum(w3) / 3 if w3 else None
    f["net_24"] = sum(w24) / 24 if w24 else None
    f["net_168"] = sum(w168) / 168 if w168 else None
    f["acik_168"] = sum(1 for v in w168 if v > 0) / 168 if w168 else None
    smf = S["smf"].get(hkey(t_net))
    ptf_then = S["ptf"].get(hkey(t_net))
    f["smfptf_last"] = smf - ptf_then if smf is not None and ptf_then is not None else None
    p3 = _window(S["phys"], t_phys, 3)
    f["phys_last"] = S["phys"].get(hkey(t_phys))
    f["phys_last3"] = sum(p3) / 3 if p3 else None
    f["wind_dev_last"] = S["wind_dev"].get(hkey(t_phys))
    return f


def load_model() -> dict | None:
    try:
        return json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def predict_proba(model: dict, f: dict[str, float | None]) -> tuple[float, int]:
    """
    Açık olasılığı. Eksik özellik eğitim ortalamasıyla doldurulur (standartlaştırılmış 0).
    İkinci değer eksik özellik sayısı.
    """
    z = model["intercept"]
    missing = 0
    for name, mu, sd, w in zip(model["features"], model["mean"], model["scale"], model["coef"]):
        v = f.get(name)
        if v is None:
            missing += 1
            continue
        z += w * (v - mu) / sd
    return 1 / (1 + math.exp(-z)), missing
