"""Animation oracle template loader.

Loads the parameterised ``<p:par>`` fragment templates from
``src/svg2ooxml/assets/animation_oracle/`` and substitutes the runtime tokens
each handler needs to specialise a preset for a particular shape.

The oracle is the single source of truth for the XML shape svg2ooxml emits
per PowerPoint animation preset. Handlers should load a slot by name rather
than constructing ``<p:par>`` trees imperatively.

Example::

    oracle = AnimationOracle()
    par = oracle.instantiate(
        "entr/fade",
        shape_id="2",
        par_id=6,
        duration_ms=1500,
        delay_ms=0,
        set_behavior_id=7,
        effect_behavior_id=71,
    )
    # ``par`` is an ``lxml`` element ready to be appended to the timing tree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from lxml import etree

from svg2ooxml.drawingml.xml_builder import NS_P

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

__all__ = [
    "AnimationOracle",
    "BehaviorFragment",
    "OracleSlotError",
    "PresetSlot",
    "default_oracle",
]


class OracleSlotError(KeyError):
    """Raised when a requested oracle slot cannot be resolved."""


@dataclass(frozen=True, slots=True)
class PresetSlot:
    """Metadata describing a single oracle slot."""

    name: str
    path: Path
    preset_class: str
    preset_id: int | None
    preset_subtype: int | None
    family_signature: str
    content_tokens: tuple[str, ...]
    behavior_tokens: tuple[str, ...]
    smil_patterns: tuple[str, ...]
    source: str
    verification: str
    notes: str = ""


@dataclass(frozen=True, slots=True)
class BehaviorFragment:
    """A single behavior fragment to inject into a compound slot.

    ``name`` identifies an XML file under ``emph/behaviors/<name>.xml``.
    ``tokens`` carries the substitution map that satisfies the fragment's
    template placeholders. Every fragment implicitly receives ``SHAPE_ID``
    and ``DURATION_MS`` from the compound's call; other tokens
    (``BEHAVIOR_ID``, ``TO_COLOR``, ``ROTATION_BY`` etc.) must be supplied
    here per-fragment.
    """

    name: str
    tokens: Mapping[str, Any] = field(default_factory=dict)


def _default_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "assets" / "animation_oracle"


class AnimationOracle:
    """In-memory view over the parameterised oracle templates."""

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = Path(root) if root is not None else _default_root()
        if not self._root.is_dir():
            raise FileNotFoundError(f"Animation oracle root not found: {self._root}")
        index_path = self._root / "index.json"
        if not index_path.is_file():
            raise FileNotFoundError(f"Animation oracle index missing: {index_path}")
        self._index: dict[str, PresetSlot] = {}
        self._templates: dict[str, str] = {}
        self._load_index(index_path)

    # ------------------------------------------------------------------ load

    def _load_index(self, index_path: Path) -> None:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
        slots = raw.get("slots") or {}
        for name, entry in slots.items():
            template_path = (self._root / entry["path"]).resolve()
            if not template_path.is_file():
                raise FileNotFoundError(
                    f"Oracle slot '{name}' references missing template {template_path}"
                )
            slot = PresetSlot(
                name=name,
                path=template_path,
                preset_class=entry["preset_class"],
                preset_id=entry.get("preset_id"),
                preset_subtype=entry.get("preset_subtype"),
                family_signature=entry["family_signature"],
                content_tokens=tuple(entry.get("content_tokens", [])),
                behavior_tokens=tuple(entry.get("behavior_tokens", [])),
                smil_patterns=tuple(entry.get("smil_patterns", [])),
                source=entry.get("source", ""),
                verification=entry.get("verification", "unknown"),
                notes=entry.get("notes", ""),
            )
            self._index[name] = slot
            self._templates[name] = template_path.read_text(encoding="utf-8")

    # ---------------------------------------------------------------- access

    @property
    def root(self) -> Path:
        return self._root

    def slots(self) -> list[PresetSlot]:
        return list(self._index.values())

    def slot(self, name: str) -> PresetSlot:
        try:
            return self._index[name]
        except KeyError as exc:
            raise OracleSlotError(name) from exc

    def template_text(self, name: str) -> str:
        if name not in self._templates:
            raise OracleSlotError(name)
        return self._templates[name]

    # -------------------------------------------------------- instantiation

    def instantiate(
        self,
        slot_name: str,
        *,
        shape_id: str | int,
        par_id: int,
        duration_ms: int,
        delay_ms: int = 0,
        **tokens: Any,
    ) -> etree._Element:
        """Return a fully substituted ``<p:par>`` element ready for the timing tree.

        Required keyword arguments depend on the slot's ``behavior_tokens`` and
        ``content_tokens`` declared in ``index.json``. Pass them as plain
        keyword arguments using the token name (case-sensitive).
        """
        slot = self.slot(slot_name)
        substitutions: dict[str, str] = {
            "SHAPE_ID": str(shape_id),
            "PAR_ID": str(par_id),
            "DURATION_MS": str(duration_ms),
            "DELAY_MS": str(delay_ms),
        }
        for name in slot.behavior_tokens:
            if name not in tokens:
                raise ValueError(
                    f"Slot '{slot_name}' requires behavior token '{name}'"
                )
            substitutions[name] = str(tokens.pop(name))
        for name in slot.content_tokens:
            if name not in tokens:
                raise ValueError(
                    f"Slot '{slot_name}' requires content token '{name}'"
                )
            substitutions[name] = str(tokens.pop(name))
        if tokens:
            unknown = ", ".join(sorted(tokens))
            raise ValueError(
                f"Unknown tokens for slot '{slot_name}': {unknown}"
            )

        text = self.template_text(slot_name)
        rendered = _render_template(text, substitutions)

        wrapped = (
            f'<root xmlns:p="{NS_P}" '
            f'xmlns:a="{NS_A}">'
            f"{rendered}</root>"
        )
        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.fromstring(wrapped.encode("utf-8"), parser)
        par = root[0]
        # Detach from the synthetic root so the caller owns the element.
        root.remove(par)
        return par

    # --------------------------------------------------------- compound slot

    def instantiate_compound(
        self,
        *,
        shape_id: str | int,
        par_id: int,
        duration_ms: int,
        delay_ms: int = 0,
        behaviors: Sequence[BehaviorFragment | tuple[str, Mapping[str, Any]]],
    ) -> etree._Element:
        """Assemble a compound ``<p:par>`` with arbitrary behavior children.

        This is the primary path for emitting multi-effect animations. Each
        item in *behaviors* is a :class:`BehaviorFragment` (or a
        ``(name, tokens)`` 2-tuple) naming a file under
        ``emph/behaviors/<name>.xml``. Fragments are rendered with their
        own tokens plus implicit ``SHAPE_ID`` / ``DURATION_MS`` (from the
        outer compound call), then appended as direct children of the
        compound's single ``<p:cTn>``.

        The compound slot itself is preset-free — PPT's rendering engine
        walks the ``<p:cTn>``'s ``childTnLst`` and fires every behavior
        element directly. All fragments fire simultaneously on one click.
        """
        base = self.instantiate(
            "emph/compound",
            shape_id=shape_id,
            par_id=par_id,
            duration_ms=duration_ms,
            delay_ms=delay_ms,
        )
        child_tn_lst = base.find(
            f".//{{{NS_P}}}cTn/{{{NS_P}}}childTnLst"
        )
        if child_tn_lst is None:  # pragma: no cover - template guarantees presence
            raise OracleSlotError("emph/compound template is missing <p:childTnLst>")

        for item in behaviors:
            if isinstance(item, BehaviorFragment):
                fragment = item
            else:
                name, tokens = item
                fragment = BehaviorFragment(name=name, tokens=tokens)
            for child in self._render_behavior_fragment(
                fragment,
                shape_id=shape_id,
                duration_ms=duration_ms,
            ):
                child_tn_lst.append(child)

        return base

    def _render_behavior_fragment(
        self,
        fragment: BehaviorFragment,
        *,
        shape_id: str | int,
        duration_ms: int,
    ) -> list[etree._Element]:
        """Load a behavior fragment file and return its substituted children."""
        fragment_path = self._root / "emph" / "behaviors" / f"{fragment.name}.xml"
        if not fragment_path.is_file():
            raise OracleSlotError(
                f"Behavior fragment '{fragment.name}' not found at {fragment_path}"
            )
        text = fragment_path.read_text(encoding="utf-8")

        substitutions: dict[str, str] = {
            "SHAPE_ID": str(shape_id),
            "DURATION_MS": str(duration_ms),
            "INNER_FILL": "hold",
        }
        for key, value in fragment.tokens.items():
            substitutions[str(key)] = str(value)
        rendered = _render_template(text, substitutions)

        wrapped = (
            f'<root xmlns:p="{NS_P}" xmlns:a="{NS_A}">{rendered}</root>'
        )
        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.fromstring(wrapped.encode("utf-8"), parser)
        fragment_elem = root.find("fragment")
        if fragment_elem is None:
            raise OracleSlotError(
                f"Behavior fragment '{fragment.name}' is missing <fragment> root"
            )
        # Return a list of child elements (the fragment's children become the
        # compound cTn's children). Detach to give ownership to the caller.
        children = list(fragment_elem)
        for child in children:
            fragment_elem.remove(child)
        return children


def _render_template(text: str, substitutions: Mapping[str, str]) -> str:
    # Use a targeted replace loop (not str.format) so literal braces in the
    # template — e.g. within attribute values like JSON blobs — survive.
    rendered = text
    for key, value in substitutions.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


@lru_cache(maxsize=1)
def default_oracle() -> AnimationOracle:
    """Return a process-wide cached :class:`AnimationOracle` instance."""
    return AnimationOracle()
