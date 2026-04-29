"""Compatibility shim. Use ``eap.protocol.storage.sqlite_store`` instead."""
from __future__ import annotations

from eap.protocol.storage.sqlite_store import *  # noqa: F401,F403
