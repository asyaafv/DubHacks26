"""FastAPI dependency boundary, overridable by integration tests."""
from fastapi import HTTPException, Request


def get_database(request: Request):
    database = getattr(request.app.state, 'database', None)
    if database is None:
        raise HTTPException(503, 'Database is not configured')
    return database
