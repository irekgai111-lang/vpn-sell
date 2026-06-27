# VPN Business — автоматизированные продажи VPN

Полный комплект для запуска VPN-бизнеса на автопилоте.

## Что внутри

| Файл | Что делает |
|---|---|
| `guide.html` | Визуальный гид: анализ топ-3, экономика, шаги |
| `install-marzban.sh` | Установка Marzban VPN-панели на сервер |
| `bot/bot.py` | Telegram-бот для автопродаж VPN-ключей |
| `bot/env.example` | Шаблон переменных окружения |

## Стек

- **Marzban** — панель управления пользователями VPN
- **VLESS Reality** — протокол, не блокируется в РФ
- **python-telegram-bot** — Telegram-бот для продаж
- **@CryptoBot** — приём оплаты (USDT/TON/BTC)
- **Docker** — контейнеризация Marzban

## Быстрый старт

```bash
# На сервере (Ubuntu 22.04, root):
bash install-marzban.sh

# Настроить бота:
cp bot/bot.py /opt/vpn-bot/
cp bot/env.example /opt/vpn-bot/.env
nano /opt/vpn-bot/.env  # заполнить токены
systemctl start vpn-bot
```

## Экономика

- VPS: ~800 ₽/мес → 100 клиентов → ~12 000 ₽/мес чистыми
- Масштабирование: несколько серверов × N клиентов
