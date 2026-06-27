#!/bin/bash
# ============================================================
# VPN Business — Автоматическая проверка перед сдачей клиенту
# Запуск на сервере: bash check.sh
# ============================================================
R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;34m'; N='\033[0m'; BOLD='\033[1m'

PASS=0; FAIL=0; WARN=0
BOT_DIR="/opt/vpn-bot"
DB="$BOT_DIR/vpn.db"

ok()   { echo -e "  ${G}✓${N} $1"; ((PASS++)); }
fail() { echo -e "  ${R}✗${N} $1"; ((FAIL++)); }
warn() { echo -e "  ${Y}!${N} $1"; ((WARN++)); }
hdr()  { echo -e "\n${BOLD}${B}▸ $1${N}"; }

clear
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   VPN Business — Проверка перед сдачей  ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${N}"

# ────────────────────────────────────────────
hdr "1. Системные сервисы"
# ────────────────────────────────────────────

# Marzban
if docker ps 2>/dev/null | grep -q marzban; then
    ok "Marzban контейнер запущен"
elif systemctl is-active --quiet marzban 2>/dev/null; then
    ok "Marzban сервис активен"
else
    fail "Marzban НЕ запущен"
fi

# VPN-бот
if systemctl is-active --quiet vpn-bot 2>/dev/null; then
    ok "vpn-bot сервис активен"
    UPTIME=$(systemctl show vpn-bot --property=ActiveEnterTimestamp | cut -d= -f2)
    echo -e "     Запущен: $UPTIME"
else
    fail "vpn-bot НЕ запущен — проверь: journalctl -u vpn-bot -n 30"
fi

# Nginx
if systemctl is-active --quiet nginx 2>/dev/null; then
    ok "Nginx активен"
else
    warn "Nginx не запущен (необязательно если нет домена)"
fi

# Python-процесс бота
if pgrep -f "python3.*bot.py" > /dev/null; then
    ok "Python-процесс bot.py найден"
else
    fail "Python-процесс bot.py не найден"
fi

# ────────────────────────────────────────────
hdr "2. Конфигурация (.env)"
# ────────────────────────────────────────────

if [ -f "$BOT_DIR/.env" ]; then
    ok ".env файл существует"
    source "$BOT_DIR/.env" 2>/dev/null

    [ -n "$BOT_TOKEN" ]    && ok "BOT_TOKEN задан"    || fail "BOT_TOKEN пустой"
    [ -n "$MARZBAN_PASS" ] && ok "MARZBAN_PASS задан" || fail "MARZBAN_PASS пустой"
    [ -n "$ADMIN_IDS" ]    && ok "ADMIN_IDS задан"    || fail "ADMIN_IDS пустой"

    [ -n "$CRYPTO_TOKEN" ] && ok "CRYPTO_TOKEN задан (CryptoBot)" || warn "CRYPTO_TOKEN пустой — оплата криптой недоступна"
    [ -n "$YK_SHOP_ID" ]   && ok "YK_SHOP_ID задан (YooKassa)"   || warn "YK_SHOP_ID пустой — карты недоступны"
    [ "$STARS_ENABLED" = "true" ] && ok "Telegram Stars включён" || warn "Telegram Stars выключен (STARS_ENABLED=false)"
else
    fail ".env файл не найден в $BOT_DIR"
fi

# ────────────────────────────────────────────
hdr "3. База данных"
# ────────────────────────────────────────────

if [ -f "$DB" ]; then
    ok "База данных существует: $DB"
    SIZE=$(du -sh "$DB" | cut -f1)
    echo -e "     Размер: $SIZE"

    USERS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM users;" 2>/dev/null || echo "0")
    SUBS=$(sqlite3  "$DB" "SELECT COUNT(*) FROM subscriptions WHERE status='active';" 2>/dev/null || echo "0")
    PAID=$(sqlite3  "$DB" "SELECT COUNT(*) FROM payments WHERE status='paid';" 2>/dev/null || echo "0")
    REV=$(sqlite3   "$DB" "SELECT COALESCE(ROUND(SUM(amount_rub)),0) FROM payments WHERE status='paid';" 2>/dev/null || echo "0")

    ok "Таблицы доступны (пользователей: $USERS, подписок: $SUBS, продаж: $PAID, выручка: ${REV}₽)"
else
    warn "База данных ещё не создана (создастся при первом запуске бота)"
fi

# ────────────────────────────────────────────
hdr "4. Marzban API"
# ────────────────────────────────────────────

source "$BOT_DIR/.env" 2>/dev/null
MARZ_URL="${MARZBAN_URL:-http://localhost:8000}"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$MARZ_URL/api/docs" --max-time 5 2>/dev/null)
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ]; then
    ok "Marzban API отвечает ($MARZ_URL)"
else
    fail "Marzban API недоступен ($MARZ_URL) — код: $HTTP_CODE"
fi

# Попытка авторизации
if [ -n "$MARZBAN_PASS" ]; then
    TOKEN=$(curl -s -X POST "$MARZ_URL/api/admin/token" \
        -d "username=admin&password=$MARZBAN_PASS" \
        --max-time 5 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null)
    if [ -n "$TOKEN" ]; then
        ok "Авторизация в Marzban успешна"

        # Проверяем inbound
        INBOUNDS=$(curl -s "$MARZ_URL/api/inbounds" \
            -H "Authorization: Bearer $TOKEN" --max-time 5 2>/dev/null)
        INBOUND_TAG="${INBOUND_TAG:-vless-in}"
        if echo "$INBOUNDS" | grep -q "$INBOUND_TAG"; then
            ok "Inbound '$INBOUND_TAG' найден в Marzban"
        else
            fail "Inbound '$INBOUND_TAG' НЕ найден — создай в панели (порт 443, VLESS Reality)"
        fi
    else
        fail "Авторизация в Marzban не удалась — проверь MARZBAN_PASS"
    fi
fi

# ────────────────────────────────────────────
hdr "5. Сеть и порты"
# ────────────────────────────────────────────

SERVER_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
ok "IP сервера: $SERVER_IP"

# Порт 443
if nc -zw3 "$SERVER_IP" 443 2>/dev/null; then
    ok "Порт 443 открыт (VPN работает)"
else
    fail "Порт 443 закрыт — проверь файрвол: ufw allow 443/tcp"
fi

# Порт 8000 (Marzban)
if nc -zw3 localhost 8000 2>/dev/null; then
    ok "Порт 8000 открыт (панель Marzban)"
else
    warn "Порт 8000 недоступен (нормально если закрыт файрволом снаружи)"
fi

# Порт 22 (SSH)
if nc -zw3 localhost 22 2>/dev/null; then
    ok "SSH порт 22 открыт"
else
    warn "SSH порт 22 недоступен"
fi

# ────────────────────────────────────────────
hdr "6. Watchdog"
# ────────────────────────────────────────────

if crontab -l 2>/dev/null | grep -q vpn-bot; then
    ok "Watchdog cron задан"
elif [ -f /etc/cron.d/vpn-bot-watchdog ]; then
    ok "Watchdog файл /etc/cron.d/vpn-bot-watchdog существует"
else
    warn "Watchdog не найден — добавь в cron вручную"
fi

# ────────────────────────────────────────────
hdr "7. Логи на ошибки"
# ────────────────────────────────────────────

ERRORS=$(journalctl -u vpn-bot -n 100 --no-pager 2>/dev/null | grep -c "ERROR\|Traceback\|CRITICAL" || echo "0")
if [ "$ERRORS" = "0" ]; then
    ok "Критических ошибок в логах нет"
else
    fail "Найдено $ERRORS критических ошибок — проверь: journalctl -u vpn-bot -n 100"
fi

RESTARTS=$(systemctl show vpn-bot --property=NRestarts 2>/dev/null | cut -d= -f2 || echo "0")
if [ "${RESTARTS:-0}" -lt 5 ]; then
    ok "Рестартов сервиса: ${RESTARTS:-0} (норма)"
else
    warn "Рестартов сервиса: $RESTARTS — возможны проблемы"
fi

# ────────────────────────────────────────────
# ИТОГ
# ────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo -e "  Результат проверки:"
echo -e "  ${G}✓ Пройдено: $PASS${N}  ${R}✗ Провалено: $FAIL${N}  ${Y}! Предупреждений: $WARN${N}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo -e "${G}${BOLD}  ✅ Система готова к сдаче клиенту!${N}"
elif [ "$FAIL" -le 2 ]; then
    echo -e "${Y}${BOLD}  ⚠️  Есть мелкие проблемы — исправь перед сдачей${N}"
else
    echo -e "${R}${BOLD}  ❌ Серьёзные проблемы — система не готова${N}"
fi
echo ""

echo -e "  Панель Marzban:  ${Y}http://${SERVER_IP}:8000/dashboard${N}"
echo -e "  Логи бота:       ${Y}journalctl -u vpn-bot -f${N}"
echo -e "  Данные системы:  ${Y}cat /root/vpn-business-info.txt${N}"
echo ""
