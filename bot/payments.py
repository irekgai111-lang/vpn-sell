"""Платёжные провайдеры: CryptoBot (USDT) + YooKassa (карты/СБП)."""
import uuid, requests
from config import CRYPTO_TOKEN, YK_SHOP_ID, YK_SECRET


# ─── CryptoBot ────────────────────────────────────────────────────────────────

CRYPTO_URL = "https://pay.crypt.bot/api"


def crypto_create(amount_usdt: float, description: str) -> dict:
    """Возвращает {"invoice_id": str, "pay_url": str}"""
    r = requests.post(
        f"{CRYPTO_URL}/createInvoice",
        json={
            "asset": "USDT",
            "amount": round(amount_usdt, 2),
            "description": description,
            "allow_comments": False,
            "allow_anonymous": False,
            "expires_in": 3600,
        },
        headers={"Crypto-Pay-API-Token": CRYPTO_TOKEN},
        timeout=10,
    )
    r.raise_for_status()
    res = r.json()["result"]
    return {"invoice_id": str(res["invoice_id"]), "pay_url": res["pay_url"]}


def crypto_check(invoice_id: str) -> bool:
    """True если оплачен."""
    r = requests.get(
        f"{CRYPTO_URL}/getInvoices",
        params={"invoice_ids": invoice_id},
        headers={"Crypto-Pay-API-Token": CRYPTO_TOKEN},
        timeout=10,
    )
    if not r.ok:
        return False
    items = r.json().get("result", {}).get("items", [])
    return bool(items) and items[0]["status"] == "paid"


# ─── YooKassa ─────────────────────────────────────────────────────────────────

YK_URL = "https://api.yookassa.ru/v3"


def yk_create(amount_rub: float, description: str, return_url: str) -> dict:
    """Возвращает {"invoice_id": str, "pay_url": str}"""
    idempotency = uuid.uuid4().hex
    r = requests.post(
        f"{YK_URL}/payments",
        json={
            "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description,
            "capture": True,
        },
        auth=(YK_SHOP_ID, YK_SECRET),
        headers={"Idempotence-Key": idempotency, "Content-Type": "application/json"},
        timeout=10,
    )
    r.raise_for_status()
    res = r.json()
    return {
        "invoice_id": res["id"],
        "pay_url": res["confirmation"]["confirmation_url"],
    }


def yk_check(payment_id: str) -> bool:
    r = requests.get(
        f"{YK_URL}/payments/{payment_id}",
        auth=(YK_SHOP_ID, YK_SECRET),
        timeout=10,
    )
    if not r.ok:
        return False
    return r.json().get("status") == "succeeded"


# ─── Unified check ────────────────────────────────────────────────────────────

def check_payment(method: str, invoice_id: str) -> bool:
    if method == "crypto":
        return crypto_check(invoice_id)
    if method == "card":
        return yk_check(invoice_id)
    return False
