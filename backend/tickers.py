"""
tickers.py

A curated set of tech-sector tickers, grouped by domain. This is NOT every
tech company that exists (there are thousands, and Yahoo Finance's free API
will rate-limit you long before you get through all of them) - it's a
reasonably broad starting universe you can extend.

To add more: just append tickers to any list below, or add a new domain key.
The same ticker can appear in more than one domain (e.g. AAPL is both
"big_tech" and "hardware_consumer") - run_universe.py dedupes for the actual
API calls but still tags each ticker with every domain it belongs to.
"""

TECH_UNIVERSE = {
    "big_tech": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
    "semiconductors": ["NVDA", "AMD", "INTC", "TSM", "AVGO", "QCOM", "TXN", "MU"],
    "semiconductor_equipment": ["ASML", "LRCX", "AMAT", "KLAC"],
    "software_saas": ["CRM", "ADBE", "ORCL", "SAP", "NOW", "INTU", "WDAY", "TEAM"],
    "cybersecurity": ["PANW", "CRWD", "FTNT", "ZS", "OKTA", "S"],
    "cloud_infra": ["SNOW", "DDOG", "NET", "MDB", "AKAM"],
    "ecommerce_internet": ["SHOP", "EBAY", "ETSY", "PINS", "SNAP", "UBER", "ABNB"],
    "social_media": ["META", "SNAP", "PINS", "RDDT"],
    "ev_autonomous": ["TSLA", "RIVN", "LCID", "NIO"],
    "fintech": ["PYPL", "SQ", "COIN", "AFRM", "SOFI"],
    "hardware_consumer": ["AAPL", "DELL", "HPQ", "SONY"],
    "ai_focused": ["NVDA", "PLTR", "AI", "SMCI", "ARM"],
    "telecom_networking": ["CSCO", "JNPR", "ANET"],
    "gaming_entertainment": ["EA", "TTWO", "RBLX", "U"],
    "chinese_tech": ["BABA", "PDD", "JD", "BIDU"],
}
