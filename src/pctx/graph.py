from __future__ import annotations

from .models import Record
from .store import Store


class Graph:
    def __init__(self, store: Store):
        self.store = store
        self._cache: dict[str, Record] | None = None

    @property
    def records(self) -> dict[str, Record]:
        if self._cache is None:
            self._cache = {r.id: r for r in self.store.list_all()}
        return self._cache

    def invalidate(self) -> None:
        self._cache = None

    def _forward_links(
        self, record: Record, link_types: list[str] | None = None
    ) -> list[tuple[str, str]]:
        """IDs this record points to: (target_id, link_type)."""
        results: list[tuple[str, str]] = []
        for lt, targets in record.links.items():
            if link_types and lt not in link_types:
                continue
            for tid in targets:
                results.append((tid, lt))
        return results

    def _reverse_links(
        self, record_id: str, link_types: list[str] | None = None
    ) -> list[tuple[str, str]]:
        """IDs that point TO this record: (source_id, link_type)."""
        results: list[tuple[str, str]] = []
        for rid, record in self.records.items():
            for lt, targets in record.links.items():
                if link_types and lt not in link_types:
                    continue
                if record_id in targets:
                    results.append((rid, lt))
        return results

    def impact(self, record_id: str, depth: int = 3) -> dict:
        """Everything affected if this record changes."""
        record = self.records.get(record_id)
        if not record:
            return {}

        result: dict = {
            "id": record_id,
            "title": record.title,
            "type": record.type.value,
            "upstream": [],
            "downstream": [],
        }

        # Upstream: what this record depends on / is inspired by / is part of
        for tid, lt in self._forward_links(record, ["depends_on", "inspired_by", "part_of"]):
            target = self.records.get(tid)
            if target:
                result["upstream"].append(
                    {"id": tid, "title": target.title, "link_type": lt}
                )
        for sid, lt in self._reverse_links(record_id, ["enables"]):
            source = self.records.get(sid)
            if source and not any(u["id"] == sid for u in result["upstream"]):
                result["upstream"].append(
                    {"id": sid, "title": source.title, "link_type": lt}
                )

        # Downstream: what depends on / is enabled by this record
        visited: set[str] = {record_id}

        def walk(rid: str, d: int) -> list[dict]:
            if d >= depth:
                return []
            affected: list[dict] = []

            # Records that depend_on / are inspired_by / are part_of rid
            for sid, lt in self._reverse_links(rid, ["depends_on", "inspired_by", "part_of"]):
                if sid in visited:
                    continue
                visited.add(sid)
                source = self.records.get(sid)
                if source:
                    children = walk(sid, d + 1)
                    affected.append(
                        {
                            "id": sid,
                            "title": source.title,
                            "link_type": lt,
                            "children": children,
                        }
                    )

            # Records that rid enables
            r = self.records.get(rid)
            if r:
                for tid, lt in self._forward_links(r, ["enables"]):
                    if tid in visited:
                        continue
                    visited.add(tid)
                    target = self.records.get(tid)
                    if target:
                        children = walk(tid, d + 1)
                        affected.append(
                            {
                                "id": tid,
                                "title": target.title,
                                "link_type": lt,
                                "children": children,
                            }
                        )

            # Weaker: records that relate_to or contradict this
            for sid, lt in self._reverse_links(rid, ["relates_to", "contradicts"]):
                if sid in visited:
                    continue
                visited.add(sid)
                source = self.records.get(sid)
                if source:
                    affected.append(
                        {
                            "id": sid,
                            "title": source.title,
                            "link_type": lt,
                            "children": [],
                        }
                    )

            return affected

        result["downstream"] = walk(record_id, 0)
        return result

    def why(self, record_id: str, depth: int = 5) -> dict:
        """Reasoning chain: why was this decided?"""
        visited: set[str] = set()

        def trace(rid: str, d: int) -> dict | None:
            if d >= depth or rid in visited:
                return None
            visited.add(rid)

            record = self.records.get(rid)
            if not record:
                return None

            node: dict = {
                "id": rid,
                "title": record.title,
                "type": record.type.value,
                "status": record.status.value,
                "because": [],
                "informed_by": [],
            }

            if record.body:
                node["body_preview"] = record.body[:300]

            # Hard chain: depends_on / inspired_by (forward from this record)
            for tid, _ in self._forward_links(record, ["depends_on", "inspired_by"]):
                child = trace(tid, d + 1)
                if child:
                    node["because"].append(child)

            # Hard chain: who enables this record (reverse)
            for sid, _ in self._reverse_links(rid, ["enables"]):
                if sid not in visited:
                    child = trace(sid, d + 1)
                    if child:
                        node["because"].append(child)

            # Soft: relates_to / contradicts (show but don't recurse deeply)
            for tid, _ in self._forward_links(record, ["relates_to", "contradicts"]):
                target = self.records.get(tid)
                if target:
                    node["informed_by"].append(
                        {
                            "id": tid,
                            "title": target.title,
                            "type": target.type.value,
                        }
                    )

            return node

        return trace(record_id, 0) or {}

    def context_for(self, topic: str) -> dict:
        """All relevant context for a topic, with link expansion."""
        matches = self.store.search(topic)

        expanded_ids: set[str] = set()
        for r in matches:
            expanded_ids.add(r.id)
            for targets in r.links.values():
                expanded_ids.update(targets)

        match_ids = {r.id for r in matches}
        related: list[Record] = []
        for rid in expanded_ids - match_ids:
            record = self.records.get(rid)
            if record:
                related.append(record)

        return {
            "topic": topic,
            "direct_matches": [
                {
                    "id": r.id,
                    "title": r.title,
                    "type": r.type.value,
                    "status": r.status.value,
                    "body": r.body,
                }
                for r in matches
            ],
            "related": [
                {
                    "id": r.id,
                    "title": r.title,
                    "type": r.type.value,
                    "status": r.status.value,
                    "body": r.body,
                }
                for r in related
            ],
        }
