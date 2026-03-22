# Google Workspace Add-on

Convert SVGs to PowerPoint or Google Slides from within Google Docs,
Sheets, or Slides.

## Install

1. Open any Google Doc, Sheet, or Slide
2. **Extensions → Apps Script**
3. Delete the default code
4. Paste the contents of `Code.gs`
5. Copy `appsscript.json` to the manifest (View → Show manifest file)
6. **Project Settings → Script Properties** → add `SVG2OOXML_API_KEY` with the
   value of the server's `SVG2OOXML_API_KEY` environment variable
7. Reload the document — the **SVG → Slides** menu appears

## Use

### Sidebar
**SVG → Slides → Open converter** opens a sidebar where you can:
- Paste SVG markup and convert to PowerPoint (saved to Drive)
- Paste SVG and open directly in Google Slides
- Enter a Drive file ID to convert an SVG file

### Menu
- **Convert from clipboard** — prompt for SVG, saves PPTX to Drive
- **Convert file from Drive** — prompt for Drive file ID

### From code
```javascript
// Convert and save PPTX to Drive
var result = convertSvg('<svg>...</svg>', 'my-diagram');
// → {url: "https://drive.google.com/...", filename: "my-diagram.pptx", format: "PowerPoint (.pptx)"}

// Upload directly to Google Slides
var result = convertSvg('<svg>...</svg>', 'my-diagram', true);
// → {url: "https://docs.google.com/presentation/...", filename: "my-diagram", format: "Google Slides"}
```

## How it works

```
User pastes SVG → Apps Script → POST /api/v1/addon/convert → PPTX → Google Drive
                                                            ↘ Google Slides API
```

- **Auth**: API key via `SVG2OOXML_API_KEY` script property, sent as Bearer token
- **Dimensions**: Auto-extracted from the SVG's `width`/`height` attributes or `viewBox`
- **Conversion**: SVG → native DrawingML shapes (not images). Animations,
  gradients, text, and filters are preserved as editable PowerPoint objects.
- **Slides upload**: Uses the user's OAuth token (`ScriptApp.getOAuthToken()`)
  to upload via Google Drive API with automatic conversion to Slides format
