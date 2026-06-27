"""SQLite — единственный источник правды. Все данные здесь, ничего в памяти."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from config import DB_PATH


def _conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id       INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            referrer_id INTEGER,
            trial_used  INTEGER DEFAULT 0,
            created_at  TEXT    DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id      INTEGER NOT NULL,
            vpn_user   TEXT    NOT NULL,
            plan       TEXT    NOT NULL,
            expires_at TEXT    NOT NULL,
            status     TEXT    DEFAULT 'active',
            notif_3d   INTEGER DEFAULT 0,
            notif_1d   INTEGER DEFAULT 0,
            notif_exp  INTEGER DEFAULT 0,
            notif_dead INTEGER DEFAULT 0,
            created_at TEXT    DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS payments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id       INTEGER NOT NULL,
            invoice_id  TEXT    NOT NULL UNIQUE,
            method      TEXT    NOT NULL,
            plan        TEXT    NOT NULL,
            amount_rub  REAL    DEFAULT 0,
            amount_usdt REAL    DEFAULT 0,
            status      TEXT    DEFAULT 'pending',
            created_at  TEXT    DEFAULT (datetime('now')),
            paid_at     TEXT
        );
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL UNIQUE,
            bonus_given INTEGER DEFAULT 0,
            created_at  TEXT    DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS rate_limits (
            tg_id        INTEGER PRIMARY KEY,
            last_invoice TEXT
        );
        """)


# ─── Users ────────────────────────────────────────────────────────────────────

def upsert_user(tg_id: int, username: str, first_name: str, referrer_id: int = None):
    with _conn() as db:
        db.execute("""
            INSERT INTO users (tg_id, username, first_name, referrer_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
        """, (tg_id, username or "", first_name or "", referrer_id))


def get_user(tg_id: int) -> dict | None:
    with _conn() as db:
        row = db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        return dict(row) if row else None


def mark_trial_used(tg_id: int):
    with _conn() as db:
        db.execute("UPDATE users SET trial_used=1 WHERE tg_id=?", (tg_id,))


def total_users() -> int:
    with _conn() as db:
        return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# ─── Subscriptions ────────────────────────────────────────────────────────────

def add_subscription(tg_id: int, vpn_user: str, plan: str, days: int):
    expires = (datetime.utcnow() + timedelta(days=days)).isoformat()
    with _conn() as db:
        db.execute("""
            INSERT INTO subscriptions (tg_id, vpn_user, plan, expires_at)
            VALUES (?, ?, ?, ?)
        """, (tg_id, vpn_user, plan, expires))


def get_active_sub(tg_id: int) -> dict | None:
    with _conn() as db:
        row = db.execute("""
            SELECT * FROM subscriptions WHERE tg_id=? AND status='active'
            ORDER BY expires_at DESC LIMIT 1
        """, (tg_id,)).fetchone()
        return dict(row) if row else None


def extend_or_add(tg_id: int, vpn_user: str, plan: str, days: int):
    """Продлевает активную подписку. Если нет — создаёт новую."""
    with _conn() as db:
        row = db.execute("""
            SELECT id, expires_at FROM subscriptions
            WHERE tg_id=? AND status='active'
            ORDER BY expires_at DESC LIMIT 1
        """, (tg_id,)).fetchone()
        if row:
            base = max(datetime.fromisoformat(row["expires_at"]), datetime.utcnow())
            new_exp = (base + timedelta(days=days)).isoformat()
            db.execute(
                "UPDATE subscriptions SET expires_at=?, plan=? WHERE id=?",
                (new_exp, plan, row["id"])
            )
        else:
            add_subscription(tg_id, vpn_user, plan, days)


def deactivate_expired():
    with _conn() as db:
        db.execute("""
            UPDATE subscriptions SET status='expired'
            WHERE status='active' AND expires_at < datetime('now')
        """)


def get_expiring(days_ahead: int) -> list[dict]:
    """Подписки, которые истекают через days_ahead дней (окно ±1 час)."""
    now    = datetime.utcnow()
    lo     = (now + timedelta(days=days_ahead, hours=-1)).isoformat()
    hi     = (now + timedelta(days=days_ahead)).isoformat()
    col    = {3: "notif_3d", 1: "notif_1d", 0: "notif_exp"}.get(days_ahead, "notif_dead")
    query  = f"SELECT * FROM subscriptions WHERE status='active' AND {col}=0 AND expires_at BETWEEN ? AND ?"
    with _conn() as db:
        return [dict(r) for r in db.execute(query, (lo, hi)).fetchall()]


