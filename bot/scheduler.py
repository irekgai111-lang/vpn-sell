"""
Фоновые задачи (запускаются внутри процесса бота):
  • check_payments — каждые 30 сек, закрывает оплаченные инвойсы
  • send_reminders — каждые 30 мин, уведомляет об истечении подписок
  • cleanup        — каждый час, деактивирует истёкшие подписки
"""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot

import db, marzban, payments
from config import PLANS, ADMIN_IDS, REF_BONUS

log = logging.getLogger(__name__)


async def _deliver_key(bot: Bot, tg_id: int, vpn_user: str, plan_key: str):
    """Отправляет VPN-ключ клиенту после оплаты."""
    try:
        links = marzban.get_links(vpn_user)
    except Exception as e:
        log.error(f"get_links failed for {vpn_user}: {e}")
        links = []

    plan = PLANS.get(plan_key, {})
    expire_date = (datetime.utcnow() + timedelta(days=plan.get("days", 30))).strftime("%d.%m.%Y")
    links_text = "\n".join(f"<code>{l}</code>" for l in links) if links else "<i>Ключи появятся в течение минуты</i>"

    text = (
        f"✅ <b>Оплата принята! VPN активирован.</b>\n\n"
        f"Тариф: {plan.get('name', plan_key)}\n"
        f"Действует до: <b>{expire_date}</b>\n\n"
        f"<b>🔑 Твой VPN-ключ:</b>\n{links_text}\n\n"
        f"<b>Как подключить:</b>\n"
        f"• iOS / Mac → App Store: <b>Hiddify</b>\n"
        f"• Android → Google Play: <b>Hiddify</b>\n"
        f"• Windows → hiddify.com → Download\n\n"
        f"В приложении: <b>+</b> → Добавить по ссылке → вставь ключ.\n\n"
        f"Вопросы — жми /start → Поддержка 💬"
    )
    await bot.send_message(tg_id, text, parse_mode="HTML")


async def check_payments(bot: Bot):
    """Проверяет все pending-инвойсы, выдаёт ключи оплатившим."""
    pending = db.get_pending()
    if not pending:
        return

    for pay in pending:
        try:
            paid = payments.check_payment(pay["method"], pay["invoice_id"])
        except Exception as e:
            log.warning(f"check_payment error {pay['invoice_id']}: {e}")
            continue

        if not paid:
            continue

        # Фиксируем оплату
        db.mark_paid(pay["invoice_id"])
        tg_id    = pay["tg_id"]
        plan_key = pay["plan"]
        plan     = PLANS.get(plan_key, {})
        days     = plan.get("days", 30)
        gb       = plan.get("gb", 100)

        # Создаём или продлеваем пользователя в Marzban
        try:
            sub = db.get_active_sub(tg_id)
            if sub:
                # Продление: обновляем дату в Marzban и БД
                vpn_user = sub["vpn_user"]
                active_exp = datetime.fromisoformat(sub["expires_at"])
                new_exp = max(active_exp, datetime.utcnow()) + timedelta(days=days)
                marzban.set_expire(vpn_user, new_exp)
                db.extend_or_add(tg_id, vpn_user, plan_key, days)
            else:
                # Новый пользователь
                user_data = marzban.create_user(tg_id, days, gb)
                vpn_user  = user_data["username"]
                db.add_subscription(tg_id, vpn_user, plan_key, days)
        except Exception as e:
            log.error(f"Marzban error for tg:{tg_id}: {e}")
            await bot.send_message(
                tg_id,
                "✅ Оплата получена! Ключ генерируется — пришлём через минуту.\n"
                "Если не пришёл через 5 минут — напишите в поддержку /start"
            )
            if ADMIN_IDS:
                await bot.send_message(ADMIN_IDS[0], f"⚠️ Marzban ошибка tg:{tg_id} план:{plan_key}\n{e}")
            continue

        # Отдаём ключ клиенту
        await _deliver_key(bot, tg_id, vpn_user, plan_key)

        # Реферальный бонус рефереру
        referrer_id = db.get_referrer(tg_id)
        if referrer_id and db.try_give_bonus(referrer_id, tg_id):
            db.extend_or_add(referrer_id, "", "bonus", REF_BONUS)
            ref_sub = db.get_active_sub(referrer_id)
            if ref_sub:
                try:
                    new_exp = datetime.fromisoformat(ref_sub["expires_at"]) + timedelta(days=REF_BONUS)
                    marzban.set_expire(ref_sub["vpn_user"], new_exp)
                except Exception:
                    pass
            try:
                await bot.send_message(
                    referrer_id,
                    f"🎁 <b>+{REF_BONUS} дней бесплатно!</b>\n\n"
                    f"Твой реферал оплатил подписку — бонус начислен.",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        # Уведомление админу
        if ADMIN_IDS:
            method_label = "💳 Карта" if pay["method"] == "card" else "🪙 Крипта"
            await bot.send_message(
                ADMIN_IDS[0],
                f"💚 Продажа!\n"
                f"tg:{tg_id} | {plan.get('name', plan_key)} | "
                f"+{plan.get('rub', 0)}₽ {method_label}"
            )

    db.mark_expired_payments()


async def send_reminders(bot: Bot):
    """Уведомления об истечении подписки: за 3д, 1д, в день X, и реактивация через 3д."""
    for days_left in [3, 1, 0]:
        col = {3: "notif_3d", 1: "notif_1d", 0: "notif_exp"}[days_left]
        for sub in db.get_expiring(days_left):
            try:
                if days_left == 0:
                    text = (
                        "⏰ <b>Подписка истекла сегодня.</b>\n\n"
                        "Чтобы не потерять VPN — продли прямо сейчас.\n"
                        "Кнопка <b>Продлить</b> → /start"
                    )
                elif days_left == 1:
                    text = (
                        "⚠️ <b>Завтра истекает VPN-подписка.</b>\n\n"
                        "Продли сегодня, чтобы не осталось без VPN.\n"
                        "/start → Продлить подписку"
                    )
                else:
                    text = (
                        "📅 <b>Подписка истекает через 3 дня.</b>\n\n"
                        "Можешь продлить заранее — срок прибавится к текущему.\n"
                        "/start → Продлить подписку"
                    )
                await bot.send_message(sub["tg_id"], text, parse_mode="HTML")
                db.mark_notified(sub["id"], col)
            except Exception as e:
                log.warning(f"Reminder error tg:{sub['tg_id']}: {e}")

    # Реактивация (через 3 дня после истечения)
    for sub in db.get_dead_subs():
        try:
            await bot.send_message(
                sub["tg_id"],
                "🔒 <b>Эй, VPN не работает уже 3 дня.</b>\n\n"
                "Возможно, ты просто забыл продлить?\n"
                "Восстанови доступ за 2 минуты → /start",
                parse_mode="HTML"
            )
            db.mark_notified(sub["id"], "notif_dead")
        except Exception:
            pass


async def cleanup(bot: Bot):
    db.deactivate_expired()


def start(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_payments, "interval", seconds=30,  args=[bot], id="check_pay")
    scheduler.add_job(send_reminders, "interval", minutes=30,  args=[bot], id="reminders")
    scheduler.add_job(cleanup,        "interval", hours=1,     args=[bot], id="cleanup")
    scheduler.start()
    log.info("Scheduler started")
    return scheduler
