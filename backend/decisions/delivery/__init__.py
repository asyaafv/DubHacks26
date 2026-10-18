"""Durable SSE and offline reconciliation; integration owns application wiring."""
from .router import router
from .service import startup, shutdown

__all__ = ['router', 'startup', 'shutdown']
