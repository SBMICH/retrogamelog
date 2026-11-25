from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import GameStatus, LogKind, Performance


def pg_enum(enum_class: type, name: str) -> Enum:
    # Guarda los valores en minúscula ("playing"), no los nombres de Python.
    return Enum(enum_class, name=name, values_callable=lambda e: [m.value for m in e])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    username: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_public: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# Unicidad sin distinguir mayúsculas. El backend además guarda el email en minúsculas.
Index("uq_users_email_lower", func.lower(User.email), unique=True)
Index("uq_users_username_lower", func.lower(User.username), unique=True)


class UserGame(Base):
    __tablename__ = "user_games"
    __table_args__ = (
        UniqueConstraint("user_id", "game_id"),
        CheckConstraint("rating BETWEEN 1 AND 10", name="rating_range"),
        CheckConstraint("priority BETWEEN 1 AND 3", name="priority_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    status: Mapped[GameStatus] = mapped_column(pg_enum(GameStatus, "game_status"))
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_game_id: Mapped[int] = mapped_column(
        ForeignKey("user_games.id", ondelete="CASCADE")
    )
    kind: Mapped[LogKind] = mapped_column(pg_enum(LogKind, "log_kind"))
    entry_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_model_id: Mapped[int] = mapped_column(ForeignKey("device_models.id"))
    nickname: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PlaySetup(Base):
    __tablename__ = "play_setups"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_game_id: Mapped[int] = mapped_column(
        ForeignKey("user_games.id", ondelete="CASCADE")
    )
    # Sin ondelete: borrar un dispositivo con configuraciones falla (regla de borrado). La
    # comprobación se difiere al final de la transacción: con RESTRICT/NO ACTION inmediato,
    # borrar un usuario fallaba porque PostgreSQL revisa devices antes de borrar sus play_setups.
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", deferrable=True, initially="DEFERRED")
    )
    emulator_id: Mapped[int | None] = mapped_column(ForeignKey("emulators.id"))
    performance: Mapped[Performance] = mapped_column(pg_enum(Performance, "performance"))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
