"""
VPN Sales Bot — автоматические продажи VPN через Telegram
Стек: python-telegram-bot + Marzban API + CryptoBot
"""
import os, asyncio, uuid, logging, json
from datetime import datetime, timedelta
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          ContextTypes, MessageHandler, filters)

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ─── Конфиг из окружения ────────────────────────────────────────────────────
BOT_TOKEN      = os.getenv("BOT_TOKEN", "")
MARZBAN_URL    = os.getenv("MARZBAN_URL", "http://localhost:8000")
MARZBAN_USER   = os.getenv("MARZBAN_USER", "admin")
MARZBAN_PASS   = os.getenv("MARZBAN_PASS", "")
ADMIN_ID       = int(os.getenv("ADMIN_ID", "0"))
CRYPTO_TOKEN   = os.getenv("CRYPTO_TOKEN", "")       # токен @CryptoBot
INBOUND_TAG    = os.getenv("INBOUND_TAG", "vless-in") # название inbound в Marzban

# ─── Тарифы ─────────────────────────────────────────────────────────────────
PLANS = {
    "1m":  {"name": "1 месяц",    "price_rub": 149,  "price_usdt": 1.65, "days": 30,  "gb": 100},
    "3m":  {"name": "3 месяца",   "price_rub": 399,  "price_usdt": 4.40, "days": 90,  "gb": 300},
    "6m":  {"name": "6 месяцев",  "price_rub": 699,  "price_usdt": 7.70, "days": 180, "gb": 999},
    "12m": {"name": "1 год",      "price_rub": 1199, "price_usdt": 13.2, "days": 365, "gb": 9999},
}

# ─── Marzban API ─────────────────────────────────────────────────────────────
def marzban_token() -> str:
    r = requests.post(f"{MARZBAN_URL}/api/admin/token",
                      data={"username": MARZBAN_USER, "password": MARZBAN_PASS},
                      timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]

def create_user(plan_key: str, tg_id: int) -> dict:
    token = marzban_token()
    plan  = PLANS[plan_key]
    uname = f"tg_{tg_id}_{uuid.uuid4().hex[:6]}"
    expire = int((datetime.utcnow() + timedelta(days=plan["days"])).timestamp())
    payload = {
        "username": uname,
        "proxies": {"vless": {"flow": "xtls-rprx-vision"}},
        "inbounds": {"vless": [INBOUND_TAG]},
        "data_limit": plan["gb"] * 1_073_741_824,
        "data_limit_reset_strategy": "no_reset",
        "expire": expire,
        "note": f"tg:{tg_id} plan:{plan_key}",
    }
    r = requests.post(f"{MARZBAN_URL}/api/user", json=payload,
                      headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    return r.json()

def get_user_links(username: str) -> list[str]:
    token = marzban_token()
    r = requests.get(f"{MARZBAN_URL}/api/user/{username}",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    data  = r.json()
    links = data.get("links", [])
    return links

# ─── CryptoBot Invoice ────────────────────────────────────────────────────────
def create_invoice(amount_usdt: float, payload: str) -> dict:
    """Создаёт инвойс в @CryptoBot, возвращает {"pay_url": ..., "invoice_id": ...}"""
    url = "https://pay.crypt.bot/api/createInvoice"
    body = {
        "asset": "USDT",
        "amount": round(amount_usdt, 2),
        "description": "VPN подписка",
        "payload": payload,
        "allow_comments": False,
        "allow_anonymous": False,
        "expires_in": 3600,
    }
    headers = {"Crypto-Pay-API-Token": CRYPTO_TOKEN}
    r = requests.post(url, json=body, headers=headers, timeout=10)
    r.raise_for_status()
    result = r.json()["result"]
    return {"pay_url": result["pay_url"], "invoice_id": result["invoice_id"]}

def check_invoice(invoice_id: int) -> bool:
    """Проверяет оплачен ли инвойс."""
    url = f"https://pay.crypt.bot/api/getInvoices?invoice_ids={invoice_id}"
    headers = {"Crypto-Pay-API-Token": CRYPTO_TOKEN}
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    items = r.json()["result"]["items"]
    if not items:
        return False
    return items[0]["status"] == "paid"

# ─── Хранилище ожидающих оплат (в памяти — для прода используй Redis/SQLite) ─
pending_payments: dict[str, dict] = {}  # invoice_id → {tg_id, plan_key, chat_id}

# ─── Тексты ──────────────────────────────────────────────────────────────────
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Купить VPN",     callback_data="buy")],
        [InlineKeyboardButton("📊 Мой аккаунт",    callback_data="account")],
        [InlineKeyboardButton("📱 Как подключить", callback_data="howto")],
        [InlineKeyboardButton("💬 Поддержка",      callback_data="support")],
    ])

