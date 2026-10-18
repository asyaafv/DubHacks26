"""Async Postgres lifecycle and a user-scoped unit of work."""
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID
import os

import asyncpg


class Database:
    def __init__(self, pool, encryption_key: str):
        if len(encryption_key) < 32:
            raise ValueError("PERK_ENCRYPTION_KEY must contain at least 32 characters")
        self.pool = pool
        self._key = encryption_key

    @classmethod
    async def connect(cls, url=None, key=None):
        key = key or os.environ.get("PERK_ENCRYPTION_KEY", "")
        if len(key) < 32:
            raise ValueError("PERK_ENCRYPTION_KEY must contain at least 32 characters")
        pool = await asyncpg.create_pool(url or os.environ["DATABASE_URL"],
                                       min_size=1, max_size=10,
                                       server_settings={"timezone": "UTC"})
        return cls(pool, key)

    async def close(self):
        await self.pool.close()

    async def list_user_ids(self, after: UUID | None = None, limit: int = 100) -> list[UUID]:
        """Trusted scheduler registry enumeration; never expose as a user endpoint.

        Returns identifiers only. Every subsequent owned-data read or mutation must
        run in transaction(user_id), which acquires the user's serialization lock.
        """
        if not 1 <= limit <= 1000:
            raise ValueError("Invalid user page size")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM users WHERE ($1::uuid IS NULL OR id > $1) ORDER BY id LIMIT $2",
                after, limit)
        return [row["id"] for row in rows]

    async def migrate(self):
        """Explicit CLI operation, never run DDL or seeds on application startup."""
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(72635103)")
            await conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
            for path in sorted(Path(__file__).with_name("migrations").glob("*.sql")):
                if not await conn.fetchval("SELECT 1 FROM schema_migrations WHERE version=$1", path.name):
                    await conn.execute(path.read_text())
                    await conn.execute("INSERT INTO schema_migrations(version) VALUES($1)", path.name)

    @asynccontextmanager
    async def transaction(self, user_id: UUID):
        """Commit reward changes and outbox together. Never nest independent UoWs.

        Locking the owner row serializes writers *before* event sequence allocation,
        so a later committed cursor cannot skip an earlier uncommitted event.
        """
        from .repository import Repository
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute("INSERT INTO users(id,email,email_hash) VALUES($1,$2,$3) ON CONFLICT(id) DO NOTHING",
                               user_id, f"{user_id}@demo.invalid", str(user_id))
            await conn.fetchval("SELECT id FROM users WHERE id=$1 FOR UPDATE", user_id)
            yield Repository(conn, user_id, self._key)
