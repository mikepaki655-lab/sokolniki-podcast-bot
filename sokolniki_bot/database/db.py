from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from database.models import Base, SectionContent

DATABASE_URL = "sqlite+aiosqlite:///sokolniki.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Tree-style formatting: ├ (U+251C) for middle rows, └ (U+2514) for last row
DEFAULTS: list[dict] = [
    {
        "key": "welcome",
        "title": "🏠 Приветствие",
        "local_banner": "banner_welcome.png",
        "text": (
            "🎙 <b>Студия «Сокольники»</b>\n"
            "├ 🎥 Видео-подкасты\n"
            "├ 🎙 Профессиональный звук\n"
            "├ ✂️ Монтаж выпусков\n"
            "└ 📱 Shorts / Reels\n\n"
            "Выберите раздел 👇"
        ),
    },
    {
        "key": "booking",
        "title": "🎬 Запись подкаста",
        "local_banner": "banner_record.png",
        "text": (
            "🎬 <b>Запись подкаста</b>\n\n"
            "Как вас зовут?"
        ),
    },
    {
        "key": "prices",
        "title": "💰 Цены",
        "local_banner": "banner_prices.png",
        "text": (
            "💰 <b>Тарифы студии</b>\n\n"
            "🎙 <b>START</b>\n"
            "├ Аренда студии\n"
            "├ Съёмка на проф. оборудование\n"
            "└ <b>от 4 500 ₽ / час</b>\n\n"
            "🎬 <b>PRO</b>\n"
            "├ Аренда студии\n"
            "├ Съёмка на проф. оборудование\n"
            "├ Монтаж видео\n"
            "└ <b>от 8 000 ₽ / час</b>\n\n"
            "🚀 <b>FULL — Подкаст под ключ</b>\n"
            "├ Студия на 3 часа\n"
            "├ Съёмка на проф. оборудование\n"
            "├ Монтаж видео\n"
            "├ 5 коротких видео (Reels / Shorts)\n"
            "└ <b>от 35 000 ₽</b>"
        ),
    },
    {
        "key": "address",
        "title": "📍 Адрес студии",
        "local_banner": "banner_address.jpg",
        "text": (
            "📍 <b>Адрес студии</b>\n"
            "├ г. Москва, Песочный пер., дом 3\n"
            "├ м. Сокольники — 5 минут пешком\n"
            "├ Вход со стороны ул. Сокольнической Слободки\n"
            "└ Часы работы: 10:00 — 20:00 (24/7 по запросу)"
        ),
    },
    {
        "key": "free",
        "title": "🔥 Первый выпуск бесплатно",
        "local_banner": "banner_free.png",
        "text": (
            "🔥 <b>Первый выпуск бесплатно</b>\n"
            "├ Аренда студии на 2 часа\n"
            "├ Съёмка на профессиональное оборудование\n"
            "│  (камеры, микрофоны, свет)\n"
            "└ Только для новых клиентов студии"
        ),
    },
]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed_content()


async def _seed_content() -> None:
    async with async_session() as session:
        for item in DEFAULTS:
            exists = await session.execute(
                select(SectionContent).where(SectionContent.key == item["key"])
            )
            if not exists.scalar_one_or_none():
                session.add(SectionContent(**item))
        await session.commit()


async def reset_content_to_defaults() -> None:
    """Force-reset all sections to default content (admin command)."""
    async with async_session() as session:
        for item in DEFAULTS:
            result = await session.execute(
                select(SectionContent).where(SectionContent.key == item["key"])
            )
            section = result.scalar_one_or_none()
            if section:
                section.text = item["text"]
                section.local_banner = item["local_banner"]
                # Keep custom photo_file_id if admin set one
            else:
                session.add(SectionContent(**item))
        await session.commit()


async def get_content(key: str) -> SectionContent | None:
    async with async_session() as session:
        result = await session.execute(
            select(SectionContent).where(SectionContent.key == key)
        )
        return result.scalar_one_or_none()


async def get_all_content() -> list[SectionContent]:
    async with async_session() as session:
        result = await session.execute(select(SectionContent))
        return list(result.scalars().all())


async def update_content_text(key: str, text: str) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(SectionContent).where(SectionContent.key == key)
        )
        section = result.scalar_one_or_none()
        if section:
            section.text = text
            await session.commit()


async def update_content_photo(key: str, file_id: str) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(SectionContent).where(SectionContent.key == key)
        )
        section = result.scalar_one_or_none()
        if section:
            section.photo_file_id = file_id
            await session.commit()


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
