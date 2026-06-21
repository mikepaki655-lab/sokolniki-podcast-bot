from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Client(Base):
    """User profile — one per Telegram account."""
    __tablename__ = "clients"

    id:          Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int]        = mapped_column(BigInteger, unique=True, index=True)
    username:    Mapped[str | None] = mapped_column(String(100), nullable=True)
    name:        Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone:       Mapped[str | None] = mapped_column(String(50),  nullable=True)
    created_at:  Mapped[datetime]   = mapped_column(DateTime, default=func.now(), server_default=func.now())

    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="client",
                                                      cascade="all, delete-orphan")


class Booking(Base):
    """Individual booking/lead — many per client."""
    __tablename__ = "bookings"

    id:              Mapped[int]         = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id:       Mapped[int]         = mapped_column(Integer, ForeignKey("clients.id"), index=True)
    lead_type:       Mapped[str]         = mapped_column(String(30), default="booking")   # booking | free_episode
    content_type:    Mapped[str | None]  = mapped_column(String(100), nullable=True)
    booking_date:    Mapped[str | None]  = mapped_column(String(20),  nullable=True)      # DD.MM.YYYY
    booking_time:    Mapped[str | None]  = mapped_column(String(10),  nullable=True)      # HH:00
    booking_hours:   Mapped[int | None]  = mapped_column(Integer,     nullable=True)
    status:          Mapped[str]         = mapped_column(String(30), default="new_request")
    status_note:     Mapped[str | None]  = mapped_column(Text,        nullable=True)
    payment_amount:  Mapped[float | None]= mapped_column(Float,       nullable=True)
    payment_hours:   Mapped[float | None]= mapped_column(Float,       nullable=True)
    reschedule_from: Mapped[str | None]  = mapped_column(String(20),  nullable=True)
    reminded:        Mapped[int]         = mapped_column(Integer, default=0, server_default="0")  # 1 = reminder sent
    created_at:      Mapped[datetime]    = mapped_column(DateTime, default=func.now(), server_default=func.now())
    updated_at:      Mapped[datetime]    = mapped_column(DateTime, default=func.now(),
                                                         onupdate=func.now(), server_default=func.now())

    client: Mapped["Client"] = relationship("Client", back_populates="bookings")


class SectionContent(Base):
    __tablename__ = "section_content"

    id:            Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    key:           Mapped[str]        = mapped_column(String(50), unique=True, index=True)
    title:         Mapped[str]        = mapped_column(String(100))
    text:          Mapped[str]        = mapped_column(Text)
    photo_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    local_banner:  Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at:    Mapped[datetime]   = mapped_column(DateTime, default=func.now(),
                                                      onupdate=func.now(), server_default=func.now())
