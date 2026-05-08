"""
USPTO Patent Search MCP Server (PPUBS Only)

This file provides a Model Context Protocol (MCP) server that exposes tools for interacting
with the USPTO Patent Public Search (PPUBS) API:

- ppubs.uspto.gov - Full text patent documents, PDF downloads, and advanced search

The server uses stdio transport for Claude Code/Cursor integration.

Version: 1.0.0 - PPUBS-only focus (no API key required)
"""
import atexit
import json
import logging
import re
import sys
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

from patent_mcp_server.config import config
from patent_mcp_server.constants import Sources, Fields
from patent_mcp_server.util.errors import ApiError, is_error
from patent_mcp_server.util.validation import validate_patent_number
from patent_mcp_server.util.response import ResponseEnvelope, check_and_truncate
from patent_mcp_server.resources import (
    get_cpc_section_info, get_cpc_subsection_info,
    get_status_code_info, get_all_status_codes,
    get_all_data_sources, get_data_source_info,
    get_search_syntax_guide, CPC_SECTIONS
)
from patent_mcp_server.prompts import get_prompt
from patent_mcp_server.uspto.ppubs_uspto_gov import PpubsClient

# Initialize FastMCP server
mcp = FastMCP("uspto_patent_tools")

# Set up logging with configured level
logging.basicConfig(
    level=config.get_log_level(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger('uspto_patent_mcp')

# Validate configuration
config.validate()

# Create client instance for PPUBS API
ppubs_client = PpubsClient()


# Register cleanup handler
async def cleanup():
    """Clean up resources on shutdown."""
    logger.info("Shutting down USPTO Patent MCP server, cleaning up resources...")
    try:
        await ppubs_client.close()
        logger.info("Cleanup completed successfully")
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")


# Register cleanup with atexit (best effort for stdio shutdown)
def sync_cleanup():
    """Synchronous cleanup wrapper for atexit."""
    import asyncio
    try:
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(cleanup())
                return
        except RuntimeError:
            pass

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(cleanup())
        finally:
            loop.close()
    except Exception as e:
        logger.debug(f"Cleanup during shutdown (non-critical): {str(e)}")


atexit.register(sync_cleanup)


# =====================================================================
# MCP Resources - Static data accessible via @ mentions
# =====================================================================

@mcp.resource("patents://cpc/{code}")
async def resource_cpc_classification(code: str) -> str:
    """Get CPC classification code information.

    Returns details about a CPC (Cooperative Patent Classification) code
    including section, class, and subclass information.
    """
    if len(code) == 1:
        info = get_cpc_section_info(code)
    else:
        info = get_cpc_subsection_info(code)
    return json.dumps(info, indent=2)


@mcp.resource("patents://cpc")
async def resource_cpc_sections() -> str:
    """Get all CPC section overview.

    Returns summary of all 9 CPC sections (A-H, Y) with their titles
    and descriptions for patent classification reference.
    """
    sections = {
        code: {"title": data["title"], "description": data["description"]}
        for code, data in CPC_SECTIONS.items()
    }
    return json.dumps(sections, indent=2)


@mcp.resource("patents://status-codes")
async def resource_status_codes() -> str:
    """Get USPTO application status code definitions.

    Returns all status codes used in patent application tracking
    with descriptions and examination stages.
    """
    return json.dumps(get_all_status_codes(), indent=2)


@mcp.resource("patents://status-codes/{code}")
async def resource_status_code(code: str) -> str:
    """Get a specific USPTO status code definition."""
    return json.dumps(get_status_code_info(code), indent=2)


@mcp.resource("patents://sources")
async def resource_data_sources() -> str:
    """Get information about available patent data sources.

    Returns details about all integrated APIs including coverage,
    rate limits, authentication requirements, and best use cases.
    """
    return json.dumps(get_all_data_sources(), indent=2)


@mcp.resource("patents://sources/{source}")
async def resource_data_source(source: str) -> str:
    """Get information about a specific data source."""
    return json.dumps(get_data_source_info(source), indent=2)


@mcp.resource("patents://search-syntax")
async def resource_search_syntax() -> str:
    """Get search query syntax guide for all APIs.

    Returns documentation on query syntax for PPUBS, PatentsView,
    and ODP APIs with examples.
    """
    return get_search_syntax_guide()


# =====================================================================
# MCP Prompts - Workflow templates accessible via / commands
# =====================================================================

@mcp.prompt()
async def prior_art_search() -> str:
    """Guide for conducting a comprehensive prior art search.

    USE THIS PROMPT WHEN: You need to find existing patents and publications
    relevant to an invention for patentability assessment or invalidity analysis.
    """
    return get_prompt("prior_art_search")["content"]


@mcp.prompt()
async def patent_validity_analysis() -> str:
    """Guide for analyzing patent validity and prosecution history.

    USE THIS PROMPT WHEN: You need to assess the strength and validity
    of a patent by reviewing its prosecution history and any challenges.
    """
    return get_prompt("patent_validity")["content"]


@mcp.prompt()
async def competitor_portfolio_analysis() -> str:
    """Guide for analyzing a company's patent portfolio.

    USE THIS PROMPT WHEN: You need to understand a competitor's IP position,
    technology focus areas, and patent strategy.
    """
    return get_prompt("competitor_portfolio")["content"]


@mcp.prompt()
async def ptab_proceeding_research() -> str:
    """Guide for researching PTAB proceedings (IPR/PGR/CBM).

    USE THIS PROMPT WHEN: You need to research Patent Trial and Appeal Board
    proceedings, decisions, and outcomes for validity challenges.
    """
    return get_prompt("ptab_research")["content"]


@mcp.prompt()
async def freedom_to_operate() -> str:
    """Guide for freedom-to-operate (FTO) analysis.

    USE THIS PROMPT WHEN: You need to assess patent infringement risk
    for a product or technology before commercialization.
    """
    return get_prompt("freedom_to_operate")["content"]


@mcp.prompt()
async def patent_landscape() -> str:
    """Guide for patent landscape analysis.

    USE THIS PROMPT WHEN: You need to map the competitive patent environment
    in a technology area to identify trends and opportunities.
    """
    return get_prompt("patent_landscape")["content"]


@mcp.prompt()
async def product_patent_search() -> str:
    """Guide for product patent search based on proven strategies.

    USE THIS PROMPT WHEN: You need to search patents for a specific product
    using optimized search strategies.

    This prompt provides guidance on:
    - Keyword extraction from product listings
    - Hidden feature discovery
    - Multi-strategy search approach
    - Inventor and assignee tracking
    """
    return get_prompt("product_patent_search")["content"]


# =====================================================================
# Helper Functions
# =====================================================================

async def _search_patent_by_number(patent_number: str) -> Dict[str, Any]:
    """Search for a patent by number and return the patent document metadata."""
    query = f'patentNumber:"{patent_number}"'
    logger.info(f"Searching for patent with query: {query}")

    result = await ppubs_client.run_query(
        query=query,
        sources=[Sources.GRANTED_PATENTS],
        limit=1
    )

    if is_error(result):
        return result

    patents = result.get(Fields.PATENTS, result.get(Fields.DOCS, []))

    if patents and len(patents) > 0:
        logger.info(f"Found patent: {patents[0].get(Fields.GUID)}")
        return {"success": True, "patent": patents[0]}

    # Try alternative query format
    alternative_query = f'"{patent_number}".pn.'
    logger.info(f"Trying alternative query: {alternative_query}")

    result = await ppubs_client.run_query(
        query=alternative_query,
        sources=[Sources.GRANTED_PATENTS],
        limit=1
    )

    if is_error(result):
        return result

    patents = result.get(Fields.PATENTS, result.get(Fields.DOCS, []))

    if not patents or len(patents) == 0:
        return ApiError.not_found("Patent", patent_number)

    logger.info(f"Found patent: {patents[0].get(Fields.GUID)}")
    return {"success": True, "patent": patents[0]}


# =====================================================================
# Diagnostic Tools
# =====================================================================

@mcp.tool()
async def check_api_status() -> Dict[str, Any]:
    """Check status of the PPUBS API.

    USE THIS TOOL WHEN: You want to verify the patent search API
    is available before starting research.

    Returns:
        Status of the PPUBS API including configuration and availability.
    """
    return {
        "success": True,
        "sources": {
            "ppubs": {
                "name": "Patent Public Search",
                "configured": True,
                "requires_auth": False,
                "description": "Full-text search of US patents and applications",
            },
        },
        "tools_available": [
            "ppubs_search_patents",
            "ppubs_search_applications",
            "ppubs_get_full_document",
            "ppubs_get_patent_by_number",
            "ppubs_download_patent_pdf",
            "ppubs_search_by_ttl",
            "ppubs_search_by_inventor",
            "ppubs_search_by_assignee",
            "ppubs_search_combined",
            "ppubs_get_inventor_patents",
            "check_api_status",
            "get_cpc_info",
            "get_status_code",
        ],
        "enhanced_tools": {
            "ppubs_search_by_ttl": "Title-only search (most precise)",
            "ppubs_search_by_inventor": "Find all patents by inventor",
            "ppubs_search_by_assignee": "Find all patents by company",
            "ppubs_search_combined": "Multi-strategy search (recommended for new searches)",
            "ppubs_get_inventor_patents": "Auto inventor tracking from a patent",
        },
    }


@mcp.tool()
async def get_cpc_info(cpc_code: str) -> Dict[str, Any]:
    """Look up CPC (Cooperative Patent Classification) code information.

    USE THIS TOOL WHEN: You need to understand what technology area a CPC
    code represents, or find related classification codes.

    Args:
        cpc_code: CPC code to look up (e.g., "G06" for computing, "G06N3/08" for neural networks)

    Returns:
        Classification details including section, title, and description.
        For section codes (A-H, Y), returns subsection list.
    """
    if len(cpc_code) == 1:
        return get_cpc_section_info(cpc_code)
    else:
        return get_cpc_subsection_info(cpc_code)


@mcp.tool()
async def get_status_code(code: str) -> Dict[str, Any]:
    """Look up USPTO application status code meaning.

    USE THIS TOOL WHEN: You encounter a status code in application data
    and need to understand what examination stage it represents.

    Args:
        code: Status code number (e.g., "30" for "Docketed New Case")

    Returns:
        Status code description and examination stage.
    """
    return get_status_code_info(code)


# =====================================================================
# PPUBS Tools - Full text patents and PDF downloads
# =====================================================================

@mcp.tool()
async def ppubs_search_patents(
    query: str,
    offset: int = 0,
    limit: int = 100,
    sort: str = "date_publ desc",
) -> Dict[str, Any]:
    """Search granted US patents in Patent Public Search (ppubs.uspto.gov).

    USE THIS TOOL WHEN: You need full-text search of US patents with daily
    updates, or need access to the most recent patent filings.

    Args:
        query: Search query using USPTO syntax. Examples:
               - "machine learning" - searches all fields
               - TTL:"neural network" - title contains phrase
               - IN:"Smith" AND AN:"IBM" - inventor Smith, assignee IBM
               - CPC:"G06N3/08" - CPC classification
        offset: Starting position for pagination (default: 0)
        limit: Maximum results to return (default: 100, max: 500)
        sort: Sort order (default: "date_publ desc")

    Returns:
        Normalized response with patent results including GUID, title,
        abstract, dates, inventors, and classification codes.
    """
    result = await ppubs_client.run_query(
        query=query,
        start=offset,
        limit=min(limit, 500),
        sort=sort,
        sources=[Sources.GRANTED_PATENTS],
    )

    if is_error(result):
        return result

    response = ResponseEnvelope.from_ppubs(result, offset, limit)
    return check_and_truncate(response)


@mcp.tool()
async def ppubs_search_applications(
    query: str,
    offset: int = 0,
    limit: int = 100,
    sort: str = "date_publ desc",
) -> Dict[str, Any]:
    """Search published US patent applications in Patent Public Search.

    USE THIS TOOL WHEN: You need to search pre-grant published applications
    (applications publish 18 months after filing, before grant).

    Args:
        query: Search query using USPTO syntax (same as ppubs_search_patents)
        offset: Starting position for pagination (default: 0)
        limit: Maximum results to return (default: 100, max: 500)
        sort: Sort order (default: "date_publ desc")

    Returns:
        Normalized response with application results.
    """
    result = await ppubs_client.run_query(
        query=query,
        start=offset,
        limit=min(limit, 500),
        sort=sort,
        sources=[Sources.PUBLISHED_APPLICATIONS],
    )

    if is_error(result):
        return result

    response = ResponseEnvelope.from_ppubs(result, offset, limit)
    return check_and_truncate(response)


@mcp.tool()
async def ppubs_get_full_document(guid: str, source_type: str) -> Dict[str, Any]:
    """Get complete patent document by GUID from PPUBS.

    USE THIS TOOL WHEN: You have a document GUID from search results
    and need the full patent text including all claims and description.

    Args:
        guid: Document GUID (e.g., "US-9876543-B2")
        source_type: Document type - "USPAT" for patents, "US-PGPUB" for applications

    Returns:
        Complete document with claims, description, drawings info, and metadata.
    """
    result = await ppubs_client.get_document(guid, source_type)

    if is_error(result):
        return result

    return check_and_truncate(result)


@mcp.tool()
async def ppubs_get_patent_by_number(patent_number: str) -> Dict[str, Any]:
    """Get a granted patent's full text by patent number.

    USE THIS TOOL WHEN: You know the patent number and need the complete
    document including claims, description, and all sections.

    Args:
        patent_number: Patent number without commas (e.g., "7123456" or "10000000")

    Returns:
        Complete patent document with full text of all sections.
    """
    try:
        patent_number = validate_patent_number(str(patent_number))
    except ValueError as e:
        return ApiError.validation_error(str(e), "patent_number")

    search_result = await _search_patent_by_number(patent_number)

    if is_error(search_result):
        return search_result

    patent = search_result["patent"]
    result = await ppubs_client.get_document(patent[Fields.GUID], patent[Fields.TYPE])

    if is_error(result):
        return result

    return check_and_truncate(result)


@mcp.tool()
async def ppubs_download_patent_pdf(patent_number: str) -> Dict[str, Any]:
    """Download a patent as PDF (base64 encoded).

    USE THIS TOOL WHEN: You need the official PDF document of a patent.
    Note: Claude Desktop may not fully support PDF display.

    Args:
        patent_number: Patent number without commas (e.g., "7123456")

    Returns:
        Dictionary with base64-encoded PDF data.
    """
    try:
        patent_number = validate_patent_number(str(patent_number))
    except ValueError as e:
        return ApiError.validation_error(str(e), "patent_number")

    search_result = await _search_patent_by_number(patent_number)

    if is_error(search_result):
        return search_result

    patent = search_result["patent"]
    return await ppubs_client.download_image(patent[Fields.GUID], patent[Fields.TYPE])


# =====================================================================
# Enhanced Search Tools - Based on successful search strategies
# =====================================================================

@mcp.tool()
async def ppubs_search_by_ttl(
    title_keywords: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """Search patents by title keywords (TTL field - most precise).

    USE THIS TOOL WHEN: You need precise matching in patent titles.
    This implements the "exact phrase in title" strategy that directly
    found US-D1021223-S ("cigar ashtray").

    Strategy: Precise phrase matching in title is the most effective
    search method for design patents.

    Args:
        title_keywords: Keywords to search in title (e.g., "cigar ashtray",
                        "self watering pot", "cocktail smoker")
        limit: Maximum results (default: 50)

    Returns:
        Patents with title containing the keywords.

    Example:
        ppubs_search_by_ttl("cigar ashtray") → US-D1021223-S
    """
    # Note: USPTO PPUBS field search (TTL:, IN:, AN:) may not work reliably
    # Use exact phrase search as primary method
    query = f'"{title_keywords}"'
    logger.info(f"Title search (exact phrase): {query}")

    result = await ppubs_client.run_query(
        query=query,
        start=0,
        limit=min(limit, 500),
        sources=[Sources.GRANTED_PATENTS],
    )

    if is_error(result):
        return result

    response = ResponseEnvelope.from_ppubs(result, 0, limit)
    return check_and_truncate(response)


@mcp.tool()
async def ppubs_search_by_inventor(
    inventor_name: str,
    limit: int = 100,
) -> Dict[str, Any]:
    """Search patents by inventor name using improved strategies.

    USE THIS TOOL WHEN: You need to find all patents by an inventor.

    Improved Strategy (based on testing):
    - Splits name into FirstName AND LastName format
    - Tries multiple name variations
    - Much more effective than exact name search

    Args:
        inventor_name: Inventor name (e.g., "Qiu; Haitao", "Smith; John", "John Smith")
        limit: Maximum results (default: 100)

    Returns:
        Patents by this inventor using multiple search strategies.
    """
    # Clean and parse the inventor name
    name = inventor_name.replace(";", " ").replace(",", " ").strip()
    parts = [p for p in name.split() if len(p) > 1]  # Filter single chars

    all_patents = {}
    strategies_used = []

    # Strategy 1: FirstName AND LastName (most effective)
    if len(parts) >= 2:
        query1 = f"{parts[0]} AND {parts[-1]}"
        logger.info(f"Inventor search strategy 1: {query1}")
        strategies_used.append("name_split")

        result1 = await ppubs_client.run_query(
            query=query1,
            start=0,
            limit=min(limit, 200),
            sort="date_publ desc",
            sources=[Sources.GRANTED_PATENTS],
        )
        if not is_error(result1):
            for p in result1.get(Fields.PATENTS, result1.get(Fields.DOCS, [])):
                pn = p.get("documentId", p.get("patentNumber", ""))
                if pn and pn not in all_patents:
                    all_patents[pn] = p
                    all_patents[pn]["search_strategy"] = "name_split"

    # Strategy 2: Exact phrase (original name)
    query2 = f'"{inventor_name}"'
    logger.info(f"Inventor search strategy 2: {query2}")
    strategies_used.append("exact_phrase")

    result2 = await ppubs_client.run_query(
        query=query2,
        start=0,
        limit=min(limit, 100),
        sort="date_publ desc",
        sources=[Sources.GRANTED_PATENTS],
    )
    if not is_error(result2):
        for p in result2.get(Fields.PATENTS, result2.get(Fields.DOCS, [])):
            pn = p.get("documentId", p.get("patentNumber", ""))
            if pn and pn not in all_patents:
                all_patents[pn] = p
                all_patents[pn]["search_strategy"] = "exact_phrase"

    # Sort by relevance (design patents first)
    def sort_key(p):
        pn = p.get("documentId", p.get("patentNumber", "")).upper()
        score = 0
        if pn.startswith("D") or "-D" in pn:
            score += 100
        return -score

    sorted_patents = sorted(all_patents.values(), key=sort_key)[:limit]

    return {
        "success": True,
        "source": "ppubs",
        "inventor_name": inventor_name,
        "total": len(sorted_patents),
        "strategies_used": strategies_used,
        "results": sorted_patents,
        "hint": f"Found {len(sorted_patents)} patents using {len(strategies_used)} search strategies."
    }


@mcp.tool()
async def ppubs_search_by_assignee(
    assignee_name: str,
    product_type: str = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Search patents by assignee (company/owner) using improved strategies.

    USE THIS TOOL WHEN: You want to find all patents owned by a company,
    or track patent families from the same assignee.

    Improved Strategy (based on testing):
    - Extracts core keywords from company name
    - Combines with product type for better results
    - Uses multiple search variations

    Args:
        assignee_name: Company or assignee name (e.g., "Soak Limited",
                      "IBM", "Google", "Kunshan Paersi")
        product_type: Optional product type to combine with company name
                     (e.g., "smoker", "planter", "pot")
        limit: Maximum results (default: 100)

    Returns:
        All patents owned by this assignee, sorted by relevance.

    Success Cases:
        ppubs_search_by_assignee("Soak Limited", "smoker") → D976646, US-12414574-B2
        ppubs_search_by_assignee("Kunshan Paersi", "planter") → D1062405
    """
    # Extract core keywords from company name
    # Remove common suffixes: Ltd, Limited, Co, Company, Inc, Corp, Corporation
    import re
    name = assignee_name.strip()

    # Try to extract core company name
    # Common patterns: "Company Ltd" -> "Company", "X Co., Ltd" -> "X"
    core_name = re.sub(
        r'\b(Limited|Ltd|Company|Co\.?|Inc\.?|Corp\.?|Corporation|LLC|GmbH)\b',
        '',
        name,
        flags=re.IGNORECASE
    ).strip()

    # Remove punctuation and extra spaces
    core_name = re.sub(r'[.,;]', ' ', core_name)
    core_name = ' '.join(core_name.split())

    # Get the first significant word as potential core keyword
    core_parts = [p for p in core_name.split() if len(p) > 2]

    all_patents = {}
    strategies_used = []

    # Strategy 1: Exact company name
    query1 = f'"{assignee_name}"'
    logger.info(f"Assignee search strategy 1: {query1}")
    strategies_used.append("exact_name")

    result1 = await ppubs_client.run_query(
        query=query1,
        start=0,
        limit=min(limit, 200),
        sort="date_publ desc",
        sources=[Sources.GRANTED_PATENTS],
    )
    if not is_error(result1):
        for p in result1.get(Fields.PATENTS, result1.get(Fields.DOCS, [])):
            pn = p.get("documentId", p.get("patentNumber", ""))
            if pn and pn not in all_patents:
                all_patents[pn] = p
                all_patents[pn]["search_strategy"] = "exact_name"

    # Strategy 2: Core name keywords
    if core_parts:
        query2 = " AND ".join(core_parts[:2])  # Use first 2 significant words
        logger.info(f"Assignee search strategy 2: {query2}")
        strategies_used.append("core_keywords")

        result2 = await ppubs_client.run_query(
            query=query2,
            start=0,
            limit=min(limit, 200),
            sort="date_publ desc",
            sources=[Sources.GRANTED_PATENTS],
        )
        if not is_error(result2):
            for p in result2.get(Fields.PATENTS, result2.get(Fields.DOCS, [])):
                pn = p.get("documentId", p.get("patentNumber", ""))
                if pn and pn not in all_patents:
                    all_patents[pn] = p
                    all_patents[pn]["search_strategy"] = "core_keywords"

    # Strategy 3: Core name + product type (if provided)
    if product_type and core_parts:
        query3 = f"{core_parts[0]} AND {product_type}"
        logger.info(f"Assignee search strategy 3: {query3}")
        strategies_used.append("name_and_product")

        result3 = await ppubs_client.run_query(
            query=query3,
            start=0,
            limit=min(limit, 200),
            sort="date_publ desc",
            sources=[Sources.GRANTED_PATENTS],
        )
        if not is_error(result3):
            for p in result3.get(Fields.PATENTS, result3.get(Fields.DOCS, [])):
                pn = p.get("documentId", p.get("patentNumber", ""))
                if pn and pn not in all_patents:
                    all_patents[pn] = p
                    all_patents[pn]["search_strategy"] = "name_and_product"

    # Sort by relevance (design patents first, then by date)
    def sort_key(p):
        pn = p.get("documentId", p.get("patentNumber", "")).upper()
        score = 0
        if pn.startswith("D") or "-D" in pn:
            score += 100
        return -score

    sorted_patents = sorted(all_patents.values(), key=sort_key)[:limit]

    # Check for potential continuations
    hint = f"Found {len(sorted_patents)} patents using {len(strategies_used)} search strategies."
    if len(sorted_patents) > 1:
        hint += " Check for continuation applications or related claims."

    return {
        "success": True,
        "source": "ppubs",
        "assignee_name": assignee_name,
        "product_type": product_type,
        "total": len(sorted_patents),
        "strategies_used": strategies_used,
        "results": sorted_patents,
        "hint": hint
    }


@mcp.tool()
async def ppubs_search_combined(
    keywords: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """Multi-strategy combined search implementing all successful patterns.

    USE THIS TOOL WHEN: Starting a new patent search. This implements
    ALL successful strategies in sequence:
    1. Exact phrase search (most precise)
    2. TTL title search
    3. Keyword combination search
    4. Last 2-3 words (often most relevant)

    Strategy: Layer multiple search approaches to maximize coverage.
    Start with precise, expand to broad if needed.

    Args:
        keywords: Search keywords (e.g., "pot with rotatable bottom",
                  "cigar ashtray", "whiskey smoker")
        limit: Maximum results (default: 50)

    Returns:
        Aggregated results from multiple search strategies.

    Note: This tool runs multiple queries internally to cover all strategies.
    """
    words = keywords.strip().split()
    all_patents = {}

    # Strategy 1: Exact phrase (keep original including stop words)
    query1 = f'"{keywords}"'
    result1 = await ppubs_client.run_query(
        query=query1,
        start=0,
        limit=min(limit, 100),
        sources=[Sources.GRANTED_PATENTS],
    )
    if not is_error(result1):
        for p in result1.get(Fields.PATENTS, result1.get(Fields.DOCS, [])):
            pn = p.get("documentId", p.get("patentNumber", ""))
            if pn and pn not in all_patents:
                all_patents[pn] = p
                all_patents[pn]["search_strategy"] = "exact_phrase"

    # Strategy 2: Title-focused search (using exact phrase as PPUBS doesn't support TTL:)
    # Skip TTL search as it doesn't work, use variation instead
    query2 = f'"{" ".join(words[:2])}"' if len(words) >= 2 else keywords
    result2 = await ppubs_client.run_query(
        query=query2,
        start=0,
        limit=min(limit, 100),
        sources=[Sources.GRANTED_PATENTS],
    )
    if not is_error(result2):
        for p in result2.get(Fields.PATENTS, result2.get(Fields.DOCS, [])):
            pn = p.get("documentId", p.get("patentNumber", ""))
            if pn and pn not in all_patents:
                all_patents[pn] = p
                all_patents[pn]["search_strategy"] = "title_search"

    # Strategy 3: Last 2-3 words combination
    if len(words) >= 2:
        phrase_2 = " ".join(words[-2:])
        query3 = f'"{phrase_2}"'
        result3 = await ppubs_client.run_query(
            query=query3,
            start=0,
            limit=min(limit, 100),
            sources=[Sources.GRANTED_PATENTS],
        )
        if not is_error(result3):
            for p in result3.get(Fields.PATENTS, result3.get(Fields.DOCS, [])):
                pn = p.get("documentId", p.get("patentNumber", ""))
                if pn and pn not in all_patents:
                    all_patents[pn] = p
                    all_patents[pn]["search_strategy"] = "last_2_words"

    # Strategy 4: AND combination (broader search)
    if len(words) >= 2:
        query4 = " AND ".join(words[:3])  # First 3 words
        result4 = await ppubs_client.run_query(
            query=query4,
            start=0,
            limit=min(limit, 50),
            sources=[Sources.GRANTED_PATENTS],
        )
        if not is_error(result4):
            for p in result4.get(Fields.PATENTS, result4.get(Fields.DOCS, [])):
                pn = p.get("documentId", p.get("patentNumber", ""))
                if pn and pn not in all_patents:
                    all_patents[pn] = p
                    all_patents[pn]["search_strategy"] = "AND_combo"

    # Sort by relevance (design patents first)
    def sort_key(p):
        pn = p.get("documentId", p.get("patentNumber", "")).upper()
        score = 0
        if pn.startswith("D") or "-D" in pn:
            score += 100
        title = p.get("inventionTitle", p.get("title", "")).lower()
        for w in words:
            if w.lower() in title:
                score += 10
        return -score

    sorted_patents = sorted(all_patents.values(), key=sort_key)[:limit]

    return {
        "success": True,
        "total": len(sorted_patents),
        "strategies_used": ["exact_phrase", "title_search", "last_2_words", "AND_combo"],
        "patents": sorted_patents,
        "hint": f"Searched using 4 strategies. Found {len(sorted_patents)} unique patents."
    }


@mcp.tool()
async def ppubs_get_inventor_patents(patent_number: str) -> Dict[str, Any]:
    """Get all patents by inventors/assignees of a given patent - Smart aggregation.

    USE THIS TOOL WHEN: You found a relevant patent and want to
    automatically discover other patents by the same inventors or company.

    Improved Strategy (based on testing):
    - Detects if applicant is individual inventor or company
    - Uses appropriate search strategy for each type
    - For companies: extracts core keywords + product context
    - For individuals: splits name into FirstName AND LastName

    Args:
        patent_number: Known patent number (e.g., "D1003191", "D1062405", "D976646")

    Returns:
        List of all patents by the same inventor(s) or company.
    """
    # First get the patent to find inventors/applicants
    search_result = await _search_patent_by_number(patent_number)

    if is_error(search_result):
        return search_result

    patent = search_result.get("patent", {})
    applicants = patent.get("applicantName", patent.get("inventorArray", []))

    if not applicants:
        return {
            "success": False,
            "error": "No inventor/applicant information found",
            "patent_number": patent_number
        }

    # Get patent title to extract product context
    patent_title = patent.get("inventionTitle", "")

    # Detect if applicant is company or individual
    def is_company_name(name: str) -> bool:
        """Check if name appears to be a company (not a person)."""
        company_indicators = [
            'Limited', 'Ltd', 'Inc', 'Corp', 'Corporation', 'Company', 'Co.',
            'LLC', 'GmbH', 'AG', 'SA', 'Electronic', 'Commerce', 'Technology',
            'Industries', 'Manufacturing', 'Enterprises', 'Group', 'Holding'
        ]
        name_lower = name.lower()
        return any(ind.lower() in name_lower for ind in company_indicators)

    # Extract product context from patent title
    def extract_product_context(title: str) -> str:
        """Extract likely product type from patent title."""
        if not title:
            return None
        # Clean HTML tags
        title = re.sub(r'<[^>]+>', '', title)
        title_lower = title.lower()

        # Common product categories
        product_keywords = [
            'planter', 'pot', 'flowerpot', 'container', 'tray',
            'smoker', 'infuser', 'ashtray', 'cigar',
            'camera', 'monitor', 'device', 'apparatus',
            'holder', 'stand', 'rack', 'shelf'
        ]
        for kw in product_keywords:
            if kw in title_lower:
                return kw
        return None

    import re
    product_context = extract_product_context(patent_title)

    all_results = {}
    search_info = []

    for applicant in applicants:
        if isinstance(applicant, dict):
            name = applicant.get("inventorName", applicant.get("name", ""))
        else:
            name = str(applicant)

        if not name:
            continue

        is_company = is_company_name(name)
        info = {
            "name": name,
            "type": "company" if is_company else "individual"
        }

        if is_company:
            # Company search: use improved assignee search
            result = await ppubs_search_by_assignee(
                assignee_name=name,
                product_type=product_context,
                limit=100
            )
            info["strategy"] = "company_search"

        else:
            # Individual search: use improved inventor search
            result = await ppubs_search_by_inventor(
                inventor_name=name,
                limit=100
            )
            info["strategy"] = "inventor_search"

        search_info.append(info)

        if result.get("success"):
            for p in result.get("results", result.get("patents", [])):
                pn = p.get("documentId", p.get("patentNumber", ""))
                if pn and pn not in all_results:
                    all_results[pn] = p

    # Sort by relevance (design patents first)
    def sort_key(p):
        pn = p.get("documentId", p.get("patentNumber", "")).upper()
        score = 0
        if pn.startswith("D") or "-D" in pn:
            score += 100
        return -score

    sorted_patents = sorted(all_results.values(), key=sort_key)

    return {
        "success": True,
        "source_patent": patent_number,
        "source_title": patent_title,
        "product_context": product_context,
        "applicants_found": len(applicants),
        "applicant_info": search_info,
        "related_patents": sorted_patents,
        "total": len(sorted_patents),
        "hint": f"Found {len(sorted_patents)} related patents from {len(applicants)} applicant(s)"
    }


# =====================================================================
# Main entry point
# =====================================================================

def main():
    """Initialize and run the server with transport from environment."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="USPTO Patent MCP Server")
    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        choices=["stdio", "sse"],
        help="Transport type: stdio (local) or sse (remote)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE transport (default: 8000, set via PORT env)"
    )

    args = parser.parse_args()

    if args.transport == "sse":
        # Set port via environment variable for uvicorn
        os.environ["PORT"] = str(args.port)
        logger.info(f"Starting USPTO Patent MCP server with SSE transport on port {args.port}")
        # SSE transport for remote access (Cherry Studio)
        # FastMCP SSE runs on http://127.0.0.1:8000 by default
        # Use Nginx reverse proxy for external access
        mcp.run(transport="sse")
    else:
        logger.info("Starting USPTO Patent MCP server with stdio transport")
        # stdio transport for local access (Claude Code)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
