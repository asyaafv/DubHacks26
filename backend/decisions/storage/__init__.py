"""Database entry point. Use Database.transaction(user_id) for all owned data."""
from .database import Database

__all__ = ["Database"]
