#!/bin/bash
# Local deployment helper to VPS
if [ -z "$1" ]; then
    echo "=========================================================="
    echo "  Использование: ./deploy.sh root@IP_ВАШЕГО_VPS"
    echo "  Пример:       ./deploy.sh root@194.87.12.34"
    echo "=========================================================="
    exit 1
fi

VPS_HOST="$1"
TARGET_DIR="~/bubaclipper"

echo "📦 Копирование проекта на $VPS_HOST:$TARGET_DIR..."
ssh "$VPS_HOST" "mkdir -p $TARGET_DIR"

rsync -avz --progress \
    --exclude='.venv' \
    --exclude='output/*.mp4' \
    --exclude='*.jpg' \
    --exclude='*.png' \
    --exclude='__pycache__' \
    --exclude='.git' \
    ./ "$VPS_HOST:$TARGET_DIR/"

echo "🚀 Запуск автоматической установки на сервере..."
ssh -t "$VPS_HOST" "cd $TARGET_DIR && chmod +x setup_vps.sh && ./setup_vps.sh"
