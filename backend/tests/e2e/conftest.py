import os
import secrets
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from backend.decisions.lookup.embeddings import MiniLMQueryEncoder
from backend.decisions.storage import Database


@pytest_asyncio.fixture
async def db():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('TEST_DATABASE_URL is required for real Postgres tests')
    schema = 'test_lapse_e2e_' + uuid4().hex
    admin = await asyncpg.connect(url)
    try:
        for extension in ('pgcrypto', 'vector', 'uuid-ossp'):
            await admin.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension}" WITH SCHEMA public')
        await admin.execute(f'CREATE SCHEMA {schema}')
    finally:
        await admin.close()
    pool = await asyncpg.create_pool(url, min_size=1, max_size=5,
        server_settings={'search_path': schema + ',public', 'timezone': 'UTC'})
    # A fresh key for fresh disposable records, never a replacement for an existing key.
    database = Database(pool, secrets.token_hex(32))
    database.test_url, database.test_schema = url, schema
    try:
        await database.migrate()
        yield database
    finally:
        await database.close()
        # Open after the test: its deliberate server restart closes old connections.
        admin = await asyncpg.connect(url)
        try:
            await admin.execute(f'DROP SCHEMA {schema} CASCADE')
        finally:
            await admin.close()


@pytest.fixture(scope='session')
def encoder():
    if os.getenv('RUN_SEMANTIC_TESTS') != '1':
        pytest.skip('Set RUN_SEMANTIC_TESTS=1 and LAPSE_MODEL_CACHE for real MiniLM')
    return MiniLMQueryEncoder(cache_folder=os.environ['LAPSE_MODEL_CACHE'], offline=True)
