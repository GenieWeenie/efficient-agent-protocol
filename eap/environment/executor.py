import asyncio

from environment.executor import AsyncLocalExecutor as _AsyncLocalExecutor

AsyncLocalExecutor = _AsyncLocalExecutor


class LocalExecutor(_AsyncLocalExecutor):
    """Sync compatibility wrapper for older examples."""

    def execute_macro(self, macro):
        return asyncio.run(super().execute_macro(macro))


__all__ = ["AsyncLocalExecutor", "LocalExecutor"]
