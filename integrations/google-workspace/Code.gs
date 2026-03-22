/**
 * svg2ooxml Google Workspace Add-on
 *
 * Converts SVG to PowerPoint or Google Slides from any Google app.
 * Works in Docs, Sheets, Slides, and standalone.
 */

const API_URL = 'https://svg2ooxml.tactcheck.com/api/v1/export';

// ---------------------------------------------------------------------------
// Menu & Sidebar
// ---------------------------------------------------------------------------

function onOpen(e) {
  const ui = (SpreadsheetApp && SpreadsheetApp.getUi)
    ? SpreadsheetApp.getUi()
    : (DocumentApp && DocumentApp.getUi)
      ? DocumentApp.getUi()
      : SlidesApp.getUi();

  ui.createMenu('SVG → Slides')
    .addItem('Open converter', 'showSidebar')
    .addSeparator()
    .addItem('Convert from clipboard', 'convertFromPrompt')
    .addItem('Convert file from Drive', 'convertFromDrive')
    .addToUi();
}

function showSidebar() {
  const html = HtmlService.createHtmlOutput(getSidebarHtml_())
    .setTitle('SVG → Slides')
    .setWidth(300);

  const ui = getUi_();
  ui.showSidebar(html);
}

// ---------------------------------------------------------------------------
// Conversion
// ---------------------------------------------------------------------------

/**
 * Convert SVG to PPTX and save to Drive.
 * Called from sidebar or menu.
 *
 * @param {string} svgMarkup - SVG content
 * @param {string} filename - Output filename
 * @param {boolean} openInSlides - Upload to Google Slides instead
 * @returns {Object} {url, filename, format}
 */
function convertSvg(svgMarkup, filename, openInSlides) {
  filename = filename || 'converted';
  if (!filename.endsWith('.pptx')) filename += '.pptx';

  // Validate SVG
  if (!svgMarkup || !svgMarkup.trim().includes('<svg')) {
    throw new Error('Input does not appear to be valid SVG markup.');
  }

  const payload = {
    frames: [{
      svg: svgMarkup.trim(),
      title: filename.replace('.pptx', ''),
    }],
    figma_file_name: filename,
    output_format: openInSlides ? 'slides' : 'pptx',
  };

  // Add Google token for Slides upload
  if (openInSlides) {
    payload.google_access_token = ScriptApp.getOAuthToken();
  }

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
  const code = response.getResponseCode();

  if (code !== 200) {
    const body = response.getContentText();
    throw new Error('Conversion failed (' + code + '): ' + body.substring(0, 200));
  }

  if (openInSlides) {
    // API returns JSON with Slides URL
    const result = JSON.parse(response.getContentText());
    return {
      url: result.slides_url || result.url,
      filename: filename,
      format: 'Google Slides',
    };
  }

  // Save PPTX to Drive
  const blob = response.getBlob().setName(filename);
  const file = DriveApp.createFile(blob);

  return {
    url: file.getUrl(),
    filename: filename,
    format: 'PowerPoint (.pptx)',
  };
}

/**
 * Convert an SVG file from Google Drive.
 */
function convertDriveFile(fileId, openInSlides) {
  const file = DriveApp.getFileById(fileId);
  const svg = file.getBlob().getDataAsString();
  const name = file.getName().replace(/\.svg$/i, '');
  return convertSvg(svg, name, openInSlides);
}

// ---------------------------------------------------------------------------
// Menu actions
// ---------------------------------------------------------------------------

function convertFromPrompt() {
  const ui = getUi_();
  const result = ui.prompt(
    'SVG → Slides',
    'Paste SVG markup:',
    ui.ButtonSet.OK_CANCEL
  );
  if (result.getSelectedButton() !== ui.Button.OK) return;

  try {
    const output = convertSvg(result.getResponseText());
    ui.alert('Created ' + output.format + ':\n' + output.url);
  } catch (e) {
    ui.alert('Error: ' + e.message);
  }
}

