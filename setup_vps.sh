#!/bin/bash
set -e

echo "======================================================"
echo "    🚀 Установка BubaClipper Pro на Ubuntu / Debian    "
echo "======================================================"

# 1. Update and install system dependencies
echo "📦 Установка системных зависимостей (FFmpeg, Python3)..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg curl git

# 2. Setup Virtual Environment
echo "🐍 Настройка виртуального окружения Python..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Create output directory
mkdir -p output

# 4. Optional: create systemd service for 24/7 background running
CURRENT_DIR=$(pwd)
CURRENT_USER=$(whoami)

cat <<EOF | sudo tee /etc/systemd/system/bubaclipper.service
[Unit]
Description=BubaClipper Pro Video Clipper Service
After=network.target

[Service]
User=$CURRENT_USER
WorkingDirectory=$CURRENT_DIR
ExecStart=$CURRENT_DIR/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "🔄 Активация автозапуска systemd..."
sudo systemctl daemon-reload
sudo systemctl enable bubaclipper
sudo systemctl restart bubaclipper

# Get public IP
PUBLIC_IP=$(curl -s ifconfig.me || hostname -I | awk '{print $1}')

echo ""
echo "======================================================"
echo "✅ Установка завершена!"
echo "Сервис запущен 24/7 в фоне через systemd."
echo "Откройте сайт в браузере:"
echo "👉 http://$PUBLIC_IP:8000"
echo "======================================================"
echo "Полезные команды:"
echo "• Проверить статус: sudo systemctl status bubaclipper"
echo "• Смотреть логи:    sudo journalctl -u bubaclipper -f"
echo "• Перезапустить:    sudo systemctl restart bubaclipper"
echo "======================================================"
