from unittest.mock import AsyncMock

import pytest

from patent_mcp_server import patents
from patent_mcp_server.google.gp_client import GooglePatentsClient
from patent_mcp_server.uspto.tmsearch_client import TmSearchClient
from patent_mcp_server.util.response import ResponseEnvelope
from patent_mcp_server.util.validation import validate_patent_number
from patent_mcp_server.util.aggregation import (
    evaluate_recall,
    load_recall_baselines,
    merge_patent_results,
    normalize_patent_number,
    render_codex_markdown,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("d1066113", "D1066113"),
        ("usd1066113s1", "D1066113"),
        ("US D1066113 S", "D1066113"),
        ("us8881623b2", "8881623"),
        ("8881623", "8881623"),
    ],
)
def test_patent_number_normalization_is_case_insensitive(raw, expected):
    assert validate_patent_number(raw) == expected


def test_exact_patent_match_rejects_same_digits_with_different_type():
    rows = [
        {"documentId": "US-1066113-A", "guid": "wrong"},
        {"documentId": "US D1066113 S", "guid": "right"},
    ]
    assert patents._find_exact_patent(rows, "D1066113")["guid"] == "right"
    assert patents._find_exact_patent(rows[:1], "D1066113") is None


@pytest.mark.asyncio
async def test_patent_search_ignores_non_exact_first_query_result(monkeypatch):
    run_query = AsyncMock(
        side_effect=[
            {"patents": [{"documentId": "US-1066113-A", "guid": "wrong"}]},
            {"patents": [{"documentId": "US D1066113 S", "guid": "right"}]},
        ]
    )
    monkeypatch.setattr(patents.ppubs_client, "run_query", run_query)
    result = await patents._search_patent_by_number("D1066113")
    assert result["patent"]["guid"] == "right"


def test_google_client_normalization_respects_limit():
    raw = {
        "results": {
            "total_num_results": 10,
            "cluster": [
                {"result": [{"patent": {"publication_number": f"USD{i}S1"}} for i in range(10)]}
            ],
        }
    }
    client = GooglePatentsClient()
    result = client._normalize_search_response(raw, "music box", "DESIGN", 3, 0)
    assert result["count"] == 3
    assert len(result["results"]) == 3
    assert result["limit"] == 3


def test_google_response_envelope_defensively_respects_limit():
    raw = {"results": [{"pn": str(i)} for i in range(10)], "count": 10, "total": 20}
    result = ResponseEnvelope.from_google(raw, offset=0, limit=3)
    assert result["count"] == 3
    assert len(result["results"]) == 3


def test_tmsearch_request_and_response_contract():
    body = TmSearchClient.build_search_body(
        mark_text="Nike", international_class="25", status_filter="live", limit=250
    )
    assert body["size"] == 100
    filters = body["query"]["bool"]["filter"]
    assert {"term": {"internationalClass": "025"}} in filters
    assert {"term": {"alive": True}} in filters

    parsed = TmSearchClient.parse_search_response(
        {"hits": {"totalValue": 1, "hits": [{"id": "75187260", "source": {"wordmark": "NIKE"}}]}}
    )
    assert parsed == {"total": 1, "results": [{"id": "75187260", "wordmark": "NIKE"}]}


def test_mcp_surface_contains_merged_tools_and_only_valid_prompts():
    tools = patents.mcp._tool_manager._tools
    prompts = patents.mcp._prompt_manager._prompts
    assert "ppubs_get_citation_network" in tools
    assert "tmsearch_search" in tools
    assert "tmsearch_get_by_serial" in tools
    assert "patent_search_aggregated" in tools
    assert "patent_evaluate_recall" in tools
    assert "ptab_proceeding_research" not in prompts
    assert "patent_cross_validation" not in prompts


def test_historical_recall_baselines_are_versioned_and_normalizable():
    baselines = load_recall_baselines()
    assert {
        "tape_measure",
        "music_box",
        "double_lever_corkscrew",
        "stocking_holder",
        "candy_cane_ornament",
        "liquor_pour_spout",
        "religious_cross",
    } <= baselines.keys()
    for baseline in baselines.values():
        assert baseline["queries"]
        assert baseline["expected_patents"]
        assert all(normalize_patent_number(pn) for pn in baseline["expected_patents"])


