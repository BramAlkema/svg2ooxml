# Security Validation Rules for openxml-audit

**Purpose:** Add URI safety and active content detection to
[openxml-audit](https://github.com/BramAlkema/openxml-audit) so that
any PPTX/DOCX/XLSX can be scanned for dangerous content regardless of
which tool produced it.

**Context:** svg2ooxml blocks dangerous URIs at production time, but
openxml-audit should detect them at validation time — defense in depth.
Google removed SVG import from Docs/Slides over the same class of risks.

---

## What to build

### Rule 1: Dangerous URI Schemes in Relationships

**Location:** `src/openxml_audit/semantic/` — new file `security.py`

**What it checks:** Scan all `.rels` files for `Target` attributes
containing dangerous URI schemes.

**Blocked schemes:**
```python
DANGEROUS_SCHEMES = ("javascript:", "data:", "vbscript:", "file:")
```

**Implementation:**

```python
# src/openxml_audit/semantic/security.py

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lxml import etree

from openxml_audit.errors import ValidationError, ValidationErrorType, ValidationSeverity
from openxml_audit.semantic.attributes import SemanticConstraint

if TYPE_CHECKING:
    from openxml_audit.context import ValidationContext

DANGEROUS_SCHEMES = ("javascript:", "data:", "vbscript:", "file:")

SSRF_TARGETS = (
    "169.254.169.254", "metadata.google", "metadata.azure",
    "localhost", "127.0.0.1", "0.0.0.0", "[::1]",
)


@dataclass
class DangerousUriConstraint(SemanticConstraint):
    """Flag relationships with dangerous URI schemes or SSRF targets."""

    def validate(self, element: etree._Element, context: ValidationContext) -> bool:
        target = element.get("Target", "")
        if not target:
            return True

        target_lower = target.strip().lower()

        # Check dangerous schemes
        if target_lower.startswith(DANGEROUS_SCHEMES):
            context.add_error(ValidationError(
                error_type=ValidationErrorType.SEMANTIC,
                severity=ValidationSeverity.ERROR,
                description=f"Relationship contains dangerous URI scheme: {target[:60]}",
                part=context.current_part,
                path=context.current_path,
                node=element.tag,
            ))
            return False

        # Check SSRF targets
        if any(t in target_lower for t in SSRF_TARGETS):
            context.add_error(ValidationError(
                error_type=ValidationErrorType.SEMANTIC,
                severity=ValidationSeverity.WARNING,
                description=f"Relationship targets internal/cloud network: {target[:60]}",
                part=context.current_part,
                path=context.current_path,
                node=element.tag,
            ))
            return False

        return True
```

**Where to wire it:** In the relationship validation phase of
`OpenXmlValidator`. The validator already iterates all `.rels` files —
add a call to `DangerousUriConstraint.validate()` for each
`<Relationship>` element.

```python
# In validator.py, inside the relationship validation loop:
from openxml_audit.semantic.security import DangerousUriConstraint

security_check = DangerousUriConstraint()
for rel_element in rels_root:
    security_check.validate(rel_element, context)
```

### Rule 2: Active Content Detection

**What it checks:** Scan slide XML for elements that indicate active
content (macros, ActiveX, OLE, embedded scripts).

**Flagged patterns:**
```python
ACTIVE_CONTENT_TAGS = {
    # ActiveX
    "{http://schemas.openxmlformats.org/presentationml/2006/main}oleObj",
    "{http://schemas.openxmlformats.org/presentationml/2006/main}control",
    # Embedded objects
    "{http://schemas.openxmlformats.org/presentationml/2006/main}embeddedFont",
}

ACTIVE_CONTENT_TYPES = {
    "application/vnd.ms-office.activeX+xml",
    "application/vnd.ms-office.vbaProject",
    "application/vnd.ms-excel.sheet.macroEnabled.main+xml",
}
```

**Implementation:** Check `[Content_Types].xml` for macro-enabled
content types, and scan slide XML for ActiveX/OLE elements.

### Rule 3: External Relationship Audit

**What it checks:** List all relationships with `TargetMode="External"`
— these are URLs that PowerPoint may fetch when opening the file.

**Severity:** WARNING (not ERROR — external links are valid OOXML but
worth flagging for security review).

---

## Integration points

### Existing validation phases in openxml-audit:

```
1. Package Structure  ← add Rule 2 (content type check) here
2. Schema Validation  ← existing, no change
3. Semantic Validation ← add Rule 1 (URI check) here
4. Relationship Integrity ← add Rule 3 (external audit) here
```

### How to add a new semantic constraint:

1. Create a class inheriting from `SemanticConstraint` (in
   `semantic/attributes.py`)
2. Implement `validate(element, context) -> bool`
3. Add errors via `context.add_error(ValidationError(...))`
4. Wire into the appropriate validator phase

### Error types to use:

```python
ValidationErrorType.SEMANTIC    # for security constraint violations
ValidationSeverity.ERROR        # for dangerous schemes (javascript:, etc.)
ValidationSeverity.WARNING      # for SSRF targets, external links
```

### Test pattern:

```python
# tests/test_security.py

def test_javascript_uri_flagged(tmp_path):
    """PPTX with javascript: URI in rels should fail validation."""
    pptx = create_pptx_with_rel(target="javascript:alert(1)")
    result = validate_pptx(str(pptx))
    assert not result.is_valid
    assert any("dangerous URI" in str(e) for e in result.errors)

def test_safe_https_uri_passes(tmp_path):
    """PPTX with https: URI should pass."""
    pptx = create_pptx_with_rel(target="https://example.com")
    result = validate_pptx(str(pptx))
    assert result.is_valid
```

---

## CLI output

When security rules are active, the validator should report:

```
$ openxml-audit suspicious.pptx

suspicious.pptx - Invalid
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Type     ┃ Severity ┃ Description                                       ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ semantic │ error    │ Relationship contains dangerous URI: javascript:…  │
│ semantic │ warning  │ Relationship targets internal network: 169.254.…   │
│ semantic │ warning  │ 3 external relationships found (TargetMode=External)│
└──────────┴──────────┴───────────────────────────────────────────────────┘
Errors: 1, Warnings: 2
```

---

## Priority

- **Rule 1 (dangerous URIs):** High — directly prevents XSS vectors
- **Rule 2 (active content):** Medium — detects macro-enabled content
- **Rule 3 (external audit):** Low — informational, useful for compliance
