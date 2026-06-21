from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from database.models import Base, Booking, Client, SectionContent

DATABASE_URL = "sqlite+aiosqlite:///sokolniki.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

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
        "title": "🏠 Забронировать студию",
        "local_banner": "banner_record.png",
        "text": (
            "🎬 <b>Запись подкаста</b>\n\n"
            "Заполните заявку — мы подтвердим бронирование в течение 30 минут."
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
        await conn.run_sync(_migrate)
    await _seed_content()


def _migrate(conn):
    """Safe migrations: add missing columns and migrate legacy data."""
    import sqlalchemy as sa
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # Add `reminded` column to bookings if missing
    if "bookings" in tables:
        existing = {c["name"] for c in inspector.get_columns("bookings")}
        if "reminded" not in existing:
            conn.execute(sa.text("ALTER TABLE bookings ADD COLUMN reminded INTEGER DEFAULT 0"))

    # Migrate legacy booking data from clients → bookings (one-time)
    if "clients" in tables and "bookings" in tables:
        legacy_cols = {c["name"] for c in inspector.get_columns("clients")}
        has_legacy = "booking_date" in legacy_cols and "booking_hours" in legacy_cols

        if has_legacy:
            rows = conn.execute(sa.text(
                "SELECT id, booking_date, booking_time, booking_hours, "
                "status, status_note, payment_amount, payment_hours, "
                "lead_type, service "
                "FROM clients "
                "WHERE booking_date IS NOT NULL "
                "  AND id NOT IN (SELECT client_id FROM bookings)"
            )).fetchall()

            for row in rows:
                (cid, bdate, btime, bhours, status, note,
                 pamount, phours, ltype, service) = row
                conn.execute(sa.text(
                    "INSERT INTO bookings "
                    "(client_id, lead_type, content_type, booking_date, booking_time, "
                    "booking_hours, status, status_note, payment_amount, payment_hours, reminded) "
                    "VALUES (:cid, :lt, :ct, :bd, :bt, :bh, :st, :sn, :pa, :ph, 0)"
                ), {
                    "cid": cid,
                    "lt":  ltype or "booking",
                    "ct":  service,
                    "bd":  bdate,
                    "bt":  btime,
                    "bh":  bhours,
                    "st":  status or "new_request",
                    "sn":  note,
                    "pa":  pamount,
                    "ph":  phours,
                })


async def _seed_content() -> None:
    async with async_session() as session:
        for item in DEFAULTS:
            exists = await session.execute(
                select(SectionContent).where(SectionContent.key == item["key"])
            )
            if not exists.scalar_one_or_none():
                session.add(SectionContent(**item))
        await session.commit()


# ─── CLIENT HELPERS ───────────────────────────────────────────────────────────

async def get_or_create_client(telegram_id: int, username: str | None) -> Client:
    async with async_session() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()
        if not client:
            client = Client(telegram_id=telegram_id, username=username)
            session.add(client)
            await session.commit()
            await session.refresh(client)
        return client


async def update_client_profile(telegram_id: int, name: str, phone: str) -> Client:
    async with async_session() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()
        if client:
            client.name  = name
            client.phone = phone
            await session.commit()
            await session.refresh(client)
        return client


# ─── BOOKING HELPERS ──────────────────────────────────────────────────────────

async def create_booking(client_id: int, data: dict) -> Booking:
    async with async_session() as session:
        booking = Booking(
            client_id    = client_id,
            lead_type    = data.get("lead_type", "booking"),
            content_type = data.get("content_type"),
            booking_date = data.get("date"),
            booking_time = data.get("time"),
            booking_hours= data.get("hours"),
            status       = "new_request",
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking)
        return booking


async def get_booked_hours(date_str: str) -> set[int]:
    """Return blocked hour-ints for a date (booking duration + 1 buffer hour)."""
    blocked: set[int] = set()
    async with async_session() as session:
        result = await session.execute(
            select(Booking).where(
                Booking.booking_date == date_str,
                Booking.status.not_in(["done_paid", "done_no_pay"]),
                Booking.booking_time.isnot(None),
                Booking.booking_hours.isnot(None),
            )
        )
        for b in result.scalars().all():
            try:
                start    = int(b.booking_time.split(":")[0])
                end      = start + b.booking_hours + 1  # +1 buffer
                for h in range(start, min(end, 24)):
                    blocked.add(h)
            except Exception:
                pass
    return blocked


async def get_bookings_by_status(statuses: set[str], limit: int = 50) -> list[tuple[Booking, Client]]:
    async with async_session() as session:
        result = await session.execute(
            select(Booking, Client)
            .join(Client, Booking.client_id == Client.id)
            .where(Booking.status.in_(statuses))
            .order_by(Booking.created_at.desc())
            .limit(limit)
        )
        return result.all()


async def get_booking_with_client(booking_id: int) -> tuple[Booking, Client] | None:
    async with async_session() as session:
        result = await session.execute(
            select(Booking, Client)
            .join(Client, Booking.client_id == Client.id)
            .where(Booking.id == booking_id)
        )
        return result.first()


async def update_booking_status(booking_id: int, **kwargs) -> Booking | None:
    async with async_session() as session:
        booking = await session.get(Booking, booking_id)
        if booking:
            for k, v in kwargs.items():
                setattr(booking, k, v)
            await session.commit()
            await session.refresh(booking)
        return booking


async def get_analytics(days: int = 7) -> dict:
    from sqlalchemy import func as sqlfunc
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = (datetime.now() - timedelta(days=days)).strftime("%d.%m.%Y")

    async with async_session() as session:
        def _cnt(q): return session.execute(q)

        new_q    = select(sqlfunc.count()).select_from(Booking).where(
            Booking.status.in_({"new_request", "lead"}),
            Booking.booking_date >= cutoff_str)
        proc_q   = select(sqlfunc.count()).select_from(Booking).where(
            Booking.status.in_({"confirmed", "recorded", "paid"}),
            Booking.booking_date >= cutoff_str)
        done_q   = select(sqlfunc.count()).select_from(Booking).where(
            Booking.status == "done_paid",
            Booking.booking_date >= cutoff_str)
        rev_q    = select(sqlfunc.sum(Booking.payment_amount)).where(
            Booking.status == "done_paid",
            Booking.booking_date >= cutoff_str,
            Booking.payment_amount.isnot(None))
        hours_q  = select(sqlfunc.sum(Booking.payment_hours)).where(
            Booking.status == "done_paid",
            Booking.booking_date >= cutoff_str,
            Booking.payment_hours.isnot(None))

        new_cnt  = (await session.execute(new_q)).scalar_one()  or 0
        proc_cnt = (await session.execute(proc_q)).scalar_one() or 0
        done_cnt = (await session.execute(done_q)).scalar_one() or 0
        revenue  = (await session.execute(rev_q)).scalar_one()  or 0
        hours    = (await session.execute(hours_q)).scalar_one() or 0

    return {
        "new":     new_cnt,
        "proc":    proc_cnt,
        "done":    done_cnt,
        "revenue": revenue,
        "hours":   hours,
    }


async def get_upcoming_bookings_for_reminder() -> list[tuple[Booking, Client]]:
    """Bookings happening in ~24h that haven't been reminded yet."""
    moscow = timezone(timedelta(hours=3))
    now_msk  = datetime.now(moscow)
    tomorrow = (now_msk + timedelta(hours=24)).strftime("%d.%m.%Y")

    async with async_session() as session:
        result = await session.execute(
            select(Booking, Client)
            .join(Client, Booking.client_id == Client.id)
            .where(
                Booking.booking_date == tomorrow,
                Booking.reminded == 0,
                Booking.status.in_({"confirmed", "recorded", "paid", "new_request"}),
            )
        )
        return result.all()


async def mark_reminded(booking_id: int) -> None:
    async with async_session() as session:
        booking = await session.get(Booking, booking_id)
        if booking:
            booking.reminded = 1
            await session.commit()


# ─── CONTENT HELPERS ──────────────────────────────────────────────────────────

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


async def reset_content_to_defaults() -> None:
    async with async_session() as session:
        for item in DEFAULTS:
            result = await session.execute(
                select(SectionContent).where(SectionContent.key == item["key"])
            )
            section = result.scalar_one_or_none()
            if section:
                section.text         = item["text"]
                section.local_banner = item["local_banner"]
            else:
                session.add(SectionContent(**item))
        await session.commit()
