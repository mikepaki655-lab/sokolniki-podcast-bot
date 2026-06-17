# Sokolniki Podcast Bot 🎙

Telegram-бот для подкаст-студии «Сокольники» (Москва).

## Возможности
- 📅 FSM-форма бронирования студии
- 💰 Разделы с тарифами, адресом, акцией
- 🔥 Анкета на бесплатный первый выпуск
- 🎛 Полная Admin-панель через Telegram (/admin)
- 📊 Аналитика, CRM, статусы клиентов
- 📨 Рассылки по группам клиентов
- 📝 Редактор контента: тексты и фото прямо из Telegram

## Стек
- Python 3.12 + aiogram 3
- SQLAlchemy async + SQLite
- aiogram FSM

## Запуск
```bash
cd sokolniki_bot
pip install -r requirements.txt
# Установите BOT_TOKEN и ADMIN_ID в .env
python3 app/main.py
```
