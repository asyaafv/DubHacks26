"""Real routers/lifecycle, deliberately independent of production main.py."""
import asyncio
from contextlib import asynccontextmanager
import socket

from fastapi import FastAPI
import httpx
import uvicorn

from backend.decisions.delivery import router as delivery, startup, shutdown
from backend.decisions.delivery.service import Settings
from backend.decisions.lookup.router import router as lookup
from backend.decisions.savings.router import router as savings
from backend.decisions.savings.seed import seed_redemptions
from backend.decisions.stacking.router import router as stacking
from backend.decisions.wallet.router import router as wallet


def create_app(database, encoder=None):
    @asynccontextmanager
    async def lifespan(app):
        # The fixture owns the DB pool. Production owns its separate pool lifecycle.
        app.state.database = database
        app.state.query_encoder = encoder
        await seed_redemptions(database)
        await startup(app, Settings(poll_seconds=.02, heartbeat_seconds=.1))
        try:
            yield
        finally:
            await shutdown(app)

    app = FastAPI(title='LAPSE Person 3 boundary test', lifespan=lifespan)
    for router in (wallet, stacking, lookup, delivery, savings):
        app.include_router(router)
    paths = [(route.path, method) for route in app.routes for method in getattr(route, 'methods', ())]
    assert len(paths) == len(set(paths)), 'Duplicate route would hide an actual router'
    return app


@asynccontextmanager
async def serve(database, encoder=None):
    app = create_app(database, encoder)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    running = uvicorn.Server(uvicorn.Config(app, log_level='error', timeout_graceful_shutdown=2))
    task = asyncio.create_task(running.serve(sockets=[sock]))
    try:
        for _ in range(500):
            if running.started:
                break
            if task.done():
                await task
            await asyncio.sleep(.01)
        assert running.started
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}', timeout=5) as client:
            yield client, app
    finally:
        await shutdown(app)
        running.should_exit = True
        await asyncio.wait_for(task, 8)
        sock.close()
