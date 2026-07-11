from dataclasses import dataclass
from enum import IntEnum
from typing import Literal


class EvidenceLevel(IntEnum):
    MAIN_BUSINESS_REVENUE = 1
    TRADE_AND_INDUSTRY_CHAIN = 2
    LOAN_PURPOSE = 3
    BUSINESS_SCOPE = 4


EvidenceSource = Literal["original", "objection"]


@dataclass(frozen=True)
class EvidenceFact:
    field_label: str
    raw_text: str
    indicated_business: str
    source: EvidenceSource = "original"

    @property
    def is_usable(self) -> bool:
        return bool(self.raw_text.strip() and self.indicated_business.strip())


@dataclass(frozen=True)
class EvidenceLayer:
    level: EvidenceLevel
    facts: tuple[EvidenceFact, ...] = ()
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if self.unavailable_reason is not None and not self.unavailable_reason.strip():
            raise ValueError("unavailable_reason must be non-empty when provided")

    @property
    def usable_facts(self) -> tuple[EvidenceFact, ...]:
        return tuple(fact for fact in self.facts if fact.is_usable)

    @property
    def is_available(self) -> bool:
        return self.unavailable_reason is None and bool(self.usable_facts)


@dataclass(frozen=True)
class EvidenceConflict:
    adopted_level: EvidenceLevel
    conflicting_level: EvidenceLevel
    adopted_business: str
    conflicting_business: str


@dataclass(frozen=True)
class EvidenceDecision:
    adopted_layer: EvidenceLayer
    skipped_layers: tuple[EvidenceLayer, ...]
    conflicts: tuple[EvidenceConflict, ...]

    @property
    def adopted_business(self) -> str:
        return self.adopted_layer.usable_facts[0].indicated_business.strip()


class NoUsableEvidenceError(ValueError):
    pass


def decide_primary_business(
    layers: tuple[EvidenceLayer, ...],
) -> EvidenceDecision:
    ordered_layers = tuple(sorted(layers, key=lambda layer: layer.level))
    _validate_unique_levels(ordered_layers)

    adopted_index = next(
        (index for index, layer in enumerate(ordered_layers) if layer.is_available),
        None,
    )
    if adopted_index is None:
        raise NoUsableEvidenceError("no usable evidence layer")

    adopted_layer = ordered_layers[adopted_index]
    adopted_business = adopted_layer.usable_facts[0].indicated_business.strip()
    conflicts = tuple(
        EvidenceConflict(
            adopted_level=adopted_layer.level,
            conflicting_level=layer.level,
            adopted_business=adopted_business,
            conflicting_business=fact.indicated_business.strip(),
        )
        for layer in ordered_layers[adopted_index + 1 :]
        if layer.is_available
        for fact in layer.usable_facts
        if fact.indicated_business.strip() != adopted_business
    )
    return EvidenceDecision(
        adopted_layer=adopted_layer,
        skipped_layers=ordered_layers[:adopted_index],
        conflicts=conflicts,
    )


def supplement_layer_with_objection(
    layer: EvidenceLayer,
    *,
    field_label: str,
    raw_text: str,
    indicated_business: str,
) -> EvidenceLayer:
    objection_fact = EvidenceFact(
        field_label=field_label,
        raw_text=raw_text,
        indicated_business=indicated_business,
        source="objection",
    )
    return EvidenceLayer(
        level=layer.level,
        facts=(*layer.facts, objection_fact),
        unavailable_reason=None if objection_fact.is_usable else layer.unavailable_reason,
    )


def _validate_unique_levels(layers: tuple[EvidenceLayer, ...]) -> None:
    levels = tuple(layer.level for layer in layers)
    if len(levels) != len(set(levels)):
        raise ValueError("evidence levels must be unique")
