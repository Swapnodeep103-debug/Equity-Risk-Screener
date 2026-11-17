# Equity-Risk-Screener


Two independent parts that talk over HTTP:

```
stock_app/
├── backend/            Python API (Flask) + analysis code
│   ├── server.py       the API  (run this)
│   ├── orchestrator.py, data_pipeline.py, risk_engine.py, llm_analyzer.py,
│   │   ranking.py, fx.py, cache.py, tickers.py
│   ├── main.py, run_universe.py     command-line alternatives
│   └── requirements.txt
└── frontend/           the dashboard (plain HTML/CSS/JS, no build step)
    ├── index.html
    ├── style.css
    ├── app.js
    └── config.js       <- backend address lives here
```

## Run it (one terminal, one address)

```
cd backend
pip install -r requirements.txt
python server.py
```

Then open **http://127.0.0.1:5000** in your browser. That single server
provides both the API and the dashboard (it serves the files in `frontend/`).
Pick domains, optionally add tickers, press **Run analysis**.

Before starting, close any older server windows - two copies can't use port
5000 at the same time.

(Optional) To host the frontend separately, run `python -m http.server 3000`
inside `frontend/`, open http://127.0.0.1:3000, and set
`window.STOCK_API_BASE = "http://127.0.0.1:5000"` in `frontend/config.js`.

## Changing addresses

- Frontend hosted separately from the backend: edit `frontend/config.js`
  (`window.STOCK_API_BASE`). Leave it empty for the one-server setup.
- Cross-origin use only: the backend only accepts requests from approved
  origins (default `http://127.0.0.1:3000`, `http://localhost:3000`, and
  `null` for a file opened from disk). To add one, set `ALLOWED_ORIGINS`
  before starting the backend, comma separated:
  - PowerShell: `$env:ALLOWED_ORIGINS="http://127.0.0.1:8080"`
  - cmd: `set ALLOWED_ORIGINS=http://127.0.0.1:8080`

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness check |
| GET | `/api/domains` | domains and tickers from `tickers.py` |
| POST | `/api/analyze` | start a job: `{"tickers": [...], "domains": [...], "use_llm": false}` |
| GET | `/api/jobs/<id>` | progress, then the finished report |
| GET | `/api/latest` | last completed report (saved in `backend/reports/latest.json`) |

Analyses run as background jobs, one at a time, in batches of 5 with short
pauses so Yahoo Finance doesn't rate-limit you. Max 100 tickers per job. The
server listens on 127.0.0.1 only and has no login, so don't expose it publicly.

## Command-line use (no browser)

```
cd backend
python main.py AAPL MSFT --no-llm --out report.json
python run_universe.py --domains semiconductors
```

The dashboard's **Load report.json** button can open files produced this way.

## Limitations

- This is not investment advice. The score is a hand-weighted heuristic over a
  few metrics and has not been backtested.
- The LLM overlay needs the Ollama app and `pip install ollama`; leave it off
  otherwise.
- FX conversion uses the latest rate, not a historical one.
- `tickers.py` is a curated list of about 70 tech tickers, not every tech
  company. Add your own there or type them into the dashboard.
