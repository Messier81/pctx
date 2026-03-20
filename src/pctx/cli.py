from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from .graph import Graph
from .models import RecordType, Status
from .store import Store

app = typer.Typer(
    name="pctx",
    help="Product context that lives with your code.",
    no_args_is_help=True,
)
console = Console()


def _store() -> Store:
    return Store()


def _graph() -> Graph:
    return Graph(_store())


@app.command()
def init() -> None:
    """Initialize .context/ in the current directory."""
    store = Store(root=Path.cwd())
    ctx = store.init()
    console.print(f"[green]Initialized pctx at {ctx}[/green]")


@app.command()
def new(
    record_type: str = typer.Argument(help="decision | change | context | experience | belief | thread"),
    title: str = typer.Argument(help="Short descriptive title"),
    status: str = typer.Option("draft", help="draft|proposed|accepted|deprecated|superseded"),
    authors: list[str] | None = typer.Option(None, "--author", "-a"),
    tags: list[str] | None = typer.Option(None, "--tag", "-t"),
) -> None:
    """Create a new record."""
    from datetime import date as date_mod

    from .models import Record

    store = _store()
    rt = RecordType(record_type)
    record = Record(
        id=store.next_id(rt),
        type=rt,
        title=title,
        status=Status(status),
        date=date_mod.today(),
        authors=authors or [],
        tags=tags or [],
        body=store.template_body(rt),
    )
    saved = store.save(record)
    console.print(f"[green]Created {record.id}:[/green] {record.title}")
    console.print(f"  {saved}")


@app.command(name="list")
def list_records(
    record_type: str | None = typer.Option(None, "--type", "-T"),
    status: str | None = typer.Option(None, "--status", "-s"),
    tag: str | None = typer.Option(None, "--tag", "-t"),
    all_: bool = typer.Option(False, "--all", "-A", help="Include superseded/deprecated"),
) -> None:
    """List records with optional filters."""
    store = _store()
    rt = RecordType(record_type) if record_type else None
    st = Status(status) if status else None
    incl = all_ or status in ("deprecated", "superseded")
    records = store.list_all(record_type=rt, status=st, tag=tag, include_inactive=incl)

    if not records:
        console.print("[dim]No records found.[/dim]")
        return

    for r in records:
        status_color = {
            "accepted": "green",
            "draft": "yellow",
            "proposed": "blue",
            "deprecated": "red",
            "superseded": "dim",
        }.get(r.status.value, "white")
        tags_str = f"  [dim]({', '.join(r.tags)})[/dim]" if r.tags else ""
        console.print(
            f"  {r.id}  [{status_color}][{r.status.value}][/{status_color}]  {r.title}{tags_str}"
        )


@app.command()
def show(record_id: str = typer.Argument(help="Record ID (e.g. DEC-001)")) -> None:
    """Show a record by ID."""
    store = _store()
    r = store.get(record_id)
    console.print(f"\n[bold]{r.id}[/bold]  [{r.type.value}]  {r.title}")
    console.print(f"  Status: {r.status.value}  |  Date: {r.date}  |  Authors: {', '.join(r.authors) or 'none'}")
    if r.tags:
        console.print(f"  Tags: {', '.join(r.tags)}")
    if r.extra:
        for k, v in r.extra.items():
            console.print(f"  {k}: {v}")
    if r.links:
        console.print("  Links:")
        for lt, targets in r.links.items():
            console.print(f"    {lt}: {', '.join(targets)}")
    console.print()
    console.print(r.body)


@app.command()
def search(
    query: str = typer.Argument(help="Search term"),
    all_: bool = typer.Option(False, "--all", "-A", help="Include superseded/deprecated"),
) -> None:
    """Search records by keyword."""
    store = _store()
    results = store.search(query, include_inactive=all_)
    if not results:
        console.print(f"[dim]No results for '{query}'[/dim]")
        return
    console.print(f"Found {len(results)} result(s):\n")
    for r in results:
        console.print(f"  {r.id}  [{r.type.value}] [{r.status.value}]  {r.title}")


@app.command()
def impact(
    record_id: str = typer.Argument(help="Record ID"),
    depth: int = typer.Option(3, "--depth", "-d"),
) -> None:
    """Show what depends on or is affected by a decision."""
    graph = _graph()
    result = graph.impact(record_id, depth)
    if not result:
        console.print(f"[red]Record {record_id} not found.[/red]")
        return

    console.print(f"\n[bold]Impact: {result['id']}[/bold]  {result['title']}\n")

    if result["upstream"]:
        console.print("[blue]DEPENDS ON:[/blue]")
        for u in result["upstream"]:
            console.print(f"  <- {u['id']}: {u['title']} ({u['link_type']})")
        console.print()

    if result["downstream"]:
        console.print("[yellow]AFFECTED:[/yellow]")
        _print_tree(result["downstream"])
    else:
        console.print("[dim]No downstream dependencies.[/dim]")


