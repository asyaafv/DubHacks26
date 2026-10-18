import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

import asyncpg
import pytest

from backend.decisions.common import DEMO_USER_ID
from backend.decisions.storage.seed import seed
from backend.tests.e2e.harness import serve
from backend.tests.test_storage_wallet import reward

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
async def test_fresh_migrations_seed_and_application_restart(db):
    await db.migrate()
    await seed(db)
    headers = {'X-User-Id': str(DEMO_USER_ID)}
    async with serve(db) as (client, _):
        summary = (await client.get('/savings', headers=headers)).json()
        wallet = (await client.get('/wallet', headers=headers)).json()
        assert summary['total'] == '103.51' and len(summary['items']) == 8
        assert sum((Decimal(row['saved']) for row in summary['items']), Decimal(0)) == Decimal('103.51')
        assert summary['series'][-1]['cumulative'] == '103.51'
        assert wallet['rewards'] and all(r['expires_at'] and r['code'] is None for r in wallet['rewards'])
        remove = wallet['cards'][0]['id']
        response = await client.post('/wallet', headers=headers, json={'remove_card_ids': [remove],
            'add_cards': [{'issuer': 'Test', 'network': 'visa', 'name': 'Persistent test card', 'base_rate': '2'}]})
        assert response.status_code == 200
        mutated = response.json()
        assert remove not in [c['id'] for c in mutated['cards']]
    await seed(db)
    async with serve(db) as (client, _):
        assert (await client.get('/wallet', headers=headers)).json() == mutated
        assert (await client.get('/savings', headers=headers)).json() == summary
    async with db.pool.acquire() as conn:
        assert await conn.fetchval('SELECT count(*) FROM schema_migrations') == 3
        extensions = dict(await conn.fetch("SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','pgcrypto')"))
        assert set(extensions) == {'vector', 'pgcrypto'}


@pytest.mark.asyncio
async def test_server_process_restart_preserves_cipher_wallet_ledger_and_cursor(db):
    directory = os.getenv('LAPSE_E2E_PGDATA')
    if os.getenv('LAPSE_E2E_ALLOW_PG_RESTART') != '1' or not directory:
        pytest.skip('Opt in with LAPSE_E2E_ALLOW_PG_RESTART=1 and dedicated LAPSE_E2E_PGDATA')
    directory = Path(directory).resolve()
    assert directory.parent == Path('/private/tmp') and directory.name.startswith('lapse-person3-e2e-')
    assert (directory / 'PG_VERSION').is_file()
    pg_ctl = shutil.which('pg_ctl')
    assert pg_ctl
    owner = uuid4()
    offer = reward(owner, expires_at=datetime.now(timezone.utc) + timedelta(days=2))
    await seed(db)
    async with db.transaction(owner) as repo:
        await repo.save_reward(offer)
    async with serve(db) as (client, _):
        headers = {'X-User-Id': str(owner)}
        added = await client.post('/wallet', headers=headers, json={'add_cards': [
            {'issuer': 'Test', 'network': 'visa', 'name': 'Survives Postgres restart', 'base_rate': '2'}]})
        assert added.status_code == 200
        wallet = added.json()
    async with db.transaction(owner) as repo:
        cursor = await repo.event_watermark()
        original = await repo.get_reward(offer.id, reveal_code=True)
    async with db.transaction(DEMO_USER_ID) as repo:
        history = [r.model_dump(mode='json') for r in await repo.list_redemptions()]
    # No key rotation: reopen with the same Database object's key and schema.
    await db.close()
    process = await asyncio.create_subprocess_exec(pg_ctl, '-D', str(directory), '-l',
        str(directory) + '.log', '-m', 'fast', 'restart', stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    output, error = await asyncio.wait_for(process.communicate(), 30)
    assert process.returncode == 0, (output.decode(), error.decode())
    db.pool = await asyncpg.create_pool(db.test_url, min_size=1, max_size=5,
        server_settings={'search_path': db.test_schema + ',public', 'timezone': 'UTC'})
    async with db.transaction(owner) as repo:
        assert (await repo.get_reward(offer.id, reveal_code=True)) == original
        assert await repo.event_watermark() == cursor
        assert (await repo.get_wallet()).model_dump(mode='json') == wallet
    async with db.transaction(DEMO_USER_ID) as repo:
        assert [r.model_dump(mode='json') for r in await repo.list_redemptions()] == history


@pytest.fixture
def generated(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('person3_contract_generator', ROOT / 'scripts/gen_contracts.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    monkeypatch.setattr(generator, 'SCHEMAS_DIR', tmp_path / 'schemas')
    monkeypatch.setattr(generator, 'TYPES_FILE', tmp_path / 'types.ts')
    monkeypatch.setattr(generator, 'OPENAPI_FILE', tmp_path / 'openapi.json')
    generator.main()
    return tmp_path


def test_generated_models_and_types_match_committed_files(generated):
    tmp_path = generated
    for actual in (tmp_path / 'schemas').glob('*.json'):
        assert json.loads(actual.read_text()) == json.loads((ROOT / 'shared/schemas' / actual.name).read_text()), actual.name
    assert (tmp_path / 'types.ts').read_bytes() == (ROOT / 'shared/types.ts').read_bytes()
    wallet = json.loads((tmp_path / 'schemas/Wallet.json').read_text())
    assert 'rewards' in wallet['properties']
    assert 'expires_at' in wallet['$defs']['Reward']['properties']


def test_generated_openapi_matches_committed_production_contract(generated):
    actual = json.loads((generated / 'openapi.json').read_text())
    committed = json.loads((ROOT / 'shared/openapi.json').read_text())

    def differences(left, right, path=''):
        if isinstance(left, dict) and isinstance(right, dict):
            return [item for key in sorted(left.keys() | right.keys())
                    for item in (differences(left[key], right[key], path + '/' + key)
                                 if key in left and key in right else [path + '/' + key])]
        return [] if left == right else [path]

    assert actual == committed, 'Generated OpenAPI drift: ' + ', '.join(differences(actual, committed))