def test_recall_evaluation_distinguishes_design_from_utility_numbers():
    result = evaluate_recall(
        ["US-1066113-A", "USD1066113S1"],
        ["D1066113", "US8881623B2"],
    )
    assert result["found_patents"] == ["D1066113"]
    assert result["missing_patents"] == ["8881623"]
    assert result["recall_percent"] == 50.0
    assert result["regression_pass"] is False


def test_merge_and_codex_layout_are_compact_clickable_and_deduplicated():
    batches = [
        {
            "source": "google_patents",
            "query": "religious cross",
            "results": [{"pn": "D1066113", "title": "Religious cross", "url": "https://example.test/d"}],
        },
        {
            "source": "ppubs",
            "query": "cross ornament",
            "results": [{"documentId": "US D1066113 S", "inventionTitle": "Religious cross"}],
        },
    ]
    merged = merge_patent_results(batches, max_results=20)
    assert len(merged) == 1
    assert merged[0]["sources"] == ["google_patents", "ppubs"]
    markdown = render_codex_markdown(
        [{"source": "google_patents", "query": "religious cross", "collected": 1, "requests": 1, "error": None}],
        merged,
        evaluate_recall(["D1066113"], ["D1066113"]),
    )
    assert "### 检索情况" in markdown
    assert "[D1066113](https://example.test/d)" in markdown
    assert "召回率：**100.0%**" in markdown


@pytest.mark.asyncio
async def test_aggregated_search_paginates_deduplicates_and_checks_baseline(monkeypatch):
    search = AsyncMock(
        side_effect=[
            {
                "success": True,
                "results": [
                    {"pn": "D951706", "title": "Pour spout"},
                    {"pn": "D100000", "title": "Bottle pourer"},
                ],
                "total": 3,
            },
            {
                "success": True,
                "results": [{"pn": "USD951706S1", "title": "Pour spout"}],
                "total": 3,
            },
        ]
    )
    monkeypatch.setattr(patents.gp_client, "search", search)
    result = await patents.patent_search_aggregated(
        queries=["bottle pour spout"],
        sources="GOOGLE",
        page_size=2,
        max_pages=3,
        baseline_name="liquor_pour_spout",
    )
    assert result["success"] is True
    assert result["requests_used"] == 2
    assert result["unique_count"] == 2
    assert result["recall"]["regression_pass"] is True
    assert result["recall"]["recall_percent"] == 100.0
    assert "### 重点专利对比" in result["codex_markdown"]


@pytest.mark.asyncio
async def test_google_aggregate_offsets_use_google_page_cap(monkeypatch):
    first_page = [{"pn": f"D{i}"} for i in range(100000, 100100)]
    search = AsyncMock(
        side_effect=[
            {"success": True, "results": first_page, "total": 101},
            {"success": True, "results": [{"pn": "D100100"}], "total": 101},
        ]
    )
    monkeypatch.setattr(patents.gp_client, "search", search)
    await patents.patent_search_aggregated(
        queries=["test"], sources="GOOGLE", page_size=500, max_pages=2
    )
    assert search.await_args_list[0].kwargs["offset"] == 0
    assert search.await_args_list[0].kwargs["limit"] == 100
    assert search.await_args_list[1].kwargs["offset"] == 100


@pytest.mark.asyncio
async def test_aggregate_circuit_breaks_failed_google_and_continues_ppubs(monkeypatch):
    google_search = AsyncMock(return_value={"error": True, "message": "rate limited", "status_code": 503})
    ppubs_search = AsyncMock(
        return_value={
            "patents": [{"documentId": "US D1066113 S", "inventionTitle": "<span>Religious</span> cross"}],
            "numFound": 1,
        }
    )
    monkeypatch.setattr(patents.gp_client, "search", google_search)
    monkeypatch.setattr(patents.ppubs_client, "run_query", ppubs_search)
    result = await patents.patent_search_aggregated(
        queries=["religious cross", "wooden cross"], sources="BOTH", type="DESIGN",
        expand_citations=False,
    )
    assert google_search.await_count == 1
    assert ppubs_search.await_count == 2
    assert result["disabled_engines"] == ["google_patents"]
    assert result["results"][0]["title"] == "Religious cross"