MAIN_TEXT = (
    "🔐 <b>VPN — быстрый и надёжный</b>\n\n"
    "✅ Протокол VLESS Reality — не блокируется в России\n"
    "✅ Все устройства: iOS, Android, Windows, Mac\n"
    "✅ Без ограничений — YouTube, Instagram, любые сайты\n"
    "✅ Ключ получаешь сразу после оплаты\n\n"
    "Выбери действие:"
)

# ─── Хендлеры ────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(MAIN_TEXT, reply_markup=main_kb())

async def cb_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = []
    for k, p in PLANS.items():
        label = f"{p['name']} — {p['price_rub']}₽ (~{p['price_usdt']} USDT)"
        kb.append([InlineKeyboardButton(label, callback_data=f"plan_{k}")])
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="back")])
    await query.edit_message_text(
        "💳 <b>Выбери тариф:</b>\n\nОплата в USDT через @CryptoBot.\nКлюч придёт автоматически через 30 секунд после оплаты.",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb)
    )

async def cb_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_key = query.data.replace("plan_", "")
    plan     = PLANS[plan_key]
    tg_id    = query.from_user.id

    # Создаём инвойс CryptoBot
    try:
        inv_payload = json.dumps({"tg_id": tg_id, "plan": plan_key})
        invoice = create_invoice(plan["price_usdt"], inv_payload)
    except Exception as e:
        log.error(f"Invoice error: {e}")
        await query.edit_message_text("❌ Ошибка создания счёта. Напишите в поддержку.")
        return

    inv_id = str(invoice["invoice_id"])
    pending_payments[inv_id] = {
        "tg_id": tg_id,
        "plan_key": plan_key,
        "chat_id": query.message.chat_id,
        "msg_id": query.message.message_id,
    }

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💳 Оплатить {plan['price_usdt']} USDT", url=invoice["pay_url"])],
        [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{inv_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="buy")],
    ])
    await query.edit_message_text(
        f"📦 <b>{plan['name']}</b>\n\n"
        f"Сумма: <b>{plan['price_usdt']} USDT</b> (~{plan['price_rub']}₽)\n\n"
        "1. Нажми «Оплатить» — откроется @CryptoBot\n"
        "2. Оплати в боте\n"
        "3. Нажми «Проверить оплату»\n"
        "4. Получи VPN-ключ!",
        parse_mode="HTML", reply_markup=kb
    )

