#!/bin/bash
# ============================================================
# Установка Marzban VPN Panel для продажи
# Ubuntu 22.04 | Запуск: bash install-marzban.sh
# ============================================================
set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }
step() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

[ "$EUID" -ne 0 ] && err "Запусти от root: sudo bash install-marzban.sh"

clear
echo -e "${GREEN}"
cat << 'EOF'
  ╔══════════════════════════════════════╗
  ║    VPN BUSINESS — Marzban Panel      ║
  ║    Автоматические продажи VPN        ║
  ╚══════════════════════════════════════╝
EOF
echo -e "${NC}"

# ────────────────────────────────────────────
step "1/5 Обновление системы"
# ────────────────────────────────────────────
apt-get update -qq && apt-get upgrade -y -qq
apt-get install -y -qq curl wget git python3 python3-pip ufw
log "Система готова"

# ────────────────────────────────────────────
step "2/5 Установка Docker"
# ────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | bash
  systemctl enable docker && systemctl start docker
  log "Docker установлен"
else
  log "Docker уже установлен"
fi

# ────────────────────────────────────────────
step "3/5 Установка Marzban"
# ────────────────────────────────────────────
bash -c "$(curl -sL https://github.com/Gozargah/Marzban-scripts/raw/master/marzban.sh)" @ install

# Ждём запуска
sleep 5
log "Marzban установлен и запущен"

# ────────────────────────────────────────────
step "4/5 Файрвол"
# ────────────────────────────────────────────
ufw --force reset > /dev/null 2>&1
ufw default deny incoming > /dev/null 2>&1
ufw default allow outgoing > /dev/null 2>&1
ufw allow 22/tcp   > /dev/null 2>&1   # SSH
ufw allow 443/tcp  > /dev/null 2>&1   # VPN
ufw allow 8000/tcp > /dev/null 2>&1   # Панель Marzban
ufw --force enable > /dev/null 2>&1
log "Файрвол настроен"

# ────────────────────────────────────────────
step "5/5 Установка бота-продавца"
# ────────────────────────────────────────────
BOT_DIR="/opt/vpn-bot"
mkdir -p "$BOT_DIR"

pip3 install -q python-telegram-bot requests

# Скачиваем бота (если есть интернет и репо)
# wget -q -O "$BOT_DIR/bot.py" https://raw.githubusercontent.com/.../bot.py

# Создаём systemd-сервис для бота
cat > /etc/systemd/system/vpn-bot.service << 'SVC'
[Unit]
Description=VPN Sales Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/vpn-bot
EnvironmentFile=/opt/vpn-bot/.env
ExecStart=/usr/bin/python3 /opt/vpn-bot/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC

systemctl daemon-reload
log "Сервис vpn-bot создан (запустится после настройки .env)"

# ────────────────────────────────────────────
# ИТОГ
# ────────────────────────────────────────────
SERVER_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

clear
echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════╗"
echo "║        MARZBAN УСТАНОВЛЕН УСПЕШНО!           ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "Панель управления: ${YELLOW}http://${SERVER_IP}:8000/dashboard${NC}"
echo ""
echo -e "${BLUE}━━━ СЛЕДУЮЩИЕ ШАГИ ━━━${NC}"
echo ""
echo "1. Открой панель в браузере:"
echo -e "   ${YELLOW}http://${SERVER_IP}:8000/dashboard${NC}"
echo ""
echo "2. Войди с логином/паролем которые ввёл при установке"
echo ""
echo "3. Добавь inbound (протокол VLESS Reality):"
echo "   Hosts → Add Inbound → VLESS → Reality → порт 443"
echo ""
echo "4. Настрой бота-продавца:"
echo "   nano /opt/vpn-bot/.env  (заполни токены)"
echo "   cp /home/agent/projects/vpn-sell/bot/bot.py /opt/vpn-bot/"
echo "   systemctl start vpn-bot"
echo "   systemctl enable vpn-bot"
echo ""
echo "5. Создай Telegram-бота: @BotFather → /newbot"
echo "   Вставь токен в /opt/vpn-bot/.env"
echo ""
echo -e "${GREEN}Готово! Осталось заполнить .env и запустить бота.${NC}"
echo ""
echo -e "Документация Marzban: ${BLUE}https://github.com/Gozargah/Marzban${NC}"
echo ""