function convertFromDrive() {
  const ui = getUi_();
  const result = ui.prompt(
    'SVG → Slides',
    'Enter Google Drive file ID of the SVG:',
    ui.ButtonSet.OK_CANCEL
  );
  if (result.getSelectedButton() !== ui.Button.OK) return;

  try {
    const output = convertDriveFile(result.getResponseText().trim());
    ui.alert('Created ' + output.format + ':\n' + output.url);
  } catch (e) {
    ui.alert('Error: ' + e.message);
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getUi_() {
  try { return SpreadsheetApp.getUi(); } catch (e) {}
  try { return DocumentApp.getUi(); } catch (e) {}
  try { return SlidesApp.getUi(); } catch (e) {}
  throw new Error('No UI available');
}

function getApiToken_() {
  const token = PropertiesService.getScriptProperties().getProperty('API_TOKEN');
  if (!token) {
    throw new Error(
      'API_TOKEN not set.\n\n' +
      'Go to Project Settings → Script Properties and add API_TOKEN.'
    );
  }
  return token;
}

function getSidebarHtml_() {
  return `
<!DOCTYPE html>
<html>
<head>
  <base target="_top">
  <style>
    body { font-family: Google Sans, Arial, sans-serif; margin: 16px; color: #202124; }
    h3 { margin: 0 0 12px; font-size: 16px; }
    textarea { width: 100%; height: 200px; border: 1px solid #dadce0; border-radius: 8px;
               padding: 8px; font-family: monospace; font-size: 12px; resize: vertical; }
    input[type=text] { width: 100%; padding: 8px; border: 1px solid #dadce0;
                       border-radius: 8px; margin: 8px 0; }
    button { background: #1a73e8; color: white; border: none; border-radius: 8px;
             padding: 10px 20px; cursor: pointer; font-size: 14px; width: 100%; margin: 4px 0; }
    button:hover { background: #1765cc; }
    button.secondary { background: white; color: #1a73e8; border: 1px solid #dadce0; }
    button.secondary:hover { background: #f8f9fa; }
    .status { margin: 12px 0; padding: 8px; border-radius: 8px; font-size: 13px; display: none; }
    .status.success { display: block; background: #e6f4ea; color: #137333; }
    .status.error { display: block; background: #fce8e6; color: #c5221f; }
    .status.loading { display: block; background: #e8f0fe; color: #1967d2; }
    label { font-size: 13px; color: #5f6368; display: block; margin: 8px 0 4px; }
    .divider { border-top: 1px solid #dadce0; margin: 16px 0; }
  </style>
</head>
<body>
  <h3>SVG → Slides</h3>

  <label>SVG markup</label>
  <textarea id="svg" placeholder="Paste SVG here..."></textarea>

  <label>Filename</label>
  <input type="text" id="filename" value="converted" placeholder="Output filename">

  <button onclick="convert(false)">Save as PowerPoint</button>
  <button class="secondary" onclick="convert(true)">Open in Google Slides</button>

  <div class="divider"></div>

  <label>Or convert a Drive file</label>
  <input type="text" id="fileId" placeholder="Google Drive file ID">
  <button class="secondary" onclick="convertFile()">Convert Drive file</button>

  <div id="status" class="status"></div>

  <script>
    function setStatus(msg, type) {
      const el = document.getElementById('status');
      el.className = 'status ' + type;
      el.textContent = msg;
    }

    function convert(openInSlides) {
      const svg = document.getElementById('svg').value;
      const filename = document.getElementById('filename').value;
      if (!svg.trim()) { setStatus('Please paste SVG markup.', 'error'); return; }

      setStatus('Converting...', 'loading');
      google.script.run
        .withSuccessHandler(function(result) {
          setStatus('Created: ' + result.format, 'success');
          window.open(result.url, '_blank');
        })
        .withFailureHandler(function(err) {
          setStatus(err.message, 'error');
        })
        .convertSvg(svg, filename, openInSlides);
    }

    function convertFile() {
      const fileId = document.getElementById('fileId').value.trim();
      if (!fileId) { setStatus('Please enter a Drive file ID.', 'error'); return; }

      setStatus('Converting...', 'loading');
      google.script.run
        .withSuccessHandler(function(result) {
          setStatus('Created: ' + result.format, 'success');
          window.open(result.url, '_blank');
        })
        .withFailureHandler(function(err) {
          setStatus(err.message, 'error');
        })
        .convertDriveFile(fileId, false);
    }
  </script>
</body>
</html>`;
}
