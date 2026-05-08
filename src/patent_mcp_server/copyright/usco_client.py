"""
US Copyright Office (USCO) Query Module

This module provides tools for querying the US Copyright Office database
to check copyright registrations for visual arts, sculptures, and other works.

Note: USCO does not provide a public API, so this module uses web scraping
techniques on the public catalog at cocatalog.loc.gov

Copyright Categories (VA - Visual Arts):
- VA000: Visual Art Works - General
- VA010: Sculpture
- VA020: Painting
- VA030: Drawing
- VA040: Photograph
- VA050: Graphic Art
- VA060: Print/Published Art
"""

import asyncio
import re
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

from patent_mcp_server.util.errors import ApiError
from patent_mcp_server.config import config

logger = logging.getLogger('usco_client')


class UscoClient:
    """Client for the US Copyright Office public catalog."""

    BASE_URL = "https://cocatalog.loc.gov"
    SEARCH_URL = f"{BASE_URL}/vwebv/searchBasic"
    RESULTS_URL = f"{BASE_URL}/vwebv/search"

    # Visual Arts category codes
    VA_CATEGORIES = {
        "VA000": "Visual Art Works - General",
        "VA010": "Sculpture",
        "VA020": "Painting",
        "VA030": "Drawing",
        "VA040": "Photograph",
        "VA050": "Graphic Art",
        "VA060": "Print/Published Art",
    }

    def __init__(self):
        self.headers = {
            "User-Agent": config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.client = httpx.AsyncClient(
            headers=self.headers,
            follow_redirects=True,
            timeout=60.0,
        )

    async def close(self):
        await self.client.aclose()

    async def search_by_title(
        self,
        title: str,
        category: Optional[str] = "VA010",  # Sculpture by default
        limit: int = 25,
    ) -> Dict[str, Any]:
        """Search copyright registrations by title.

        Args:
            title: Work title to search
            category: Category code (VA010 for sculpture)
            limit: Max results

        Returns:
            Dictionary with search results
        """
        try:
            # Note: USCO requires session-based browsing
            # This is a simplified approach

            params = {
                "searchArg1": title,
                "searchCode1": "TALL",  # Title - All
                "searchType1": "keyword",
                "searchArg2": "",
                "searchCode2": "NONE",
                "searchType2": "",
                "searchLogic": "AND",
                "yearFrom": "",
                "yearTo": "",
                "docType": category or "",
                "maxRecordsPerPage": str(limit),
                "searchSortOrder": "DATE",
                "page": "1",
            }

            response = await self.client.get(self.SEARCH_URL, params=params)

            if response.status_code != 200:
                return ApiError.create(
                    message=f"USCO search failed: {response.status_code}",
                    status_code=response.status_code
                )

            # Parse HTML response
            results = self._parse_search_results(response.text)

            return {
                "success": True,
                "source": "US Copyright Office",
                "query": title,
                "category": self.VA_CATEGORIES.get(category, "All"),
                "total_results": len(results),
                "results": results,
            }

        except Exception as e:
            logger.error(f"USCO search error: {str(e)}")
            return ApiError.from_exception(e, "USCO search failed")

    async def search_by_author(
        self,
        author_name: str,
        limit: int = 25,
    ) -> Dict[str, Any]:
        """Search copyright registrations by author name.

        Args:
            author_name: Author/creator name
            limit: Max results

        Returns:
            Dictionary with search results
        """
        try:
            params = {
                "searchArg1": author_name,
                "searchCode1": "AALL",  # Author - All
                "searchType1": "keyword",
                "searchArg2": "",
                "searchCode2": "NONE",
                "searchType2": "",
                "searchLogic": "AND",
                "yearFrom": "",
                "yearTo": "",
                "docType": "",
                "maxRecordsPerPage": str(limit),
                "searchSortOrder": "DATE",
                "page": "1",
            }

            response = await self.client.get(self.SEARCH_URL, params=params)

            if response.status_code != 200:
                return ApiError.create(
                    message=f"USCO search failed: {response.status_code}",
                    status_code=response.status_code
                )

            results = self._parse_search_results(response.text)

            return {
                "success": True,
                "source": "US Copyright Office",
                "query": author_name,
                "search_type": "author",
                "total_results": len(results),
                "results": results,
            }

        except Exception as e:
            logger.error(f"USCO search error: {str(e)}")
            return ApiError.from_exception(e, "USCO search failed")

    def _parse_search_results(self, html: str) -> List[Dict[str, Any]]:
        """Parse HTML search results from USCO catalog.

        Args:
            html: Raw HTML response

        Returns:
            List of parsed registration records
        """
        results = []

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # USCO results are in table format
            # Look for result entries
            result_rows = soup.find_all('tr', class_='resultRow')

            for row in result_rows:
                cells = row.find_all('td')
                if len(cells) >= 4:
                    record = {
                        'registration_number': cells[0].get_text(strip=True),
                        'title': cells[1].get_text(strip=True),
                        'author': cells[2].get_text(strip=True),
                        'registration_date': cells[3].get_text(strip=True),
                        'category': cells[4].get_text(strip=True) if len(cells) > 4 else '',
                    }
                    results.append(record)

            # Alternative parsing if no resultRow class
            if not results:
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows[1:]:  # Skip header
                        cells = row.find_all('td')
                        if len(cells) >= 3:
                            text = [c.get_text(strip=True) for c in cells]
                            if text[0] and text[0].startswith('VA'):  # VA registration number
                                results.append({
                                    'registration_number': text[0],
                                    'title': text[1] if len(text) > 1 else '',
                                    'author': text[2] if len(text) > 2 else '',
                                    'registration_date': text[3] if len(text) > 3 else '',
                                })

        except Exception as e:
            logger.warning(f"HTML parsing error: {str(e)}")

        return results

    async def check_copyright_status(
        self,
        title: str,
        author: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check copyright status of a work.

        Args:
            title: Work title
            author: Optional author name

        Returns:
            Copyright status information
        """
        results = []

        # Search by title
        title_search = await self.search_by_title(title)
        if title_search.get("success"):
            results.extend(title_search.get("results", []))

        # Search by author if provided
        if author:
            author_search = await self.search_by_author(author)
            if author_search.get("success"):
                results.extend(author_search.get("results", []))

        # Deduplicate by registration number
        unique_results = {}
        for r in results:
            reg_num = r.get("registration_number", "")
            if reg_num and reg_num not in unique_results:
                unique_results[reg_num] = r

        return {
            "success": True,
            "title_searched": title,
            "author_searched": author,
            "registrations_found": len(unique_results),
            "has_registered_copyright": len(unique_results) > 0,
            "registrations": list(unique_results.values()),
            "note": (
                "Note: Even if no registration is found, the work may still "
                "have automatic copyright protection under 17 U.S.C. §102. "
                "Registration is required for statutory damages and attorney fees."
            ),
        }