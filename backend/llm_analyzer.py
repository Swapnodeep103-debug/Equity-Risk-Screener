"""
llm_analyzer.py

Uses a local LLM (via ollama) to add a qualitative risk overlay on top of the
quantitative metrics - things like macro/competitive risks that don't show
up in a price series or a debt-to-equity ratio.

The model's output is validated/clamped before use (see _validate) so a
malformed or unexpected response can't corrupt the composite score or crash
the pipeline.
"""

import json
from typing import Optional

# NOTE: ollama is imported lazily inside analyze_company_risks(), not here at
# module load time. That way, running with --no-llm (which never calls that
# method) works fine even if the ollama package isn't installed - the import
# used to be at the top of this file, which meant EVERY run required ollama
# to be installed, even runs that never touched the LLM overlay.


class LLMAdversityAnalyzer:
    def __init__(self, model: str = "gemma3:4b"):
        self.model = model

    def analyze_company_risks(self, ticker: str, fundamentals: dict, quantitative_flags: list) -> dict:
        prompt = f"""You are a quantitative financial risk analyst.

Analyze the company {ticker} using the following information.

Fundamentals:
- Debt to Equity: {fundamentals.get('debt_to_equity')}
- Profit Margins: {fundamentals.get('profit_margins')}

Quantitative Flags:
{', '.join(quantitative_flags) if quantitative_flags else 'None'}

Identify important corporate, macroeconomic, and financial risks only.
Do not give investment recommendations, price targets, or buy/sell/hold language.

Return ONLY valid JSON using exactly these keys:
{{
    "macro_adversities": ["risk 1", "risk 2", "risk 3"],
    "qualitative_score_modifier": 0,
    "summary": "one sentence risk evaluation"
}}

Rules:
- macro_adversities must contain 2-3 short risk strings.
- qualitative_score_modifier must be an integer from -10 to +10.
- summary must be one sentence, purely descriptive of risk, no recommendations.
- Do not include markdown or text outside the JSON.
"""
        fallback = {
            "macro_adversities": ["AI analysis unavailable", "Market systemic volatility"],
            "qualitative_score_modifier": 0,
            "summary": "Local AI analysis failed.",
        }

        try:
            import ollama  # lazy import - see note at top of file
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={"temperature": 0.2},
            )
            parsed = json.loads(response["message"]["content"])
        except ImportError:
            fallback["summary"] = (
                "ollama package not installed. Run 'pip install ollama' and make sure "
                "the Ollama app is running locally, or use --no-llm to skip this step."
            )
            return fallback
        except Exception as e:
            fallback["summary"] = f"Local AI analysis failed: {e}"
            return fallback

        return self._validate(parsed, fallback)

    @staticmethod
    def _validate(parsed: dict, fallback: dict) -> dict:
        """Type/range-check the LLM's JSON before it's trusted anywhere else
        in the pipeline. Anything malformed falls back to a safe default
        rather than propagating (e.g. a string where an int is expected)."""
        out = dict(fallback)

        adversities = parsed.get("macro_adversities")
        if isinstance(adversities, list) and adversities and all(isinstance(x, str) for x in adversities):
            out["macro_adversities"] = adversities[:3]

        modifier = parsed.get("qualitative_score_modifier")
        try:
            modifier = int(modifier)
            out["qualitative_score_modifier"] = max(-10, min(10, modifier))
        except (TypeError, ValueError):
            pass  # keep fallback's 0

        summary = parsed.get("summary")
        if isinstance(summary, str) and summary.strip():
            out["summary"] = summary.strip()

        return out
