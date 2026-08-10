"""
MCP Prompts for USPTO Patent Server (PPUBS + Google Patents).

Prompts provide reusable workflow templates for common patent research tasks.
Users can access these via / commands.

All prompts reference only tools registered in this server:
  PPUBS: ppubs_search_patents, ppubs_search_applications, ppubs_get_full_document,
         ppubs_get_patent_by_number, ppubs_download_patent_pdf, ppubs_search_by_ttl,
         ppubs_search_by_inventor, ppubs_search_by_assignee, ppubs_search_combined,
         ppubs_get_inventor_patents, ppubs_get_citations, ppubs_get_cited_by,
         ppubs_get_citation_network
  Google: gp_search_patents, gp_get_patent_detail, gp_get_similar_patents,
          gp_get_citations
  Aggregate: patent_search_aggregated, patent_evaluate_recall
  Trademark: tmsearch_search, tmsearch_get_by_serial
  Utility: check_api_status, get_cpc_info, get_status_code
"""

PRIOR_ART_SEARCH_PROMPT = """
# Prior Art Search Workflow

A comprehensive prior art search helps identify existing patents and publications
relevant to an invention. Follow this structured approach using the dual-engine
(PPUBS + Google Patents) tools.

## Step 1: Define the Invention
- Identify the key technical features
- List the problem being solved
- Note any unique aspects or improvements

## Step 2: Keyword Search (Broad)
Start with broad text searches to understand the landscape:

Use `gp_search_patents` and `ppubs_search_combined`:
- `gp_search_patents` for design patents and ML-ranked results — best for products with visual features
- `ppubs_search_combined` for multi-strategy PPUBS search
- Try synonyms and alternative phrasings
- Use `type="PATENT"` for utility patents, `type="DESIGN"` for design patents

## Step 3: Identify Relevant CPC Codes
From initial results, identify CPC classification codes:

Use `get_cpc_info` on CPC codes found in search results:
- Note CPC codes from relevant patents
- Look up parent/child codes for broader/narrower scope

## Step 4: Classification-Based Search
Search within relevant CPC classifications:

```
gp_search_patents('cpc:"G06N3/08"', type="PATENT")
```
- Focus on identified CPC codes
- Combine with keywords if needed

## Step 5: Inventor/Assignee Search
Find patents from key players in the field:

```
ppubs_search_by_inventor("inventor name")
ppubs_search_by_assignee("company name")
ppubs_get_inventor_patents("known patent number")
```
- Search for prolific inventors in the field
- Find competitors' patent portfolios
- Track inventor networks automatically

## Step 6: Citation Analysis
Trace the citation graph for comprehensive coverage:

Use `ppubs_get_citation_network` on key patents:
- backward: older prior art the patent cites
- forward: newer patents that cite this one
- Both design and utility patents surfaced

## Step 7: Deep Dive
Get complete patent text when a lead looks promising:

```
ppubs_get_full_document(guid, source_type)  → full claims + description
ppubs_get_patent_by_number("DXXXXXX")       → granted patent text
```
"""

PATENT_VALIDITY_ANALYSIS_PROMPT = """
# Patent Validity Analysis Workflow

Analyze the validity and strength of a patent using PPUBS full documents
and citation networks.

## Step 1: Get Patent Details
```
ppubs_get_patent_by_number("patent_number")
```
- Review claims (especially independent claims)
- Note the filing and priority dates
- Identify the assignee and inventors

## Step 2: Review Full Claims Text
```
ppubs_get_full_document(guid, "USPAT")
```
- Identify independent vs dependent claims
- Note claim scope and key limitations
- Look for potential narrow vs broad interpretations

## Step 3: Citation Network Analysis
```
ppubs_get_citation_network("patent_number")
```
- backward: prior art the patent cites (potential invalidity sources)
- forward: newer patents citing this one (indicator of relevance)
- Check for conflicting prior art

## Step 4: Examiner Citations
```
ppubs_get_citations("patent_number")
```
- Extract urpn references from the full PPUBS document
- Review what prior art the examiner considered
- Note design vs utility breakdown

## Step 5: Similar Patent Discovery
```
gp_get_similar_patents("patent_number")
```
- ML-based similar patent discovery via Google Patents
- Finds patents in the same CPC class or with similar titles
- Useful for identifying hidden prior art

## Step 6: Google Patents Citation Graph
```
gp_get_citations("patent_number", direction="both")
```
- Cross-reference with PPUBS citation data
- Google's ML-ranked citation network

## Assessment Factors:
- Strength of prior art cited by examiner and found via citation network
- Scope limitations from claim language
- Forward citation count (indicator of importance)
- Similar patents in the same CPC family
"""