@app.command()
def why(
    record_id: str = typer.Argument(help="Record ID"),
    depth: int = typer.Option(5, "--depth", "-d"),
) -> None:
    """Trace the reasoning chain behind a decision."""
    graph = _graph()
    chain = graph.why(record_id, depth)
    if not chain:
        console.print(f"[red]Record {record_id} not found.[/red]")
        return

    console.print(f"\n[bold]Why was {chain['id']} decided?[/bold]\n")
    _print_why(chain)


@app.command()
def context(query: str = typer.Argument(help="Topic to get context for")) -> None:
    """Dump all relevant context for a topic."""
    graph = _graph()
    result = graph.context_for(query)

    console.print(f"\n[bold]Context for:[/bold] {result['topic']}\n")

    if result["direct_matches"]:
        console.print("[green]DIRECTLY RELEVANT:[/green]")
        for r in result["direct_matches"]:
            console.print(f"\n  {r['id']} [{r['type']}] [{r['status']}]: {r['title']}")
            if r["body"]:
                for line in r["body"][:300].split("\n"):
                    console.print(f"    {line}")

    if result["related"]:
        console.print("\n[blue]ALSO RELATED:[/blue]")
        for r in result["related"]:
            console.print(f"\n  {r['id']} [{r['type']}] [{r['status']}]: {r['title']}")

    if not result["direct_matches"] and not result["related"]:
        console.print("[dim]No context found.[/dim]")


@app.command()
def link(
    source_id: str = typer.Argument(help="Source record ID"),
    link_type: str = typer.Argument(help="supersedes|depends_on|relates_to|enables|contradicts|inspired_by|part_of"),
    target_id: str = typer.Argument(help="Target record ID"),
) -> None:
    """Add a link between two records."""
    store = _store()
    record = store.get(source_id)
    store.get(target_id)

    if link_type not in record.links:
        record.links[link_type] = []
    if target_id not in record.links[link_type]:
        record.links[link_type].append(target_id)

    store.save(record)
    console.print(f"[green]Linked {source_id} --{link_type}--> {target_id}[/green]")


@app.command()
def supersede(
    old_id: str = typer.Argument(help="Record ID to supersede"),
    new_title: str = typer.Argument(help="Title for the replacement"),
    reason: str = typer.Option(..., "--reason", "-r", help="Why this is being replaced"),
    authors: list[str] | None = typer.Option(None, "--author", "-a"),
    tags: list[str] | None = typer.Option(None, "--tag", "-t"),
) -> None:
    """Replace a decision with a new one."""
    store = _store()
    old, new = store.supersede(old_id, new_title, reason, authors=authors, tags=tags)
    console.print(f"[red]Superseded {old.id}:[/red] {old.title}")
    console.print(f"  -> status: superseded (hidden from search/list)")
    console.print(f"[green]Created {new.id}:[/green] {new.title}")
    console.print(f"  -> supersedes: {old.id}")


@app.command()
def deprecate(
    record_id: str = typer.Argument(help="Record ID to deprecate"),
    reason: str = typer.Option(..., "--reason", "-r", help="Why this is deprecated"),
) -> None:
    """Deprecate a decision without replacing it."""
    store = _store()
    record = store.deprecate(record_id, reason)
    console.print(f"[red]Deprecated {record.id}:[/red] {record.title}")
    console.print(f"  -> reason: {reason}")


@app.command()
def delete(
    record_id: str = typer.Argument(help="Record ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Permanently delete a record."""
    store = _store()
    record = store.get(record_id)
    if not force:
        console.print(f"About to delete [bold]{record.id}[/bold]: {record.title}")
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Abort()
    deleted = store.delete(record_id)
    console.print(f"[red]Deleted {record_id}[/red] ({deleted})")


@app.command()
def serve() -> None:
    """Start the pctx MCP server."""
    from .server import mcp as mcp_server

    mcp_server.run()


def _print_tree(nodes: list[dict], indent: int = 2) -> None:
    prefix = " " * indent
    for node in nodes:
        console.print(f"{prefix}-> {node['id']}: {node['title']} ({node['link_type']})")
        if node.get("children"):
            _print_tree(node["children"], indent + 2)


def _print_why(node: dict, indent: int = 0) -> None:
    pre = " " * indent
    console.print(f"{pre}{node['id']} [{node['type']}]: {node['title']}")
    for info in node.get("informed_by", []):
        console.print(f"{pre}  [dim]<- informed by {info['id']} [{info['type']}]: {info['title']}[/dim]")
    for cause in node.get("because", []):
        console.print(f"{pre}  [blue]^ because:[/blue]")
        _print_why(cause, indent + 4)
