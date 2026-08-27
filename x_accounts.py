import os

# Default watchlist of well-known crypto figures on X. Override with the
# X_ACCOUNTS env var (comma-separated usernames, no "@").
DEFAULT_ACCOUNTS = [
    "VitalikButerin",   # Vitalik Buterin, Ethereum co-founder
    "cz_binance",       # Changpeng Zhao, Binance founder
    "saylor",           # Michael Saylor, Strategy (MicroStrategy)
    "APompliano",       # Anthony Pompliano, investor/commentator
    "CryptoHayes",      # Arthur Hayes, BitMEX co-founder
    "brian_armstrong",  # Brian Armstrong, Coinbase CEO
    "balajis",          # Balaji Srinivasan, investor/former Coinbase CTO
    "WuBlockchain",     # Colin Wu, Asia-focused crypto reporter
]


def get_accounts():
    raw = os.environ.get("X_ACCOUNTS")
    if not raw:
        return list(DEFAULT_ACCOUNTS)
    return [a.strip().lstrip("@") for a in raw.split(",") if a.strip()]
