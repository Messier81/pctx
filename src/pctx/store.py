from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from .models import (
    DIRS,
    INACTIVE_STATUSES,
    PREFIX_TO_TYPE,
    PREFIXES,
    Record,
    RecordType,
    Status,
)

_TEMPLATE_SECTIONS: dict[RecordType, str] = {
    RecordType.DECISION: (
        "## Context\n\n\n\n"
        "## Decision\n\n\n\n"
        "## Why\n\n\n\n"
        "## Alternatives Considered\n\n\n\n"
        "## Consequences\n\n"
    ),
    RecordType.CHANGE: (
        "## What Changed\n\n\n\n"
        "## Why\n\n\n\n"
        "## Impact\n\n"
    ),
    RecordType.CONTEXT: (
        "## Background\n\n\n\n"
        "## Why This Matters\n\n"
    ),
    RecordType.EXPERIENCE: (
        "## What Happened\n\n\n\n"
        "## Reaction\n\n\n\n"
        "## What It Connects To\n\n"
    ),
    RecordType.BELIEF: (
        "## Position\n\n\n\n"
        "## Why I Think This\n\n\n\n"
        "## What Could Change My Mind\n\n"
    ),
    RecordType.THREAD: (
        "## What This Is About\n\n\n\n"
        "## Current State\n\n\n\n"
        "## Open Questions\n\n"
    ),
}


class Store:
    def __init__(self, root: Path | None = None):
        if root:
            self.root = root
        else:
            self.root = self._find_root_or_cwd()
        self.context_dir = self.root / ".context"

    def _find_root_or_cwd(self) -> Path:
        current = Path.cwd()
        check = current
        while check != check.parent:
            if (check / ".context").is_dir():
                return check
            check = check.parent
        return current

    def init(self) -> Path:
        self.context_dir.mkdir(exist_ok=True)
        for dir_name in DIRS.values():
            (self.context_dir / dir_name).mkdir(exist_ok=True)

        config = self.context_dir / "config.yaml"
        if not config.exists():
            config.write_text(
                yaml.dump({"version": 1, "project": self.root.name})
            )
        return self.context_dir

    _STANDARD_FIELDS = {"id", "type", "title", "status", "date", "authors", "links", "tags"}

    def _parse_record(self, path: Path) -> Record:
        content = path.read_text()
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid record format in {path}")

        meta = yaml.safe_load(parts[1])
        body = parts[2].strip()

        raw_links: dict[str, list[str]] = {}
        for key, val in (meta.get("links") or {}).items():
            raw_links[key] = val if isinstance(val, list) else [val]

        extra = {k: v for k, v in meta.items() if k not in self._STANDARD_FIELDS}

        return Record(
            id=meta["id"],
            type=RecordType(meta["type"]),
            title=meta["title"],
            status=Status(meta.get("status", "draft")),
            date=meta.get("date", date.today()),
            authors=meta.get("authors") or [],
            links=raw_links,
            tags=meta.get("tags") or [],
            body=body,
            extra=extra,
        )

    def _serialize_record(self, record: Record) -> str:
        meta: dict = {
            "id": record.id,
            "type": record.type.value,
            "title": record.title,
            "status": record.status.value,
            "date": str(record.date),
            "authors": record.authors,
            "tags": record.tags,
        }
        if record.links:
            meta["links"] = {
                k: v if len(v) != 1 else v[0]
                for k, v in record.links.items()
            }
        if record.extra:
            meta.update(record.extra)

        frontmatter = yaml.dump(meta, default_flow_style=False, sort_keys=False)
        return f"---\n{frontmatter}---\n\n{record.body}\n"

    def get(self, record_id: str) -> Record:
        prefix = record_id.split("-")[0]
        if prefix not in PREFIX_TO_TYPE:
            raise ValueError(f"Unknown prefix '{prefix}' in ID '{record_id}'")
        record_type = PREFIX_TO_TYPE[prefix]
        dir_name = DIRS[record_type]
        path = self.context_dir / dir_name / f"{record_id}.md"
        if not path.exists():
            raise FileNotFoundError(f"Record {record_id} not found")
        return self._parse_record(path)

    def list_all(
        self,
        record_type: RecordType | None = None,
        status: Status | None = None,
        tag: str | None = None,
        include_inactive: bool = True,
    ) -> list[Record]:
        records: list[Record] = []
        dirs = [DIRS[record_type]] if record_type else list(DIRS.values())

        for dir_name in dirs:
            dir_path = self.context_dir / dir_name
            if not dir_path.exists():
                continue
            for path in sorted(dir_path.glob("*.md")):
                try:
                    record = self._parse_record(path)
                except Exception:
                    continue
                if not include_inactive and record.status in INACTIVE_STATUSES:
                    continue
                if status and record.status != status:
                    continue
                if tag and tag not in record.tags:
                    continue
                records.append(record)
        return records

    def next_id(self, record_type: RecordType) -> str:
        prefix = PREFIXES[record_type]
        existing = self.list_all(record_type=record_type)
        if not existing:
            return f"{prefix}-001"
        max_num = max(r.number for r in existing)
        return f"{prefix}-{max_num + 1:03d}"

    def save(self, record: Record) -> Path:
        dir_name = DIRS[record.type]
        dir_path = self.context_dir / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
        path = dir_path / f"{record.id}.md"
        path.write_text(self._serialize_record(record))
        return path

    def search(
        self, query: str, include_inactive: bool = False
    ) -> list[Record]:
        query_lower = query.lower()
        scored: list[tuple[int, Record]] = []
        for record in self.list_all(include_inactive=include_inactive):
            score = 0
            if query_lower in record.title.lower():
                score += 3
            if query_lower in record.body.lower():
                score += 1
            if any(query_lower in t.lower() for t in record.tags):
                score += 2
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored]

    def supersede(
        self,
        old_id: str,
        new_title: str,
        reason: str,
        authors: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> tuple[Record, Record]:
        old = self.get(old_id)
        old.status = Status.SUPERSEDED
        old.body = (
            f"> **SUPERSEDED** — This decision is no longer active. "
            f"See replacement below.\n>\n"
            f"> Reason: {reason}\n\n"
            f"{old.body}"
        )

        new_record = Record(
            id=self.next_id(old.type),
            type=old.type,
            title=new_title,
            status=Status.ACCEPTED,
            date=date.today(),
            authors=authors or old.authors,
            links={"supersedes": [old_id]},
            tags=tags or old.tags,
            body=(
                f"Supersedes {old_id} ({old.title}).\n\n"
                f"Reason: {reason}\n\n"
                f"{self.template_body(old.type)}"
            ),
        )

        self.save(old)
        self.save(new_record)
        return old, new_record

    def deprecate(self, record_id: str, reason: str) -> Record:
        record = self.get(record_id)
        record.status = Status.DEPRECATED
        record.body = (
            f"> **DEPRECATED** — This decision is no longer active.\n>\n"
            f"> Reason: {reason}\n\n"
            f"{record.body}"
        )
        self.save(record)
        return record

    def delete(self, record_id: str) -> Path:
        prefix = record_id.split("-")[0]
        if prefix not in PREFIX_TO_TYPE:
            raise ValueError(f"Unknown prefix '{prefix}' in ID '{record_id}'")
        record_type = PREFIX_TO_TYPE[prefix]
        dir_name = DIRS[record_type]
        path = self.context_dir / dir_name / f"{record_id}.md"
        if not path.exists():
            raise FileNotFoundError(f"Record {record_id} not found")
        path.unlink()
        return path

    def template_body(self, record_type: RecordType) -> str:
        return _TEMPLATE_SECTIONS.get(record_type, "")
