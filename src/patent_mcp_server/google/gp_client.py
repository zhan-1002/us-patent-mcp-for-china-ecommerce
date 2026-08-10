"""
Google Patents XHR API Client.

Provides async access to patents.google.com/xhr/query for design and utility
patent search.

Google Patents has no public API — the /xhr/query endpoint is the internal
AJAX endpoint used by the patents.google.com web frontend.  To avoid being
blocked as a bot the client must:

1. Visit the home page first to obtain session cookies (like PPUBS).
2. Use a browser User-Agent string — "patent-mcp-server/…" is an instant
   block on Google's side.
3. Set ``X-Requested-With: XMLHttpRequest`` and a correct ``Referer`` so
   the XHR endpoint sees a legitimate in-page AJAX call.

Rate limiting remains critical even with browser-like headers: Google issues
503 IP bans after ~9 rapid requests.  A 2 s minimum interval is enforced.
"""

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import Any, Optional, Dict, List
from urllib.parse import quote

import httpx

from patent_mcp_server.config import config
from patent_mcp_server.util.errors import ApiError

logger = logging.getLogger("google_patents")

# ---------------------------------------------------------------------------
# Browser-like defaults (Google blocks non-browser User-Agent strings)
# ---------------------------------------------------------------------------

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_BROWSER_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8"
)

_BROWSER_ACCEPT_LANGUAGE = "en-US,en;q=0.9"

# ---------------------------------------------------------------------------
# Patent-number format helpers
# ---------------------------------------------------------------------------

# US D1066113 S → D1066113  /  US 12345678 S → 12345678
_PPUBS_PN_RE = re.compile(r"^US\s+([A-Z]?\d+)\s+[A-Z]\d*$")

# USD1066113S1 → D1066113  /  US12345678B2 → 12345678
_GOOGLE_PN_RE = re.compile(r"^US([A-Z]?\d+)[A-Z]\d*$")

# D1066113 (design) or 12345678 (utility)
_PLAIN_PN_RE = re.compile(r"^[A-Z]?\d+$")


def google_to_plain(pn: str) -> str:
    """Convert Google format to plain: USD1066113S1 → D1066113, US12345678B2 → 12345678."""
    pn = pn.strip()
    m = _GOOGLE_PN_RE.match(pn)
    if m:
        return m.group(1)
    # Already plain or unknown format — return as-is after stripping US prefix
    if pn.startswith("US"):
        pn = pn[2:]
    return pn


def plain_to_google(pn: str, kind: str = "") -> str:
    """Convert plain to Google format: D1066113 → USD1066113S1, 12345678 → US12345678B2.

    *kind* defaults to ``"S1"`` for design patents and ``"B2"`` for utility.
    """
    pn = pn.strip()
    if pn.startswith("US"):
        return pn  # already Google format
    if not kind:
        kind = "S1" if _is_design_plain(pn) else "B2"
    return f"US{pn}{kind}"


def ppubs_to_plain(pn: str) -> str:
    """Convert PPUBS format to plain: US D1066113 S → D1066113, US 12345678 S → 12345678."""
    pn = pn.strip()
    m = _PPUBS_PN_RE.match(pn)
    if m:
        return m.group(1)
    return pn


def _is_design_plain(pn: str) -> bool:
    """Return True if *pn* is a plain design patent number (starts with a letter)."""
    pn = pn.strip()
    return bool(pn) and pn[0].isalpha()


def plain_to_ppubs(pn: str) -> str:
    """Convert plain patent number to PPUBS format: D1066113 → US D1066113 S."""
    pn = pn.strip()
    if pn.startswith("US "):
        return pn  # already PPUBS format
    return f"US {pn} S"


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    if not text:
        return ""
    return _HTML_TAG_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# GooglePatentsClient
# ---------------------------------------------------------------------------

