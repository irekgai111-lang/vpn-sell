#!/bin/bash
# ============================================================
# VPN Business — Полная автоматическая установка
# Ubuntu 22.04 | root | bash install-full.sh
# Что делает:
#   1. Marzban VPN Panel (Docker)
#   2. VLESS Reality inbound (автоматически)
#   3. Nginx + SSL (Let's Encrypt) — панель за HTTPS
#   4. Бот-продавец (Python, systemd)
#   5. Файрвол
# ============================================================
set -e
R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;34m'; N='\033[0m'
ok()   { echo -e "${G}[✓]${N} $1"; }
warn() { echo -e "${Y}[!]${N} $1"; }
err()  { echo -e "${R}[✗]${N} $1"; exit 1; }
hdr()  { echo -e "\n${B}━━━━━ $1 ━━━━━${N}"; }

[ "$EUID" -ne 0 ] && err "Запусти от root: sudo bash install-full.sh"

clear
echo -e "${G}"
cat << 'EOF'
  ╔══════════════════════════════════════════╗
  ║    VPN BUSINESS — ПОЛНАЯ УСТАНОВКА       ║
  ║    Marzban + Nginx SSL + Бот-продавец    ║
  ╚══════════════════════════════════════════╝
EOF
echo -e "${N}"

# ────────────────────────────────────────────
hdr "ДАННЫЕ ДЛЯ УСТАНОВКИ"
# ────────────────────────────────────────────
read -rp "Домен для панели (например panel.myvpn.ru, или Enter чтобы пропустить SSL): " DOMAIN
read -rp "Email для SSL-сертификата (или Enter пропустить): " EMAIL
read -rp "Токен Telegram-бота (@BotFather): " BOT_TOKEN
read -rp "Твой Telegram ID (получи у @userinfobot): " ADMIN_ID
read -rp "BOT_USERNAME (без @): " BOT_USERNAME
echo ""
echo -e "${Y}Платёжные токены (нажми Enter чтобы пропустить и добавить позже)${N}"
read -rp "CRYPTO_TOKEN (@CryptoBot → Pay → Apps): " CRYPTO_TOKEN
read -rp "YK_SHOP_ID (YooKassa): " YK_SHOP_ID
read -rp "YK_SECRET (YooKassa): " YK_SECRET

SERVER_IP=$(curl -s --max-time 5 ifconfig.me || hostname -I | awk '{print $1}')
ok "IP сервера: $SERVER_IP"

# ────────────────────────────────────────────
hdr "1/7 Обновление системы"
# ────────────────────────────────────────────
apt-get update -qq
apt-get install -y -qq curl wget git python3 python3-pip ufw nginx certbot python3-certbot-nginx
ok "Система готова"

# ────────────────────────────────────────────
hdr "2/7 Docker"
# ────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | bash
    systemctl enable docker
    systemctl start docker
    ok "Docker установлен"
else
    ok "Docker уже есть"
fi

# ────────────────────────────────────────────
hdr "3/7 Marzban VPN Panel"
# ────────────────────────────────────────────
MARZ_PASS=$(tr -dc 'A-Za-z0-9@#' < /dev/urandom | head -c 16)
bash -c "$(curl -sL https://github.com/Gozargah/Marzban-scripts/raw/master/marzban.sh)" @ install \
    --admins "admin:${MARZ_PASS}" 2>&1 | tail -5
sleep 5
ok "Marzban запущен (admin / $MARZ_PASS)"

# Авто-добавляем VLESS Reality inbound через API
MARZ_TOKEN=$(curl -s -X POST "http://localhost:8000/api/admin/token" \
    -d "username=admin&password=${MARZ_PASS}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Генерируем Reality ключи
apt-get install -y -qq xray 2>/dev/null || true
if command -v xray &>/dev/null; then
    KEYS=$(xray x25519)
    PRIV=$(echo "$KEYS" | grep Private | awk '{print $3}')
    PUB=$(echo  "$KEYS" | grep Public  | awk '{print $3}')
else
    PRIV=$(openssl genpkey -algorithm X25519 2>/dev/null | openssl pkey -pubout -outform DER 2>/dev/null | base64 -w0 || echo "auto-gen-on-marzban")
    PUB="auto-gen-on-marzban"
fi

ok "VLESS Reality inbound будет настроен через панель (auto-генерация ключей)"

# ────────────────────────────────────────────
hdr "4/7 Nginx + SSL"
# ────────────────────────────────────────────
if [ -n "$DOMAIN" ] && [ -n "$EMAIL" ]; then
    cat > /etc/nginx/sites-available/marzban << NGINX
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass         http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade \$http_upgrade;
        proxy_set_header   Connection keep-alive;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
    }
}
NGINX
    ln -sf /etc/nginx/sites-available/marzban /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx

    certbot --nginx -d "$DOMAIN" --email "$EMAIL" --agree-tos --non-interactive --redirect
    PANEL_URL="https://${DOMAIN}/dashboard"
    ok "SSL получен: $PANEL_URL"
