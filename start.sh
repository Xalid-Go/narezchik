#!/bin/bash
# BubaClipper Launcher
cd "$(dirname "$0")"

echo "=================================================="
echo "      🚀 Запуск BubaClipper Pro (БУБА MEDIA)     "
echo "=================================================="

if [ ! -d ".venv" ]; then
    echo "Создание виртуального окружения..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install imageio-ffmpeg fastapi uvicorn aiofiles python-multipart
else
    source .venv/bin/activate
fi

# Ensure ffmpeg binary symlink exists
if [ ! -f ".venv/bin/ffmpeg" ]; then
    FFMPEG_PATH=$(.venv/bin/python3 -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" 2>/dev/null)
    if [ -n "$FFMPEG_PATH" ]; then
        ln -sf "$FFMPEG_PATH" .venv/bin/ffmpeg
    fi
fi

echo "Сервер запускается на http://localhost:8000"
echo "Открываем браузер..."
sleep 1 && open "http://localhost:8000" &

.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
