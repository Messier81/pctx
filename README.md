# pctx

Product context that lives with your code. Track decisions, architecture, and the *why* as your codebase evolves.

AI assistants are great at reading code. They're terrible at understanding *why* the code exists, what alternatives were considered, and what breaks if you change direction. `pctx` fixes that by giving your repo a structured, queryable memory of product and architecture decisions.

## What it does

- **Decisions** (`DEC-001`) — What was chosen and why. Alternatives considered, consequences accepted.
- **Changes** (`CHG-001`) — What shifted organizationally or strategically, and what it enabled.
- **Context** (`CTX-001`) — Background knowledge that informs decisions but isn't a decision itself.

Records are markdown files with YAML frontmatter, stored in `.context/` inside your repo. Human readable, git diffable, PR reviewable.

Records link to each other with typed edges (`depends_on`, `enables`, `relates_to`, `supersedes`), forming a lightweight graph that can be traversed to answer questions like:

- *"What breaks if we change this decision?"* → `pctx impact DEC-003`
- *"Why was this decided?"* → `pctx why DEC-005`
- *"Give me everything about auth"* → `pctx context auth`

## Install

```bash
pip install -e .
```

## CLI

```bash
pctx init                                    # set up .context/ in your repo
pctx new decision "Choose Postgres"          # create a decision record
pctx new context "Why we avoid ORMs"         # create a context record
pctx new change "Migrated to microservices"  # create a change record
pctx list                                    # list all active records
pctx list --type decision --status accepted  # filter by type and status
pctx list --all                              # include superseded/deprecated
pctx show DEC-001                            # show a specific record
pctx search "database"                       # search active records
pctx search "database" --all                 # search everything
pctx link DEC-002 depends_on DEC-001         # add a link between records
pctx impact DEC-001                          # what's affected if this changes?
pctx why DEC-005                             # trace the reasoning chain
pctx context "auth"                          # dump all context for a topic
```

### Lifecycle

Decisions aren't permanent. When one turns out to be wrong:

```bash
pctx supersede DEC-001 "Use Memcached" -r "Redis licensing changed"
pctx deprecate DEC-003 -r "No longer relevant after rewrite"
pctx delete DEC-007 --force                  # hard delete (no history)
```

- **`supersede`** marks the old record as superseded, creates a replacement that links back, and adds a warning banner to the old body.
- **`deprecate`** marks it as inactive without a replacement.
- **`delete`** removes the file entirely (use for duplicates/mistakes, not wrong decisions).

Superseded and deprecated records are **hidden by default** from `list`, `search`, and `context`. AI assistants will never accidentally reference an outdated decision. Use `--all` (CLI) or `include_inactive=True` (MCP) to see them.

## MCP Server

`pctx` is an MCP (Model Context Protocol) server, so AI assistants can query your product context directly as a tool.

```bash
pctx serve
```

To configure in Cursor (or any MCP-compatible editor):

```json
{
  "mcpServers": {
    "pctx": {
      "command": "pctx",
      "args": ["serve"],
      "env": { "PCTX_ROOT": "/path/to/your/repo" }
    }
  }
}
```

### Available MCP tools

| Tool | Description |
|------|-------------|
| `pctx_init` | Initialize `.context/` in a repo |
| `pctx_new` | Create a decision, change, or context record |
| `pctx_show` | Read a specific record by ID |
| `pctx_list` | List records with type/status/tag filters |
| `pctx_search` | Keyword search across titles, body, and tags |
| `pctx_impact` | Trace downstream — what breaks if this changes? |
| `pctx_why` | Trace upstream — reasoning chain behind a decision |
| `pctx_context` | Dump everything relevant to a topic |
| `pctx_link` | Add a typed link between two records |
| `pctx_supersede` | Replace a decision with a new one (hides old from AI) |
| `pctx_deprecate` | Mark a decision as inactive without replacement |
| `pctx_delete` | Permanently remove a record |

## How it works

```
your-repo/
├── .context/
│   ├── config.yaml
│   ├── decisions/
│   │   ├── DEC-001.md
│   │   └── DEC-002.md
│   ├── changes/
│   │   └── CHG-001.md
│   └── contexts/
│       └── CTX-001.md
├── src/
└── ...
```

Each record is a markdown file with YAML frontmatter:

```yaml
---
id: DEC-002
type: decision
title: "Use Postgres over DynamoDB"
status: accepted
date: 2026-01-15
authors: [jane, carlos]
tags: [database, infrastructure]
links:
  depends_on: DEC-001
  relates_to: [CTX-001, CTX-002]
---

## Context
We need a primary datastore for the application.

## Decision
Use PostgreSQL with pgvector for combined relational + vector storage.

## Why
- Need ACID transactions for financial data
- pgvector avoids a separate vector DB dependency
- Team has deep Postgres expertise

## Alternatives Considered
1. **DynamoDB** — Rejected. No relational joins, vendor lock-in.
2. **MongoDB** — Rejected. Schema flexibility isn't needed here.

## Consequences
- Must manage connection pooling at scale
- Tied to SQL migration tooling
```

## License

MIT