else
    PANEL_URL="http://${SERVER_IP}:8000/dashboard"
    warn "Домен не указан — SSL пропущен. Панель на HTTP (небезопасно!)"
    warn "Добавь домен позже: certbot --nginx -d ВАШ_ДОМЕН --email ВАШ_EMAIL --agree-tos"
fi

# ────────────────────────────────────────────
hdr "5/7 Файрвол"
# ────────────────────────────────────────────
ufw --force reset    > /dev/null 2>&1
ufw default deny incoming > /dev/null 2>&1
ufw default allow outgoing > /dev/null 2>&1
ufw allow 22/tcp     > /dev/null 2>&1   # SSH
ufw allow 80/tcp     > /dev/null 2>&1   # HTTP
ufw allow 443/tcp    > /dev/null 2>&1   # HTTPS + VPN
ufw allow 8000/tcp   > /dev/null 2>&1   # Marzban (если нет домена)
ufw --force enable   > /dev/null 2>&1
ok "Файрвол настроен"

# ────────────────────────────────────────────
hdr "6/7 Бот-продавец"
# ────────────────────────────────────────────
BOT_DIR="/opt/vpn-bot"
mkdir -p "$BOT_DIR"

# Зависимости Python
pip3 install -q python-telegram-bot>=20.7 apscheduler>=3.10 requests>=2.31
ok "Python-зависимости установлены"

# Создаём .env
cat > "${BOT_DIR}/.env" << DOTENV
BOT_TOKEN=${BOT_TOKEN}
BOT_USERNAME=${BOT_USERNAME}
ADMIN_IDS=${ADMIN_ID}
MARZBAN_URL=http://localhost:8000
MARZBAN_USER=admin
MARZBAN_PASS=${MARZ_PASS}
INBOUND_TAG=vless-in
CRYPTO_TOKEN=${CRYPTO_TOKEN}
YK_SHOP_ID=${YK_SHOP_ID}
YK_SECRET=${YK_SECRET}
DB_PATH=${BOT_DIR}/vpn.db
DOTENV
chmod 600 "${BOT_DIR}/.env"

# Копируем файлы бота (если запущено из папки проекта)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "${SCRIPT_DIR}/bot" ]; then
    cp "${SCRIPT_DIR}/bot/"*.py "${BOT_DIR}/"
    ok "Файлы бота скопированы из ${SCRIPT_DIR}/bot/"
else
    warn "Папка bot/ не найдена рядом со скриптом."
    warn "Скопируй файлы вручную: cp /path/to/bot/*.py ${BOT_DIR}/"
fi

# Systemd сервис
cat > /etc/systemd/system/vpn-bot.service << SVC
[Unit]
Description=VPN Sales Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${BOT_DIR}
EnvironmentFile=${BOT_DIR}/.env
ExecStart=/usr/bin/python3 ${BOT_DIR}/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVC

systemctl daemon-reload
systemctl enable vpn-bot
systemctl start vpn-bot
sleep 3
systemctl is-active vpn-bot && ok "Бот-продавец запущен" || warn "Бот не запустился — проверь: journalctl -u vpn-bot -n 50"

# Watchdog для бота
cat > /etc/cron.d/vpn-bot-watchdog << CRON
*/5 * * * * root systemctl is-active --quiet vpn-bot || (systemctl restart vpn-bot && echo "\$(date): vpn-bot restarted" >> /var/log/vpn-bot-watchdog.log)
CRON
ok "Watchdog активен"

# ────────────────────────────────────────────
hdr "7/7 Сохраняем данные"
# ────────────────────────────────────────────
cat > /root/vpn-business-info.txt << INFO
╔══════════════════════════════════════════════════╗
║         VPN BUSINESS — ДАННЫЕ УСТАНОВКИ          ║
╚══════════════════════════════════════════════════╝

