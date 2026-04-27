"""SSOT vocabulary loaders for the animation oracle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from svg2ooxml.common.boundaries import safe_lxml_parser
from svg2ooxml.drawingml.animation.evidence import (
    EvidenceTier,
    evidence_tiers_for_oracle_verification,
)

__all__ = [
    "AttrNameEntry",
    "DeadPath",
    "FilterEntry",
    "load_attrname_vocabulary",
    "load_dead_paths",
    "load_filter_vocabulary",
]


@dataclass(frozen=True, slots=True)
class FilterEntry:
    """One entry from the animEffect filter vocabulary SSOT."""

    value: str
    description: str
    entrance_preset_id: int | None
    entrance_preset_subtype: int | None
    exit_preset_id: int | None
    exit_preset_subtype: int | None
    verification: str
    source: str

    @property
    def evidence_tiers(self) -> tuple[EvidenceTier, ...]:
        return evidence_tiers_for_oracle_verification(self.verification)

    @property
    def is_entrance_only(self) -> bool:
        return self.entrance_preset_id is not None and self.exit_preset_id is None

    @property
    def is_exit_only(self) -> bool:
        return self.exit_preset_id is not None and self.entrance_preset_id is None

    @property
    def is_pseudo(self) -> bool:
        """True for filter values not usable as standalone entrance/exit effects."""
        return self.entrance_preset_id == -1 and self.exit_preset_id == -1


@dataclass(frozen=True, slots=True)
class AttrNameEntry:
    """One entry from the <p:attrName> vocabulary SSOT."""

    value: str
    category: str
    scope: str
    description: str
    used_by: str
    verification: str
    source: str

    @property
    def evidence_tiers(self) -> tuple[EvidenceTier, ...]:
        return evidence_tiers_for_oracle_verification(self.verification)


@dataclass(frozen=True, slots=True)
class DeadPath:
    """One empirically falsified animation shape."""

    id: str
    element: str
    attribute_names: tuple[str, ...]
    attribute_values: tuple[str, ...]
    context: str
    description: str
    verdict: str
    source: str
    replacement_slot: str
    replacement_note: str


def load_filter_vocabulary(root_path: Path) -> tuple[FilterEntry, ...]:
    vocab_path = root_path / "filter_vocabulary.xml"
    if not vocab_path.is_file():
        raise FileNotFoundError(f"Filter vocabulary SSOT missing: {vocab_path}")
    parser = safe_lxml_parser(remove_blank_text=True, remove_comments=True)
    root = etree.fromstring(vocab_path.read_bytes(), parser)
    entries: list[FilterEntry] = []
    for filt in root.findall("filter"):
        entrance = filt.find("entrance")
        exit_el = filt.find("exit")
        entries.append(
            FilterEntry(
                value=filt.get("value", ""),
                description=(filt.findtext("description") or "").strip(),
                entrance_preset_id=_int_or_none(entrance, "preset-id"),
                entrance_preset_subtype=_int_or_none(entrance, "preset-subtype"),
                exit_preset_id=_int_or_none(exit_el, "preset-id"),
                exit_preset_subtype=_int_or_none(exit_el, "preset-subtype"),
                verification=(filt.findtext("verification") or "unknown").strip(),
                source=(filt.findtext("source") or "").strip(),
            )
        )
    return tuple(entries)


def load_attrname_vocabulary(root_path: Path) -> tuple[AttrNameEntry, ...]:
    vocab_path = root_path / "attrname_vocabulary.xml"
    if not vocab_path.is_file():
        raise FileNotFoundError(f"attrName vocabulary SSOT missing: {vocab_path}")
    parser = safe_lxml_parser(remove_blank_text=True, remove_comments=True)
    root = etree.fromstring(vocab_path.read_bytes(), parser)
    entries: list[AttrNameEntry] = []
    for attr_el in root.findall("attrname"):
        entries.append(
            AttrNameEntry(
                value=attr_el.get("value", ""),
                category=(attr_el.findtext("category") or "").strip(),
                scope=(attr_el.findtext("scope") or "").strip(),
                description=(attr_el.findtext("description") or "").strip(),
                used_by=(attr_el.findtext("used-by") or "").strip(),
                verification=(attr_el.findtext("verification") or "unknown").strip(),
                source=(attr_el.findtext("source") or "").strip(),
            )
        )
    return tuple(entries)


def load_dead_paths(root_path: Path) -> tuple[DeadPath, ...]:
    dead_path = root_path / "dead_paths.xml"
    if not dead_path.is_file():
        raise FileNotFoundError(f"dead_paths SSOT missing: {dead_path}")
    parser = safe_lxml_parser(remove_blank_text=True, remove_comments=True)
    root = etree.fromstring(dead_path.read_bytes(), parser)
    entries: list[DeadPath] = []
    for dp_el in root.findall("dead-path"):
        entries.append(_parse_dead_path(dp_el))
    return tuple(entries)


def _parse_dead_path(dp_el: etree._Element) -> DeadPath:
    shape = dp_el.find("shape")
    element_name = ""
    attr_names: list[str] = []
    attr_values: list[str] = []
    context = ""
    if shape is not None:
        element_name = (shape.findtext("element") or "").strip()
        for attr in shape.findall("attribute"):
            name = attr.get("name", "")
            if name:
                attr_names.append(name)
                attr_values.append((attr.text or "").strip())
        context = (shape.findtext("context") or "").strip()

    replacement = dp_el.find("replacement")
    replacement_slot = ""
    replacement_note = ""
    if replacement is not None:
        replacement_slot = (replacement.findtext("slot") or "").strip()
        replacement_note = (replacement.findtext("note") or "").strip()

    return DeadPath(
        id=dp_el.get("id", ""),
        element=element_name,
        attribute_names=tuple(attr_names),
        attribute_values=tuple(attr_values),
        context=context,
        description=(dp_el.findtext("description") or "").strip(),
        verdict=(dp_el.findtext("verdict") or "").strip(),
        source=(dp_el.findtext("source") or "").strip(),
        replacement_slot=replacement_slot,
        replacement_note=replacement_note,
    )


def _int_or_none(el: etree._Element | None, attr: str) -> int | None:
    if el is None:
        return None
    raw = el.get(attr)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
