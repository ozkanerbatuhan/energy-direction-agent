"""
train_model.py — app/model.json'u yeniden eğitir.

    python scripts/train_model.py                    # EPİAŞ'tan 1 Oca'dan bugüne çeker
    python scripts/train_model.py --cache hist.json  # çekilen veriyi kaydet / varsa ondan oku

Gerekenler (yalnız eğitim için, backend'e girmez): numpy, scikit-learn. .env'de EPİAŞ hesabı.
Ayda bir yeniden eğitmek yeterli; rejim (açık/fazla oranı) aydan aya kayıyor.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import numpy as np  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from app import config as c  # noqa: E402
from app.auth import get_current_tgt, refresh_tgt  # noqa: E402
from app.fetcher import _post_sync  # noqa: E402
from app.model import FEATURES, MODEL_PATH, build_series, features  # noqa: E402

HORIZONS = [1, 2, 3, 4, 6, 8, 12, 18, 24]
C_REG = 0.03
PATHS = {
    "ptf": c.EPIAS_KPTF_PATH, "smf": c.EPIAS_SMF_PATH, "load_estimation": c.EPIAS_LOAD_ESTIMATION_PATH,
    "realtime_consumption": c.EPIAS_REALTIME_CONSUMPTION_PATH, "realtime_generation": c.EPIAS_REALTIME_GENERATION_PATH,
    "dpp": c.EPIAS_DPP_PATH, "yal": c.EPIAS_YAL_PATH, "system_direction": c.EPIAS_SYSTEM_DIRECTION_PATH,
}


async def pull(start: date, end: date) -> dict[str, list[dict]]:
    await refresh_tgt()
    tgt = await get_current_tgt()
    out: dict[str, list[dict]] = {k: [] for k in PATHS}
    s = start
    while s <= end:
        e = min(end, (s.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1))
        body = {"startDate": f"{s}T00:00:00+03:00", "endDate": f"{e}T00:00:00+03:00"}
        for k, p in PATHS.items():
            b = {**body, "region": "TR1"} if k == "dpp" else body
            out[k] += (_post_sync(c.EPIAS_BASE_URL + p, b, tgt) or {}).get("items") or []
        print(s, {k: len(v) for k, v in out.items()}, flush=True)
        s = e + timedelta(days=1)
    return out


def rows(S, hours):
    X, y, months = [], [], []
    for t in hours:
        net = S["net"].get(t.strftime("%Y-%m-%dT%H"))
        if not net:  # yayınlanmamış ya da tam denge
            continue
        for k in HORIZONS:
            f = features(S, t, k)
            if any(f[n] is None for n in FEATURES):
                continue
            X.append([f[n] for n in FEATURES])
            y.append(1 if net > 0 else 0)
            months.append(t.year * 100 + t.month)
    return np.array(X), np.array(y), np.array(months)


def fit(X, y):
    sc = StandardScaler().fit(X)
    lr = LogisticRegression(max_iter=5000, C=C_REG).fit(sc.transform(X), y)
    return sc, lr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache")
    ap.add_argument("--start", default="2026-01-01")
    a = ap.parse_args()

    if a.cache and Path(a.cache).exists():
        items = json.loads(Path(a.cache).read_text(encoding="utf-8"))
    else:
        items = asyncio.run(pull(date.fromisoformat(a.start), date.today()))
        if a.cache:
            Path(a.cache).write_text(json.dumps(items), encoding="utf-8")

    S = build_series(items)
    t0 = datetime.fromisoformat(a.start)
    hours = [t0 + timedelta(hours=i) for i in range(int((datetime.now() - t0).total_seconds() // 3600))]
    X, y, months = rows(S, hours)
    print(f"satır {len(y)}, açık oranı {y.mean():.3f}")

    # Ay ay ileri yürüyen test: her ay yalnız kendisinden önceki aylarla eğitilir
    uniq = sorted(set(months))
    report = []
    for m in uniq[4:]:
        tr, te = months < m, months == m
        sc, lr = fit(X[tr], y[tr])
        acc = float((lr.predict(sc.transform(X[te])) == y[te]).mean())
        net7 = float(((X[te][:, FEATURES.index("net7")] > 0).astype(int) == y[te]).mean())
        report.append({"month": int(m), "n": int(te.sum()), "model": round(acc, 4), "net7": round(net7, 4)})
        print(m, f"model {acc:.3f}  7g-ort {net7:.3f}  n={te.sum()}")
    wm = sum(r["model"] * r["n"] for r in report) / sum(r["n"] for r in report)
    wb = sum(r["net7"] * r["n"] for r in report) / sum(r["n"] for r in report)
    print(f"ağırlıklı: model {wm:.3f}  7g-ort {wb:.3f}")

    sc, lr = fit(X, y)
    MODEL_PATH.write_text(json.dumps({
        "type": "logistic_regression",
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "train_range": [a.start, hours[-1].strftime("%Y-%m-%d")],
        "rows": int(len(y)),
        "horizons": HORIZONS,
        "C": C_REG,
        "features": FEATURES,
        "mean": sc.mean_.round(6).tolist(),
        "scale": sc.scale_.round(6).tolist(),
        "coef": lr.coef_[0].round(6).tolist(),
        "intercept": round(float(lr.intercept_[0]), 6),
        "walk_forward": {"monthly": report, "model": round(wm, 4), "net7_baseline": round(wb, 4)},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("yazıldı:", MODEL_PATH)


if __name__ == "__main__":
    main()
