from __future__ import annotations

from typing import Optional, Sequence

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)


class BoundedHTTPClient:
    """Reusable requests client with pooling, explicit timeouts, and bounded retries."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        connect_timeout_seconds: Optional[float] = None,
        max_retries: int = 2,
        backoff_factor: float = 0.25,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
        retry_status_codes: Sequence[int] = DEFAULT_RETRY_STATUS_CODES,
        session: Optional[requests.Session] = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        resolved_connect_timeout = connect_timeout_seconds
        if resolved_connect_timeout is None:
            resolved_connect_timeout = min(5.0, float(timeout_seconds))
        if resolved_connect_timeout <= 0:
            raise ValueError("connect_timeout_seconds must be > 0")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if backoff_factor < 0:
            raise ValueError("backoff_factor must be >= 0")

        self.timeout = (float(resolved_connect_timeout), float(timeout_seconds))
        self._owns_session = session is None
        self._session = session or requests.Session()
        if session is None:
            retry = Retry(
                total=max_retries,
                connect=max_retries,
                read=max_retries,
                status=max_retries,
                backoff_factor=backoff_factor,
                status_forcelist=tuple(retry_status_codes),
                allowed_methods=frozenset({"GET", "POST"}),
                raise_on_status=False,
                respect_retry_after_header=True,
            )
            adapter = HTTPAdapter(
                pool_connections=pool_connections,
                pool_maxsize=pool_maxsize,
                max_retries=retry,
            )
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)

    def post(self, url: str, **kwargs: object) -> requests.Response:
        if "timeout" not in kwargs or kwargs["timeout"] is None:
            kwargs["timeout"] = self.timeout
        return self._session.post(url, **kwargs)

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def __enter__(self) -> BoundedHTTPClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
