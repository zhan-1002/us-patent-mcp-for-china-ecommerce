"""
USPTO Patent & Trademark Search MCP Server

This file provides a Model Context Protocol (MCP) server that exposes tools for interacting
with USPTO patent and trademark data APIs:

- ppubs.uspto.gov - Full text patent documents, PDF downloads, and advanced search
- tmsearch.uspto.gov - Full-text trademark search (undocumented internal API, no API key)

The server uses stdio transport for Claude Code/Cursor integration.

Version: 0.10.0 - Added trademark search support (no API key required)
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
from patent_mcp_server.util.validation import validate_patent_number, validate_google_pn
from patent_mcp_server.util.response import ResponseEnvelope, check_and_truncate
from patent_mcp_server.resources import (
    get_cpc_section_info, get_cpc_subsection_info,
    get_status_code_info, get_all_status_codes,
    get_all_data_sources, get_data_source_info,
    get_search_syntax_guide, CPC_SECTIONS
)
from patent_mcp_server.prompts import get_prompt
from patent_mcp_server.uspto.ppubs_uspto_gov import PpubsClient
from patent_mcp_server.uspto.tmsearch_client import TmSearchClient
from patent_mcp_server.google import GooglePatentsClient

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

# Create client instances
ppubs_client = PpubsClient()
gp_client = GooglePatentsClient()

# Create client instance for Trademark Search API
tmsearch_client = TmSearchClient()


# Register cleanup handler
async def cleanup():
    """Clean up resources on shutdown."""
    logger.info("Shutting down USPTO Patent MCP server, cleaning up resources...")
    try:
        await ppubs_client.close()
        await gp_client.close()
        logger.info("Cleanup completed successfully")
    except Exception as e:
        logger.error(f"Error during PPUBS cleanup: {str(e)}")
    try:
        await tmsearch_client.close()
        logger.info("TmSearch cleanup completed")
    except Exception as e:
        logger.error(f"Error during TmSearch cleanup: {str(e)}")
    logger.info("Cleanup completed successfully")


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


@mcp.prompt()
async def patent_cross_validation() -> str:
    """USPTO + Patsnap dual-source cross-validation workflow.

    USE THIS PROMPT WHEN: You need comprehensive patent search with
    cross-validation across independent data sources. Covers US patents
    via USPTO and global patents (including China) via Patsnap.

    This workflow:
    - Runs both USPTO and Patsnap searches in parallel
    - Cross-compares results to identify gaps
    - Leverages Patsnap's image-based design search
    - Expands coverage beyond US to Chinese patents
    - Produces a confidence-rated cross-validation report
    """
    return get_prompt("patent_cross_validation")["content"]


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

    Performs a lightweight connectivity check against PPUBS (session
    establishment) and returns configuration plus live status for both
    PPUBS and Google Patents engines.

    Returns:
        Status of the PPUBS API including configuration and availability.
    """
    # ── Lightweight PPUBS connectivity check ──────────────────────────
    ppubs_reachable = False
    ppubs_check_error = None
    try:
        session = await ppubs_client.get_session()
        ppubs_reachable = session is not None
        if not ppubs_reachable:
            ppubs_check_error = "Session establishment returned None (API may be down or unreachable)"
    except Exception as exc:
        ppubs_check_error = f"Connectivity check failed: {exc}"

    # ── Google Patents reachability check ─────────────────────────────
    gp_reachable = False
    gp_check_error = None
    try:
        gp_reachable = await gp_client._ensure_session()
        if not gp_reachable:
            gp_check_error = "Home page unreachable (connection error, DNS failure, or timeout)"
    except Exception as exc:
        gp_check_error = f"Connectivity check failed: {exc}"

    return {
        "success": True,
        "connectivity": {
            "ppubs": ppubs_reachable,
            "google_patents": gp_reachable,
        },
        "connectivity_errors": {
            k: v for k, v in [
                ("ppubs", ppubs_check_error),
                ("google_patents", gp_check_error),
            ] if v is not None
        } or None,
        "sources": {
            "ppubs": {
                "name": "Patent Public Search",
                "configured": True,
                "requires_auth": False,
                "description": "Full-text search of US patents and applications",
                "reachable": ppubs_reachable,
            },
            "google_patents": {
                "name": "Google Patents",
                "configured": True,
                "requires_auth": False,
                "description": "ML-ranked patent search with design patent faceting — supplements PPUBS",
                "rate_limit_note": "Enforces >=2s delay between requests to avoid 503 bans",
                "reachable": gp_reachable,
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
            "ppubs_get_citations",
            "ppubs_get_cited_by",
            "ppubs_get_citation_network",
            "gp_search_patents",
            "gp_get_patent_detail",
            "gp_get_similar_patents",
            "gp_get_citations",
            "tmsearch_search",
            "tmsearch_get_by_serial",
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
            "ppubs_get_citations": "Extract urpn references from PPUBS full document",
            "ppubs_get_cited_by": "Reverse citation lookup — who cited this patent?",
            "ppubs_get_citation_network": "Bidirectional citation network (backward + forward in one call) — recommended",
            "gp_search_patents": "Google Patents search with DESIGN/PATENT/ANY type filter",
            "gp_get_patent_detail": "Google Patents detail with abstract, CPC, citations",
            "gp_get_similar_patents": "ML-based similar patent discovery via CPC codes",
            "gp_get_citations": "Forward/backward citation graph from Google Patents",
            "tmsearch_search": "US trademark full-text search (no API key)",
            "tmsearch_get_by_serial": "Look up trademark by serial number",
        },
        "dual_engine_strategy": {
            "description": "PPUBS + Google Patents complement each other. Use GP for design patent discovery (ML ranking beats TF-IDF), then PPUBS for full legal text.",
            "when_ppubs": "Full claims text, PDF downloads, authoritative USPTO data, urpn citation extraction",
            "when_google": "Design patent search, citation browsing, ML-ranked keyword search",
            "workflow": "gp_search_patents (discover) → ppubs_get_citation_network (bidirectional family) → gp_get_similar_patents (ML recommendations) → ppubs_get_full_document (get legal text)",
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
    return await ppubs_client.download_image(
        patent[Fields.GUID],
        patent.get(Fields.IMAGE_LOCATION, ""),
        patent.get(Fields.PAGE_COUNT, 1),
        patent[Fields.TYPE],
    )


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
# Trademark Search Tools - tmsearch.uspto.gov (no API key required)
# =====================================================================

@mcp.tool()
async def tmsearch_search(
    query: str = None,
    mark_text: str = None,
    owner_name: str = None,
    serial_number: str = None,
    registration_number: str = None,
    goods_services: str = None,
    international_class: str = None,
    status_filter: str = None,
    offset: int = 0,
    limit: int = 25,
) -> Dict[str, Any]:
    """Search US trademarks via tmsearch.uspto.gov (full-text, no API key).

    USE THIS TOOL WHEN: You need to search US trademark records — find marks
    by name, owner, serial/registration number, goods/services, or class.

    This searches the same internal Elasticsearch index that powers the USPTO
    trademark search web app (TESS replacement at tmsearch.uspto.gov). No API
    key is required. Same risk profile as PPUBS: undocumented internal API,
    may change without notice.

    Args:
        query: Raw Elasticsearch query_string (e.g., "Nike AND shoes").
               Searches the wordmark field by default.
        mark_text: Word mark text to match (e.g., "Apple", "Tesla")
        owner_name: Owner/assignee name (e.g., "Microsoft", "Nike, Inc.")
        serial_number: Exact 8-digit application serial number
        registration_number: Exact registration number
        goods_services: Terms to match in goods/services description
                        (e.g., "footwear", "software")
        international_class: Nice class number as string (e.g., "9", "25").
                             Zero-padded to 3 digits internally.
        status_filter: "live" for active marks, "dead" for expired/abandoned,
                       or omit for both.
        offset: Pagination offset (default: 0)
        limit: Maximum results (default: 25, max: 100)

    Returns:
        {"results": [...], "total": N} with trademark records including
        wordmark, serial number, owner, class, status, and dates.

    Example:
        tmsearch_search(mark_text="Nike", status_filter="live") → live NIKE marks
        tmsearch_search(owner_name="Apple Inc.") → marks owned by Apple
        tmsearch_search(serial_number="75187260") → exact serial lookup
    """
    # At least one search criterion is required
    if not any([query, mark_text, owner_name, serial_number,
                registration_number, goods_services, international_class]):
        return ApiError.validation_error(
            "At least one search criterion is required: query, mark_text, "
            "owner_name, serial_number, registration_number, goods_services, "
            "or international_class"
        )

    result = await tmsearch_client.search(
        query=query,
        mark_text=mark_text,
        owner_name=owner_name,
        serial_number=serial_number,
        registration_number=registration_number,
        goods_services=goods_services,
        international_class=international_class,
        status_filter=status_filter,
        offset=offset,
        limit=min(limit, 100),
    )

    if result.get("error", False):
        return result

    logo = "🔒" if status_filter == "live" else ("💀" if status_filter == "dead" else "🔍")
    header = f"{logo} Trademark results {result['total']} total"
    if mark_text:
        header += f" for mark '{mark_text}'"
    elif owner_name:
        header += f" for owner '{owner_name}'"
    elif serial_number:
        header += f" for serial '{serial_number}'"

    search_params = {
        k: v for k, v in {
            "query": query, "mark_text": mark_text, "owner_name": owner_name,
            "serial_number": serial_number, "registration_number": registration_number,
            "goods_services": goods_services, "international_class": international_class,
            "status_filter": status_filter, "offset": offset
        }.items() if v is not None
    }

    return {
        "success": True,
        "source": "tmsearch",
        "search_params": search_params,
        "total": result["total"],
        "count": len(result["results"]),
        "offset": offset,
        "limit": limit,
        "has_more": (offset + len(result["results"])) < result["total"],
        "results": result["results"],
        "header": header,
        "hint": (
            "Trademark records from tmsearch.uspto.gov. Serial numbers (id field) "
            "can be used to look up full details at https://tsdr.uspto.gov/."
        ),
    }


# PPUBS Citation Helpers
# =====================================================================

def _normalize_pn(patent_number: str) -> str:
    """Normalize any patent number format to plain form (e.g. ``"D656429"``).

    Accepts Google (``USD656429S1``), PPUBS (``US D656429 S``), plain with
    kind-code suffix (``D656429S``), and bare plain (``D656429``).
    Returns the plain form or the empty string when the input is unrecognised.
    """
    pn = str(patent_number).strip()
    if not pn:
        return ""
    # PPUBS format: "US D786128 S" → "D786128" / "US 12345678 S" → "12345678"
    m = re.match(r'^US\s+([A-Z]?\d+)\s+[A-Z]\d*$', pn)
    if m:
        return m.group(1)
    # Google format: "USD786128S1" → "D786128" / "US12345678B2" → "12345678"
    m = re.match(r'^US([A-Z]?\d+)[A-Z]\d*$', pn)
    if m:
        return m.group(1)
    # Plain with trailing kind code: "D786128S" → "D786128" / "12345678B2" → "12345678"
    m = re.match(r'^([A-Z]?\d+)[A-Z]\d*$', pn)
    if m:
        return m.group(1)
    # Bare design patent (no kind code): "D1050666" → "D1050666"
    if re.match(r'^[A-Z]\d+$', pn):
        return pn
    # Bare digits (utility patent): "7123456" → "7123456"
    if re.match(r'^\d+$', pn):
        return pn
    return ""


def _is_design_patent(pn: str) -> bool:
    """Check if a patent number string represents a design patent.

    Normalises the input first so that Google (``USD1066113S1``), PPUBS
    (``US D1066113 S``), plain-with-kind-code (``D1066113S``), and bare
    (``D1066113``) formats are all recognised correctly.
    """
    if not pn:
        return False
    normalised = _normalize_pn(str(pn))
    if not normalised:
        return False
    # After normalisation, a design patent body starts with 'D'
    return normalised[0] == 'D'


# Direction-specific citation field groups
_BACKWARD_CITATION_FIELDS = [
    "urpn", "urpnCode", "usCitation", "citedPatents",
    "backwardCitations", "backward_citations",
    "referencesCited", "usPatentsCited",
]

_FORWARD_CITATION_FIELDS = [
    "forwardCitations", "forward_citations",
    "citingPatents",
]

_ALL_CITATION_FIELDS = _BACKWARD_CITATION_FIELDS + _FORWARD_CITATION_FIELDS


def _extract_pns_from_fields(doc: Dict[str, Any], fields: list) -> list:
    """Extract patent numbers from *doc* for the given field names.

    Returns a deduplicated, sorted list of patent number strings.
    """
    found: set = set()
    for field in fields:
        values = doc.get(field, [])
        if not values:
            continue
        if isinstance(values, list):
            for item in values:
                if isinstance(item, str):
                    found.add(item)
                elif isinstance(item, dict):
                    for sub in ("patentNumber", "documentId", "number", "pn", "code"):
                        v = item.get(sub, "")
                        if v:
                            found.add(str(v))
                            break
        elif isinstance(values, str):
            found.add(values)
    return sorted(found)


def _extract_backward_citation_pns(doc: Dict[str, Any]) -> list:
    """Extract BACKWARD citation patent numbers (patents THIS patent cites)."""
    return _extract_pns_from_fields(doc, _BACKWARD_CITATION_FIELDS)


def _extract_forward_citation_pns(doc: Dict[str, Any]) -> list:
    """Extract FORWARD citation patent numbers (patents that cite THIS patent)."""
    return _extract_pns_from_fields(doc, _FORWARD_CITATION_FIELDS)


def _extract_citation_field_names(doc: Dict[str, Any]) -> list:
    """Return the names of citation-related fields actually present in *doc*."""
    return [f for f in _ALL_CITATION_FIELDS if f in doc and doc[f]]


# =====================================================================
# PPUBS Citation Tools
# =====================================================================

@mcp.tool()
async def ppubs_get_citations(patent_number: str) -> Dict[str, Any]:
    """Get citation information for a patent from PPUBS full document.

    USE THIS TOOL WHEN: You want to find out which patents a given patent
    references (backward citations) and which patents cite it (forward citations).
    Citation chains are critical for design patent discovery — design patents
    often cite visually similar prior art.

    Extracts urpn/urpnCode and other citation fields from the PPUBS full
    document response. Design patents are flagged separately.

    Args:
        patent_number: Patent number in any format (e.g., "D786128S",
                       "US D786128 S", "USD786128S1", or "786128").

    Returns:
        Dictionary with patent info, references list, and citation field names found.
    """
    pn = _normalize_pn(patent_number)
    if not pn:
        return ApiError.validation_error("Patent number cannot be empty", field="patent_number")

    # 1. Find the patent metadata using the correct PPUBS query format
    query = f'"{pn}".pn.'
    logger.info(f"Searching for patent with citation query: {query}")
    result = await ppubs_client.run_query(
        query=query,
        sources=[Sources.GRANTED_PATENTS],
        limit=1,
    )

    if is_error(result):
        return result

    patents = result.get(Fields.PATENTS, result.get(Fields.DOCS, []))
    if not patents:
        return ApiError.not_found("Patent", pn)

    patent = patents[0]
    guid = patent.get(Fields.GUID)
    doc_type = patent.get(Fields.TYPE, Sources.GRANTED_PATENTS)
    document_id = patent.get("documentId", patent.get("patentNumber", pn))
    title = patent.get("inventionTitle", patent.get("title", ""))

    if not guid:
        return ApiError.not_found("Patent GUID for", pn)

    # 2. Get full document (contains citation fields)
    doc = await ppubs_client.get_document(guid, doc_type)
    if is_error(doc):
        # Fallback: return what we have from the search result
        field_names = _extract_citation_field_names(patent)
        return {
            "success": True,
            "source": "ppubs",
            "patent": {
                "pn": document_id,
                "title": title,
                "guid": guid,
            },
            "references": [],
            "cited_by": [],
            "design_count": 0,
            "total_count": 0,
            "citation_fields_found": field_names,
            "hint": "Full document unavailable — citation fields extracted from search result only. Some citation data may be missing.",
        }

    # 3. Extract citation data — separate backward and forward
    field_names = _extract_citation_field_names(doc)
    ref_pns = _extract_backward_citation_pns(doc)

    # Separate design from utility
    designs = [p for p in ref_pns if _is_design_patent(p)]
    utilities = [p for p in ref_pns if not _is_design_patent(p)]

    # Build reference list
    references = []
    for p in ref_pns:
        references.append({
            "pn": p,
            "type": "design" if _is_design_patent(p) else "utility",
        })

    # Forward citations
    fwd_pns = _extract_forward_citation_pns(doc)

    return {
        "success": True,
        "source": "ppubs",
        "patent": {
            "pn": document_id,
            "title": title,
            "guid": guid,
        },
        "references": references,
        "cited_by": [{"pn": p, "type": "design" if _is_design_patent(p) else "utility"} for p in fwd_pns],
        "design_count": len(designs),
        "utility_count": len(utilities),
        "total_count": len(ref_pns),
        "forward_count": len(fwd_pns),
        "citation_fields_found": field_names,
    }


@mcp.tool()
async def ppubs_get_cited_by(patent_number: str, max_results: int = 50) -> Dict[str, Any]:
    """Reverse citation lookup — find patents that cite a given patent.

    USE THIS TOOL WHEN: You found a relevant patent and want to discover
    newer patents that reference it.  This is the "forward citation" path —
    newer designs often cite earlier visually similar designs.

    This tool searches for the patent number in PPUBS and inspects each
    result's urpn field.  NOTE: this is an expensive operation (N+1 API
    calls); max_results caps the search scope.

    Args:
        patent_number: Patent number to search for (e.g., "D656429S").
        max_results: Maximum search results to inspect (default 50, max 100).

    Returns:
        Dictionary with the source patent and list of citing patents.
    """
    pn = _normalize_pn(patent_number)
    if not pn:
        return ApiError.validation_error("Patent number cannot be empty", field="patent_number")

    max_results = min(max(max_results, 1), 100)

    # Search for the patent number in urpn field of other patents
    query = f'"{pn}".urpn.'
    result = await ppubs_client.run_query(
        query=query,
        sources=[Sources.GRANTED_PATENTS],
        limit=max_results,
        sort="date_publ desc",
    )

    if is_error(result):
        return result

    patents = result.get(Fields.PATENTS, result.get(Fields.DOCS, []))
    if not patents:
        return ApiError.not_found("Patent references to", pn)

    # The .urpn. query already selected patents that cite the target.
    # We inspect the search result's urpn fields when available for verification
    # certainty, but if urpn data is absent from the basic search record we still
    # trust the query hit (marking it unverified).
    citing_patents = []
    checked = 0
    for patent in patents[:max_results]:
        checked += 1
        patent_pn = patent.get("documentId", patent.get("patentNumber", ""))
        # Skip the patent itself — use normalized equality, not substring
        if _normalize_pn(str(pn)) == _normalize_pn(str(patent_pn)):
            continue

        # Try to verify via urpn fields in the search result
        refs = _extract_backward_citation_pns(patent)
        verified = False
        if refs:
            # urpn data is present — verify the target is among them
            if any(_normalize_pn(str(pn)) == _normalize_pn(str(r)) for r in refs):
                verified = True
        else:
            # urpn not expanded in basic search result — trust the .urpn. query hit
            verified = False

        citing_patents.append({
            "pn": patent_pn,
            "title": patent.get("inventionTitle", patent.get("title", "")),
            "date": patent.get("datePublished", ""),
            "type": "design" if _is_design_patent(patent_pn) else "utility",
            "verified": verified,
        })

    verified_count = sum(1 for c in citing_patents if c["verified"])
    return {
        "success": True,
        "source": "ppubs",
        "patent": {"pn": pn},
        "cited_by": citing_patents,
        "count": len(citing_patents),
        "verified_count": verified_count,
        "checked": checked,
        "hint": (
            f"Found {len(citing_patents)} citing patents out of {checked} search results "
            f"({verified_count} verified via urpn fields, "
            f"{len(citing_patents) - verified_count} from .urpn. query hit without expanded urpn). "
            f"Note: urpn data may not be present in basic search results — "
            f"use ppubs_get_citations() on individual results for definitive citation data."
        ),
    }


@mcp.tool()
async def tmsearch_get_by_serial(serial_number: str) -> Dict[str, Any]:
    """Get a trademark record by serial number from tmsearch.

    USE THIS TOOL WHEN: You have a trademark serial number and need the
    search-index record with mark text, owner, class, status, and dates.

    Args:
        serial_number: 8-digit trademark application serial number

    Returns:
        Single trademark record or error.
    """
    result = await tmsearch_client.get_by_serial(serial_number)

    if result.get("error", False):
        return result

    if not result.get("results"):
        return ApiError.not_found("Trademark", serial_number)

    record = result["results"][0]
    return {
        "success": True,
        "source": "tmsearch",
        "serial_number": serial_number,
        "record": record,
        "wordmark": record.get("wordmark", "N/A"),
        "owner": record.get("ownerFullText", "N/A"),
        "status": record.get("statusDescription", "N/A"),
    }

async def ppubs_get_citation_network(patent_number: str, max_forward: int = 50) -> Dict[str, Any]:
    """Bidirectional citation network — both backward AND forward citations.

    USE THIS TOOL WHEN: You found a core patent and want the COMPLETE patent
    family in one call.  This is the recommended single-call replacement for
    running ``ppubs_get_citations`` + ``ppubs_get_cited_by`` separately.

    **Strategy**: design patents with short/generic titles (e.g. "Cross") are
    invisible to keyword search.  They can ONLY be found through forward
    citation traversal from earlier patents they cite.  This tool guarantees
    both directions are covered.

    Args:
        patent_number: Patent number in any format.
        max_forward: Maximum forward-citation search results to inspect
                     (default 50, max 100).

    Returns:
        Dictionary with:
        - ``patent`` — source patent metadata
        - ``backward`` — patents THIS patent cites (older prior art)
        - ``forward`` — patents that cite THIS patent (newer designs)
        - ``backward_count`` / ``forward_count`` — counts
        - ``design_count`` / ``utility_count`` — type breakdown
        - ``family_summary`` — one-line summary of the citation network
    """
    pn = _normalize_pn(patent_number)
    if not pn:
        return ApiError.validation_error("Patent number cannot be empty", field="patent_number")

    max_forward = min(max(max_forward, 1), 100)

    # ── 1. Backward citations (full document urpn extraction) ──────────
    query = f'"{pn}".pn.'
    result = await ppubs_client.run_query(
        query=query, sources=[Sources.GRANTED_PATENTS], limit=1,
    )
    if is_error(result):
        return result

    patents = result.get(Fields.PATENTS, result.get(Fields.DOCS, []))
    if not patents:
        return ApiError.not_found("Patent", pn)

    patent = patents[0]
    guid = patent.get(Fields.GUID)
    doc_type = patent.get(Fields.TYPE, Sources.GRANTED_PATENTS)
    document_id = patent.get("documentId", patent.get("patentNumber", pn))
    title = patent.get("inventionTitle", patent.get("title", ""))
    patent_date = patent.get("datePublished", "")

    backward_refs: list = []
    backward_designs: list = []
    backward_utilities: list = []
    backward_warning = None

    if guid:
        doc = await ppubs_client.get_document(guid, doc_type)
        if not is_error(doc):
            ref_pns = _extract_backward_citation_pns(doc)
            for rp in ref_pns:
                entry = {"pn": rp, "type": "design" if _is_design_patent(rp) else "utility"}
                backward_refs.append(entry)
                if _is_design_patent(rp):
                    backward_designs.append(rp)
                else:
                    backward_utilities.append(rp)
        else:
            backward_warning = f"Backward citation extraction failed for {document_id}: {doc.get('message', 'unknown error')}"
    else:
        backward_warning = f"No GUID found for {document_id} — backward citations unavailable"

    # ── 2. Forward citations (.urpn. search) ───────────────────────────
    fwd_query = f'"{pn}".urpn.'
    fwd_result = await ppubs_client.run_query(
        query=fwd_query,
        sources=[Sources.GRANTED_PATENTS],
        limit=max_forward,
        sort="date_publ desc",
    )
    forward_warning = None
    if is_error(fwd_result):
        forward_warning = f"Forward citation query failed: {fwd_result.get('message', 'unknown error')}"
        fwd_result = {Fields.PATENTS: []}

    fwd_patents = fwd_result.get(Fields.PATENTS, fwd_result.get(Fields.DOCS, []))
    forward_refs: list = []
    forward_designs: list = []
    forward_utilities: list = []
    checked = 0

    for fp in fwd_patents[:max_forward]:
        checked += 1
        fp_pn = fp.get("documentId", fp.get("patentNumber", ""))
        # Skip self — normalized equality comparison
        if _normalize_pn(str(pn)) == _normalize_pn(str(fp_pn)):
            continue

        # Trust .urpn. query hits; verify via urpn fields when available
        refs = _extract_backward_citation_pns(fp)
        verified = bool(refs) and any(
            _normalize_pn(str(pn)) == _normalize_pn(str(r)) for r in refs
        )
        entry = {
            "pn": fp_pn,
            "title": fp.get("inventionTitle", fp.get("title", "")),
            "date": fp.get("datePublished", ""),
            "type": "design" if _is_design_patent(fp_pn) else "utility",
            "verified": verified,
        }
        forward_refs.append(entry)
        if _is_design_patent(fp_pn):
            forward_designs.append(fp_pn)
        else:
            forward_utilities.append(fp_pn)

    # ── 3. Merge ───────────────────────────────────────────────────────
    total_backward = len(backward_refs)
    total_forward = len(forward_refs)
    total_designs = len(backward_designs) + len(forward_designs)
    total_utilities = len(backward_utilities) + len(forward_utilities)

    # Build warnings for partial results
    warnings = []
    if backward_warning:
        warnings.append(backward_warning)
    if forward_warning:
        warnings.append(forward_warning)

    # Build a one-line family summary
    summary_parts = [f"{pn} ({title[:60]})"]
    if total_backward:
        summary_parts.append(f"cites {total_backward} patents ({len(backward_designs)} design)")
    if total_forward:
        summary_parts.append(f"cited by {total_forward} patents ({len(forward_designs)} design)")

    return {
        "success": True,
        "source": "ppubs",
        "partial": bool(warnings),
        "warnings": warnings or None,
        "patent": {
            "pn": document_id,
            "title": title,
            "date": patent_date,
            "guid": guid,
        },
        "backward": backward_refs,
        "backward_count": total_backward,
        "backward_design_count": len(backward_designs),
        "backward_utility_count": len(backward_utilities),
        "forward": forward_refs,
        "forward_count": total_forward,
        "forward_design_count": len(forward_designs),
        "forward_utility_count": len(forward_utilities),
        "forward_checked": checked,
        "design_count": total_designs,
        "utility_count": total_utilities,
        "family_summary": " | ".join(summary_parts),
    }


# =====================================================================
# Google Patents Tools
# =====================================================================

@mcp.tool()
async def gp_search_patents(
    query: str,
    type: str = "DESIGN",
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Search US patents on Google Patents.

    USE THIS TOOL WHEN: You need to search for design patents or when PPUBS
    keyword search fails to find short-title design patents. Google Patents
    uses ML-based ranking and a dedicated type=DESIGN facet that is far
    superior to PPUBS TF-IDF for design patents.

    Args:
        query: Search query using Google Patents syntax. Supports quoted
               phrases, AND/OR, inventor:"Name", assignee:"Company", cpc:"code".
        type: Patent type filter — "DESIGN" (default), "PATENT", or "ANY".
        limit: Maximum results (default 20, max 100).
        offset: Starting position for pagination (default 0).
               NOTE: Google Patents paginates by page, not row; offset is
               rounded down to the nearest multiple of limit.

    Returns:
        Standardized search results with pn, title, date, assignee, thumbnail_url.
    """
    # Validate inputs
    query = query.strip() if query else ""
    if not query:
        return ApiError.validation_error("query cannot be empty", field="query")

    type_norm = type.strip().upper() if type else "DESIGN"
    if type_norm not in ("DESIGN", "PATENT", "ANY"):
        return ApiError.validation_error(
            "type must be one of: DESIGN, PATENT, ANY", field="type",
        )

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    result = await gp_client.search(
        query=query,
        type_filter=type_norm,
        limit=limit,
        offset=offset,
    )

    if is_error(result):
        return result

    response = ResponseEnvelope.from_google(result, offset, limit)
    return check_and_truncate(response)


@mcp.tool()
async def gp_get_patent_detail(patent_number: str) -> Dict[str, Any]:
    """Get detailed patent information from Google Patents.

    USE THIS TOOL WHEN: You have a patent number and need full details
    including abstract, CPC classification, citations, and images.
    Google Patents provides better legal status and citation graphs
    than PPUBS, but does NOT include full claims text.

    Args:
        patent_number: Patent number in any format (e.g., "D1066113",
                       "USD1066113S1", or "US D1066113 S").

    Returns:
        Full patent object with abstract, cpc_codes, citations, and metadata.
    """
    try:
        pn = validate_google_pn(patent_number)
    except ValueError as e:
        return ApiError.validation_error(str(e), field="patent_number")

    result = await gp_client.get_patent(pn)

    if is_error(result):
        return result

    return check_and_truncate(result)


@mcp.tool()
async def gp_get_similar_patents(
    patent_number: str,
    limit: int = 10,
) -> Dict[str, Any]:
    """Get similar patents via Google Patents ML recommendations.

    USE THIS TOOL WHEN: You found a relevant design patent and want to
    discover visually or conceptually similar patents.  Google Patents
    uses ML-based similarity combining CPC classification, citations,
    and visual features.

    Uses CPC-code-based similarity search (the ML similarity endpoint
    is not publicly documented).  Falls back gracefully when no CPC
    codes are available.

    Args:
        patent_number: Source patent number (any format).
        limit: Maximum similar patents to return (default 10).

    Returns:
        Dictionary with source patent and ranked similar patents.
    """
    try:
        pn = validate_google_pn(patent_number)
    except ValueError as e:
        return ApiError.validation_error(str(e), field="patent_number")

    result = await gp_client.get_similar(pn, limit=limit)

    if is_error(result):
        return result

    return check_and_truncate(result)


@mcp.tool()
async def gp_get_citations(
    patent_number: str,
    direction: str = "both",
) -> Dict[str, Any]:
    """Get forward/backward citations for a patent from Google Patents.

    USE THIS TOOL WHEN: You want to trace the citation network around a
    patent — which earlier patents it cites (backward) and which later
    patents cite it (forward).  This is essential for design patent
    landscape analysis.

    Args:
        patent_number: Patent number (any format).
        direction: "forward" (patents that cite this one),
                   "backward" (patents this one cites), or
                   "both" (default).

    Returns:
        Dictionary with forward/backward citation lists.
    """
    # Validate direction
    valid_directions = {"forward", "backward", "both"}
    direction = direction.strip().lower()
    if direction not in valid_directions:
        return ApiError.validation_error(
            f"direction must be one of: {', '.join(sorted(valid_directions))}",
            field="direction",
        )

    try:
        pn = validate_google_pn(patent_number)
    except ValueError as e:
        return ApiError.validation_error(str(e), field="patent_number")

    # Get full detail first
    detail = await gp_client.get_patent(pn)
    if is_error(detail):
        return detail

    patent = detail.get("patent", {})

    def _normalize_citations(raw_list):
        """Convert raw citation objects to {pn, title, date} format."""
        if not raw_list or not isinstance(raw_list, list):
            return []
        result = []
        for c in raw_list:
            if isinstance(c, str):
                result.append({"pn": c, "title": "", "date": ""})
            elif isinstance(c, dict):
                result.append({
                    "pn": c.get("publication_number", c.get("pn", c.get("number", ""))),
                    "title": c.get("title", ""),
                    "date": c.get("publication_date", c.get("date", "")),
                })
        return result

    backward = _normalize_citations(patent.get("backward_citations", []))
    forward = _normalize_citations(patent.get("forward_citations", []))

    # Filter by direction
    response = {
        "success": True,
        "source": "google_patents",
        "patent": {
            "pn": patent.get("publication_number", pn),
            "title": patent.get("title", ""),
        },
    }

    if direction in ("backward", "both"):
        response["backward_citations"] = backward
        response["backward_count"] = len(backward)
    if direction in ("forward", "both"):
        response["forward_citations"] = forward
        response["forward_count"] = len(forward)

    return check_and_truncate(response)


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
