"""
Database layer — SQLite backend with an asyncpg-compatible surface.

The original app targeted PostgreSQL via asyncpg. The deploy host (LankaHost
cPanel shared hosting) has no PostgreSQL, only file-based storage, so this
module provides a thin shim over `aiosqlite` that mimics just enough of the
asyncpg Pool/Connection API for the call sites to keep working unchanged:

    async with pool.acquire() as conn:
        row  = await conn.fetchrow("... $1 ...", arg)   # -> dict | None
        rows = await conn.fetch("...")                   # -> list[dict]
        await conn.execute("INSERT ... $1 ...", arg)

SQL is translated on the fly:
  * `$N`  positional params  -> `?N` numbered params (reuse-safe)
  * `::jsonb` / `::text` casts are stripped (SQLite is dynamically typed)

Schema is created lazily on first acquire (the FastAPI startup event does not
fire under the Passenger/a2wsgi WSGI bridge, so we cannot rely on it).
"""

import os
import re
import asyncio

import aiosqlite

# DB file lives next to the app; override with AEGIS_DB_PATH if needed.
_DB_PATH = os.environ.get(
    "AEGIS_DB_PATH",
    os.path.join(os.path.dirname(__file__), "data", "aegis.db"),
)

_CAST = re.compile(r"::[a-zA-Z_]+")
_PARAM = re.compile(r"\$(\d+)")


def _translate(sql: str) -> str:
    """Postgres SQL -> SQLite SQL (params + casts)."""
    sql = _CAST.sub("", sql)
    sql = _PARAM.sub(r"?\1", sql)
    return sql


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id    TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    country        TEXT NOT NULL,
    province       TEXT,
    public_key_hex TEXT NOT NULL,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attestations (
    id         TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    signature  TEXT NOT NULL,
    signer_id  TEXT NOT NULL,
    sig_valid  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_attestations_signer ON attestations(signer_id);

CREATE TABLE IF NOT EXISTS attestation_inputs (
    attestation_id TEXT NOT NULL REFERENCES attestations(id),
    input_id       TEXT NOT NULL,
    PRIMARY KEY (attestation_id, input_id)
);

CREATE TABLE IF NOT EXISTS published_products (
    product_id   TEXT PRIMARY KEY,
    name         TEXT,
    chain        TEXT NOT NULL,
    published_by TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

_schema_ready = False
_schema_lock = asyncio.Lock()


async def _ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    async with _schema_lock:
        if _schema_ready:
            return
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        async with aiosqlite.connect(_DB_PATH) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.executescript(_SCHEMA)
            await conn.commit()
        _schema_ready = True


# ── asyncpg-compatible connection wrapper ──────────────────────────────────────

class _Conn:
    def __init__(self, raw: aiosqlite.Connection):
        self._raw = raw

    async def execute(self, sql: str, *args):
        cur = await self._raw.execute(_translate(sql), list(args))
        await cur.close()
        await self._raw.commit()
        return "OK"

    async def fetch(self, sql: str, *args) -> list[dict]:
        cur = await self._raw.execute(_translate(sql), list(args))
        rows = await cur.fetchall()
        await cur.close()
        # INSERT ... RETURNING also commits via this path
        await self._raw.commit()
        return [dict(r) for r in rows]

    async def fetchrow(self, sql: str, *args):
        cur = await self._raw.execute(_translate(sql), list(args))
        row = await cur.fetchone()
        await cur.close()
        await self._raw.commit()
        return dict(row) if row is not None else None

    async def fetchval(self, sql: str, *args):
        row = await self.fetchrow(sql, *args)
        if not row:
            return None
        return next(iter(row.values()))


class _Acquire:
    """Async context manager yielding a fresh _Conn (one sqlite handle each)."""

    def __init__(self):
        self._raw = None

    async def __aenter__(self) -> _Conn:
        await _ensure_schema()
        self._raw = await aiosqlite.connect(_DB_PATH)
        self._raw.row_factory = aiosqlite.Row
        await self._raw.execute("PRAGMA busy_timeout=8000")
        return _Conn(self._raw)

    async def __aexit__(self, *exc):
        if self._raw is not None:
            await self._raw.close()
        return False


class Pool:
    """Minimal stand-in for asyncpg.Pool."""

    def acquire(self) -> _Acquire:
        return _Acquire()

    # Pool-level convenience (asyncpg allows pool.execute / pool.fetch too).
    async def execute(self, sql: str, *args):
        async with self.acquire() as c:
            return await c.execute(sql, *args)

    async def fetch(self, sql: str, *args):
        async with self.acquire() as c:
            return await c.fetch(sql, *args)

    async def fetchrow(self, sql: str, *args):
        async with self.acquire() as c:
            return await c.fetchrow(sql, *args)

    async def fetchval(self, sql: str, *args):
        async with self.acquire() as c:
            return await c.fetchval(sql, *args)


# Single shared pool object (stateless — connections are per-acquire).
POOL = Pool()


async def get_pool() -> Pool:
    await _ensure_schema()
    return POOL


async def init_schema(pool: "Pool | None" = None) -> None:
    """Kept for API compatibility with the original startup event."""
    await _ensure_schema()
