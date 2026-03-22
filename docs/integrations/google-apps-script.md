# Google Apps Script Integration

Convert SVGs to PowerPoint from Google Docs, Sheets, or Slides using
the svg2ooxml API on Coolify.

## Architecture

```
Google Apps Script → svg2ooxml API (Coolify) → PPTX bytes → Google Drive
```

Google removed SVG import from Docs/Slides. This integration fills that
gap: paste SVG markup, get a PowerPoint file in your Drive.

## Setup

### 1. API Key

The production API requires authentication. For Apps Script integration,
add an API key endpoint to your Coolify deployment, or use Supabase
service role auth.

### 2. Apps Script

In any Google Doc/Sheet/Slide: **Extensions → Apps Script**, paste:

```javascript
/**
 * svg2ooxml Google Apps Script integration.
 *
 * Converts SVG markup to PPTX via the svg2ooxml API and saves to Drive.
 */

const API_URL = 'https://svg2ooxml.tactcheck.com/api/v1/export';

/**
 * Convert SVG text to a PowerPoint file in Google Drive.
 *
 * @param {string} svgMarkup - The SVG content to convert.
 * @param {string} [filename] - Output filename (default: 'converted.pptx').
 * @returns {string} Google Drive URL of the created file.
 */
function svgToPptx(svgMarkup, filename) {
  filename = filename || 'converted.pptx';

  const payload = {
    frames: [{
      svg: svgMarkup,
      title: filename.replace('.pptx', ''),
    }],
    figma_file_name: filename,
    output_format: 'pptx',
  };

  const options = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    headers: {
      'Authorization': 'Bearer ' + getApiToken_(),
    },
    muteHttpExceptions: true,
  };

  const response = UrlFetchApp.fetch(API_URL, options);

  if (response.getResponseCode() !== 200) {
    throw new Error('Conversion failed: ' + response.getContentText());
  }

  // Save PPTX to Drive
  const blob = response.getBlob().setName(filename);
  const file = DriveApp.createFile(blob);

  return file.getUrl();
}

/**
 * Convert SVG from a Google Drive file to PPTX.
 *
 * @param {string} svgFileId - Google Drive file ID of the SVG.
 * @returns {string} Google Drive URL of the created PPTX.
 */
function convertSvgFile(svgFileId) {
  const svgFile = DriveApp.getFileById(svgFileId);
  const svgContent = svgFile.getBlob().getDataAsString();
  const pptxName = svgFile.getName().replace(/\.svg$/i, '.pptx');
  return svgToPptx(svgContent, pptxName);
}

/**
 * Add a custom menu to Google Sheets/Docs.
 */
function onOpen() {
  const ui = SpreadsheetApp.getUi();  // or DocumentApp / SlidesApp
  ui.createMenu('SVG to PPTX')
    .addItem('Convert SVG from cell...', 'convertFromCell')
    .addItem('Convert SVG file from Drive...', 'convertFromDrive')
    .addToUi();
}

/**
 * Prompt user for SVG content and convert.
 */
function convertFromCell() {
  const ui = SpreadsheetApp.getUi();
  const result = ui.prompt(
    'SVG to PPTX',
    'Paste SVG markup:',
    ui.ButtonSet.OK_CANCEL
  );

  if (result.getSelectedButton() === ui.Button.OK) {
    const url = svgToPptx(result.getResponseText());
    ui.alert('PPTX created: ' + url);
  }
}

/**
 * Prompt user for Drive file ID and convert.
 */
function convertFromDrive() {
  const ui = SpreadsheetApp.getUi();
  const result = ui.prompt(
    'SVG to PPTX',
    'Enter Google Drive SVG file ID:',
    ui.ButtonSet.OK_CANCEL
  );

  if (result.getSelectedButton() === ui.Button.OK) {
    const url = convertSvgFile(result.getResponseText().trim());
    ui.alert('PPTX created: ' + url);
  }
}

// --- Auth helper ---

/**
 * Get API token from script properties.
 * Set via: File → Project Settings → Script Properties → API_TOKEN
 */
function getApiToken_() {
  const token = PropertiesService.getScriptProperties().getProperty('API_TOKEN');
  if (!token) {
    throw new Error(
      'API_TOKEN not set. Go to File → Project Settings → Script Properties.'
    );
  }
  return token;
}
```

### 3. Set API Token

In Apps Script: **File → Project Settings → Script Properties**

Add: `API_TOKEN` = your Supabase service role JWT or API key.

### 4. Use It

- **From menu:** Sheets/Docs → SVG to PPTX → Convert SVG from cell
- **From code:** `=svgToPptx(A1)` where A1 contains SVG markup
- **From Drive:** provide a Drive file ID of an .svg file

## Adding a Public API Key Endpoint

For simpler integration without Supabase auth, add to the API:

```python
# src/svg2ooxml/api/routes/export.py

from fastapi import Header

API_KEYS = set(os.environ.get("SVG2OOXML_API_KEYS", "").split(","))

@router.post("/export/simple")
async def export_simple(
    request: ExportRequest,
    x_api_key: str = Header(...),
):
    """Convert SVG to PPTX with API key auth (no Supabase)."""
    if x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return await _do_export(request)
```

Then in Google Apps Script, use:
```javascript
headers: { 'X-API-Key': getApiToken_() }
```

## Google Slides Direct Upload

The API already supports uploading directly to Google Slides:

```javascript
function svgToSlides(svgMarkup, googleAccessToken) {
  const payload = {
    frames: [{ svg: svgMarkup, title: 'Slide 1' }],
    output_format: 'slides',
    google_access_token: googleAccessToken,
  };
  // ... same fetch pattern
  // Returns Google Slides URL directly
}
```

This requires the user's Google OAuth token, which Apps Script provides
via `ScriptApp.getOAuthToken()`:

```javascript
const token = ScriptApp.getOAuthToken();
const slidesUrl = svgToSlides(svgMarkup, token);
```