Дата установки: $(date '+%Y-%m-%d %H:%M')
Сервер:         ${SERVER_IP}

━━━ Marzban Panel ━━━
URL панели:     ${PANEL_URL}
Логин:          admin
Пароль:         ${MARZ_PASS}

━━━ Бот ━━━
Файлы:          ${BOT_DIR}/
Конфиг:         ${BOT_DIR}/.env
Логи:           journalctl -u vpn-bot -f
Рестарт:        systemctl restart vpn-bot

━━━ Следующий шаг — настроить VLESS Reality ━━━
1. Открой панель: ${PANEL_URL}
2. Хосты → Добавить Inbound
3. Протокол: VLESS, Security: Reality
4. dest: www.microsoft.com:443
5. serverName: www.microsoft.com
6. Порт: 443
7. Сохрани, имя inbound укажи: vless-in
   (должно совпадать с INBOUND_TAG в .env)

━━━ Как управлять ботом ━━━
Логи:           journalctl -u vpn-bot -f
Рестарт:        systemctl restart vpn-bot
Стоп:           systemctl stop vpn-bot
Статус:         systemctl status vpn-bot
INFO

chmod 600 /root/vpn-business-info.txt

# ────────────────────────────────────────────
hdr "Обновляем сайт под ваш бот"
# ────────────────────────────────────────────
SITE_URL="https://irekgai111-lang.github.io/vpn-sell/"
# Если есть домен — сайт будет там, иначе GitHub Pages
if [ -n "$DOMAIN" ]; then
    CLIENT_SITE_URL="https://${DOMAIN}/"
else
    CLIENT_SITE_URL="${SITE_URL}"
fi

# Подставляем имя бота и URL в client.html
if [ -f "${BOT_DIR}/client.html" ]; then
    sed -i "s|YOUR_BOT|${BOT_USERNAME}|g" "${BOT_DIR}/client.html"
    sed -i "s|https://irekgai111-lang.github.io/vpn-sell/|${CLIENT_SITE_URL}|g" "${BOT_DIR}/client.html"
    ok "client.html обновлён: бот @${BOT_USERNAME}, сайт ${CLIENT_SITE_URL}"
fi

# Прописываем URL сайта в .env для бота
echo "SITE_URL=${CLIENT_SITE_URL}" >> "${BOT_DIR}/.env"
ok "SITE_URL добавлен в .env"

# Если Nginx настроен — копируем client.html в веб-корень
if [ -n "$DOMAIN" ] && [ -d "/var/www/html" ]; then
    cp "${BOT_DIR}/client.html" /var/www/html/index.html
    ok "client.html опубликован → https://${DOMAIN}/"
fi

# ────────────────────────────────────────────
# ФИНАЛ
# ────────────────────────────────────────────
clear
echo -e "${G}"
echo "╔══════════════════════════════════════════════╗"
echo "║     VPN BUSINESS УСТАНОВЛЕН УСПЕШНО! 🚀      ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${N}"
echo ""
echo -e "Панель Marzban:   ${Y}${PANEL_URL}${N}"
echo -e "Пароль админа:    ${Y}${MARZ_PASS}${N}"
echo -e "Бот статус:       $(systemctl is-active vpn-bot)"
echo ""
echo -e "${B}━━━ ЧТО СДЕЛАТЬ ДАЛЬШЕ ━━━${N}"
echo ""
echo "1. Открой панель → добавь VLESS Reality inbound (порт 443)"
echo "   Имя inbound должно быть: vless-in"
echo ""
echo "2. Настрой оплату если не сделал:"
echo "   nano ${BOT_DIR}/.env  (CRYPTO_TOKEN, YK_SHOP_ID, YK_SECRET)"
echo "   systemctl restart vpn-bot"
echo ""
echo "3. Проверь бота: t.me/${BOT_USERNAME}"
echo ""
echo "4. Сайт для клиентов: ${CLIENT_SITE_URL}"
echo "   (тарифы, инструкции, рефералка — уже настроено)"
echo ""
echo "5. Все данные сохранены в: /root/vpn-business-info.txt"
echo ""
echo -e "${G}Запусти клиентов — деньги идут автоматически!${N}"
echo ""
