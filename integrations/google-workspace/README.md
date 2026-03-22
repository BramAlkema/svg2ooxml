# Google Workspace Add-on

Convert SVGs to PowerPoint or Google Slides from within Google Docs,
Sheets, or Slides.

## Install

1. Open any Google Doc, Sheet, or Slide
2. **Extensions → Apps Script**
3. Delete the default code
4. Paste the contents of `Code.gs`
5. Copy `appsscript.json` to the manifest (View → Show manifest file)
6. **Project Settings → Script Properties** → add `API_TOKEN` with your
   svg2ooxml API key
7. Reload the document — "SVG → Slides" menu appears

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
// In any Apps Script
const url = convertSvg('<svg>...</svg>', 'my-diagram');
// Returns Drive URL of the created PPTX

// Or open directly in Google Slides
const slidesUrl = convertSvg('<svg>...</svg>', 'my-diagram', true);
```

## How it works

```
User pastes SVG → Apps Script → svg2ooxml API (Coolify) → PPTX → Google Drive
                                                        ↘ Google Slides API
```

The API converts SVG to native DrawingML shapes (not images). Animations,
gradients, text, and filters are preserved as editable PowerPoint objects.

For Google Slides output, the API uses the user's OAuth token
(`ScriptApp.getOAuthToken()`) to upload directly via Google Slides API.
