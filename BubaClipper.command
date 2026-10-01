#!/bin/bash
cd "$(dirname "$0")"

echo "======================================================="
echo "       🚀 Запуск BubaClipper Pro Desktop Studio        "
echo "======================================================="

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Check if port 8000 is running
if ! lsof -i :8000 > /dev/null 2>&1; then
    echo "⚡ Запускаем локальный видеосервер на порту 8000..."
    .venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000 &
    sleep 2
fi

echo "🌐 Открываем интерфейс видеоредактора..."
open "http://localhost:8000"

echo ""
echo "✅ BubaClipper Pro работает!"
echo "Не закрывайте это окно во время работы."
echo "======================================================="

wait
