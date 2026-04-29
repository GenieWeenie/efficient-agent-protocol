"""Compatibility shim. Use ``eap.protocol.storage.postgres_store`` instead."""
from __future__ import annotations

from eap.protocol.storage.postgres_store import *  # noqa: F401,F403
