"""
main.py

CLI entry point.

Examples:
    python main.py AAPL MSFT TSLA
    python main.py AAPL MSFT --no-llm --currency USD --tiers 50 200 1000
"""

import argparse
import json
import sys

from orchestrator import StockAnalysisOrchestrator


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze stocks and produce a scored report.")
    parser.add_argument("tickers", nargs="+", help="Ticker symbols, e.g. AAPL MSFT TSLA")
    parser.add_argument("--period", default="3y", help="History window for price data (default: 3y)")
    parser.add_argument("--currency", default="USD", help="Target currency for comparisons (default: USD)")
    parser.add_argument("--risk-free-rate", type=float, default=0.04, help="Annual risk-free rate (default: 0.04)")
    parser.add_argument("--llm-model", default="gemma3:4b", help="Ollama model name for qualitative analysis")
    parser.add_argument("--no-llm", action="store_true", help="Skip the LLM qualitative overlay (faster, offline)")
    parser.add_argument(
        "--tiers", nargs="*", type=float, default=None,
        help="Price tier upper bounds for budget grouping, e.g. --tiers 50 200 1000"
    )
    parser.add_argument("--out", default=None, help="Optional path to write the JSON report to")
    return parser.parse_args()


def main():
    args = parse_args()

    orchestrator = StockAnalysisOrchestrator(
        target_currency=args.currency,
        risk_free_rate=args.risk_free_rate,
        llm_model=args.llm_model,
    )

    report = orchestrator.analyze_and_report(
        tickers=[t.upper() for t in args.tickers],
        period=args.period,
        use_llm=not args.no_llm,
        price_tiers=args.tiers,
    )

    output = json.dumps(report, indent=2, default=str)

    if args.out:
        with open(args.out, "w") as f:
            f.write(output)
        print(f"Report written to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    sys.exit(main() or 0)
