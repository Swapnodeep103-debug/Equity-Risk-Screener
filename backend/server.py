"""
server.py  (BACKEND)

Flask JSON API for the stock analyzer. The dashboard code lives in the separate
../frontend folder; this server also serves those files for convenience.

Because a full analysis can take minutes (yfinance is slow), requests don't
block: POST /api/analyze starts a background job and returns a job id, and the
dashboard polls GET /api/jobs/<id> for progress until the report is ready.

Run:
    python server.py
Then open http://127.0.0.1:5000 - the server serves the dashboard from
../frontend AND the API, so one command and one address is all you need.
(The frontend can still be hosted separately; see CORS below.)

CORS: browsers only let the dashboard call this API if the API says its origin
is allowed. By default these are allowed: http://127.0.0.1:3000,
http://localhost:3000 and "null" (a dashboard opened straight from disk).
Override with an environment variable, comma separated:
    set ALLOWED_ORIGINS=http://127.0.0.1:8080        (Windows cmd)
    $env:ALLOWED_ORIGINS="http://127.0.0.1:8080"     (PowerShell)

Endpoints:
    GET  /api/health          -> {"status": "ok"}
    GET  /api/domains         -> {domain: [tickers]} from tickers.py
    POST /api/analyze         -> start a job. JSON body (need tickers or domains):
                                   {"tickers": ["AAPL"], "domains": ["semiconductors"],
                                    "use_llm": false, "period": "3y",
                                    "price_tiers": [50, 200, 1000]}
    GET  /api/jobs/<job_id>   -> {status, done, total, report?, error?}
    GET  /api/latest          -> the most recently completed report (survives restarts)
"""

import json
import os
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, send_from_directory

from orchestrator import StockAnalysisOrchestrator
from tickers import TECH_UNIVERSE
import ranking

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
LATEST_PATH = os.path.join(REPORTS_DIR, "latest.json")

MAX_TICKERS_PER_JOB = 100
BATCH_SIZE = 5
PAUSE_BETWEEN_BATCHES = 2.0  # seconds; keeps Yahoo from rate-limiting you
TICKER_RE = re.compile(r"^[A-Z0-9.\-=^]{1,15}$")
VALID_PERIODS = {"1y", "2y", "3y", "5y", "10y", "max"}

ALLOWED_ORIGINS = {
    o.strip() for o in os.environ.get(
        "ALLOWED_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000,null"
    ).split(",") if o.strip()
}

app = Flask(__name__, static_folder=None)


@app.after_request
def add_cors_headers(resp):
    origin = request.headers.get("Origin")
    if origin and origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Max-Age"] = "600"
    return resp

JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
RUN_LOCK = threading.Lock()  # one analysis at a time, to be gentle on Yahoo


def _resolve_tickers(tickers: Optional[List[str]], domains: Optional[List[str]]):
    """Merge explicit tickers and domain selections into one deduped list,
    plus a ticker -> domains map for the dashboard's domain filter."""
    ordered: List[str] = []
    ticker_domains: Dict[str, List[str]] = {}

    for domain in domains or []:
        for t in TECH_UNIVERSE.get(domain, []):
            ticker_domains.setdefault(t, [])
            if domain not in ticker_domains[t]:
                ticker_domains[t].append(domain)
            if t not in ordered:
                ordered.append(t)

    for t in tickers or []:
        if t not in ordered:
            ordered.append(t)

    return ordered, ticker_domains


