# pctx

Product context that lives with your code. Track decisions, architecture, and the "why" as your codebase evolves.

## Install

```bash
pip install -e .
```

## Usage

### CLI

```bash
pctx init                          # set up .context/ in your repo
pctx new decision "Choose Postgres" # create a decision record
pctx list                           # list all records
pctx show DEC-001                   # show a record
pctx search "database"              # search by keyword
pctx impact DEC-001                 # what's affected if this changes?
pctx why DEC-001                    # trace the reasoning chain
pctx context "auth"                 # dump all context for a topic
pctx link DEC-002 depends_on DEC-001 # add a link
```

### MCP Server

```bash
pctx serve
```

Or configure in your AI editor (Cursor, etc.):

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
