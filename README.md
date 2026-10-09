# ⚡ Energy Agent — Turkish Grid Direction Forecaster

> **Live Demo:** [https://energy-direction-agent.vercel.app](https://energy-direction-agent.vercel.app)

An AI-powered forecasting dashboard that predicts whether the Turkish electricity grid will be in **deficit (AÇIK)** or **surplus (FAZLA)** for every hour of the day — by analyzing historical patterns, real-time momentum, and active grid outages sourced directly from [EPİAŞ](https://seffaflik.epias.com.tr/) (the Turkish Electricity Market Transparency Platform).

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────┐
│               Next.js Frontend (Vercel)               │
│           energy-direction-agent.vercel.app           │
└───────────────────────┬──────────────────────────────┘
                        │ API Calls
┌───────────────────────▼──────────────────────────────┐
│            FastAPI Backend (Render.com)               │
│     https://energy-direction-agent.onrender.com       │
│                                                       │
│   ┌─────────────┐   ┌──────────────┐  ┌───────────┐  │
│   │  Scheduler  │   │    Engine    │  │  Storage  │  │
│   │ (APScheduler│   │ (Forecasting │  │  (Cache / │  │
│   │   / cron)   │   │   Logic)     │  │  JSON DB) │  │
│   └─────────────┘   └──────────────┘  └───────────┘  │
└───────────────────────┬──────────────────────────────┘
                        │ Fetch
              ┌─────────▼─────────┐
              │   EPİAŞ Şeffaflık │
              │    Transparency   │
              │     Platform API  │
              └───────────────────┘
```

---

## 🧠 Forecasting Engine

The target is EPİAŞ's realized **net balancing instruction** (YAL − YAT, MWh) per hour:

- `Net > 0` → Grid was **AÇIK (DEFICIT)** — TEİAŞ ordered up-regulation
- `Net < 0` → Grid was **FAZLA (SURPLUS)** — TEİAŞ ordered down-regulation

A logistic regression (`app/model.py`, weights in `app/model.json`) gives the deficit
probability for each hour, using only what is known `k` hours ahead: day-ahead PTF and its
shape within the day, KGÜP components (gas, wind, solar, hydro…), LEP, the last published
net instructions (published ~6 h late), SMF − PTF, and the solar-excluded physical deviation
(~2 h late). Bar height = (2p − 1) × mean |net| of that hour over the past 7 days.

Walk-forward test (train on all months before, test the next month; May–Oct 2026,
~38k hour×horizon rows, horizons 1–24 h):

| Model | Direction hit rate |
|---|---|
| Always "surplus" | 47.5% |
| 7-day same-hour net mean | 60.0% |
| **Logistic regression (current)** | **65.3%** |
| … when p > 0.8 or p < 0.2 (13% of hours) | 78% |

Old in-place physical formula: 46.6% (19 Sep – 8 Oct backtest).

Retrain monthly: `python scripts/train_model.py --cache hist.json` (needs numpy + scikit-learn
locally; the backend only reads the JSON weights).

The old formula subtracted realtime generation (only metered, licensed PV ≈ 3 GW) from KGÜP
(all PV incl. unlicensed ≈ 15–19 GW), which showed a fake ~13 GW "deficit" every midday.
Adding momentum or the physical deviation lowered the hit rate, so they are reported for
information only. Distribution outages lower consumption, so they are not a deficit term.

---

## 📊 Dashboard Features

### Agent Forecast Tab
- **24-hour bar chart** — realized hours show actual values; future hours show AI forecasts
- **Forecast accuracy tracking** — for past hours: predicted vs. actual vs. error margin
- **Structured reasoning** — each hour displays 3-line breakdown: `Tarihsel`, `Momentum`, `Arıza` contributions in MW

### Raw EPİAŞ Plan Tab
- **LEP vs DPP chart** — plots the raw market plan delta (Load Estimation Plan minus Day-Ahead Production Plan) without any AI layer
- **Full data table** — shows LEP (MWh), DPP (MWh), and their theoretical difference per hour

### Outage Monitor
- **Planned outages** (Şebeke Çalışmaları) and **unplanned outages** (Plansız Kesintiler)
- Table columns: Province, District, Outage Start, Outage End, Distribution Company, Reason, Affected Subscribers, Load Loss (MW)
- Sortable by publish date or criticality (MW impact)

---

## 🔌 Data Sources (EPİAŞ APIs)

| Dataset | Description |
|---------|-------------|
| `load-estimation-plan` (LEP) | Hourly electricity load forecast |
| `realtime-generation` | Actual generation per hour |
| `realtime-consumption` | Actual consumption per hour |
| `dpp` (KKGÜP) | Day-ahead confirmed production plan |
| `planned-outages` | Scheduled grid maintenance |
| `unplanned-outages` | Emergency / fault outages |

---

## ⚙️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15 (App Router), Recharts, Tailwind CSS, Lucide Icons |
| Backend | FastAPI, Uvicorn, APScheduler |
| Data Cache | Local JSON file store with LRU-style TTL (3-day sliding window) |
| Deployment | Vercel (frontend) + Render (backend) |
| Auth | EPİAŞ credentials via environment variables |

---

## 🚀 Local Development

### Backend

```bash
# Clone and install
pip install -r requirements.txt

# Set credentials
cp .env.example .env
# Edit .env → EPIAS_USERNAME, EPIAS_PASSWORD

# Run
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd energy-dashboard
npm install
npm run dev
```

The frontend will run at `http://localhost:3000` and connect to the backend at `http://localhost:8000`.

---

## 🌍 Environment Variables

| Variable | Description |
|----------|-------------|
| `EPIAS_USERNAME` | EPİAŞ Transparency Platform username |
| `EPIAS_PASSWORD` | EPİAŞ Transparency Platform password |

---

## 📁 Project Structure

```
energy-direction-agent/
├── app/                    # FastAPI backend
│   ├── main.py             # API routes
│   ├── engine.py           # Forecasting algorithm
│   ├── fetcher.py          # EPİAŞ API client
│   ├── storage.py          # JSON cache layer
│   ├── scheduler.py        # Background data refresh
│   └── config.py           # Settings
├── energy-dashboard/       # Next.js frontend
│   └── app/
│       ├── page.tsx        # Main dashboard
│       └── layout.tsx      # App layout & metadata
├── data/                   # Cached EPİAŞ data (auto-managed)
└── requirements.txt
```

---

## 📄 License

MIT
