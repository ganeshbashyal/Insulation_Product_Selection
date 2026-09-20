"""Shared pytest configuration.

Pins the rate limiter to the in-memory backend for the whole test session. The
production default is the SQLite limiter, which persists its window to disk on
purpose; under test that would carry counters between runs and exhaust a site's
quota (acme allows 10/minute), making unrelated tests fail intermittently.
"""
import os

os.environ.setdefault("AURORA_RATE_LIMIT_BACKEND", "memory")