COMPETITOR_PORTFOLIO_ANALYSIS_PROMPT = """
# Competitor Patent Portfolio Analysis Workflow

Analyze a company's patent portfolio using PPUBS assignee search and
citation networks.

## Step 1: Identify Company Patents
```
ppubs_search_by_assignee("company name", product_type="optional product type")
```
- Search for company name and variations
- Add product type context for better results
- Note subsidiary names

## Step 2: Get Portfolio Overview
```
ppubs_search_patents('"company name".as.')
```
- Get count of total patents
- Identify date range of filings
- Note technology distribution by CPC

## Step 3: Technology Focus Analysis
Use `get_cpc_info` on CPC codes from company patents:
- Identify top CPC codes in portfolio
- Map technology areas covered
- Find gaps or emerging focus areas

## Step 4: Inventor Analysis
```
ppubs_search_by_inventor("inventor name")
ppubs_get_inventor_patents("representative patent number")
```
- Identify key inventors
- Track inventor portfolios
- Find prolific inventors by patent count

## Step 5: Citation Network Mapping
```
ppubs_get_citation_network("key patent number")
```
- Identify most-cited patents (crown jewels)
- Find citation relationships with competitors
- Map technology influence through forward citations

## Step 6: Google Patents Cross-Reference
```
gp_search_patents('assignee:"Company Name"', type="ANY")
gp_get_patent_detail("patent number")
```
- ML-ranked view of company's portfolio
- Design patent discovery (often missed by PPUBS)

## Step 7: Filing Trends
Search with date filters and track:
- Analyze year-over-year filing trends
- Identify ramp-up or slow-down periods
- Correlate with business events if known
"""

PATENT_LANDSCAPE_PROMPT = """
# Patent Landscape Analysis Workflow

Map the patent landscape for a technology area using dual-engine search.

## Step 1: Define Technology Scope
- Identify the core technology area
- List related/adjacent technologies
- Define time period of interest

## Step 2: Identify Key CPC Classifications
```
get_cpc_info("G06")  → section overview
get_cpc_info("G06N3/08")  → specific subclass
```
- Find relevant CPC codes
- Map hierarchical relationships
- Note cross-cutting codes

## Step 3: Quantitative Search
```
gp_search_patents('cpc:"CODE"', type="ANY", limit=100)
ppubs_search_patents('"CODE".cpc.', limit=100)
```
- Count total patents per CPC code
- Track filings over time
- Identify growth trends

## Step 4: Top Assignee Analysis
```
ppubs_search_by_assignee("company name")
```
- Rank companies by patent count
- Calculate market share of filings
- Identify new entrants vs incumbents

## Step 5: Citation Network Analysis
```
ppubs_get_citation_network("foundational patent")
```
- Identify highly-cited foundational patents
- Map citation relationships between companies
- Find technology leaders by citation metrics

## Step 6: Design Patent Coverage
```
gp_search_patents("product category", type="DESIGN")
```
- Design patents are often more relevant for consumer products
- Google Patents ML ranking superior to PPUBS for design

## Step 7: White Space Analysis
Identify underserved areas:
- CPC codes with low filing activity
- Technology combinations not covered
- Emerging areas with few patents
"""

