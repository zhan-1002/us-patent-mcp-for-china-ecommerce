# E-commerce Patent Scout MCP: Practical Tutorial

This tutorial shows how to turn an e-commerce product description into a reproducible US patent search with pagination, source aggregation, citation expansion, and historical recall checks.

## 1. Install

```bash
git clone https://github.com/zhan-1002/ecommerce-patent-scout-mcp.git
cd ecommerce-patent-scout-mcp
uv sync
uv run patent-mcp-server
```

The core PPUBS, Google Patents, and trademark search paths do not require a USPTO ODP API key. Never commit third-party credentials.

## 2. Connect Codex

The repository includes a safe `.mcp.json`. Start Codex from the repository directory and confirm that the `patents` MCP server is available.

Try this first prompt:

```text
Use the patents MCP to search US design patents for religious cross.
Expand wooden cross, heart cross, and cross ornament,
run paginated PPUBS and Google Patents aggregation,
and present codex_markdown first.
```

## 3. Build the query set

Do not rely on a literal translation of a product listing. Cover multiple dimensions:

| Dimension | Example |
|---|---|
| Generic product | bottle pourer |
| Formal or trade term | olive oil nozzle |
| Function | drip-free pouring |
| Structure | tapered stopper, air tube |
| Shape | curved spout |
| Use context | liquor bottle, oil bottle |

Product language and patent titles can differ substantially. D951706 looks like a liquor pour spout in commerce, while its patent title is `Olive oil nozzle`.

## 4. Run bounded aggregation

Ask Codex to call `patent_search_aggregated` with explicit bounds:

```text
queries:
- bottle pour spout
- bottle pourer
- olive oil nozzle
type: DESIGN
sources: BOTH
page_size: 100
max_pages: 3
max_requests: 18
expand_citations: true
```

Inspect four things in the response:

1. Requests executed for each query and source;
2. Source failures such as Google 503 or a PPUBS transport error;
3. The merged, de-duplicated candidate count;
4. Which seed patents were used for citation expansion.

`max_requests` is a network budget, not the total number of patents in the database. Improve query diversity before increasing page depth.

## 5. Evaluate historical recall

When an older tool produced a known candidate set, select its baseline:

```text
baseline_name: liquor_pour_spout
minimum_recall: 1.0
```

Recall answers whether the new search still finds known historical candidates. It is not code coverage, and it does not mean that every returned result is relevant.

## 6. Expand strong candidates

For a relevant design patent, continue with:

```text
ppubs_get_citation_network
gp_get_similar_patents
ppubs_search_by_inventor
ppubs_search_by_assignee
ppubs_download_patent_pdf
```

Citations, shared inventors, and shared assignees are discovery signals. Design-patent risk still requires comparison of the overall visual impression shown in the official figures.

## 7. Recommended chat layout

Ask Codex to show:

1. Search execution summary;
2. A focused patent comparison table;
3. Historical recall results;
4. Partial failures and search boundaries;
5. Official PDF figures that need human review.

Keep hundreds of raw records out of the main chat. The complete data remains available in structured `results`.

## 8. Common mistakes

- Searching only one literal product phrase;
- Treating a single-page `limit` as the complete result set;
- Ignoring design patents with generic titles;
- Repeatedly retrying Google after a 503;
- Injecting expected patent numbers into queries to manufacture perfect recall;
- Treating a title match as an infringement conclusion.

The result is an explainable candidate set for preliminary screening, not legal advice.
