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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'CanonicalCandidate':
        """
        Deserializes a dict back into a CanonicalCandidate.
        """
        def parse_fv(fv_dict):
            if not fv_dict: return None
            provs = [Provenance(**p) for p in fv_dict.get('provenance', [])]
            return FieldValue(
                value=fv_dict.get('value'),
                confidence=fv_dict.get('confidence', 0.0),
                provenance=provs,
                conflicting_values=fv_dict.get('conflicting_values', [])
            )
            
        return cls(
            candidate_id=d.get('candidate_id', ''),
            full_name=parse_fv(d.get('full_name')),
            emails=[parse_fv(e) for e in d.get('emails', []) if parse_fv(e)],
            phones=[parse_fv(p) for p in d.get('phones', []) if parse_fv(p)],
            location=parse_fv(d.get('location')),
            links=d.get('links', {}),
            headline=parse_fv(d.get('headline')),
            years_experience=parse_fv(d.get('years_experience')),
            skills=[parse_fv(s) for s in d.get('skills', []) if parse_fv(s)],
            experience=d.get('experience', []),
            education=d.get('education', []),
            overall_confidence=d.get('overall_confidence', 0.0)
        )


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