def _run_job(job_id: str, tickers: List[str], ticker_domains: Dict[str, List[str]],
             use_llm: bool, period: str, price_tiers: Optional[List[float]]):
    def update(**kw):
        with JOBS_LOCK:
            JOBS[job_id].update(kw)

    with RUN_LOCK:
        update(status="running")
        try:
            orchestrator = StockAnalysisOrchestrator()
            all_results: Dict[str, Any] = {}

            for i in range(0, len(tickers), BATCH_SIZE):
                batch = tickers[i:i + BATCH_SIZE]
                try:
                    all_results.update(orchestrator.analyze(batch, period=period, use_llm=use_llm))
                except Exception as e:  # one bad batch shouldn't kill the job
                    for t in batch:
                        all_results[t] = {"error": f"batch failed: {e}"}
                update(done=min(i + BATCH_SIZE, len(tickers)))
                if i + BATCH_SIZE < len(tickers):
                    time.sleep(PAUSE_BETWEEN_BATCHES)

            report = ranking.build_report(all_results, price_tiers=price_tiers)
            report["ticker_domains"] = ticker_domains
            report["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            report["errors"] = {t: r["error"] for t, r in all_results.items() if "error" in r}

            os.makedirs(REPORTS_DIR, exist_ok=True)
            with open(LATEST_PATH, "w") as f:
                json.dump(report, f, indent=2, default=str)

            update(status="done", report=report, done=len(tickers))
        except Exception as e:
            update(status="error", error=str(e))


@app.get("/api/health")
def health():
    return jsonify(status="ok")


@app.get("/")
def dashboard():
    # One-server mode: the dashboard lives in ../frontend and is served from
    # here, so the page and the API share one address (http://127.0.0.1:5000).
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:filename>")
def frontend_files(filename):
    # Only reached for paths that aren't /api/... routes. send_from_directory
    # refuses anything outside FRONTEND_DIR (no ../ escapes).
    return send_from_directory(FRONTEND_DIR, filename)


@app.get("/api/domains")
def domains():
    return jsonify(TECH_UNIVERSE)


@app.post("/api/analyze")
def analyze():
    body = request.get_json(silent=True) or {}

    raw_tickers = body.get("tickers") or []
    raw_domains = body.get("domains") or []
    if not isinstance(raw_tickers, list) or not isinstance(raw_domains, list):
        return jsonify(error="'tickers' and 'domains' must be lists"), 400

    tickers = [str(t).strip().upper() for t in raw_tickers if str(t).strip()]
    bad = [t for t in tickers if not TICKER_RE.match(t)]
    if bad:
        return jsonify(error=f"invalid ticker symbol(s): {bad}"), 400

    unknown_domains = [d for d in raw_domains if d not in TECH_UNIVERSE]
    if unknown_domains:
        return jsonify(error=f"unknown domain(s): {unknown_domains}",
                       valid_domains=list(TECH_UNIVERSE.keys())), 400

    all_tickers, ticker_domains = _resolve_tickers(tickers, raw_domains)
    if not all_tickers:
        return jsonify(error="provide at least one ticker or domain"), 400
    if len(all_tickers) > MAX_TICKERS_PER_JOB:
        return jsonify(error=f"too many tickers ({len(all_tickers)}); max {MAX_TICKERS_PER_JOB} per job"), 400

    period = body.get("period", "3y")
    if period not in VALID_PERIODS:
        return jsonify(error=f"period must be one of {sorted(VALID_PERIODS)}"), 400

    price_tiers = body.get("price_tiers")
    if price_tiers is not None:
        try:
            price_tiers = [float(x) for x in price_tiers]
        except (TypeError, ValueError):
            return jsonify(error="price_tiers must be a list of numbers"), 400

    use_llm = bool(body.get("use_llm", False))

    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "queued", "done": 0, "total": len(all_tickers),
                        "created": time.time()}

    threading.Thread(
        target=_run_job,
        args=(job_id, all_tickers, ticker_domains, use_llm, period, price_tiers),
        daemon=True,
    ).start()

    return jsonify(job_id=job_id, total=len(all_tickers)), 202


@app.get("/api/jobs/<job_id>")
def job_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return jsonify(error="unknown job id"), 404
        return jsonify(job)


@app.get("/api/latest")
def latest():
    if not os.path.exists(LATEST_PATH):
        return jsonify(error="no report yet"), 404
    with open(LATEST_PATH) as f:
        return jsonify(json.load(f))


if __name__ == "__main__":
    # debug=False on purpose: the debug reloader would restart the server (and
    # kill running jobs) every time a file changes.
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)

