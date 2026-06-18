from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"

    id:             Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id:    Mapped[int]        = mapped_column(BigInteger, unique=True, index=True)
    username:       Mapped[str | None] = mapped_column(String(100), nullable=True)
    name:           Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone:          Mapped[str | None] = mapped_column(String(50),  nullable=True)
    social_link:    Mapped[str | None] = mapped_column(String(500), nullable=True)
    occupation:     Mapped[str | None] = mapped_column(String(300), nullable=True)
    podcast_goal:   Mapped[str | None] = mapped_column(String(500), nullable=True)
    client_type:    Mapped[str | None] = mapped_column(String(100), nullable=True)
    service:        Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Booking fields
    booking_date:   Mapped[str | None] = mapped_column(String(20),  nullable=True)  # DD.MM.YYYY
    booking_time:   Mapped[str | None] = mapped_column(String(10),  nullable=True)  # HH:00
    booking_hours:  Mapped[int | None] = mapped_column(Integer,     nullable=True)
    # Status & history
    status:         Mapped[str]        = mapped_column(String(50), default="lead")
    status_note:    Mapped[str | None] = mapped_column(Text,        nullable=True)
    reschedule_from: Mapped[str | None]= mapped_column(String(50),  nullable=True)
    payment_amount: Mapped[float | None]= mapped_column(Float,      nullable=True)
    payment_hours:  Mapped[float | None]= mapped_column(Float,      nullable=True)
    lead_type:      Mapped[str | None] = mapped_column(String(50),  nullable=True)
    comment:        Mapped[str | None] = mapped_column(Text,        nullable=True)
    # Legacy field kept for compatibility
    date:           Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at:     Mapped[datetime]   = mapped_column(DateTime, default=func.now(), server_default=func.now())
    updated_at:     Mapped[datetime]   = mapped_column(DateTime, default=func.now(), onupdate=func.now(), server_default=func.now())


class SectionContent(Base):
    __tablename__ = "section_content"

    id:           Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    key:          Mapped[str]        = mapped_column(String(50), unique=True, index=True)
    title:        Mapped[str]        = mapped_column(String(100))
    text:         Mapped[str]        = mapped_column(Text)
    photo_file_id:Mapped[str | None] = mapped_column(String(500), nullable=True)
    local_banner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at:   Mapped[datetime]   = mapped_column(DateTime, default=func.now(), onupdate=func.now(), server_default=func.now())
