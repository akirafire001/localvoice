from contextlib import contextmanager

from flask import current_app, g
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def init_engine(app):
    engine = create_engine(app.config["LV"].DATABASE_URL, pool_pre_ping=True, future=True)
    app.extensions["lv_engine"] = engine
    app.extensions["lv_sessionmaker"] = sessionmaker(bind=engine, expire_on_commit=False)

    @app.teardown_appcontext
    def _close(exc):
        s = g.pop("db", None)
        if s is not None:
            if exc is not None:
                s.rollback()
            s.close()


def get_db():
    """Request-scoped SQLAlchemy session."""
    if "db" not in g:
        g.db = current_app.extensions["lv_sessionmaker"]()
    return g.db


@contextmanager
def session_scope(app):
    """Standalone session for workers / CLI."""
    s = app.extensions["lv_sessionmaker"]()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def create_schema(app):
    from . import models  # noqa: F401  (register tables)

    engine = app.extensions["lv_engine"]
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    # create_all does not add columns to existing tables; columns added since are added here
    with engine.begin() as conn:
        for stmt in UPGRADES:
            conn.execute(text(stmt))


UPGRADES = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS home_country varchar(2) NOT NULL DEFAULT 'jp'",  # 2026-10-09
]


def drop_schema(app):
    from . import models  # noqa: F401

    Base.metadata.drop_all(app.extensions["lv_engine"])
