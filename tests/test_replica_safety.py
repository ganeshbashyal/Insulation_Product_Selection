"""Tests for Phase 2 replica safety: shared-state rate limiting and sessions.

The defect being fixed is that InMemoryRateLimiter keeps counters per process,
so `uvicorn --workers N` silently granted N times the configured quota. That is
invisible in single-worker development, which is what makes it dangerous.
"""
import multiprocessing
import tempfile
import time
from pathlib import Path

import pytest

import redis_support
from auth_middleware import (
    InMemoryRateLimiter,
    RedisRateLimiter,
    SQLiteRateLimiter,
    build_rate_limiter,
)
from session_store import (
    RedisSessionStore,
    SQLiteSessionStore,
    build_session_store,
)

REDIS_AVAILABLE = redis_support.is_available()
requires_redis = pytest.mark.skipif(
    not REDIS_AVAILABLE,
    reason="No local Redis server reachable; multi-host backends are optional.",
)


class FakeRedis:
    """
    Faithful stand-in for the command subset RedisSessionStore uses.

    The store only calls set/get/delete, whose semantics are simple enough to
    model exactly, so these tests run everywhere rather than being skipped on a
    machine with no Redis. Deliberately not used for RedisRateLimiter: that one
    depends on server-side Lua and sorted sets, and a fake would prove nothing
    about the atomicity that is the entire point of the implementation.
    """

    def __init__(self):
        self.store: dict[str, str] = {}
        self.expiries: dict[str, int] = {}

    def set(self, key, value, ex=None):
        self.store[key] = value
        if ex is not None:
            self.expiries[key] = ex

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)
        self.expiries.pop(key, None)


@pytest.fixture
def limiter_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "rate_limits.sqlite3"


@pytest.fixture
def redis_client():
    client = redis_support.get_client()
    for key in client.scan_iter("aurora:test:*"):
        client.delete(key)
    yield client
    for key in client.scan_iter("aurora:test:*"):
        client.delete(key)


@pytest.fixture(params=["fake", "real"])
def session_client(request):
    """
    Exercises the session store against the in-process fake always, and against
    a real server as well whenever one is reachable.
    """
    if request.param == "fake":
        return FakeRedis()
    if not REDIS_AVAILABLE:
        pytest.skip("No local Redis server reachable.")
    client = redis_support.get_client()
    for key in client.scan_iter("aurora:test:*"):
        client.delete(key)
    return client


def _hammer(db_path_str, key, limit, count, queue):
    """Run in a separate process to prove cross-process coordination."""
    limiter = SQLiteRateLimiter(Path(db_path_str))
    granted = sum(1 for _ in range(count) if limiter.is_allowed(key, limit))
    queue.put(granted)


class TestSQLiteRateLimiter:
    """The default backend: correct across workers on a single host."""

    def test_allows_under_limit(self, limiter_db):
        limiter = SQLiteRateLimiter(limiter_db)
        assert limiter.is_allowed("site:1.1.1.1", 3)
        assert limiter.is_allowed("site:1.1.1.1", 3)

    def test_blocks_over_limit(self, limiter_db):
        limiter = SQLiteRateLimiter(limiter_db)
        for _ in range(3):
            assert limiter.is_allowed("site:1.1.1.1", 3)
        assert not limiter.is_allowed("site:1.1.1.1", 3)

    def test_keys_are_independent(self, limiter_db):
        limiter = SQLiteRateLimiter(limiter_db)
        for _ in range(2):
            assert limiter.is_allowed("site:1.1.1.1", 2)
        assert not limiter.is_allowed("site:1.1.1.1", 2)
        assert limiter.is_allowed("site:2.2.2.2", 2)

    def test_window_expires(self, limiter_db):
        limiter = SQLiteRateLimiter(limiter_db, window_seconds=1)
        assert limiter.is_allowed("site:1.1.1.1", 1)
        assert not limiter.is_allowed("site:1.1.1.1", 1)
        time.sleep(1.1)
        assert limiter.is_allowed("site:1.1.1.1", 1)

    def test_quota_is_shared_between_instances(self, limiter_db):
        """Two limiter objects must not each get a full quota."""
        one = SQLiteRateLimiter(limiter_db)
        two = SQLiteRateLimiter(limiter_db)
        assert one.is_allowed("site:1.1.1.1", 2)
        assert two.is_allowed("site:1.1.1.1", 2)
        assert not one.is_allowed("site:1.1.1.1", 2)
        assert not two.is_allowed("site:1.1.1.1", 2)

    def test_quota_is_shared_across_processes(self, limiter_db):
        """
        The real regression guard. Four worker processes each try 10 requests
        against a limit of 5; exactly 5 may be granted in total.
        """
        SQLiteRateLimiter(limiter_db)  # create schema before workers race
        queue = multiprocessing.Queue()
        procs = [
            multiprocessing.Process(
                target=_hammer, args=(str(limiter_db), "site:9.9.9.9", 5, 10, queue)
            )
            for _ in range(4)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)

        total_granted = sum(queue.get() for _ in procs)
        assert total_granted == 5

    def test_recovers_if_backing_file_is_removed(self, limiter_db):
        """
        A worker outlives its storage: the file is rotated or cleared away.
        The limiter must rebuild rather than fail every later request, which
        would turn a recoverable storage problem into a full API outage.
        """
        limiter = SQLiteRateLimiter(limiter_db)
        assert limiter.is_allowed("site:1.1.1.1", 2)

        for path in limiter_db.parent.glob(f"{limiter_db.name}*"):
            path.unlink()

        assert limiter.is_allowed("site:1.1.1.1", 2)
        assert limiter.is_allowed("site:1.1.1.1", 2)
        assert not limiter.is_allowed("site:1.1.1.1", 2)


