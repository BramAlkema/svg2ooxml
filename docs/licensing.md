<!--
SPDX-FileCopyrightText: 2026 SVG2OOXML Contributors
SPDX-License-Identifier: CC-BY-NC-SA-4.0
-->

# Licensing Guide

This repository uses a split license model:

- Software code: `AGPL-3.0-only`
- Documentation and selected content assets: `CC BY-NC-SA 4.0`

Reference files:

- `LICENSE` (software)
- `LICENSE-CONTENT` (content scope)

## SPDX Headers For New Files

Use SPDX headers in new files so license intent is explicit at file level.

### Python Source Files (AGPL)

```python
# SPDX-FileCopyrightText: 2026 SVG2OOXML Contributors
# SPDX-License-Identifier: AGPL-3.0-only
```

### Markdown Docs (CC BY-NC-SA)

```markdown
<!--
SPDX-FileCopyrightText: 2026 SVG2OOXML Contributors
SPDX-License-Identifier: CC-BY-NC-SA-4.0
-->
```

### SVG Fixture/Asset Files (CC BY-NC-SA)

```xml
<!--
SPDX-FileCopyrightText: 2026 SVG2OOXML Contributors
SPDX-License-Identifier: CC-BY-NC-SA-4.0
-->
```

## Templates

Starter templates with headers are available in:

- `tools/templates/python_module.py.tmpl`
- `tools/templates/markdown_doc.md.tmpl`
- `tools/templates/svg_fixture.svg.tmpl`
