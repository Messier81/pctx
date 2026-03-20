from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class RecordType(str, Enum):
    DECISION = "decision"
    CHANGE = "change"
    CONTEXT = "context"
    EXPERIENCE = "experience"
    BELIEF = "belief"
    THREAD = "thread"


class Status(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


class LinkType(str, Enum):
    SUPERSEDES = "supersedes"
    DEPENDS_ON = "depends_on"
    RELATES_TO = "relates_to"
    ENABLES = "enables"
    CONTRADICTS = "contradicts"
    INSPIRED_BY = "inspired_by"
    PART_OF = "part_of"


INACTIVE_STATUSES: set[Status] = {Status.DEPRECATED, Status.SUPERSEDED}


PREFIXES: dict[RecordType, str] = {
    RecordType.DECISION: "DEC",
    RecordType.CHANGE: "CHG",
    RecordType.CONTEXT: "CTX",
    RecordType.EXPERIENCE: "EXP",
    RecordType.BELIEF: "BLF",
    RecordType.THREAD: "THR",
}

PREFIX_TO_TYPE: dict[str, RecordType] = {v: k for k, v in PREFIXES.items()}

DIRS: dict[RecordType, str] = {
    RecordType.DECISION: "decisions",
    RecordType.CHANGE: "changes",
    RecordType.CONTEXT: "contexts",
    RecordType.EXPERIENCE: "experiences",
    RecordType.BELIEF: "beliefs",
    RecordType.THREAD: "threads",
}


@dataclass
class Record:
    id: str
    type: RecordType
    title: str
    status: Status
    date: date
    authors: list[str] = field(default_factory=list)
    links: dict[str, list[str]] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    body: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def prefix(self) -> str:
        return PREFIXES[self.type]

    @property
    def number(self) -> int:
        return int(self.id.split("-")[1])
