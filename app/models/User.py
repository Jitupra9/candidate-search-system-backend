
from app.core.db import Base,UUIDPKMixin,TimestampMixin
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer

class User(UUIDPKMixin, TimestampMixin,Base):
    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password: Mapped[str] = mapped_column(String(255))
