# Animation Event-Based Begin Triggers

**Status:** Implemented (current pipeline)
**Related:** `docs/adr/ADR-020-animation-writer-rewrite.md` (Section 5.4)

## Current State

The animation IR supports both:
- `AnimationTiming.begin: float` (backward-compatible numeric fallback), and
- `AnimationTiming.begin_triggers: list[BeginTrigger]` for structured SMIL begin conditions.

Parsing is implemented in `src/svg2ooxml/core/animation/parser.py`, and PowerPoint condition emission is implemented in `src/svg2ooxml/drawingml/animation/xml_builders.py`.

## Supported SVG `begin` Syntax

The parser accepts semicolon-separated begin tokens and maps each to a `BeginTrigger`:

| SVG syntax | Parsed trigger |
|---|---|
| `0s`, `2s`, `500ms` | `TIME_OFFSET` |
| `click` | `CLICK` |
| `click+0.5s` | `CLICK` with `delay_seconds=0.5` |
| `click + 0.5s` | `CLICK` with `delay_seconds=0.5` |
| `rect1.click` | `CLICK` targeted at `rect1` |
| `rect1.begin` | `ELEMENT_BEGIN` targeted at `rect1` |
| `rect1.end` | `ELEMENT_END` targeted at `rect1` |
| `rect1.end+0.5s` | `ELEMENT_END` with offset |
| `rect1.end + 0.5s` | `ELEMENT_END` with offset |
| `rect1.begin-1s` | `ELEMENT_BEGIN` with negative offset |
| `indefinite` | `INDEFINITE` (parsed, not emitted to PPT) |

## PowerPoint `<p:cond>` Mapping

`AnimationXMLBuilder._append_begin_conditions()` maps begin triggers to `<p:stCondLst><p:cond .../></p:stCondLst>`:

| Trigger | PPT output |
|---|---|
| `TIME_OFFSET` | `<p:cond delay="..."/>` |
| `CLICK` | `<p:cond evt="onClick" delay="...">` (+ optional `<p:tgtEl><p:spTgt .../>`) |
| `ELEMENT_BEGIN` | `<p:cond evt="onBegin" delay="...">` (+ `<p:tgtEl><p:spTgt .../>`) |
| `ELEMENT_END` | `<p:cond evt="onEnd" delay="...">` (+ `<p:tgtEl><p:spTgt .../>`) |

## Notes

- `begin="click+0.5s"` is explicitly supported and emits `evt="onClick"` with `delay="500"`.
- Whitespace around offsets is supported (for example `begin="click + 0.5s"`).
- Multiple begin conditions are preserved as multiple `<p:cond>` entries.
- `indefinite` is parsed but currently not emitted to native PowerPoint timing (no equivalent trigger).
