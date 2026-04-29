# environment/tools/web_tools.py
import ipaddress
import json
import logging
import os
import socket
import time
from typing import Dict, Iterable, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("eap.environment.tools.web_tools")

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MAX_BYTES = 1_000_000
DEFAULT_MAX_TEXT_CHARACTERS = 100_000
DEFAULT_MAX_LINKS = 200
DEFAULT_MAX_REDIRECTS = 5
_STREAM_CHUNK_SIZE = 64 * 1024
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def _normalize_host(host: str) -> str:
    return host.strip().lower().rstrip(".")


def _load_host_allowlist(extra_allowlist: Optional[Iterable[str]] = None) -> Set[str]:
    raw_hosts = os.environ.get("EAP_WEB_TOOL_HOST_ALLOWLIST", "")
    hosts = {_normalize_host(host) for host in raw_hosts.split(",") if host.strip()}
    if extra_allowlist:
        hosts.update(_normalize_host(host) for host in extra_allowlist if host.strip())
    return hosts


def _is_unsafe_ip(address: str) -> bool:
    parsed = ipaddress.ip_address(address)
    return (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_reserved
        or parsed.is_multicast
        or parsed in _CGNAT_NETWORK
    )


def _validate_safe_url(url: str, host_allowlist: Optional[Iterable[str]] = None) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or not parsed.hostname:
        raise ValueError(f"Invalid URL '{url}'. URL must include http/https scheme and host.")

    host = _normalize_host(parsed.hostname)
    allowlist = _load_host_allowlist(host_allowlist)
    if host in allowlist:
        return

    try:
        address_infos = socket.getaddrinfo(host, parsed.port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"URL host '{host}' could not be resolved safely.") from exc

    resolved_addresses = {info[4][0] for info in address_infos if info and info[4]}
    if not resolved_addresses:
        raise ValueError(f"URL host '{host}' did not resolve to any address.")

    for address in resolved_addresses:
        if address in allowlist:
            continue
        try:
            if _is_unsafe_ip(address):
                raise ValueError(f"URL host '{host}' resolved to disallowed address '{address}'.")
        except ValueError:
            raise


def _response_text(response: requests.Response, body_bytes: bytes) -> str:
    if response.encoding:
        return body_bytes.decode(response.encoding, errors="replace")
    return body_bytes.decode("utf-8", errors="replace")


def _read_streaming_body(response: requests.Response, max_bytes: int, deadline: float) -> bytes:
    body = bytearray()
    for chunk in response.iter_content(chunk_size=_STREAM_CHUNK_SIZE):
        if time.monotonic() > deadline:
            raise TimeoutError("Response body streaming exceeded timeout_seconds budget.")
        if not chunk:
            continue
        body.extend(chunk)
        if len(body) > max_bytes:
            raise ValueError(f"Response body exceeds max_bytes={max_bytes}.")
    return bytes(body)


def _load_text_response(
    url: str,
    timeout_seconds: int,
    max_bytes: int,
    headers: Optional[Dict[str, str]] = None,
    host_allowlist: Optional[Iterable[str]] = None,
) -> str:
    if timeout_seconds < 1:
        raise ValueError("'timeout_seconds' must be >= 1.")
    if max_bytes < 1:
        raise ValueError("'max_bytes' must be >= 1.")

    current_url = url
    request_headers = dict(headers or {})
    deadline = time.monotonic() + float(timeout_seconds * 2)

    with requests.Session() as session:
        for redirect_count in range(DEFAULT_MAX_REDIRECTS + 1):
            _validate_safe_url(current_url, host_allowlist=host_allowlist)
            if time.monotonic() > deadline:
                raise TimeoutError("HTTP request exceeded timeout_seconds budget before completion.")

            response = session.get(
                current_url,
                timeout=timeout_seconds,
                headers=request_headers,
                stream=True,
                allow_redirects=False,
            )
            try:
                if response.is_redirect or response.is_permanent_redirect:
                    if redirect_count >= DEFAULT_MAX_REDIRECTS:
                        raise ValueError(f"Too many redirects fetching URL '{url}'.")
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError(f"Redirect response for URL '{current_url}' omitted Location header.")
                    current_url = urljoin(current_url, location)
                    continue

                response.raise_for_status()
                body_bytes = _read_streaming_body(response, max_bytes=max_bytes, deadline=deadline)
                return _response_text(response, body_bytes)
            finally:
                response.close()

    raise ValueError(f"Too many redirects fetching URL '{url}'.")


def scrape_url(
    url: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_characters: int = DEFAULT_MAX_TEXT_CHARACTERS,
    host_allowlist: Optional[Iterable[str]] = None,
) -> str:
    """Fetches and cleans text content from a URL."""
    logger.info(
        "tool invoked",
        extra={"tool_name": "scrape_url"},
    )
    _validate_safe_url(url, host_allowlist=host_allowlist)
    if max_characters < 1:
        raise ValueError("'max_characters' must be >= 1.")

    try:
        text_html = _load_text_response(
            url,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            host_allowlist=host_allowlist,
        )
        soup = BeautifulSoup(text_html, "html.parser")

        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()

        text = soup.get_text(separator=" ")
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        cleaned = "\n".join(chunk for chunk in chunks if chunk)
        if len(cleaned) > max_characters:
            cleaned = cleaned[:max_characters]
        return cleaned
    except requests.RequestException as exc:
        raise RuntimeError(f"Error scraping URL '{url}': {str(exc)}") from exc
    except Exception as exc:
        raise RuntimeError(f"Error scraping URL '{url}': {str(exc)}") from exc


