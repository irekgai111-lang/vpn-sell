"""
VPN Sales Bot v2 — полная автоматизация продаж
Оплата: Telegram Stars + YooKassa (карты/СБП) + CryptoBot (USDT)
Функции: пробный период, промокоды, трафик в кабинете,
         напоминания, рефералы, антифрод, admin-команды.
"""
import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton as IKB, InlineKeyboardMarkup as IKM, LabeledPrice
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, PreCheckoutQueryHandler,
    MessageHandler, filters,
)

import db, marzban, payments, scheduler
from config import (
    BOT_TOKEN, BOT_USERNAME, ADMIN_IDS, PLANS, OLD_PRICES,
    RATE_LIMIT, REF_BONUS, TRIAL_DAYS, STARS_ENABLED, CHANNEL_ID,
)

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def is_admin(tg_id: int) -> bool:
    return tg_id in ADMIN_IDS


def main_kb(tg_id: int) -> IKM:
    user = db.get_user(tg_id)
    trial_ok = user and not user["trial_used"]
    sub = db.get_active_sub(tg_id)
    rows = []
    if trial_ok:
        rows.append([IKB("🎁 Попробовать 3 дня бесплатно", callback_data="trial")])
    if sub:
        rows.append([IKB("🔄 Продлить подписку", callback_data="buy")])
    else:
        rows.append([IKB("💳 Купить VPN", callback_data="buy")])
    rows += [
        [IKB("📊 Моя подписка", callback_data="mysub")],
        [IKB("👥 Пригласить друга  (+7 дней)", callback_data="ref")],
        [IKB("📱 Как подключить", callback_data="howto")],
        [IKB("💬 Поддержка", callback_data="support")],
    ]
    return IKM(rows)


def main_text(tg_id: int) -> str:
    sub = db.get_active_sub(tg_id)
    if sub:
        exp = datetime.fromisoformat(sub["expires_at"])
        days_left = (exp - datetime.utcnow()).days
        badge = f"🟢 Подписка активна ещё {days_left} дн."
    else:
        badge = "🔴 Нет активной подписки"

    return (
        f"🔐 <b>VPN — быстрый и надёжный</b>\n\n"
        f"{badge}\n\n"
        f"✅ VLESS Reality — не блокируется в России\n"
        f"✅ Все устройства: iOS, Android, Windows, Mac\n"
        f"✅ YouTube, Instagram, любые сайты без ограничений\n"
        f"✅ Ключ приходит автоматически после оплаты\n\n"
        f"Выбери действие:"
    )


def plan_text(plan_key: str) -> str:
    p    = PLANS[plan_key]
    old  = OLD_PRICES.get(plan_key, 0)
    save = old - p["rub"] if old else 0
    extra = f"  <s>{old}₽</s>  экономия {save}₽" if save else ""
    return f"{p['name']} — <b>{p['rub']}₽</b>{extra}"


