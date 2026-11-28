"""SQLAlchemy 2.0 engine, session and declarative base."""

from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Database:
    def __init__(self, url: str):
        kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, **kw)
        if url.startswith("sqlite"):
            # pysqlite workaround so SAVEPOINTs work (SQLAlchemy docs, "Serializable
            # isolation / Savepoints / Transactional DDL").
            @event.listens_for(self.engine, "connect")
            def _pragmas(conn, _rec):
                conn.isolation_level = None
                cur = conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.close()

            @event.listens_for(self.engine, "begin")
            def _begin(conn):
                conn.exec_driver_sql("BEGIN")
        self.sessionmaker = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self):
        Base.metadata.create_all(self.engine)

    def session(self) -> Iterator[Session]:
        with self.sessionmaker() as s:
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise
