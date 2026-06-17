#!/bin/bash
# Обновление бота (запускать от root или sokolniki)
# bash update.sh

set -e

echo "=== Останавливаем бота ==="
systemctl stop sokolniki-bot

echo "=== Получаем обновления с GitHub ==="
cd /home/sokolniki/sokolniki-podcast-bot
git pull origin main

echo "=== Обновляем зависимости ==="
/home/sokolniki/venv/bin/pip install -r sokolniki_bot/requirements.txt -q

echo "=== Запускаем бота ==="
systemctl start sokolniki-bot
sleep 2
systemctl status sokolniki-bot --no-pager

echo "✅ Бот обновлён!"
