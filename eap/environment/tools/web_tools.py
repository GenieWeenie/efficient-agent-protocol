# environment/tools/web_tools.py
import json
import logging
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("eap.environment.tools.web_tools")

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MAX_BYTES = 1_000_000
DEFAULT_MAX_TEXT_CHARACTERS = 100_000
DEFAULT_MAX_LINKS = 200


def _validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Invalid URL '{url}'. URL must include http/https scheme and host.")


def _load_text_response(
    url: str,
    timeout_seconds: int,
    max_bytes: int,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    if timeout_seconds < 1:
        raise ValueError("'timeout_seconds' must be >= 1.")
    if max_bytes < 1:
        raise ValueError("'max_bytes' must be >= 1.")

    response = requests.get(url, timeout=timeout_seconds, headers=headers)
    response.raise_for_status()

    body_bytes = response.content
    if len(body_bytes) > max_bytes:
        raise ValueError(f"Response body exceeds max_bytes={max_bytes}.")

    if response.encoding:
        return body_bytes.decode(response.encoding, errors="replace")
    return body_bytes.decode("utf-8", errors="replace")


def scrape_url(
    url: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_characters: int = DEFAULT_MAX_TEXT_CHARACTERS,
) -> str:
    """Fetches and cleans text content from a URL."""
    logger.info(
        "tool invoked",
        extra={"tool_name": "scrape_url"},
    )
    _validate_http_url(url)
    if max_characters < 1:
        raise ValueError("'max_characters' must be >= 1.")

    try:
        text_html = _load_text_response(url, timeout_seconds=timeout_seconds, max_bytes=max_bytes)
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
) -> str:
    """Fetches a URL and returns parsed JSON as pretty-printed text."""
    logger.info(
        "tool invoked",
        extra={"tool_name": "fetch_json_url"},
    )
    _validate_http_url(url)

    try:
        body_text = _load_text_response(
            url,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            headers={"Accept": "application/json"},
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
) -> str:
    """Extracts normalized links from a webpage and returns JSON metadata."""
    logger.info(
        "tool invoked",
        extra={"tool_name": "extract_links_from_url"},
    )
    _validate_http_url(url)
    if max_links < 1:
        raise ValueError("'max_links' must be >= 1.")

    try:
        source_domain = urlparse(url).netloc
        html = _load_text_response(url, timeout_seconds=timeout_seconds, max_bytes=max_bytes)
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
