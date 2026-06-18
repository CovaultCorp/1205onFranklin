from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    return database_url


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


def safe_database_identity() -> dict[str, str]:
    url: URL = engine.url
    return {
        "driver": url.drivername,
        "host": url.host or "local-file",
        "database": url.database or "",
        "url": url.render_as_string(hide_password=True),
    }


settings = get_settings()
database_url = _normalize_database_url(settings.database_url)

engine = create_engine(database_url, **_engine_kwargs(database_url))
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def configure_database(database_url: str) -> None:
    global engine, SessionLocal
    normalized_url = _normalize_database_url(database_url)
    engine = create_engine(normalized_url, **_engine_kwargs(normalized_url))
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