def get_dead_subs() -> list[dict]:
    """Истекшие 3 дня назад, ещё не уведомлённые (реактивация)."""
    now = datetime.utcnow()
    lo  = (now - timedelta(days=3, hours=1)).isoformat()
    hi  = (now - timedelta(days=3)).isoformat()
    with _conn() as db:
        return [dict(r) for r in db.execute("""
            SELECT * FROM subscriptions WHERE status='expired'
            AND notif_dead=0 AND expires_at BETWEEN ? AND ?
        """, (lo, hi)).fetchall()]


def mark_notified(sub_id: int, col: str):
    with _conn() as db:
        db.execute(f"UPDATE subscriptions SET {col}=1 WHERE id=?", (sub_id,))


def active_count() -> int:
    with _conn() as db:
        return db.execute("SELECT COUNT(*) FROM subscriptions WHERE status='active'").fetchone()[0]


# ─── Payments ─────────────────────────────────────────────────────────────────

def add_payment(tg_id: int, invoice_id: str, method: str, plan: str,
                amount_rub: float = 0, amount_usdt: float = 0):
    with _conn() as db:
        db.execute("""
            INSERT OR IGNORE INTO payments
                (tg_id, invoice_id, method, plan, amount_rub, amount_usdt)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tg_id, invoice_id, method, plan, amount_rub, amount_usdt))


def get_pending() -> list[dict]:
    with _conn() as db:
        return [dict(r) for r in db.execute("""
            SELECT * FROM payments WHERE status='pending'
            AND created_at > datetime('now', '-1 hour')
        """).fetchall()]


def mark_paid(invoice_id: str):
    with _conn() as db:
        db.execute("""
            UPDATE payments SET status='paid', paid_at=datetime('now')
            WHERE invoice_id=?
        """, (invoice_id,))
        return db.execute(
            "SELECT tg_id, plan FROM payments WHERE invoice_id=?", (invoice_id,)
        ).fetchone()


def mark_expired_payments():
    with _conn() as db:
        db.execute("""
            UPDATE payments SET status='expired'
            WHERE status='pending' AND created_at < datetime('now', '-1 hour')
        """)


def revenue() -> float:
    with _conn() as db:
        return db.execute(
            "SELECT COALESCE(SUM(amount_rub),0) FROM payments WHERE status='paid'"
        ).fetchone()[0]


def paid_count() -> int:
    with _conn() as db:
        return db.execute("SELECT COUNT(*) FROM payments WHERE status='paid'").fetchone()[0]


def today_revenue() -> float:
    with _conn() as db:
        return db.execute("""
            SELECT COALESCE(SUM(amount_rub),0) FROM payments
            WHERE status='paid' AND paid_at >= date('now')
        """).fetchone()[0]


# ─── Referrals ────────────────────────────────────────────────────────────────

def add_referral(referrer_id: int, referred_id: int):
    if referrer_id == referred_id:
        return
    with _conn() as db:
        db.execute("""
            INSERT OR IGNORE INTO referrals (referrer_id, referred_id)
            VALUES (?, ?)
        """, (referrer_id, referred_id))


def try_give_bonus(referrer_id: int, referred_id: int) -> bool:
    """Отдаёт бонус рефереру при первой оплате реферала. Возвращает True если выдан."""
    with _conn() as db:
        row = db.execute("""
            SELECT rowid FROM referrals
            WHERE referrer_id=? AND referred_id=? AND bonus_given=0
        """, (referrer_id, referred_id)).fetchone()
        if not row:
            return False
        db.execute("UPDATE referrals SET bonus_given=1 WHERE rowid=?", (row[0],))
        return True


def ref_count(tg_id: int) -> int:
    with _conn() as db:
        return db.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (tg_id,)
        ).fetchone()[0]


def get_referrer(tg_id: int) -> int | None:
    with _conn() as db:
        row = db.execute(
            "SELECT referrer_id FROM referrals WHERE referred_id=?", (tg_id,)
        ).fetchone()
        return row["referrer_id"] if row else None


# ─── Rate Limit ───────────────────────────────────────────────────────────────

def can_invoice(tg_id: int, cooldown: int = 600) -> bool:
    with _conn() as db:
        row = db.execute("SELECT last_invoice FROM rate_limits WHERE tg_id=?", (tg_id,)).fetchone()
        if not row:
            return True
        elapsed = (datetime.utcnow() - datetime.fromisoformat(row["last_invoice"])).total_seconds()
        return elapsed >= cooldown


def touch_rate(tg_id: int):
    with _conn() as db:
        db.execute("""
            INSERT INTO rate_limits(tg_id, last_invoice) VALUES(?, datetime('now'))
            ON CONFLICT(tg_id) DO UPDATE SET last_invoice=datetime('now')
        """, (tg_id,))
