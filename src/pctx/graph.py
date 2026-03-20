from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations

from .models import INACTIVE_STATUSES, Record, RecordType
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

    def _record_dict(self, r: Record) -> dict:
        d: dict = {
            "id": r.id,
            "title": r.title,
            "type": r.type.value,
            "status": r.status.value,
            "date": str(r.date),
            "body": r.body,
        }
        if r.tags:
            d["tags"] = r.tags
        if r.extra:
            d["extra"] = r.extra
        return d

    def reflect(self, topic_or_id: str) -> dict:
        """Structured synthesis of everything known about a topic or thread."""
        collected: dict[str, Record] = {}

        # If it looks like a record ID, start from that record
        record = self.records.get(topic_or_id)
        if record:
            collected[record.id] = record
            # Get everything that's part_of this record
            for sid, _ in self._reverse_links(record.id, ["part_of"]):
                r = self.records.get(sid)
                if r and r.status not in INACTIVE_STATUSES:
                    collected[sid] = r
            # Expand all forward links from collected records
            for rid in list(collected):
                r = collected[rid]
                for tid, _ in self._forward_links(r):
                    target = self.records.get(tid)
                    if target and target.status not in INACTIVE_STATUSES:
                        collected[tid] = target
        else:
            # Search by topic and expand
            for r in self.store.search(topic_or_id):
                collected[r.id] = r
                for targets in r.links.values():
                    for tid in targets:
                        target = self.records.get(tid)
                        if target and target.status not in INACTIVE_STATUSES:
                            collected[tid] = target

        # Group by type
        type_order = ["thread", "experience", "belief", "decision", "change", "context"]
        grouped: dict[str, list[dict]] = {t: [] for t in type_order}
        for r in collected.values():
            tv = r.type.value
            if tv in grouped:
                grouped[tv].append(self._record_dict(r))

        # Sort experiences by date
        grouped["experience"].sort(key=lambda x: x["date"])

        # Find contradictions: active belief pairs linked by contradicts
        contradictions: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()
        for r in collected.values():
            if r.type != RecordType.BELIEF:
                continue
            for tid, lt in self._forward_links(r, ["contradicts"]):
                target = self.records.get(tid)
                if not target or target.status in INACTIVE_STATUSES:
                    continue
                pair = tuple(sorted([r.id, tid]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    contradictions.append({
                        "a": {"id": r.id, "title": r.title},
                        "b": {"id": tid, "title": target.title},
                    })

        return {
            "topic": topic_or_id,
            "sections": {k: v for k, v in grouped.items() if v},
            "contradictions": contradictions,
        }

    def evolve(self, stale_days: int = 30) -> dict:
        """Self-monitoring: what needs attention?"""
        today = date.today()
        stale_cutoff = today - timedelta(days=stale_days)
        recent_cutoff = today - timedelta(days=7)

        active = [r for r in self.records.values() if r.status not in INACTIVE_STATUSES]

        # Stale beliefs
        stale_beliefs = [
            self._record_dict(r) for r in active
            if r.type == RecordType.BELIEF and r.date < stale_cutoff
        ]
        stale_beliefs.sort(key=lambda x: x["date"])

        # Unresolved contradictions (both sides active)
        contradictions: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for r in active:
            for tid, lt in self._forward_links(r, ["contradicts"]):
                target = self.records.get(tid)
                if not target or target.status in INACTIVE_STATUSES:
                    continue
                pair = tuple(sorted([r.id, tid]))
                if pair not in seen:
                    seen.add(pair)
                    contradictions.append({
                        "a": {"id": r.id, "title": r.title, "date": str(r.date)},
                        "b": {"id": tid, "title": target.title, "date": str(target.date)},
                    })

        # Dormant threads: active threads with no recent part_of records
        dormant_threads: list[dict] = []
        for r in active:
            if r.type != RecordType.THREAD:
                continue
            parts = self._reverse_links(r.id, ["part_of"])
            latest = None
            for sid, _ in parts:
                source = self.records.get(sid)
                if source and source.status not in INACTIVE_STATUSES:
                    if latest is None or source.date > latest:
                        latest = source.date
            if latest is None or latest < stale_cutoff:
                entry = self._record_dict(r)
                entry["last_activity"] = str(latest) if latest else "never"
                dormant_threads.append(entry)

        # Recent activity
        recent: dict[str, list[dict]] = defaultdict(list)
        for r in active:
            if r.date >= recent_cutoff:
                recent[r.type.value].append(self._record_dict(r))

        return {
            "stale_beliefs": stale_beliefs,
            "contradictions": contradictions,
            "dormant_threads": dormant_threads,
            "recent": dict(recent),
        }

    def connections(self) -> dict:
        """Discover records that share tags but aren't linked."""
        active = [r for r in self.records.values() if r.status not in INACTIVE_STATUSES]

        # Build set of all existing links (both directions)
        linked: set[tuple[str, str]] = set()
        for r in active:
            for targets in r.links.values():
                for tid in targets:
                    linked.add((r.id, tid))
                    linked.add((tid, r.id))

        # Find unlinked pairs sharing tags
        suggestions: list[dict] = []
        for a, b in combinations(active, 2):
            if not a.tags or not b.tags:
                continue
            if (a.id, b.id) in linked:
                continue
            shared = set(a.tags) & set(b.tags)
            if shared:
                suggestions.append({
                    "a": {"id": a.id, "title": a.title, "type": a.type.value},
                    "b": {"id": b.id, "title": b.title, "type": b.type.value},
                    "shared_tags": sorted(shared),
                })

        suggestions.sort(key=lambda x: len(x["shared_tags"]), reverse=True)
        return {"suggestions": suggestions}
