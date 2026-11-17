"""
run_universe.py

Runs the analysis across the curated tech universe in tickers.py, grouped
by domain. Writes one JSON report per domain plus a merged master report.

This queries a lot of tickers, so it processes them in small batches with a
pause in between to reduce the chance of Yahoo Finance rate-limiting you.
Expect this to take a while - anywhere from several minutes (no LLM, ~90
tickers) to much longer if you enable --llm, since that's a full model call
per ticker.

Examples:
    python run_universe.py
    python run_universe.py --domains semiconductors ai_focused
    python run_universe.py --llm --batch-size 3 --pause-seconds 3
"""

import argparse
import json
import os
import time

from orchestrator import StockAnalysisOrchestrator
from tickers import TECH_UNIVERSE
import ranking


def flatten_universe(domains=None):
    selected = {d: t for d, t in TECH_UNIVERSE.items() if not domains or d in domains}
    all_tickers = []
    for tickers in selected.values():
        for t in tickers:
            if t not in all_tickers:
                all_tickers.append(t)
    return selected, all_tickers


def main():
    parser = argparse.ArgumentParser(description="Analyze the curated tech stock universe, by domain.")
    parser.add_argument(
        "--domains", nargs="*", default=None,
        help=f"Subset of domains to run (default: all). Options: {list(TECH_UNIVERSE.keys())}"
    )
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--period", default="3y")
    parser.add_argument("--llm", action="store_true", help="Enable the LLM qualitative overlay (much slower)")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--pause-seconds", type=float, default=2.0, help="Pause between batches to avoid rate limits")
    parser.add_argument("--out-dir", default="reports")
    args = parser.parse_args()

    selected_domains, all_tickers = flatten_universe(args.domains)

    if args.domains:
        unknown = [d for d in args.domains if d not in TECH_UNIVERSE]
        if unknown:
            print(f"[warn] unrecognized domain(s): {unknown} - check spelling against: {list(TECH_UNIVERSE.keys())}")
    if not all_tickers:
        print("No tickers matched the requested domain(s). Nothing to analyze.")
        return

    print(f"Analyzing {len(all_tickers)} unique tickers across {len(selected_domains)} domains...")

    os.makedirs(args.out_dir, exist_ok=True)
    orchestrator = StockAnalysisOrchestrator(target_currency=args.currency)

    all_results = {}
    num_batches = (len(all_tickers) + args.batch_size - 1) // args.batch_size
    for i in range(0, len(all_tickers), args.batch_size):
        batch = all_tickers[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        print(f"  batch {batch_num}/{num_batches}: {batch}")
        try:
            batch_results = orchestrator.analyze(batch, period=args.period, use_llm=args.llm)
            all_results.update(batch_results)
        except Exception as e:
            print(f"  [warn] batch {batch_num} failed: {e}")
        if i + args.batch_size < len(all_tickers):
            time.sleep(args.pause_seconds)

    # One report per domain
    for domain, tickers in selected_domains.items():
        domain_results = {t: all_results[t] for t in tickers if t in all_results}
        domain_report = ranking.build_report(domain_results)
        domain_report["domain"] = domain
        path = os.path.join(args.out_dir, f"{domain}.json")
        with open(path, "w") as f:
            json.dump(domain_report, f, indent=2, default=str)

    # Merged master report, tagging each ticker with every domain it's in
    ticker_domains = {}
    for domain, tickers in selected_domains.items():
        for t in tickers:
            ticker_domains.setdefault(t, []).append(domain)

    master_report = ranking.build_report(all_results)
    master_report["ticker_domains"] = ticker_domains
    master_path = os.path.join(args.out_dir, "master_report.json")
    with open(master_path, "w") as f:
        json.dump(master_report, f, indent=2, default=str)

    print(f"Done. Domain reports + master_report.json written to {args.out_dir}/")


if __name__ == "__main__":
    main()