class TestInMemoryLimiterIsNotReplicaSafe:
    """Documents precisely why the default had to change."""

    def test_separate_instances_each_get_a_full_quota(self):
        one = InMemoryRateLimiter()
        two = InMemoryRateLimiter()
        assert one.is_allowed("site:1.1.1.1", 1)
        assert not one.is_allowed("site:1.1.1.1", 1)
        # A second worker grants a fresh quota for the same caller.
        assert two.is_allowed("site:1.1.1.1", 1)


class TestRateLimiterFactory:
    def test_defaults_to_sqlite(self, monkeypatch):
        monkeypatch.delenv("AURORA_RATE_LIMIT_BACKEND", raising=False)
        assert isinstance(build_rate_limiter(), SQLiteRateLimiter)

    def test_memory_backend_selectable(self):
        assert isinstance(build_rate_limiter("memory"), InMemoryRateLimiter)

    def test_unknown_backend_rejected(self):
        with pytest.raises(ValueError, match="Unknown AURORA_RATE_LIMIT_BACKEND"):
            build_rate_limiter("cassandra")


class TestSessionStoreFactory:
    def test_defaults_to_sqlite(self, monkeypatch):
        monkeypatch.delenv("AURORA_SESSION_BACKEND", raising=False)
        assert isinstance(build_session_store(), SQLiteSessionStore)

    def test_unknown_backend_rejected(self):
        with pytest.raises(ValueError, match="Unknown AURORA_SESSION_BACKEND"):
            build_session_store("mongo")


@requires_redis
class TestRedisRateLimiterAtomicity:
    """
    Multi-host rate limiting. Requires a real server because the guarantee under
    test is server-side Lua atomicity, which cannot be faked meaningfully.
    """

    def test_blocks_over_limit(self, redis_client):
        limiter = RedisRateLimiter(redis_client, namespace="aurora:test:rl:")
        for _ in range(3):
            assert limiter.is_allowed("site:1.1.1.1", 3)
        assert not limiter.is_allowed("site:1.1.1.1", 3)

    def test_quota_is_shared_between_instances(self, redis_client):
        one = RedisRateLimiter(redis_client, namespace="aurora:test:rl:")
        two = RedisRateLimiter(redis_client, namespace="aurora:test:rl:")
        assert one.is_allowed("site:2.2.2.2", 2)
        assert two.is_allowed("site:2.2.2.2", 2)
        assert not two.is_allowed("site:2.2.2.2", 2)

    def test_keys_are_independent(self, redis_client):
        limiter = RedisRateLimiter(redis_client, namespace="aurora:test:rl:")
        assert limiter.is_allowed("site:3.3.3.3", 1)
        assert not limiter.is_allowed("site:3.3.3.3", 1)
        assert limiter.is_allowed("site:4.4.4.4", 1)


class TestRedisRateLimiterFailureMode:
    """Failure handling needs no server."""

    def test_fails_closed_when_backend_is_down(self):
        class BrokenClient:
            def register_script(self, script):
                def run(keys, args):
                    raise ConnectionError("redis is down")
                return run

        limiter = RedisRateLimiter(BrokenClient())
        # Denied rather than granted: an outage must not become an unmetered
        # open door, which is what a fail-open except/return True would create.
        assert limiter.is_allowed("site:1.1.1.1", 100) is False


class TestRedisSessionStore:
    """Must behave identically to the SQLite store, including tenant scoping."""

    def test_create_and_get(self, session_client):
        store = RedisSessionStore(session_client, namespace="aurora:test:sess:")
        store.create("s1", "local", {"answers": {"a": 1}})
        session = store.get("s1", "local")
        assert session is not None
        assert session.site_id == "local"
        assert session.to_dict()["conversation"] == {"answers": {"a": 1}}

    def test_missing_session_returns_none(self, session_client):
        store = RedisSessionStore(session_client, namespace="aurora:test:sess:")
        assert store.get("nope", "local") is None

    def test_sessions_isolated_by_site(self, session_client):
        store = RedisSessionStore(session_client, namespace="aurora:test:sess:")
        store.create("shared_id", "local", {"answers": {"site": "local"}})
        assert store.get("shared_id", "local") is not None
        # Same session id under a different tenant must not resolve.
        assert store.get("shared_id", "acme") is None

    def test_update_changes_payload(self, session_client):
        store = RedisSessionStore(session_client, namespace="aurora:test:sess:")
        store.create("s2", "local", {"answers": {}})
        store.update("s2", "local", {"answers": {"priority": "acoustic"}})
        session = store.get("s2", "local")
        assert session.to_dict()["conversation"]["answers"]["priority"] == "acoustic"

    def test_update_missing_session_raises(self, session_client):
        store = RedisSessionStore(session_client, namespace="aurora:test:sess:")
        with pytest.raises(KeyError):
            store.update("ghost", "local", {"answers": {}})

    def test_delete(self, session_client):
        store = RedisSessionStore(session_client, namespace="aurora:test:sess:")
        store.create("s3", "local", {"answers": {}})
        store.delete("s3", "local")
        assert store.get("s3", "local") is None

    def test_ttl_is_applied_on_create(self, session_client):
        store = RedisSessionStore(session_client, namespace="aurora:test:sess:")
        store.create("s4", "local", {"answers": {}})
        if isinstance(session_client, FakeRedis):
            assert session_client.expiries["aurora:test:sess:local:s4"] == store.TTL_SECONDS
        else:
            assert session_client.ttl("aurora:test:sess:local:s4") > 0