def ref_link(tg_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref{tg_id}"


# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id      = update.effective_user.id
    username   = update.effective_user.username or ""
    first_name = update.effective_user.first_name or ""
    args       = ctx.args

    # Парсим реферала
    referrer_id = None
    if args and args[0].startswith("ref"):
        try:
            ref_val = int(args[0][3:])
            if ref_val != tg_id:
                referrer_id = ref_val
        except ValueError:
            pass

    user = db.get_user(tg_id)
    if not user:
        db.upsert_user(tg_id, username, first_name, referrer_id)
        if referrer_id:
            db.add_referral(referrer_id, tg_id)
    else:
        db.upsert_user(tg_id, username, first_name)

    await update.message.reply_html(main_text(tg_id), reply_markup=main_kb(tg_id))


# ─── Пробный период ───────────────────────────────────────────────────────────

async def cb_trial(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    tg_id  = query.from_user.id
    await query.answer()

    user = db.get_user(tg_id)
    if not user or user["trial_used"]:
        await query.answer("Пробный период уже использован.", show_alert=True)
        return

    try:
        user_data = marzban.create_user(tg_id, TRIAL_DAYS, 5)
        vpn_user  = user_data["username"]
        links     = marzban.get_links(vpn_user)
    except Exception as e:
        log.error(f"Trial Marzban error tg:{tg_id}: {e}")
        await query.edit_message_text("❌ Ошибка при создании пробного доступа. Попробуй позже.")
        return

    db.add_subscription(tg_id, vpn_user, "trial", TRIAL_DAYS)
    db.mark_trial_used(tg_id)

    links_text = "\n".join(f"<code>{l}</code>" for l in links) if links else "<i>Ключи генерируются...</i>"
    exp_date   = (datetime.utcnow() + timedelta(days=TRIAL_DAYS)).strftime("%d.%m.%Y")

    await query.edit_message_text(
        f"🎁 <b>3 дня бесплатного VPN активированы!</b>\n\n"
        f"Действует до: <b>{exp_date}</b>\n\n"
        f"<b>🔑 Твой ключ:</b>\n{links_text}\n\n"
        f"<b>Как подключить:</b>\n"
        f"• iOS/Mac → App Store: <b>Hiddify</b>\n"
        f"• Android → Google Play: <b>Hiddify</b>\n"
        f"• Windows → hiddify.com\n\n"
        f"В приложении: <b>+</b> → Добавить по ссылке → вставь ключ выше.",
        parse_mode="HTML",
        reply_markup=IKM([[IKB("⬅️ Главное меню", callback_data="back")]])
    )


# ─── Покупка ──────────────────────────────────────────────────────────────────

async def cb_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sub = db.get_active_sub(query.from_user.id)
    note = ""
    if sub:
        exp = datetime.fromisoformat(sub["expires_at"])
        note = f"Текущая подписка: до <b>{exp.strftime('%d.%m.%Y')}</b>. Срок прибавится к текущему.\n\n"

    rows = [[IKB(plan_text(k), callback_data=f"plan_{k}")] for k in PLANS if k != "trial"]
    rows.append([IKB("⬅️ Назад", callback_data="back")])

    await query.edit_message_text(
        f"💳 <b>Выбери тариф:</b>\n\n{note}"
        f"Все тарифы — безлимитный трафик, любое кол-во устройств.",
        parse_mode="HTML",
        reply_markup=IKM(rows)
    )


async def cb_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    tg_id    = query.from_user.id
    plan_key = query.data.replace("plan_", "")
    await query.answer()

    if not db.can_invoice(tg_id, RATE_LIMIT):
        await query.answer("Подожди немного перед созданием нового счёта.", show_alert=True)
        return

    plan = PLANS[plan_key]

    # Проверяем есть ли активный промокод в ctx (сохраняется через cb_promo)
    promo      = ctx.user_data.get("promo")
    disc_pct   = promo["discount_pct"] if promo else 0
    rub_final  = round(plan["rub"] * (1 - disc_pct / 100))
    usdt_final = round(plan["usdt"] * (1 - disc_pct / 100), 2)
    stars_final = round(plan["stars"] * (1 - disc_pct / 100))

    promo_note = f"\n🏷 Промокод <b>{promo['code']}</b>: скидка {disc_pct}%!" if promo else ""

    rows = []
    if STARS_ENABLED and plan["stars"]:
        rows.append([IKB(f"⭐ Telegram Stars — {stars_final} Stars", callback_data=f"pay_stars_{plan_key}")])
    rows.append([IKB(f"💳 Карта / СБП — {rub_final}₽", callback_data=f"pay_card_{plan_key}")])
    rows.append([IKB(f"🪙 USDT — {usdt_final} USDT", callback_data=f"pay_crypto_{plan_key}")])
    if not promo:
        rows.append([IKB("🏷 Есть промокод", callback_data=f"promo_{plan_key}")])
    rows.append([IKB("⬅️ Назад", callback_data="buy")])

    await query.edit_message_text(
        f"📦 <b>{plan['name']}</b>\n\n"
        f"Срок: {plan['days']} дней  |  Трафик: {'∞' if plan['gb'] > 999 else str(plan['gb'])+' ГБ'}"
        f"{promo_note}\n\n"
        f"Выбери способ оплаты:",
        parse_mode="HTML",
        reply_markup=IKM(rows)
    )


async def cb_pay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Карта (YooKassa) и крипта (CryptoBot)."""
    query    = update.callback_query
    tg_id    = query.from_user.id
    _, method, plan_key = query.data.split("_", 2)
    await query.answer()

    plan       = PLANS[plan_key]
    promo      = ctx.user_data.get("promo")
    disc_pct   = promo["discount_pct"] if promo else 0
    rub_final  = round(plan["rub"]  * (1 - disc_pct / 100))
    usdt_final = round(plan["usdt"] * (1 - disc_pct / 100), 2)

    try:
        if method == "crypto":
            inv = payments.crypto_create(usdt_final, f"VPN {plan['name']}")
        else:
            inv = payments.yk_create(rub_final, f"VPN {plan['name']}",
                                     return_url=f"https://t.me/{BOT_USERNAME}")
    except Exception as e:
        log.error(f"Create invoice tg:{tg_id} {method}: {e}")
        await query.edit_message_text(
            "❌ Не удалось создать счёт. Попробуй другой способ оплаты или /start"
        )
        return

    db.add_payment(tg_id, inv["invoice_id"], method, plan_key,
                   amount_rub=rub_final if method == "card" else 0,
                   amount_usdt=usdt_final if method == "crypto" else 0)
    db.touch_rate(tg_id)

    # Фиксируем промокод
    if promo:
        db.apply_promo(promo["code"], tg_id)
        ctx.user_data.pop("promo", None)

    label = f"{usdt_final} USDT" if method == "crypto" else f"{rub_final}₽"
    await query.edit_message_text(
        f"🧾 <b>Счёт создан</b>\n\n"
        f"Тариф: {plan['name']}\nСумма: <b>{label}</b>\n\n"
        f"1. Нажми «Оплатить»\n"
        f"2. Оплати в открывшемся окне\n"
        f"3. Нажми «Проверить оплату» — ключ придёт за 30 секунд.",
        parse_mode="HTML",
        reply_markup=IKM([
            [IKB(f"💳 Оплатить {label}", url=inv["pay_url"])],
            [IKB("✅ Проверить оплату", callback_data=f"chk_{inv['invoice_id']}_{method}")],
            [IKB("⬅️ Назад", callback_data="buy")],
        ])
    )


async def cb_pay_stars(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Telegram Stars — нативная оплата внутри Telegram."""
    query    = update.callback_query
    tg_id    = query.from_user.id
    plan_key = query.data.replace("pay_stars_", "")
    await query.answer()

    plan       = PLANS[plan_key]
    promo      = ctx.user_data.get("promo")
    disc_pct   = promo["discount_pct"] if promo else 0
    stars_final = max(1, round(plan["stars"] * (1 - disc_pct / 100)))

    if promo:
        db.apply_promo(promo["code"], tg_id)
        ctx.user_data.pop("promo", None)

    # Отправляем инвойс через нативный Telegram Stars
    await ctx.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=f"VPN — {plan['name']}",
        description="VLESS Reality VPN. Все устройства. Ключ придёт автоматически.",
        payload=f"stars|{plan_key}|{tg_id}",
        currency="XTR",
        prices=[LabeledPrice(plan["name"], stars_final)],
    )
    await query.edit_message_text(
        f"⭐ <b>Счёт на {stars_final} Stars</b>\n\nОплати в сообщении выше — ключ придёт автоматически.",
        parse_mode="HTML"
    )


async def pre_checkout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Подтверждаем любой Stars-платёж."""
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем Stars-платёж после успешного списания."""
    payload  = update.message.successful_payment.invoice_payload
    tg_id    = update.effective_user.id

    try:
        _, plan_key, _ = payload.split("|")
    except ValueError:
        return

    plan = PLANS.get(plan_key, {})
    days = plan.get("days", 30)
    gb   = plan.get("gb", 100)
    stars = update.message.successful_payment.total_amount

    # Записываем платёж (Stars → рублёвый эквивалент ~0.7₽/Stars)
    inv_id = f"stars_{tg_id}_{update.message.message_id}"
    db.add_payment(tg_id, inv_id, "stars", plan_key,
                   amount_rub=round(stars * 0.7), amount_usdt=0)
    db.mark_paid(inv_id)

    # Создаём/продлеваем VPN
    try:
        sub = db.get_active_sub(tg_id)
        if sub:
            new_exp = max(datetime.fromisoformat(sub["expires_at"]),
                          datetime.utcnow()) + timedelta(days=days)
            marzban.set_expire(sub["vpn_user"], new_exp)
            db.extend_or_add(tg_id, sub["vpn_user"], plan_key, days)
            vpn_user = sub["vpn_user"]
        else:
            data     = marzban.create_user(tg_id, days, gb)
            vpn_user = data["username"]
            db.add_subscription(tg_id, vpn_user, plan_key, days)
    except Exception as e:
        log.error(f"Stars Marzban error tg:{tg_id}: {e}")
        await update.message.reply_html(
            "✅ Оплата получена! Ключ генерируется, пришлём через минуту."
        )
        return

    links     = marzban.get_links(vpn_user)
    links_txt = "\n".join(f"<code>{l}</code>" for l in links)
    exp_date  = (datetime.utcnow() + timedelta(days=days)).strftime("%d.%m.%Y")

    await update.message.reply_html(
        f"✅ <b>VPN активирован!</b>\n\n"
        f"Тариф: {plan.get('name', plan_key)}  |  До: <b>{exp_date}</b>\n\n"
        f"<b>🔑 Ключ:</b>\n{links_txt}\n\n"
        f"Hiddify: + → Добавить по ссылке → вставь ключ."
    )

    # Реферальный бонус
    referrer_id = db.get_referrer(tg_id)
    if referrer_id and db.try_give_bonus(referrer_id, tg_id):
        try:
            await ctx.bot.send_message(
                referrer_id,
                f"🎁 <b>+{REF_BONUS} дней!</b> Твой друг оплатил подписку.",
                parse_mode="HTML"
            )
        except Exception:
            pass

    # Пост в канал
    if CHANNEL_ID:
        try:
            await ctx.bot.send_message(
                CHANNEL_ID,
                f"💚 Новая продажа — {plan.get('name', plan_key)} (Stars)"
            )
        except Exception:
            pass

    if ADMIN_IDS:
        await ctx.bot.send_message(
            ADMIN_IDS[0],
            f"💚 Stars-продажа! tg:{tg_id} | {plan.get('name')} | ⭐{stars}"
        )


async def cb_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Проверяю...")
    _, invoice_id, method = query.data.split("_", 2)  # chk_XXXXX_card

    try:
        paid = payments.check_payment(method, invoice_id)
    except Exception as e:
        log.warning(f"Manual check error: {e}")
        await query.answer("Ошибка проверки. Подожди и попробуй снова.", show_alert=True)
        return

    if paid:
        await query.edit_message_text(
            "✅ Оплата получена! Создаём VPN-ключ — пришлём через несколько секунд.",
            reply_markup=IKM([[IKB("⬅️ Главное меню", callback_data="back")]])
        )
        # scheduler сам обработает через 30 секунд, но можно форсировать:
        await scheduler.check_payments(ctx.bot)
    else:
        await query.answer("Оплата ещё не поступила. Подожди и попробуй снова.", show_alert=True)


# ─── Кабинет клиента ──────────────────────────────────────────────────────────

async def cb_mysub(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tg_id = query.from_user.id
    await query.answer()

    sub = db.get_active_sub(tg_id)
    if not sub:
        await query.edit_message_text(
            "❌ <b>Активной подписки нет.</b>\n\nКупи VPN или активируй пробный период.",
            parse_mode="HTML",
            reply_markup=IKM([
                [IKB("💳 Купить VPN", callback_data="buy")],
                [IKB("⬅️ Назад", callback_data="back")],
            ])
        )
        return

    exp       = datetime.fromisoformat(sub["expires_at"])
    days_left = max(0, (exp - datetime.utcnow()).days)

    try:
        links      = marzban.get_links(sub["vpn_user"])
        links_text = "\n".join(f"<code>{l}</code>" for l in links)
        traffic    = marzban.get_traffic(sub["vpn_user"])
        used_gb    = traffic.get("used_gb", 0)
        limit_gb   = traffic.get("limit_gb", 0)
        if limit_gb:
            traffic_line = f"📶 Трафик: <b>{used_gb} ГБ</b> из {limit_gb} ГБ использовано"
        else:
            traffic_line = f"📶 Трафик: <b>{used_gb} ГБ</b> использовано (безлимит)"
    except Exception:
        links_text   = "<i>Ошибка загрузки ключа. Обратись в поддержку.</i>"
        traffic_line = ""

    await query.edit_message_text(
        f"📊 <b>Моя подписка</b>\n\n"
        f"Тариф: {PLANS.get(sub['plan'], {}).get('name', sub['plan'])}\n"
        f"Истекает: <b>{exp.strftime('%d.%m.%Y')}</b> (осталось {days_left} дн.)\n"
        f"{traffic_line}\n\n"
        f"<b>🔑 Ключ:</b>\n{links_text}",
        parse_mode="HTML",
        reply_markup=IKM([
            [IKB("🔄 Продлить", callback_data="buy")],
            [IKB("⬅️ Назад", callback_data="back")],
        ])
    )


# ─── Рефералы ─────────────────────────────────────────────────────────────────

async def cb_ref(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tg_id = query.from_user.id
    await query.answer()
    count = db.ref_count(tg_id)
    link  = ref_link(tg_id)
    await query.edit_message_text(
        f"👥 <b>Реферальная программа</b>\n\n"
        f"Приглашай друзей — получай <b>+{REF_BONUS} дней</b> бесплатно за каждого!\n\n"
        f"Твоя ссылка:\n<code>{link}</code>\n\n"
        f"Приглашено: <b>{count}</b> чел.\n"
        f"Заработано дней: <b>{count * REF_BONUS}</b> дн.\n\n"
        f"Бонус начисляется когда друг оплачивает первую подписку.",
        parse_mode="HTML",
        reply_markup=IKM([[IKB("⬅️ Назад", callback_data="back")]])
    )


# ─── Инструкция подключения ───────────────────────────────────────────────────

async def cb_howto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📱 <b>Как подключить VPN</b>\n\n"
        "<b>Шаг 1 — Скачай Hiddify</b>\n"
        "• iPhone / Mac → App Store: <b>Hiddify</b>\n"
        "• Android → Google Play: <b>Hiddify</b>\n"
        "• Windows → hiddify.com → Download\n\n"
        "<b>Шаг 2 — Добавь ключ</b>\n"
        "Открой Hiddify → нажми <b>+</b> → «Добавить по ссылке» → вставь свой ключ из раздела «Моя подписка»\n\n"
        "<b>Шаг 3 — Включи VPN</b>\n"
        "Переключи тумблер → готово!\n\n"
        "🟢 <b>VLESS Reality</b> — работает даже там, где другие VPN заблокированы.",
        parse_mode="HTML",
        reply_markup=IKM([[IKB("⬅️ Назад", callback_data="back")]])
    )


async def cb_support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💬 <b>Поддержка</b>\n\n"
        f"Напиши своё имя и проблему — ответим в течение часа.\n"
        f"Твой ID: <code>{query.from_user.id}</code>",
        parse_mode="HTML",
        reply_markup=IKM([[IKB("⬅️ Назад", callback_data="back")]])
    )


async def cb_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tg_id = query.from_user.id
    await query.answer()
    await query.edit_message_text(
        main_text(tg_id), parse_mode="HTML", reply_markup=main_kb(tg_id)
    )


# ─── Промокоды ───────────────────────────────────────────────────────────────

async def cb_promo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Кнопка «Есть промокод» — просит ввести код."""
    query    = update.callback_query
    plan_key = query.data.replace("promo_", "")
    await query.answer()
    ctx.user_data["awaiting_promo_plan"] = plan_key
    await query.edit_message_text(
        "🏷 <b>Введи промокод</b>\n\nНапечатай код и отправь сообщением:",
        parse_mode="HTML",
        reply_markup=IKM([[IKB("⬅️ Отмена", callback_data=f"plan_{plan_key}")]])
    )


async def handle_promo_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Принимает текстовый ввод промокода."""
    plan_key = ctx.user_data.get("awaiting_promo_plan")
    if not plan_key:
        return

    code  = update.message.text.strip().upper()
    tg_id = update.effective_user.id
    promo = db.check_promo(code, tg_id)

    if not promo:
        await update.message.reply_html(
            "❌ Промокод не найден или уже использован.\n\n"
            f"Продолжить без скидки → нажми /start → Купить VPN"
        )
        ctx.user_data.pop("awaiting_promo_plan", None)
        return

    ctx.user_data["promo"] = {"code": code, "discount_pct": promo["discount_pct"]}
    ctx.user_data.pop("awaiting_promo_plan", None)

    await update.message.reply_html(
        f"✅ Промокод <b>{code}</b> активирован — скидка <b>{promo['discount_pct']}%</b>!\n\n"
        f"Возврат к выбору тарифа:",
        reply_markup=IKM([[IKB("← Выбрать тариф", callback_data=f"plan_{plan_key}")]])
    )


# ─── Команды администратора ───────────────────────────────────────────────────

async def cmd_stat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    s = db.get_stats() if hasattr(db, "get_stats") else {}

    users    = db.total_users()
    active   = db.active_count()
    paid     = db.paid_count()
    rev      = db.revenue()
    rev_today = db.today_revenue()

    await update.message.reply_html(
        f"📊 <b>Статистика VPN-бота</b>\n\n"
        f"👤 Пользователей: <b>{users}</b>\n"
        f"🟢 Активных подписок: <b>{active}</b>\n"
        f"💳 Всего продаж: <b>{paid}</b>\n"
        f"💰 Общая выручка: <b>{rev:.0f}₽</b>\n"
        f"📅 Сегодня: <b>{rev_today:.0f}₽</b>"
    )


async def cmd_adddays(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Добавить дни подписке: /adddays <tg_id> <days>"""
    if not is_admin(update.effective_user.id):
        return
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Формат: /adddays <tg_id> <days>")
        return
    try:
        target_id = int(args[0])
        days      = int(args[1])
    except ValueError:
        await update.message.reply_text("Неверный формат чисел.")
        return

    sub = db.get_active_sub(target_id)
    if sub:
        new_exp = datetime.fromisoformat(sub["expires_at"]) + timedelta(days=days)
        try:
            marzban.set_expire(sub["vpn_user"], new_exp)
        except Exception:
            pass
        db.extend_or_add(target_id, sub["vpn_user"], sub["plan"], days)
    else:
        await update.message.reply_text(f"У tg:{target_id} нет активной подписки.")
        return

    try:
        await ctx.bot.send_message(
            target_id,
            f"🎁 <b>Администратор добавил вам +{days} дней VPN!</b>\n\nПриятного использования.",
            parse_mode="HTML"
        )
    except Exception:
        pass
    await update.message.reply_text(f"✅ Добавлено {days} дней для tg:{target_id}")


async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Рассылка: /broadcast <текст>"""
    if not is_admin(update.effective_user.id):
        return
    text = " ".join(ctx.args)
    if not text:
        await update.message.reply_text("Формат: /broadcast <текст>")
        return

    with db._conn() as dbc:
        rows = dbc.execute("SELECT tg_id FROM users").fetchall()

    ok = 0
    for row in rows:
        try:
            await ctx.bot.send_message(row["tg_id"], text, parse_mode="HTML")
            ok += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Отправлено {ok}/{len(rows)}")


async def cmd_promo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/promo CODE DISCOUNT_PCT [USES] — создать промокод. USES=-1 безлимит."""
    if not is_admin(update.effective_user.id):
        return
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Формат: /promo КОД СКИДКА_% [КОЛ-ВО_ИСПОЛЬЗОВАНИЙ]\nПример: /promo SUPER20 20 100")
        return
    code     = args[0].upper()
    try:
        disc = int(args[1])
        uses = int(args[2]) if len(args) > 2 else -1
    except ValueError:
        await update.message.reply_text("СКИДКА и КОЛ-ВО должны быть числами.")
        return
    db.create_promo(code, disc, uses)
    uses_label = "∞" if uses == -1 else str(uses)
    await update.message.reply_html(
        f"✅ Промокод создан:\n"
        f"Код: <code>{code}</code>\n"
        f"Скидка: <b>{disc}%</b>\n"
        f"Использований: <b>{uses_label}</b>"
    )


# ─── Запуск ───────────────────────────────────────────────────────────────────

async def on_startup(app):
    db.init()
    scheduler.start(app.bot)
    log.info("Bot started")


def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не задан в .env")
        return

    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    # Команды
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("stat",      cmd_stat))
    app.add_handler(CommandHandler("adddays",   cmd_adddays))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("promo",     cmd_promo))

    # Telegram Stars
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    # Промокод — текстовый ввод (до общего текст-хендлера)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_promo_text
    ))

    # Кнопки
    app.add_handler(CallbackQueryHandler(cb_trial,      pattern="^trial$"))
    app.add_handler(CallbackQueryHandler(cb_buy,        pattern="^buy$"))
    app.add_handler(CallbackQueryHandler(cb_plan,       pattern="^plan_"))
    app.add_handler(CallbackQueryHandler(cb_pay,        pattern="^pay_(?!stars)"))
    app.add_handler(CallbackQueryHandler(cb_pay_stars,  pattern="^pay_stars_"))
    app.add_handler(CallbackQueryHandler(cb_check,      pattern="^chk_"))
    app.add_handler(CallbackQueryHandler(cb_promo,      pattern="^promo_"))
    app.add_handler(CallbackQueryHandler(cb_mysub,      pattern="^mysub$"))
    app.add_handler(CallbackQueryHandler(cb_ref,        pattern="^ref$"))
    app.add_handler(CallbackQueryHandler(cb_howto,  pattern="^howto$"))
    app.add_handler(CallbackQueryHandler(cb_support,pattern="^support$"))
    app.add_handler(CallbackQueryHandler(cb_back,   pattern="^back$"))

    log.info("VPN Sales Bot запущен")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
