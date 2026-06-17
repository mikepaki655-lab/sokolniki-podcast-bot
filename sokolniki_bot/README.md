# 🎙 Sokolniki Podcast Studio Bot

Telegram-бот для подкаст-студии «Сокольники». Production-ready MVP.

## Функции

- Приём заявок клиентов (FSM-анкета)
- Бесплатный первый выпуск (отдельная анкета)
- Раздел цен с тарифами
- Адрес студии с картой
- CRM-панель для администратора
- Аналитика за 7 и 30 дней
- Управление статусами клиентов
- Рассылки по группам клиентов

## Быстрый старт

### 1. Создать бота в Telegram

Напишите [@BotFather](https://t.me/BotFather):
```
/newbot
```
Скопируйте токен бота.

### 2. Узнать свой Telegram ID

Напишите [@userinfobot](https://t.me/userinfobot) — он покажет ваш ID.

### 3. Настроить переменные окружения

```bash
cp .env.example .env
```

Отредактируйте `.env`:
```
BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_ID=ваш_telegram_id
```

### 4. Установить зависимости

```bash
pip install -r requirements.txt
```

### 5. Запустить бота

```bash
python app/main.py
```

## Структура проекта

```
sokolniki_bot/
├── app/
│   └── main.py          # Точка входа, инициализация бота
├── bot/
│   ├── handlers.py      # Пользовательские обработчики
│   ├── admin.py         # Администраторские обработчики
│   ├── keyboards.py     # Клавиатуры
│   └── states.py        # FSM состояния
├── database/
│   ├── models.py        # SQLAlchemy модели
│   └── db.py            # Инициализация БД
├── images/              # Баннеры для разделов
├── config.py            # Конфигурация
├── requirements.txt
└── .env.example
```

## Статусы CRM

| Статус | Описание |
|--------|----------|
| `lead` | Оставил контакт (бесплатный выпуск) |
| `new_request` | Оставил заявку на запись |
| `paid` | Оплатил услугу |
| `completed` | Завершённый клиент |

## Команды бота

- `/start` — главное меню
- `/admin` — панель администратора (только для ADMIN_ID)

## Технологии

- Python 3.12
- aiogram 3.27
- SQLAlchemy 2.x async
- SQLite (aiosqlite)
- python-dotenv
