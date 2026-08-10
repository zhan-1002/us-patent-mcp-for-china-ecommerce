# Changelog

## 1.1.0 - 2026-08-10

### Codex experience

- Added a Codex-first chat layout based on real patent-search conversations: concise query summary, clickable candidate comparison table, and an explicit historical-recall section.
- Added `codex_markdown` to aggregated search responses. Codex should display this field first and keep the complete structured result set available on demand.
- Added a ready-to-use local `.mcp.json` for Codex and removed hard-coded third-party credentials.
- Added guidance that chat truncation is a presentation choice, not a search limit.

### Search and quality

- Added `patent_search_aggregated` with multi-query Google Patents/PPUBS pagination, global request budgets, normalized de-duplication, cross-source scoring, and up to 2,000 merged results.
- Added `patent_evaluate_recall` and `patents://recall-baselines` for non-regression checks against old-tool historical samples.
- Versioned seven initial baselines: tape measure, music box, double-lever corkscrew, stocking holder, candy-cane ornament, liquor pour spout, and religious cross.
- Existing single-engine tools remain available for focused searches and diagnostics.

### Reliability and security

- Retained the patent-number, PDF, limit, lifecycle, prompt, trademark-merge, and packaging fixes completed during the 2026-08-10 repair cycle.
- Removed an exposed third-party credential from the current MCP configuration. Repository owners must rotate the credential because removal does not erase Git history.

### Compatibility

- Tool count: 24.
- Prompt count: 6.
- Fixed resources: 5, plus existing resource templates.
- Published as the first E-commerce Patent Scout MCP release.