FREEDOM_TO_OPERATE_PROMPT = """
# Freedom to Operate (FTO) Analysis Workflow

Assess the risk of patent infringement for a product or technology using
the dual-engine (PPUBS + Google Patents) tool set.

## Step 1: Define the Product/Technology
- List all technical features and components
- Identify the country/countries of operation
- Note planned manufacturing, sale, and use locations

## Step 2: Keyword and Classification Search
```
gp_search_patents("product keywords", type="DESIGN")   → consumer product designs
gp_search_patents("technical feature", type="PATENT")  → utility patents
ppubs_search_combined("product description")           → PPUBS full-text
```
- Search for each technical feature
- Use multiple synonyms and phrasings
- Google for ML-ranked design discovery, PPUBS for full claims

## Step 3: Identify Potentially Relevant Patents
For each patent found, evaluate:
- Is it still in force? (check dates)
- Does it cover the geography of interest? (US only from these tools)
- Are the claims potentially reading on the product?

## Step 4: Detailed Claim Analysis
```
ppubs_get_full_document(guid, "USPAT")
ppubs_get_patent_by_number("patent number")
```
- Read independent claims carefully
- Compare each claim element to the product
- Document any differences (design-arounds)

## Step 5: Citation Network — Find Related Patents
```
ppubs_get_citation_network("key patent number")
```
- backward: prior art → might reveal additional risk patents through common ancestors
- forward: later patents → designs that built on this one
- Critical for finding patents with different titles in the same design family

## Step 6: Similar Patent Discovery
```
gp_get_similar_patents("patent number")
```
- ML-based similar patent discovery
- Often finds design patents with different names but similar appearance
- Complements citation-based discovery

## Step 7: Status Check
```
get_status_code("status code number")
```
- Verify patent status codes
- Check if maintenance fees are current

## Risk Assessment Categories:
- **High Risk**: Claims appear to cover product, patent is valid and enforced
- **Medium Risk**: Claims may cover, some validity questions, design-around possible
- **Low Risk**: Clear non-infringement or strong invalidity arguments
- **Clear**: No relevant patents found or all expired
"""