async def cb_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer("Проверяю оплату...")
    inv_id  = query.data.replace("check_", "")
    payment = pending_payments.get(inv_id)

    if not payment:
        await query.edit_message_text("❌ Счёт не найден. Обратитесь в поддержку.")
        return

    try:
        paid = check_invoice(int(inv_id))
    except Exception as e:
        log.error(f"Check invoice error: {e}")
        await query.answer("Ошибка проверки, попробуй снова.", show_alert=True)
        return

    if not paid:
        await query.answer("Оплата ещё не поступила. Подожди и проверь снова.", show_alert=True)
        return

    # Оплата прошла — создаём пользователя
    plan_key = payment["plan_key"]
    tg_id    = payment["tg_id"]
    try:
        user  = create_user(plan_key, tg_id)
        links = get_user_links(user["username"])
    except Exception as e:
        log.error(f"Create user error: {e}")
        await ctx.bot.send_message(
            payment["chat_id"],
            "✅ Оплата принята, но при создании ключа ошибка. Мы разберёмся и пришлём ключ вручную."
        )
        await ctx.bot.send_message(ADMIN_ID, f"⚠️ Ошибка создания VPN для tg:{tg_id} plan:{plan_key}\nError: {e}")
        return

    del pending_payments[inv_id]
    plan = PLANS[plan_key]

    links_text = "\n".join(f"<code>{l}</code>" for l in links) if links else "<i>Ожидай — ключ генерируется</i>"

    await ctx.bot.send_message(
        payment["chat_id"],
        f"✅ <b>Оплата принята! VPN готов.</b>\n\n"
        f"Тариф: {plan['name']}\n"
        f"Действует до: {(datetime.now() + timedelta(days=plan['days'])).strftime('%d.%m.%Y')}\n\n"
        f"<b>🔑 Твой VPN-ключ:</b>\n{links_text}\n\n"
        f"<b>Как подключить:</b>\n"
        f"• iOS/Mac: App Store → Hiddify или Streisand\n"
        f"• Android: Google Play → Hiddify\n"
        f"• Windows: github.com/hiddify/hiddify-app\n\n"
        f"В приложении: + → Добавить по ссылке → вставь ключ выше.\n\n"
        f"Если есть вопросы — нажми /start → Поддержка",
        parse_mode="HTML"
    )
    await ctx.bot.send_message(ADMIN_ID, f"💚 Новая продажа! tg:{tg_id} план:{plan_key} +{plan['price_rub']}₽")

async def cb_account(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📊 <b>Мой аккаунт</b>\n\nДля проверки статуса подписки напишите /start → Поддержка и укажите ваш Telegram ID:\n"
        f"<code>{query.from_user.id}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back")]])
    )

async def cb_howto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "📱 <b>Как подключить VPN</b>\n\n"
        "<b>1. Скачай Hiddify</b>\n"
        "• iPhone/Mac — App Store → Hiddify\n"
        "• Android — Google Play → Hiddify\n"
        "• Windows — hiddify.com → Download\n\n"
        "<b>2. Добавь VPN-ключ</b>\n"
        "Открой Hiddify → нажми + → «Добавить по ссылке» → вставь свой ключ\n\n"
        "<b>3. Включи VPN</b>\n"
        "Переключи тумблер в Hiddify → готово!\n\n"
        "🟢 VLESS Reality работает даже там, где другие VPN не работают."
    )
    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back")]])
    )

async def cb_support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💬 <b>Поддержка</b>\n\nОпиши проблему — помогу разобраться. Укажи свой Telegram ID:\n"
        f"<code>{query.from_user.id}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back")]])
    )

async def cb_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(MAIN_TEXT, parse_mode="HTML", reply_markup=main_kb())

# ─── Команды администратора ───────────────────────────────────────────────────
async def cmd_stat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        token = marzban_token()
        r = requests.get(f"{MARZBAN_URL}/api/users?limit=1000",
                         headers={"Authorization": f"Bearer {token}"}, timeout=10)
        data  = r.json()
        total = data.get("total", 0)
        active = sum(1 for u in data.get("users", []) if u.get("status") == "active")
        await update.message.reply_html(
            f"📊 <b>Статистика</b>\n\n"
            f"Всего пользователей: {total}\n"
            f"Активных: {active}\n"
            f"Ожидающих оплат: {len(pending_payments)}"
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

# ─── Запуск ───────────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не задан в .env")
        return
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stat",  cmd_stat))
    app.add_handler(CallbackQueryHandler(cb_buy,     pattern="^buy$"))
    app.add_handler(CallbackQueryHandler(cb_plan,    pattern="^plan_"))
    app.add_handler(CallbackQueryHandler(cb_check,   pattern="^check_"))
    app.add_handler(CallbackQueryHandler(cb_account, pattern="^account$"))
    app.add_handler(CallbackQueryHandler(cb_howto,   pattern="^howto$"))
    app.add_handler(CallbackQueryHandler(cb_support, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(cb_back,    pattern="^back$"))

    print("🤖 VPN-бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