def fetch_json_url(
    url: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    host_allowlist: Optional[Iterable[str]] = None,
) -> str:
    """Fetches a URL and returns parsed JSON as pretty-printed text."""
    logger.info(
        "tool invoked",
        extra={"tool_name": "fetch_json_url"},
    )
    _validate_safe_url(url, host_allowlist=host_allowlist)

    try:
        body_text = _load_text_response(
            url,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            headers={"Accept": "application/json"},
            host_allowlist=host_allowlist,
        )
        parsed = json.loads(body_text)
        return json.dumps(parsed, indent=2, sort_keys=True)
    except requests.RequestException as exc:
        raise RuntimeError(f"Error fetching JSON URL '{url}': {str(exc)}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Error fetching JSON URL '{url}': response was not valid JSON.") from exc
    except Exception as exc:
        raise RuntimeError(f"Error fetching JSON URL '{url}': {str(exc)}") from exc


def extract_links_from_url(
    url: str,
    same_domain_only: bool = False,
    include_text: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_links: int = DEFAULT_MAX_LINKS,
    host_allowlist: Optional[Iterable[str]] = None,
) -> str:
    """Extracts normalized links from a webpage and returns JSON metadata."""
    logger.info(
        "tool invoked",
        extra={"tool_name": "extract_links_from_url"},
    )
    _validate_safe_url(url, host_allowlist=host_allowlist)
    if max_links < 1:
        raise ValueError("'max_links' must be >= 1.")

    try:
        source_domain = urlparse(url).netloc
        html = _load_text_response(
            url,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            host_allowlist=host_allowlist,
        )
        soup = BeautifulSoup(html, "html.parser")

        links = []
        seen_urls = set()
        truncated = False

        for anchor in soup.find_all("a", href=True):
            normalized = urljoin(url, anchor["href"]).strip()
            parsed = urlparse(normalized)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                continue
            if same_domain_only and parsed.netloc != source_domain:
                continue
            if normalized in seen_urls:
                continue

            seen_urls.add(normalized)
            if len(links) >= max_links:
                truncated = True
                break
            entry = {"url": normalized}
            if include_text:
                entry["text"] = anchor.get_text(strip=True)
            links.append(entry)

        payload = {
            "source_url": url,
            "same_domain_only": same_domain_only,
            "include_text": include_text,
            "max_links": max_links,
            "truncated": truncated,
            "link_count": len(links),
            "links": links,
        }
        return json.dumps(payload)
    except requests.RequestException as exc:
        raise RuntimeError(f"Error extracting links from URL '{url}': {str(exc)}") from exc
    except Exception as exc:
        raise RuntimeError(f"Error extracting links from URL '{url}': {str(exc)}") from exc


SCRAPE_SCHEMA = {
    "name": "scrape_url",
    "description": "Fetches a URL and returns cleaned page text.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "minLength": 1,
                "description": "The full URL to scrape (e.g., https://example.com).",
            },
            "timeout_seconds": {
                "type": "integer",
                "minimum": 1,
                "maximum": 120,
                "description": "HTTP timeout for the request.",
            },
            "max_bytes": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10000000,
                "description": "Maximum response size in bytes before failing.",
            },
            "max_characters": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500000,
                "description": "Maximum cleaned text characters to return.",
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    },
}

FETCH_JSON_SCHEMA = {
    "name": "fetch_json_url",
    "description": "Fetches JSON from a URL and returns pretty-printed JSON text.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "minLength": 1,
                "description": "The full URL to fetch JSON from.",
            },
            "timeout_seconds": {
                "type": "integer",
                "minimum": 1,
                "maximum": 120,
                "description": "HTTP timeout for the request.",
            },
            "max_bytes": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10000000,
                "description": "Maximum response size in bytes before failing.",
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    },
}

EXTRACT_LINKS_SCHEMA = {
    "name": "extract_links_from_url",
    "description": "Extracts normalized links from a webpage and returns JSON metadata.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "minLength": 1,
                "description": "The full URL to extract links from.",
            },
            "same_domain_only": {
                "type": "boolean",
                "description": "If true, only include links on the source domain.",
            },
            "include_text": {
                "type": "boolean",
                "description": "If true, include anchor text for each link.",
            },
            "timeout_seconds": {
                "type": "integer",
                "minimum": 1,
                "maximum": 120,
                "description": "HTTP timeout for the request.",
            },
            "max_bytes": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10000000,
                "description": "Maximum response size in bytes before failing.",
            },
            "max_links": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5000,
                "description": "Maximum number of links to return.",
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    },
}
