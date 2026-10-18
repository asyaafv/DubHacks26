"""Run retained stub contract tests against a disposable schema, without patching app routes.

Usage: TEST_DATABASE_URL=... python -m backend.tests.e2e.legacy_contracts
These checks do not establish production intake/extraction or Person 3 wiring.
"""
import asyncio
import os
import secrets
from uuid import uuid4

import asyncpg
import pytest

from backend.decisions.storage import Database
from backend.decisions.storage.seed import seed


def main():
    url = os.environ['TEST_DATABASE_URL']
    schema = 'test_lapse_contract_' + uuid4().hex
    key = os.getenv('LAPSE_ENCRYPTION_KEY') or secrets.token_hex(32)
    scoped = url + ('&' if '?' in url else '?') + 'search_path=' + schema + ',public'

    async def prepare():
        conn = await asyncpg.connect(url)
        try:
            for extension in ('pgcrypto', 'vector', 'uuid-ossp'):
                await conn.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension}" WITH SCHEMA public')
            await conn.execute(f'CREATE SCHEMA {schema}')
        finally:
            await conn.close()
        db = await Database.connect(scoped, key)
        try:
            await db.migrate()
            await seed(db)
        finally:
            await db.close()

    async def cleanup():
        conn = await asyncpg.connect(url)
        try:
            await conn.execute(f'DROP SCHEMA {schema} CASCADE')
        finally:
            await conn.close()

    try:
        asyncio.run(prepare())
        os.environ.update(DATABASE_URL=scoped, LAPSE_ENCRYPTION_KEY=key, LAPSE_ALLOW_DEMO_IDENTITY='true')
        return pytest.main(['backend/tests/test_contracts.py', '-q', '-rA', '--tb=short'])
    finally:
        asyncio.run(cleanup())


if __name__ == '__main__':
    raise SystemExit(main())
