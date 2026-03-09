from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from fastmcp import FastMCP

from .graph import Graph
from .models import PREFIXES, RecordType, Status, Record
from .store import Store

mcp = FastMCP(
    name="pctx",
    instructions=(
        "Product context server. Use these tools to understand product "
        "decisions, architecture choices, and the reasoning behind them.\n\n"
        "Before implementing features or making architectural changes:\n"
        "1. Search for relevant decisions with pctx_search\n"
        "2. Check impact of changes with pctx_impact\n"
        "3. Understand reasoning with pctx_why\n\n"
        "Never contradict an accepted decision without flagging it to the user."
    ),
)


def _root() -> Path:
    env = os.environ.get("PCTX_ROOT")
    return Path(env) if env else Path.cwd()


def _store() -> Store:
    return Store(root=_root())


def _graph() -> Graph:
    return Graph(_store())


def _fmt_record(r: Record) -> str:
    lines = [
        f"ID: {r.id}",
        f"Type: {r.type.value}",
        f"Title: {r.title}",
        f"Status: {r.status.value}",
        f"Date: {r.date}",
        f"Authors: {', '.join(r.authors) or 'none'}",
        f"Tags: {', '.join(r.tags) or 'none'}",
    ]
    if r.links:
        lines.append("Links:")
        for lt, targets in r.links.items():
            lines.append(f"  {lt}: {', '.join(targets)}")
    lines.append(f"\n{r.body}")
    return "\n".join(lines)


def _fmt_impact_tree(nodes: list[dict], lines: list[str], indent: int = 0) -> None:
    prefix = " " * indent
    for node in nodes:
        lines.append(f"{prefix}-> {node['id']}: {node['title']} ({node['link_type']})")
        if node.get("children"):
            _fmt_impact_tree(node["children"], lines, indent + 2)


def _fmt_why(node: dict, lines: list[str], indent: int = 0) -> None:
    pre = " " * indent
    lines.append(f"{pre}{node['id']} [{node['type']}]: {node['title']}")
    for info in node.get("informed_by", []):
        lines.append(f"{pre}  <- informed by {info['id']} [{info['type']}]: {info['title']}")
    for cause in node.get("because", []):
        lines.append(f"{pre}  ^ because:")
        _fmt_why(cause, lines, indent + 4)


# ── Tools ──────────────────────────────────────────────────────


@mcp.tool
def pctx_init(path: str | None = None) -> str:
    """Initialize a .context/ directory in a repository.

    Creates the directory structure for storing product decisions,
    changes, and context records. Run this once per repo.

    Args:
        path: Repo root directory. Defaults to PCTX_ROOT or cwd.
    """
    store = Store(root=Path(path) if path else _root())
    ctx = store.init()
    return f"Initialized pctx at {ctx}"


@mcp.tool
def pctx_new(
    record_type: str,
    title: str,
    body: str = "",
    authors: list[str] | None = None,
    tags: list[str] | None = None,
    status: str = "draft",
    links: dict[str, list[str]] | None = None,
    path: str | None = None,
) -> str:
    """Create a new product context record.

    Args:
        record_type: One of "decision", "change", or "context".
        title: Short descriptive title.
        body: Markdown body (sections like ## Context, ## Decision, ## Why).
              If empty, a template is generated.
        authors: List of author identifiers.
        tags: List of tags for categorization.
        status: draft | proposed | accepted | deprecated | superseded.
        links: {link_type: [record_ids]}. Types: supersedes, depends_on,
               relates_to, enables.
        path: Repo root directory.
    """
    store = Store(root=Path(path) if path else _root())
    rt = RecordType(record_type)
    record = Record(
        id=store.next_id(rt),
        type=rt,
        title=title,
        status=Status(status),
        date=date.today(),
        authors=authors or [],
        links=links or {},
        tags=tags or [],
        body=body or store.template_body(rt),
    )
    saved = store.save(record)
    return f"Created {record.id}: {record.title}\nSaved to {saved}"


@mcp.tool
def pctx_show(record_id: str, path: str | None = None) -> str:
    """Show a specific record by ID (e.g. DEC-001, CHG-002, CTX-003).

    Args:
        record_id: The record ID.
        path: Repo root directory.
    """
    store = Store(root=Path(path) if path else _root())
    return _fmt_record(store.get(record_id))


@mcp.tool
def pctx_list(
    record_type: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    path: str | None = None,
) -> str:
    """List product context records with optional filters.

    Args:
        record_type: Filter by decision | change | context.
        status: Filter by draft | proposed | accepted | deprecated | superseded.
        tag: Filter by tag.
        path: Repo root directory.
    """
    store = Store(root=Path(path) if path else _root())
    rt = RecordType(record_type) if record_type else None
    st = Status(status) if status else None
    records = store.list_all(record_type=rt, status=st, tag=tag)

    if not records:
        return "No records found."

    lines: list[str] = []
    for r in records:
        line = f"{r.id}  [{r.status.value}]  {r.title}"
        if r.tags:
            line += f"  ({', '.join(r.tags)})"
        lines.append(line)
    return "\n".join(lines)