class GooglePatentsClient:
    """Async HTTP client for patents.google.com XHR API.

    Usage::

        async with GooglePatentsClient() as gp:
            results = await gp.search("wooden cross", type_filter="DESIGN")
            detail  = await gp.get_patent("D656429S")
    """

    def __init__(self):
        self._semaphore = asyncio.Semaphore(1)
        self._last_request_time: float = 0.0
        self._session_ready: bool = False

        # Browser-like base headers for the home page
        self._page_headers = {
            "User-Agent": _BROWSER_UA,
            "Accept": _BROWSER_ACCEPT,
            "Accept-Language": _BROWSER_ACCEPT_LANGUAGE,
        }

        self.client = httpx.AsyncClient(
            headers=self._page_headers,
            http2=False,
            follow_redirects=True,
            timeout=getattr(config, "GP_REQUEST_TIMEOUT", 30.0),
        )

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _ensure_session(self) -> bool:
        """Visit the Google Patents home page to obtain session cookies.

        Google sets tracking / bot-detection cookies on the first page load.
        Without them the XHR endpoint reliably returns 503 even from a
        clean IP with a browser User-Agent.

        Returns:
            ``True`` if the home page was successfully reached (any HTTP status),
            ``False`` if a connection-level error occurred (DNS, timeout, etc.).
        """
        if self._session_ready:
            return True

        logger.info("Establishing Google Patents session (visiting home page)")
        try:
            response = await self.client.get(
                f"{config.GP_BASE_URL}/",
                headers=self._page_headers,
            )
            logger.debug(
                "Home page: HTTP %d, cookies=%d",
                response.status_code,
                len(self.client.cookies),
            )
            # 200 or even a redirect/error page — we just need the cookies.
            self._session_ready = True
            return True
        except Exception as exc:
            logger.warning("Home-page visit failed (%s); continuing anyway", exc)
            self._session_ready = True  # don't keep retrying
            return False

    def _xhr_headers(self) -> Dict[str, str]:
        """Return headers that mimic an in-page XHR request."""
        return {
            "User-Agent": _BROWSER_UA,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": _BROWSER_ACCEPT_LANGUAGE,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{config.GP_BASE_URL}/",
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def _throttle(self):
        """Enforce minimum interval between requests.

        Uses a semaphore to serialise all requests plus a wall-clock delay
        of ``GP_REQUEST_DELAY`` seconds (default 2.0).  This is the primary
        defence against Google's aggressive 503 rate-limiting.
        """
        async with self._semaphore:
            now = time.monotonic()
            delay = getattr(config, "GP_REQUEST_DELAY", 2.0)
            wait = delay - (now - self._last_request_time)
            if wait > 0:
                logger.debug("Throttling: waiting %.1fs", wait)
                await asyncio.sleep(wait)
            try:
                yield
            finally:
                self._last_request_time = time.monotonic()

    # ------------------------------------------------------------------
    # Core API methods
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        type_filter: str = "DESIGN",
        limit: int = 20,
        offset: int = 0,
        country: str = "US",
        language: str = "ENGLISH",
    ) -> Dict[str, Any]:
        """Search patents on Google Patents.

        Args:
            query: Search query (supports quotes, AND/OR).
            type_filter: ``"DESIGN"``, ``"PATENT"``, or ``"ANY"`` (no filter).
            limit: Results per page (max ~100).
            offset: 0-based offset into results.
            country: Country code filter (default ``"US"``).
            language: Language filter (default ``"ENGLISH"``).

        Returns:
            ``{"success": True, "total": N, "results": [...], ...}``
            or an error dict (``{"error": True, ...}``).
        """
        # Build the inner query params
        params = {
            "q": query,
            "country": country,
            "language": language,
        }
        if type_filter and type_filter.upper() != "ANY":
            params["type"] = type_filter.upper()
        if limit:
            params["num"] = str(limit)
        if offset:
            # Google uses 'page' not 'offset' — compute page from offset/limit
            params["page"] = str(offset // max(limit, 1))

        inner = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
        url = f"{config.GP_BASE_URL}/xhr/query?url={quote(inner)}"

        logger.info("Google Patents search: q=%r type=%r limit=%d offset=%d",
                     query, type_filter, limit, offset)

        try:
            # Ensure we have session cookies from the home page
            await self._ensure_session()

            async with self._throttle():
                response = await self.client.get(url, headers=self._xhr_headers())

            if response.status_code == 503:
                logger.warning("503 — likely rate-limited; waiting 90s and retrying once")
                await asyncio.sleep(90)
                async with self._throttle():
                    response = await self.client.get(url, headers=self._xhr_headers())
                if response.status_code == 503:
                    return ApiError.create(
                        message="Google Patents is rate-limiting this IP. "
                                "Please wait 30-120 minutes before retrying.",
                        status_code=503,
                    )

            if response.status_code != 200:
                return ApiError.create(
                    message=response.text[:500],
                    status_code=response.status_code,
                )

            data = response.json()
        except httpx.TimeoutException:
            return ApiError.create(
                message="Google Patents request timed out. Try again later.",
                status_code=408,
            )
        except Exception as exc:
            return ApiError.from_exception(exc, "Google Patents search failed")

        return self._normalize_search_response(data, query, type_filter, limit, offset)

    async def get_patent(self, patent_number: str) -> Dict[str, Any]:
        """Fetch a single patent's detail from Google Patents.

        Uses the XHR search endpoint with an exact publication-number query.
        This returns the full ``patent`` object including abstract, CPC codes,
        citations, images, and legal-status information.

        Args:
            patent_number: Patent number in any format (Google, plain, or PPUBS).

        Returns:
            ``{"success": True, "patent": {...}}`` or error dict.
        """
        plain = google_to_plain(patent_number)

        # Use the search endpoint with exact number match
        params = {
            "q": f'"{plain}"',
            "country": "US",
            "language": "ENGLISH",
            "num": "10",
        }
        inner = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
        url = f"{config.GP_BASE_URL}/xhr/query?url={quote(inner)}"

        logger.info("Google Patents get_patent: %s", patent_number)

        try:
            # Ensure we have session cookies from the home page
            await self._ensure_session()

            async with self._throttle():
                response = await self.client.get(url, headers=self._xhr_headers())

            if response.status_code != 200:
                return ApiError.create(
                    message=response.text[:500],
                    status_code=response.status_code,
                )

            data = response.json()
        except Exception as exc:
            return ApiError.from_exception(exc, "Google Patents get_patent failed")

        # Extract the matching patent from search results
        patents = self._flatten_results(data)
        target = plain_to_google(plain)

        for p in patents:
            pn = p.get("publication_number", "")
            if google_to_plain(pn) == plain:
                # Clean up the patent object
                patent = dict(p)
                patent["title"] = _strip_html(patent.get("title", ""))
                patent["abstract"] = _strip_html(patent.get("abstract", ""))
                return {"success": True, "patent": patent}

        return ApiError.not_found("Patent", patent_number)

    async def get_similar(self, patent_number: str, limit: int = 10) -> Dict[str, Any]:
        """Get similar patents via Google Patents classification search.

        Strategy (tried in priority order):
        1. Single CPC code search — most precise, stays within the patent's
           primary classification.
        2. Title keyword search — fallback for patents with narrow/missing
           CPC codes.

        Design patents are detected automatically and the type filter is
        set to ``DESIGN`` so results stay in the same patent type.

        Args:
            patent_number: Source patent number.
            limit: Max similar patents to return.

        Returns:
            ``{"success": True, "source_patent": ..., "similar": [...], ...}``
            or error dict.
        """
        # First, get the source patent detail
        detail = await self.get_patent(patent_number)
        if detail.get("error"):
            return detail

        patent = detail["patent"]

        # Extract CPC codes (up to 3) for classification search
        cpc_codes = patent.get("cpc_classification", [])
        codes: list = []
        for c in cpc_codes[:3]:
            if isinstance(c, str):
                codes.append(c)
            elif isinstance(c, dict):
                code = c.get("code", "")
                if code:
                    codes.append(code)

        source_pn = patent.get("publication_number", "")
        title = patent.get("title", "")

        # Detect design patent to stay in the same type
        is_design = bool(source_pn) and source_pn.startswith("USD")
        type_filter = "DESIGN" if is_design else "ANY"

        def _exclude_source(results_dict):
            """Filter out the source patent from a result set."""
            raw = results_dict.get("results", [])
            return [
                r for r in raw
                if r.get("pn", "") != google_to_plain(source_pn)
            ][:limit]

        # --- Strategy 1: single CPC code search ---
        if codes:
            cpc_query = f'cpc:"{codes[0]}"'
            logger.debug("get_similar CPC query: %s  type=%s", cpc_query, type_filter)
            cpc_results = await self.search(
                query=cpc_query, type_filter=type_filter, limit=limit + 1,
            )
            if not cpc_results.get("error"):
                filtered = _exclude_source(cpc_results)
                if filtered:
                    return {
                        "success": True,
                        "source_patent": patent,
                        "similar": filtered,
                        "total": len(filtered),
                        "method": "cpc_search",
                        "cpc_code_used": codes[0],
                        "query_used": cpc_query,
                        "type_filter": type_filter,
                    }

        # --- Strategy 2: title keyword fallback ---
        if title:
            keywords = " ".join(title.split()[:5])
            logger.debug("get_similar title fallback: %r  type=%s", keywords, type_filter)
            title_results = await self.search(
                query=keywords, type_filter=type_filter, limit=limit + 1,
            )
            if not title_results.get("error"):
                filtered = _exclude_source(title_results)
                return {
                    "success": True,
                    "source_patent": patent,
                    "similar": filtered,
                    "total": len(filtered),
                    "method": "title_keyword_fallback",
                    "query_used": keywords,
                    "type_filter": type_filter,
                }

        # --- Nothing found ---
        return {
            "success": True,
            "source_patent": patent,
            "similar": [],
            "total": 0,
            "method": "exhausted",
            "hint": (
                "No similar patents found via CPC classification search "
                "or title keyword search. The patent may be in a very "
                "narrow classification or use uncommon terminology."
            ),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize_search_response(
        self,
        raw: Dict[str, Any],
        query: str,
        type_filter: str,
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        """Convert raw Google Patents JSON to a standardised result dict."""
        results_data = raw.get("results", {})
        total = results_data.get("total_num_results", 0)
        patents = self._flatten_results(raw)

        normalized = []
        for p in patents:
            normalized.append({
                "pn": google_to_plain(p.get("publication_number", "")),
                "google_pn": p.get("publication_number", ""),
                "title": _strip_html(p.get("title", "")),
                "date": p.get("publication_date", ""),
                "assignee": p.get("assignee", ""),
                "inventor": p.get("inventor", ""),
                "thumbnail_url": p.get("thumbnail", ""),
                "abstract": _strip_html(p.get("abstract", "")),
                "cpc_codes": p.get("cpc_classification", []),
                "url": f"https://patents.google.com/patent/{p.get('publication_number', '')}/en",
            })

        return {
            "success": True,
            "source": "google_patents",
            "query": query,
            "type_filter": type_filter,
            "count": len(normalized),
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(normalized)) < total,
            "results": normalized,
            "metadata": {
                "google_total": total,
            },
        }

    @staticmethod
    def _flatten_results(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Flatten the nested cluster→result→patent structure into a list."""
        patents = []
        clusters = raw.get("results", {}).get("cluster", [])
        for cluster in clusters:
            for item in cluster.get("result", []):
                patent = item.get("patent", {})
                if patent:
                    patents.append(patent)
        return patents

    async def close(self):
        """Close the underlying HTTP client."""
        logger.info("Closing Google Patents client connections")
        await self.client.aclose()