@pytest.mark.asyncio
async def test_aggregate_isolates_transport_exception_and_continues_other_source(monkeypatch):
    google_search = AsyncMock(
        return_value={
            "success": True,
            "results": [{"pn": "D951706", "title": "Olive oil nozzle"}],
            "total": 1,
        }
    )
    ppubs_search = AsyncMock(side_effect=OSError("temporary outage"))
    monkeypatch.setattr(patents.gp_client, "search", google_search)
    monkeypatch.setattr(patents.ppubs_client, "run_query", ppubs_search)

    result = await patents.patent_search_aggregated(
        queries=["olive oil nozzle"], sources="BOTH", type="DESIGN",
        expected_patents=["D951706"], expand_citations=False,
    )

    assert result["success"] is True
    assert result["recall"]["regression_pass"] is True
    assert result["disabled_engines"] == ["ppubs"]
    assert "temporary outage" in result["query_stats"][1]["error"]


@pytest.mark.asyncio
async def test_aggregate_citation_expansion_recovers_generic_design_title(monkeypatch):
    ppubs_search = AsyncMock(
        return_value={
            "patents": [{"documentId": "US D656429 S", "inventionTitle": "Wooden cross"}],
            "numFound": 1,
        }
    )
    citation_network = AsyncMock(
        return_value={
            "success": True,
            "backward": [{"pn": "D1050666", "type": "design"}],
            "forward": [],
        }
    )
    monkeypatch.setattr(patents.ppubs_client, "run_query", ppubs_search)
    monkeypatch.setattr(patents, "ppubs_get_citation_network", citation_network)
    result = await patents.patent_search_aggregated(
        queries=["wooden cross"],
        sources="PPUBS",
        type="DESIGN",
        expected_patents=["D1050666"],
        max_requests=6,
    )
    assert result["citation_seeds"] == ["D656429"]
    assert result["recall"]["regression_pass"] is True
    assert {item["patent_number"] for item in result["results"]} == {"D656429", "D1050666"}


@pytest.mark.asyncio
async def test_ppubs_pagination_does_not_trust_page_capped_num_found(monkeypatch):
    page = [{"documentId": f"US D{i} S"} for i in range(100000, 100002)]
    run_query = AsyncMock(
        side_effect=[
            {"patents": page, "numFound": 2},
            {"patents": page, "numFound": 2},
            {"patents": [{"documentId": "US D100002 S"}], "numFound": 1},
        ]
    )
    monkeypatch.setattr(patents.ppubs_client, "run_query", run_query)
    batch = await patents._collect_aggregated_pages(
        "ppubs", "music box", "DESIGN", page_size=2, max_pages=5, request_budget=5
    )
    assert batch["requests"] == 3
    assert [call.kwargs["start"] for call in run_query.await_args_list] == [0, 2, 4]


@pytest.mark.asyncio
async def test_registered_prompt_functions_all_return_content():
    prompt_functions = (
        patents.prior_art_search,
        patents.patent_validity_analysis,
        patents.competitor_portfolio_analysis,
        patents.freedom_to_operate,
        patents.patent_landscape,
        patents.product_patent_search,
    )
    for prompt_function in prompt_functions:
        assert await prompt_function()


@pytest.mark.asyncio
async def test_cleanup_is_idempotent(monkeypatch):
    ppubs_close = AsyncMock()
    google_close = AsyncMock()
    trademark_close = AsyncMock()
    monkeypatch.setattr(patents.ppubs_client, "close", ppubs_close)
    monkeypatch.setattr(patents.gp_client, "close", google_close)
    monkeypatch.setattr(patents.tmsearch_client, "close", trademark_close)
    monkeypatch.setattr(patents, "_cleanup_complete", False)

    await patents.cleanup()
    await patents.cleanup()

    ppubs_close.assert_awaited_once()
    google_close.assert_awaited_once()
    trademark_close.assert_awaited_once()