@mcp.tool
def pctx_search(query: str, path: str | None = None) -> str:
    """Search records by keyword in titles, body, and tags.

    Use before implementing a feature to find relevant decisions.

    Args:
        query: Search term (e.g. "template builder", "authentication").
        path: Repo root directory.
    """
    store = Store(root=Path(path) if path else _root())
    results = store.search(query)

    if not results:
        return f"No records matching '{query}'."

    lines = [f"Found {len(results)} record(s) matching '{query}':\n"]
    for r in results:
        lines.append(f"  {r.id}  [{r.type.value}] [{r.status.value}]  {r.title}")
    return "\n".join(lines)


@mcp.tool
def pctx_impact(record_id: str, depth: int = 3, path: str | None = None) -> str:
    """Show what depends on or is affected by a decision.

    Use when considering changes to understand downstream consequences.

    Args:
        record_id: The record ID to analyze (e.g. DEC-005).
        depth: How many levels deep to trace (default 3).
        path: Repo root directory.
    """
    graph = Graph(Store(root=Path(path) if path else _root()))
    result = graph.impact(record_id, depth)

    if not result:
        return f"Record {record_id} not found."

    lines = [f"Impact analysis for {result['id']}: {result['title']}\n"]

    if result["upstream"]:
        lines.append("DEPENDS ON:")
        for u in result["upstream"]:
            lines.append(f"  <- {u['id']}: {u['title']} ({u['link_type']})")
        lines.append("")

    if result["downstream"]:
        lines.append("AFFECTED (downstream):")
        _fmt_impact_tree(result["downstream"], lines, indent=2)
    else:
        lines.append("No downstream dependencies found.")

    return "\n".join(lines)


@mcp.tool
def pctx_why(record_id: str, depth: int = 5, path: str | None = None) -> str:
    """Trace the reasoning chain behind a decision.

    Follows depends_on and enables links to explain WHY a decision
    was made, from root causes to the final decision.

    Args:
        record_id: The decision ID to trace (e.g. DEC-002).
        depth: How many levels deep (default 5).
        path: Repo root directory.
    """
    graph = Graph(Store(root=Path(path) if path else _root()))
    chain = graph.why(record_id, depth)

    if not chain:
        return f"Record {record_id} not found."

    lines = [f"Why was {chain['id']} decided?\n"]
    _fmt_why(chain, lines, indent=0)
    return "\n".join(lines)


@mcp.tool
def pctx_context(topic: str, path: str | None = None) -> str:
    """Get all relevant product context for a topic.

    Searches and expands links for comprehensive context.
    Use before implementing features to understand the full picture.

    Args:
        topic: Topic to query (e.g. "template builder", "enterprise").
        path: Repo root directory.
    """
    graph = Graph(Store(root=Path(path) if path else _root()))
    result = graph.context_for(topic)

    lines = [f"Context for: {result['topic']}\n"]

    if result["direct_matches"]:
        lines.append("DIRECTLY RELEVANT:")
        for r in result["direct_matches"]:
            lines.append(f"\n  {r['id']} [{r['type']}] [{r['status']}]: {r['title']}")
            if r["body"]:
                preview = r["body"][:300].replace("\n", "\n    ")
                lines.append(f"    {preview}")

    if result["related"]:
        lines.append("\n\nALSO RELATED (via links):")
        for r in result["related"]:
            lines.append(f"\n  {r['id']} [{r['type']}] [{r['status']}]: {r['title']}")
            if r["body"]:
                preview = r["body"][:200].replace("\n", "\n    ")
                lines.append(f"    {preview}")

    if not result["direct_matches"] and not result["related"]:
        lines.append("No context found for this topic.")

    return "\n".join(lines)


@mcp.tool
def pctx_link(
    source_id: str, link_type: str, target_id: str, path: str | None = None
) -> str:
    """Add a link between two records.

    Args:
        source_id: Source record ID.
        link_type: supersedes | depends_on | relates_to | enables.
        target_id: Target record ID.
        path: Repo root directory.
    """
    store = Store(root=Path(path) if path else _root())
    record = store.get(source_id)
    store.get(target_id)  # verify target exists

    if link_type not in record.links:
        record.links[link_type] = []
    if target_id not in record.links[link_type]:
        record.links[link_type].append(target_id)

    store.save(record)
    return f"Linked {source_id} --{link_type}--> {target_id}"
