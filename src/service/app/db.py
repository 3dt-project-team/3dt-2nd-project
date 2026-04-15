from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
from psycopg2.extras import RealDictCursor

from .config import get_settings


@contextmanager
def get_connection() -> Iterator[psycopg2.extensions.connection]:
    settings = get_settings()
    settings.require_database()

    if settings.db_connection_string:
        conninfo = settings.db_connection_string
        if conninfo.startswith("postgresql+psycopg://"):
            conninfo = conninfo.replace("postgresql+psycopg://", "postgresql://", 1)
        conn = psycopg2.connect(conninfo, cursor_factory=RealDictCursor)
    else:
        conn = psycopg2.connect(
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            sslmode=settings.db_sslmode,
            cursor_factory=RealDictCursor,
        )
    try:
        yield conn
    finally:
        conn.close()


def run_query(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return list(cur.fetchall())


# SQLSTATE codes for fallback-worthy query failures
# 3F000: invalid_schema_name
# 42703: undefined_column
# 42704: undefined_object
# 42P01: undefined_table
FALLBACK_SQLSTATE_CODES = {"3F000", "42703", "42704", "42P01"}


def run_query_with_fallbacks(
    candidates: list[tuple[str, tuple[Any, ...]]],
) -> list[dict[str, Any]]:
    last_error: Exception | None = None

    for query, params in candidates:
        try:
            return run_query(query, params)
        except psycopg2.Error as exc:
            if exc.pgcode in FALLBACK_SQLSTATE_CODES:
                last_error = exc
                continue
            raise

    if last_error is not None:
        raise last_error
    return []
