# Storage Backends

EAP pointer vault persistence is backend-pluggable via `PointerStoreBackend` in `protocol/storage/base.py`.

## Available Backends

### SQLite (default)
- Class: `SQLitePointerStore`
- File: `protocol/storage/sqlite_store.py`
- Behavior:
  - Local file persistence using `agent_state.db` by default.
  - Automatic lifecycle column migration (`created_at_utc`, `ttl_seconds`, `expires_at_utc`).

### Redis
- Class: `RedisPointerStore`
- File: `protocol/storage/redis_store.py`
- Dependency: `redis` (`pip install redis`)
- Behavior:
  - Stores each pointer as a Redis hash.
  - Tracks pointer IDs in a Redis set for listing.
  - Lifecycle cleanup (`list_expired_pointers`, `cleanup_expired_pointers`) uses backend contract defaults.

### PostgreSQL
- Class: `PostgresPointerStore`
- File: `protocol/storage/postgres_store.py`
- Dependency: `psycopg` (`pip install psycopg[binary]`)
- Behavior:
  - Creates table `public.eap_state_store` by default.
  - Persists metadata as `JSONB`.
  - Uses `TIMESTAMPTZ` for lifecycle fields.

## Backend Contract

All backends implement:
- `initialize()`
- `store_pointer(...)`
- `retrieve_pointer(pointer_id)`
- `list_pointers(include_expired=True, now_utc=None, limit=None)`
- `delete_pointer(pointer_id)`

Shared helper behavior in the base contract:
- `list_expired_pointers(now_utc=None, limit=None)`
- `cleanup_expired_pointers(now_utc=None, limit=None)`

## Wiring a Backend

`StateManager` accepts an injected backend:

```python
from eap.protocol import StateManager, RedisPointerStore

store = RedisPointerStore(redis_url="redis://localhost:6379/0")
manager = StateManager(pointer_store=store)
```

```python
from eap.protocol import PostgresPointerStore, StateManager

store = PostgresPointerStore(dsn="postgresql://user:pass@localhost:5432/eap")
manager = StateManager(pointer_store=store)
```

## Migration Notes (SQLite -> PostgreSQL)

1. Create a PostgreSQL backend and initialize schema:
   - `PostgresPointerStore(...).initialize()`
2. Read existing SQLite pointers with lifecycle metadata:
   - `sqlite_manager.list_pointers(include_expired=True)`
3. For each pointer:
   - Read raw payload via `sqlite_manager.retrieve(pointer_id)`
   - Write to PostgreSQL via `store_pointer(...)` with the same metadata/lifecycle fields.
4. Validate parity:
   - Count pointers on both stores.
   - Spot-check `retrieve_pointer`, TTL fields, and expired filtering behavior.
5. Switch runtime configuration to inject `PostgresPointerStore` into `StateManager`.

## Operational Notes

- `StateManager` still uses SQLite for execution traces and conversation history in this phase.
- Only pointer vault persistence is backend-pluggable here.
