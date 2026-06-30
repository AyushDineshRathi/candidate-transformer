"""
Canonical data model definitions.
Defines the standard internal representation of a candidate.
"""
from dataclasses import dataclass, field, asdict
from typing import Generic, TypeVar, Any

T = TypeVar('T')


@dataclass
class Provenance:
    source: str
    source_field: str
    method: str
    confidence: float


@dataclass
class FieldValue(Generic[T]):
    value: T
    confidence: float
    provenance: list[Provenance] = field(default_factory=list)
    conflicting_values: list[T] = field(default_factory=list)


@dataclass
class CanonicalCandidate:
    candidate_id: str
    full_name: FieldValue[str] | None = None
    emails: list[FieldValue[str]] = field(default_factory=list)
    phones: list[FieldValue[str]] = field(default_factory=list)
    location: FieldValue[dict[str, Any]] | None = None
    links: dict[str, Any] = field(
        default_factory=lambda: {"linkedin": None, "github": None, "portfolio": None, "other": []}
    )
    headline: FieldValue[str] | None = None
    years_experience: FieldValue[float] | None = None
    skills: list[FieldValue[str]] = field(default_factory=list)
    experience: list[dict[str, Any]] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)
    overall_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """
        Serializes the CanonicalCandidate to a plain JSON-able dict.
        """
        d = asdict(self)
        from src.explain import explain_to_review_flag
        d['needs_human_review'] = explain_to_review_flag(d)
        return d


@dataclass
class RawExtraction:
    candidate_id: str
    full_name: tuple[str, Provenance] | None = None
    emails: list[tuple[str, Provenance]] = field(default_factory=list)
    phones: list[tuple[str, Provenance]] = field(default_factory=list)
    location: tuple[dict[str, Any], Provenance] | None = None
    links: tuple[dict[str, Any], Provenance] | None = None
    headline: tuple[str, Provenance] | None = None
    years_experience: tuple[float, Provenance] | None = None
    skills: list[tuple[str, Provenance]] = field(default_factory=list)
    experience: list[tuple[dict[str, Any], Provenance]] = field(default_factory=list)
    education: list[tuple[dict[str, Any], Provenance]] = field(default_factory=list)
    overall_confidence: float = 0.0
