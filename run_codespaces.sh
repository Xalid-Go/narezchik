#!/bin/bash
set -e

echo "======================================================"
echo "    🚀 Запуск BubaClipper Pro в GitHub Codespaces      "
echo "======================================================"

# Install ffmpeg if not installed
if ! command -v ffmpeg &> /dev/null; then
    echo "📦 Установка ffmpeg..."
    sudo apt-get update && sudo apt-get install -y ffmpeg
fi

# Install requirements
echo "🐍 Проверка зависимостей Python..."
pip install -r requirements.txt

# Start server
echo "🌐 Запуск веб-сервера..."
echo "Откройте вкладку 'PORTS' внизу и нажмите на значок браузера возле порта 8000!"
uvicorn server:app --host 0.0.0.0 --port 8000
