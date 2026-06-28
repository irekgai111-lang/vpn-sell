import os

BOT_TOKEN     = os.getenv("BOT_TOKEN",     "")
BOT_USERNAME  = os.getenv("BOT_USERNAME",  "my_vpn_bot")
MARZBAN_URL   = os.getenv("MARZBAN_URL",   "http://localhost:8000")
MARZBAN_USER  = os.getenv("MARZBAN_USER",  "admin")
MARZBAN_PASS  = os.getenv("MARZBAN_PASS",  "")
INBOUND_TAG   = os.getenv("INBOUND_TAG",   "vless-in")
ADMIN_IDS     = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()]
CRYPTO_TOKEN  = os.getenv("CRYPTO_TOKEN",  "")
YK_SHOP_ID    = os.getenv("YK_SHOP_ID",    "")
YK_SECRET     = os.getenv("YK_SECRET",     "")
DB_PATH       = os.getenv("DB_PATH",       "/opt/vpn-bot/vpn.db")
STARS_ENABLED = os.getenv("STARS_ENABLED", "false").lower() == "true"
CHANNEL_ID    = os.getenv("CHANNEL_ID",    "")   # ID канала для авто-постов продаж

TRIAL_DAYS = 3
REF_BONUS  = 14   # 2 недели за приглашённого друга
RATE_LIMIT = 600

SITE_URL = os.getenv("SITE_URL", "https://irekgai111-lang.github.io/vpn-sell/")

PLANS = {
    "trial": {"name": "🎁 3 дня бесплатно", "rub": 0,    "usdt": 0,     "stars": 0,    "days": 3,   "gb": 5},
    "1m":    {"name": "1 месяц",             "rub": 250,  "usdt": 2.75,  "stars": 350,  "days": 30,  "gb": 100},
    "3m":    {"name": "3 месяца ⭐ Хит",     "rub": 599,  "usdt": 6.59,  "stars": 850,  "days": 90,  "gb": 300},
    "6m":    {"name": "6 месяцев",           "rub": 999,  "usdt": 11.00, "stars": 1400, "days": 180, "gb": 999},
    "12m":   {"name": "1 год 🏆",            "rub": 1699, "usdt": 18.70, "stars": 2400, "days": 365, "gb": 9999},
}

OLD_PRICES = {"1m": 350, "3m": 750, "6m": 1500, "12m": 3000}
