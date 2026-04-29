"""Regression tests for the StateManager / SQLitePointerStore connection
lifecycle (Phase-14 R7).

The previous implementation called ``sqlite3.connect(db_path)`` per method,
which produced wasted IO under low concurrency and ``database is locked``
failures under the new ASGI runtime. These tests exercise the new behaviour:

* a single shared SQLite connection per StateManager / SQLitePointerStore;
* explicit ``close()`` lifecycle that the runtime can call on shutdown;
* concurrent ``store_and_point`` calls do not raise ``database is locked``.
"""

from __future__ import annotations

import os
import tempfile
import threading
import unittest

from eap.protocol import StateManager
from eap.protocol.storage.sqlite_store import SQLitePointerStore


class StateManagerConnectionLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-conn-", suffix=".db")
        os.close(fd)
        self.manager = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        try:
            self.manager.close()
        except Exception:
            pass
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                os.remove(path)

    def test_state_manager_reuses_a_single_connection(self) -> None:
        """The shared connection must be the same object across calls."""
        first = self.manager._connection_obj
        self.manager.store_and_point(raw_data="x", summary="x")
        self.manager.store_and_point(raw_data="y", summary="y")
        self.assertIs(self.manager._connection_obj, first)

    def test_close_is_idempotent_and_blocks_further_use(self) -> None:
        self.manager.close()
        # Calling close() a second time must not raise.
        self.manager.close()
        with self.assertRaises(RuntimeError):
            self.manager.store_and_point(raw_data="x", summary="x")

    def test_state_manager_supports_context_manager(self) -> None:
        path = self.db_path + ".ctx"
        try:
            with StateManager(db_path=path) as sm:
                sm.store_and_point(raw_data="ctx", summary="ctx")
            # After exiting the context manager the connection must be closed.
            self.assertTrue(sm._closed)
        finally:
            for suffix in ("", "-wal", "-shm"):
                p = path + suffix
                if os.path.exists(p):
                    os.remove(p)

    def test_concurrent_store_and_point_does_not_lock(self) -> None:
        """100 concurrent store_and_point calls complete without errors."""
        errors: list[BaseException] = []

        def worker(idx: int) -> None:
            try:
                self.manager.store_and_point(
                    raw_data=f"payload-{idx}",
                    summary=f"summary-{idx}",
                )
            except BaseException as exc:  # noqa: BLE001 - we surface anything
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        # All 100 pointers must have been persisted.
        pointers = self.manager.list_pointers(include_expired=True)
        self.assertGreaterEqual(len(pointers), 100)


class SQLitePointerStoreConnectionLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-ptr-", suffix=".db")
        os.close(fd)
        self.store = SQLitePointerStore(db_path=self.db_path)
        self.store.initialize()

    def tearDown(self) -> None:
        try:
            self.store.close()
        except Exception:
            pass
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                os.remove(path)

    def test_pointer_store_reuses_connection(self) -> None:
        first = self.store._conn
        self.store.store_pointer(
            pointer_id="ptr_a",
            raw_data="a",
            summary="a",
            metadata={},
            created_at_utc="2026-01-01T00:00:00+00:00",
            ttl_seconds=None,
            expires_at_utc=None,
        )
        self.assertIs(self.store._conn, first)

    def test_pointer_store_close_blocks_further_use(self) -> None:
        self.store.close()
        self.store.close()  # idempotent
        with self.assertRaises(RuntimeError):
            self.store.retrieve_pointer("ptr_missing")


if __name__ == "__main__":
    unittest.main()
