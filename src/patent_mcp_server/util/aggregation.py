"""Pure helpers for aggregated patent search and recall evaluation."""

from importlib.resources import files
import json
import re
from typing import Any, Dict, Iterable, List, Optional


def normalize_patent_number(value: Any) -> str:
    """Normalize common US patent formats without conflating design patents."""
    text = re.sub(r"[\s-]+", "", str(value or "")).upper()
    match = re.match(r"^US([A-Z]{0,2}\d+?)(?:[A-Z]\d*)?$", text)
    if match:
        return match.group(1)
    match = re.match(r"^([A-Z]{0,2}\d+?)(?:[A-Z]\d*)?$", text)
    return match.group(1) if match else ""


def load_recall_baselines() -> Dict[str, Dict[str, Any]]:
    path = files("patent_mcp_server").joinpath("json/recall_baselines.json")
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_recall(
    retrieved_patents: Iterable[Any],
    expected_patents: Iterable[Any],
    minimum_recall: float = 1.0,
) -> Dict[str, Any]:
    """Compare retrieved patent numbers with a historical expected set."""
    retrieved = {normalize_patent_number(item) for item in retrieved_patents}
    expected = {normalize_patent_number(item) for item in expected_patents}
    retrieved.discard("")
    expected.discard("")
    found = sorted(expected & retrieved)
    missing = sorted(expected - retrieved)
    recall = len(found) / len(expected) if expected else 1.0
    return {
        "expected_count": len(expected),
        "retrieved_unique_count": len(retrieved),
        "found_count": len(found),
        "recall": round(recall, 4),
        "recall_percent": round(recall * 100, 2),
        "minimum_recall": minimum_recall,
        "regression_pass": recall >= minimum_recall,
        "found_patents": found,
        "missing_patents": missing,
    }


def merge_patent_results(
    batches: Iterable[Dict[str, Any]], max_results: int
) -> List[Dict[str, Any]]:
    """Normalize, score, and de-duplicate results from query/source batches."""
    merged: Dict[str, Dict[str, Any]] = {}
    for batch in batches:
        source = batch["source"]
        query = batch["query"]
        for rank, row in enumerate(batch.get("results", [])):
            raw_number = (
                row.get("pn")
                or row.get("documentId")
                or row.get("patentNumber")
                or row.get("publication_number")
            )
            patent_number = normalize_patent_number(raw_number)
            if not patent_number:
                continue
            item = merged.setdefault(
                patent_number,
                {
                    "patent_number": patent_number,
                    "title": _clean_text(row.get("title") or row.get("inventionTitle") or ""),
                    "date": row.get("date") or row.get("publicationDate") or row.get("datePublished") or "",
                    "assignee": row.get("assignee") or row.get("assigneeName") or "",
                    "url": row.get("url") or _google_patent_url(raw_number, patent_number),
                    "sources": [],
                    "matched_queries": [],
                    "score": 0.0,
                },
            )
            if source not in item["sources"]:
                item["sources"].append(source)
                item["score"] += 3.0
            if query not in item["matched_queries"]:
                item["matched_queries"].append(query)
                item["score"] += 2.0
            item["score"] += max(0.0, 1.0 - rank / 1000)
            for field in ("title", "date", "assignee", "url"):
                if not item[field]:
                    item[field] = _clean_text(row.get(field, "")) if field == "title" else row.get(field, "")
    ranked = sorted(
        merged.values(),
        key=lambda item: (-item["score"], item["patent_number"]),
    )
    for item in ranked:
        item["score"] = round(item["score"], 3)
    return ranked[:max_results]


def render_codex_markdown(
    query_stats: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    recall: Optional[Dict[str, Any]] = None,
    top_n: int = 12,
) -> str:
    """Render a compact chat-first layout modeled on the supplied screenshot."""
    lines = ["### 检索情况", ""]
    for stat in query_stats:
        state = f"失败：{stat['error']}" if stat.get("error") else f"收集 {stat['collected']} 条"
        lines.append(f"- `{stat['source']}` · `{stat['query']}`：{state}（{stat['requests']} 次请求）")
    lines.extend(["", "### 重点专利对比", "", "| 专利 | 标题 | 来源 | 命中检索词 |", "|---|---|---|---|"])
    for item in results[:top_n]:
        number = item["patent_number"]
        title = str(item.get("title") or "—").replace("|", "\\|")
        sources = ", ".join(item.get("sources", []))
        queries = ", ".join(item.get("matched_queries", [])[:3]).replace("|", "\\|")
        lines.append(f"| [{number}]({item['url']}) | {title} | {sources} | {queries} |")
    if not results:
        lines.append("| — | 未找到结果 | — | — |")
    if recall:
        status = "通过" if recall["regression_pass"] else "未通过"
        lines.extend(
            [
                "",
                "### 历史样本召回",
                "",
                f"- 召回率：**{recall['recall_percent']}%**（{recall['found_count']}/{recall['expected_count']}），回归{status}",
                f"- 未召回：{', '.join(recall['missing_patents']) or '无'}",
            ]
        )
    lines.extend(["", f"> 共合并去重 {len(results)} 件；表格仅展示前 {min(top_n, len(results))} 件，完整数据保留在 `results`。"])
    return "\n".join(lines)


def _google_patent_url(raw_number: Any, normalized: str) -> str:
    raw = re.sub(r"[\s-]+", "", str(raw_number or "")).upper()
    google_number = raw if raw.startswith("US") else f"US{normalized}"
    return f"https://patents.google.com/patent/{google_number}/en"


def _clean_text(value: Any) -> str:
    return re.sub(r"<[^>]+>", "", str(value or "")).replace("&amp;", "&").strip()
