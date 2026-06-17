#!/bin/bash
# Скрипт установки бота на Ubuntu 22.04 (Timeweb Cloud)
# Запускать от root: bash setup_server.sh

set -e

echo "=== Установка зависимостей ==="
apt-get update -y
apt-get install -y python3.12 python3.12-venv python3-pip git

echo "=== Создание пользователя ==="
useradd -m -s /bin/bash sokolniki 2>/dev/null || echo "Пользователь уже существует"

echo "=== Клонирование репозитория ==="
su - sokolniki -c "git clone https://github.com/mikepaki655-lab/sokolniki-podcast-bot.git"

echo "=== Установка Python-окружения ==="
su - sokolniki -c "python3.12 -m venv /home/sokolniki/venv"
su - sokolniki -c "/home/sokolniki/venv/bin/pip install -r /home/sokolniki/sokolniki-podcast-bot/sokolniki_bot/requirements.txt"

echo "=== Установка systemd-сервиса ==="
cp /home/sokolniki/sokolniki-podcast-bot/sokolniki_bot/deploy/sokolniki-bot.service /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/sokolniki-bot.service

echo ""
echo "======================================"
echo "СЛЕДУЮЩИЕ ШАГИ:"
echo "1. Отредактируйте токен и admin_id:"
echo "   nano /etc/systemd/system/sokolniki-bot.service"
echo ""
echo "2. Запустите бота:"
echo "   systemctl daemon-reload"
echo "   systemctl enable sokolniki-bot"
echo "   systemctl start sokolniki-bot"
echo ""
echo "3. Проверьте статус:"
echo "   systemctl status sokolniki-bot"
echo "   journalctl -u sokolniki-bot -f"
echo "======================================"
