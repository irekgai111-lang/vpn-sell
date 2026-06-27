"""Marzban VPN Panel API клиент."""
import uuid, logging
from datetime import datetime, timedelta
import requests
from config import MARZBAN_URL, MARZBAN_USER, MARZBAN_PASS, INBOUND_TAG

log = logging.getLogger(__name__)
_token_cache: dict = {"token": None, "exp": datetime.min}


def _token() -> str:
    global _token_cache
    if _token_cache["token"] and datetime.utcnow() < _token_cache["exp"]:
        return _token_cache["token"]
    r = requests.post(
        f"{MARZBAN_URL}/api/admin/token",
        data={"username": MARZBAN_USER, "password": MARZBAN_PASS},
        timeout=10
    )
    r.raise_for_status()
    t = r.json()["access_token"]
    _token_cache = {"token": t, "exp": datetime.utcnow() + timedelta(minutes=50)}
    return t


def _h() -> dict:
    return {"Authorization": f"Bearer {_token()}"}


def create_user(tg_id: int, days: int, gb: int) -> dict:
    """Создаёт пользователя и возвращает данные с ключами."""
    uname  = f"tg{tg_id}_{uuid.uuid4().hex[:6]}"
    expire = int((datetime.utcnow() + timedelta(days=days)).timestamp())
    body = {
        "username": uname,
        "proxies": {"vless": {"flow": "xtls-rprx-vision"}},
        "inbounds": {"vless": [INBOUND_TAG]},
        "data_limit": gb * 1_073_741_824 if gb < 9000 else 0,
        "data_limit_reset_strategy": "no_reset",
        "expire": expire,
        "note": f"tg:{tg_id}",
    }
    r = requests.post(f"{MARZBAN_URL}/api/user", json=body, headers=_h(), timeout=10)
    r.raise_for_status()
    return r.json()


def get_links(username: str) -> list[str]:
    r = requests.get(f"{MARZBAN_URL}/api/user/{username}", headers=_h(), timeout=10)
    r.raise_for_status()
    return r.json().get("links", [])


def set_expire(username: str, new_expire: datetime):
    """Обновляет дату истечения у существующего пользователя."""
    body = {"expire": int(new_expire.timestamp())}
    r = requests.put(f"{MARZBAN_URL}/api/user/{username}", json=body, headers=_h(), timeout=10)
    r.raise_for_status()


def delete_user(username: str):
    requests.delete(f"{MARZBAN_URL}/api/user/{username}", headers=_h(), timeout=10)


def panel_stats() -> dict:
    r = requests.get(f"{MARZBAN_URL}/api/core/stats", headers=_h(), timeout=10)
    return r.json() if r.ok else {}
