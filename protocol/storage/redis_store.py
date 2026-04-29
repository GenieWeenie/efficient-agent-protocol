"""Compatibility shim. Use ``eap.protocol.storage.redis_store`` instead."""
from __future__ import annotations

from eap.protocol.storage.redis_store import *  # noqa: F401,F403