PRODUCT_PATENT_SEARCH_PROMPT = """
# Product Patent Search Workflow (Optimized)

Based on successful search experiences from real cases, this workflow implements
proven strategies for finding product-related patents.

## Key Tools and When to Use

| Tool | Best For | Example |
|------|----------|---------|
| `gp_search_patents` | Design patents, products with visual features | `gp_search_patents("wooden cross", "DESIGN")` |
| `ppubs_get_citation_network` | Complete patent family (ONE call) | `ppubs_get_citation_network("D656429")` |
| `ppubs_search_combined` | Multi-strategy PPUBS search | `ppubs_search_combined("pot with rotatable bottom")` |
| `ppubs_get_inventor_patents` | Track inventor's other patents | `ppubs_get_inventor_patents("D1066113")` |
| `gp_get_similar_patents` | ML-based visual/CPC similarity | `gp_get_similar_patents("D656429")` |
| `ppubs_search_by_ttl` | Exact title matching | `ppubs_search_by_ttl("self watering pot")` |
| `ppubs_search_by_assignee` | Track company patent families | `ppubs_search_by_assignee("Soak Limited", "smoker")` |
| `patent_search_aggregated` | Comprehensive multi-page retrieval | `patent_search_aggregated(["wooden cross", "religious cross"], baseline_name="religious_cross")` |
| `patent_evaluate_recall` | Verify no old-tool candidates were lost | `patent_evaluate_recall(["D1066113"], baseline_name="religious_cross")` |

## Recommended Workflow

### Phase 0: Comprehensive Retrieval (Codex recommended)
```
patent_search_aggregated(
  queries=["product phrase", "synonym", "functional phrase"],
  type="DESIGN",
  sources="BOTH",
  max_results=300,
  page_size=100,
  max_pages=3
)
```
- Prefer the returned `codex_markdown` for the chat response.
- Do not dump the full `results` array unless the user requests it.
- A short comparison table is a display limit, not a retrieval limit.
- When a historical baseline exists, require `recall.regression_pass=true` or explicitly report every missing patent.

### Phase 1: Discovery (Google Patents)
```
1. gp_search_patents("product keywords", "DESIGN")   → find core design patents
2. gp_get_similar_patents("best match")              → ML-based similar designs
3. gp_get_patent_detail("patent")                    → verify CPC, abstract
```

### Phase 2: Family Mapping (PPUBS Citations)
```
4. ppubs_get_citation_network("core patent")         → BIDIRECTIONAL: backward + forward
   This ONE call replaces running citations + cited_by separately.
   Finds patents that keyword search misses (e.g. generically titled "Cross").
```

### Phase 3: Deep Dive (PPUBS Full Text)
```
5. ppubs_get_full_document(guid, "USPAT")            → complete claims + description
6. ppubs_get_inventor_patents("patent")              → find inventor's other designs
7. ppubs_download_patent_pdf("patent number")        → official PDF for legal review
```

## Critical Strategy: Bidirectional Citation Network

**Always run `ppubs_get_citation_network` on any core patent found.**

Design patents with short/generic titles (e.g., "Cross") are INVISIBLE to
keyword search. They can ONLY be found through forward citation traversal
from earlier patents they cite. The citation_network tool handles BOTH
directions in one call, preventing missed family members.

## Success Pattern (Real Case: Cross Design Family)

```
gp_search_patents("wooden cross", "DESIGN")        → D656429 #1
ppubs_get_citation_network("D656429")              → finds ALL 8+ family members
  backward: 25 older cross designs
  forward:  D1050666 "Cross", D1066113 "Religious cross", D786128 "Heart cross"...
```

## Common Mistakes to Avoid

| Mistake | Problem | Solution |
|---------|---------|----------|
| Single-direction citations | Misses newer patents | Always use `ppubs_get_citation_network` |
| PPUBS-only for design | TF-IDF bad for short titles | Use `gp_search_patents` for design discovery |
| Skip inventor tracking | Misses related patents | Run `ppubs_get_inventor_patents` on top matches |
| Filter stop words | PPUBS needs exact phrase | Keep original phrasing |
| Treat first page as complete | Low recall and missed historical candidates | Use `patent_search_aggregated` with bounded pagination |
| Dump raw JSON into chat | Hard to compare candidates in Codex | Present `codex_markdown`, then offer full results |
| Ignore old-tool results | Silent recall regression | Run the matching historical recall baseline |
"""

# Map of prompt names to content
PROMPTS = {
    "prior_art_search": {
        "name": "Prior Art Search",
        "description": "Guide for conducting a comprehensive prior art search using PPUBS + Google Patents",
        "content": PRIOR_ART_SEARCH_PROMPT,
    },
    "patent_validity": {
        "name": "Patent Validity Analysis",
        "description": "Guide for analyzing patent validity using citation networks and full documents",
        "content": PATENT_VALIDITY_ANALYSIS_PROMPT,
    },
    "competitor_portfolio": {
        "name": "Competitor Portfolio Analysis",
        "description": "Guide for analyzing a company's patent portfolio",
        "content": COMPETITOR_PORTFOLIO_ANALYSIS_PROMPT,
    },
    "patent_landscape": {
        "name": "Patent Landscape Analysis",
        "description": "Guide for mapping a technology patent landscape",
        "content": PATENT_LANDSCAPE_PROMPT,
    },
    "freedom_to_operate": {
        "name": "Freedom to Operate Analysis",
        "description": "Guide for FTO/infringement risk analysis using dual-engine search",
        "content": FREEDOM_TO_OPERATE_PROMPT,
    },
    "product_patent_search": {
        "name": "Product Patent Search (Optimized)",
        "description": "Guide for product patent search with bidirectional citation strategy",
        "content": PRODUCT_PATENT_SEARCH_PROMPT,
    },
}


def get_prompt(name: str) -> dict:
    """Get a prompt by name."""
    if name in PROMPTS:
        return PROMPTS[name]
    return {"error": f"Unknown prompt: {name}"}


def list_prompts() -> dict:
    """List all available prompts."""
    return {
        name: {"name": p["name"], "description": p["description"]}
        for name, p in PROMPTS.items()
    }
