/**
 * svg2ooxml Google Workspace Add-on
 *
 * Converts SVG files to PowerPoint or Google Slides.
 * Browse SVG files from Drive or paste markup directly.
 */

var API_URL = 'https://svg2ooxml.tactcheck.com/api/v1/addon/convert';

// ---------------------------------------------------------------------------
// Menu & Sidebar
// ---------------------------------------------------------------------------

function onOpen(e) {
  getUi_()
    .createMenu('SVG \u2192 Slides')
    .addItem('Open converter', 'showSidebar')
    .addToUi();
}

function showSidebar() {
  var html = HtmlService.createHtmlOutput(getSidebarHtml_())
    .setTitle('SVG \u2192 Slides')
    .setWidth(320);
  getUi_().showSidebar(html);
}

// ---------------------------------------------------------------------------
// Drive file listing (server-side, no Picker API needed)
// ---------------------------------------------------------------------------

/**
 * Search Drive for SVG files. Returns up to 50 results.
 * @param {string} query - Optional search term to filter by filename
 * @returns {Array<{id: string, name: string, updated: string}>}
 */
function listSvgFiles(query) {
  var results = [];
  var search = 'trashed = false and (mimeType = "image/svg+xml"'
    + ' or (mimeType contains "text/" and title contains ".svg")'
    + ' or (mimeType contains "xml" and title contains ".svg"))';

  if (query && query.trim()) {
    search += ' and title contains "' + query.trim().replace(/"/g, '\\"') + '"';
  }

  var files;
  try {
    files = DriveApp.searchFiles(search);
  } catch (_) {
    // Fallback: simpler query if advanced search fails
    files = DriveApp.searchFiles('trashed = false and title contains ".svg"');
  }

  var count = 0;
  while (files.hasNext() && count < 50) {
    var f = files.next();
    results.push({
      id: f.getId(),
      name: f.getName(),
      updated: f.getLastUpdated().toISOString().slice(0, 10),
    });
    count++;
  }

  return results;
}

// ---------------------------------------------------------------------------
// Conversion
// ---------------------------------------------------------------------------

/**
 * Convert SVG to PPTX and save to Drive, or upload to Google Slides.
 *
 * @param {string} svgMarkup  - SVG content
 * @param {string} filename   - Output filename (without extension)
 * @param {boolean} openInSlides - Upload to Google Slides instead of PPTX
 * @returns {{url: string, filename: string, format: string}}
 */
function convertSvg(svgMarkup, filename, openInSlides) {
  svgMarkup = (svgMarkup || '').trim();
  filename = (filename || 'converted').replace(/\.pptx$/i, '');

  if (!svgMarkup || svgMarkup.indexOf('<svg') === -1) {
    throw new Error('Input does not appear to be valid SVG markup.');
  }

  var payload = {
    svg: svgMarkup,
    filename: filename,
    output_format: openInSlides ? 'slides' : 'pptx',
  };

  if (openInSlides) {
    payload.google_access_token = ScriptApp.getOAuthToken();
  }

  var response = UrlFetchApp.fetch(API_URL, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    headers: { 'Authorization': 'Bearer ' + getApiKey_() },
    muteHttpExceptions: true,
  });

  var code = response.getResponseCode();
  if (code !== 200) {
    throw new Error(
      'Conversion failed (' + code + '): ' +
      response.getContentText().substring(0, 300)
    );
  }

  if (openInSlides) {
    var result = JSON.parse(response.getContentText());
    return {
      url: result.slides_url || result.url,
      filename: filename,
      format: 'Google Slides',
    };
  }

  var blob = response.getBlob().setName(filename + '.pptx');
  var file = DriveApp.createFile(blob);
  return {
    url: file.getUrl(),
    filename: filename + '.pptx',
    format: 'PowerPoint (.pptx)',
  };
}

/**
 * Convert an SVG file stored in Google Drive.
 *
 * @param {string} fileId       - Google Drive file ID
 * @param {boolean} openInSlides - Upload to Slides instead of PPTX
 * @returns {{url: string, filename: string, format: string}}
 */
function convertDriveFile(fileId, openInSlides) {
  var file = DriveApp.getFileById(fileId);
  var svg = file.getBlob().getDataAsString();
  var name = file.getName().replace(/\.svg$/i, '');
  return convertSvg(svg, name, openInSlides);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getUi_() {
  try { return SpreadsheetApp.getUi(); } catch (_) {}
  try { return DocumentApp.getUi(); } catch (_) {}
  try { return SlidesApp.getUi(); } catch (_) {}
  throw new Error('Could not get UI \u2014 open this from a Google Doc, Sheet, or Slide.');
}

function getApiKey_() {
  var key = PropertiesService.getScriptProperties().getProperty('SVG2OOXML_API_KEY');
  if (!key) {
    throw new Error(
      'SVG2OOXML_API_KEY not set.\n\n' +
      'Go to Project Settings \u2192 Script Properties and add SVG2OOXML_API_KEY.'
    );
  }
  return key;
}

// ---------------------------------------------------------------------------
// Sidebar HTML
// ---------------------------------------------------------------------------

function getSidebarHtml_() {
  return '<!DOCTYPE html>\
<html>\
<head>\
  <base target="_top">\
  <style>\
    * { box-sizing: border-box; }\
    body { font-family: Google Sans, Arial, sans-serif; margin: 0; padding: 16px; color: #202124; font-size: 13px; }\
    h3 { margin: 0 0 16px; font-size: 16px; font-weight: 500; }\
    \
    .file-browser { margin-bottom: 16px; }\
    .search-row { display: flex; gap: 6px; margin-bottom: 8px; }\
    .search-row input {\
      flex: 1; padding: 7px 10px; border: 1px solid #dadce0;\
      border-radius: 8px; font-size: 13px; outline: none;\
    }\
    .search-row input:focus { border-color: #1a73e8; }\
    .search-row button {\
      padding: 7px 14px; background: #1a73e8; color: white; border: none;\
      border-radius: 8px; cursor: pointer; font-size: 12px; white-space: nowrap;\
    }\
    .search-row button:hover { background: #1765cc; }\
    \
    .file-list {\
      max-height: 200px; overflow-y: auto; border: 1px solid #dadce0;\
      border-radius: 8px; background: #fff;\
    }\
    .file-list.empty { padding: 20px; text-align: center; color: #9aa0a6; font-style: italic; }\
    .file-item {\
      padding: 8px 12px; cursor: pointer; display: flex;\
      align-items: center; gap: 8px; border-bottom: 1px solid #f1f3f4;\
    }\
    .file-item:last-child { border-bottom: none; }\
    .file-item:hover { background: #f8f9fa; }\
    .file-item.selected { background: #e8f0fe; }\
    .file-item .icon { color: #f4b400; font-size: 16px; flex-shrink: 0; }\
    .file-item .details { flex: 1; min-width: 0; }\
    .file-item .fname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }\
    .file-item .fdate { font-size: 11px; color: #9aa0a6; }\
    .file-item .check { color: #1a73e8; font-size: 16px; flex-shrink: 0; visibility: hidden; }\
    .file-item.selected .check { visibility: visible; }\
    \
    .loading-files { padding: 20px; text-align: center; color: #1967d2; }\
    \
    .selected-file {\
      display: none; background: #e8f0fe; border-radius: 8px;\
      padding: 8px 12px; margin-bottom: 12px; font-size: 13px;\
      color: #1967d2; align-items: center; gap: 8px;\
    }\
    .selected-file.visible { display: flex; }\
    .selected-file .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }\
    .selected-file .clear { cursor: pointer; font-size: 18px; color: #5f6368; line-height: 1; }\
    .selected-file .clear:hover { color: #c5221f; }\
    \
    .divider { border-top: 1px solid #dadce0; margin: 16px 0; padding-top: 4px; }\
    .toggle-paste { font-size: 12px; color: #1a73e8; cursor: pointer; display: inline-block; }\
    .toggle-paste:hover { text-decoration: underline; }\
    .paste-area { display: none; margin: 8px 0 12px; }\
    .paste-area.visible { display: block; }\
    \
    textarea {\
      width: 100%; height: 120px; border: 1px solid #dadce0; border-radius: 8px;\
      padding: 8px; font-family: monospace; font-size: 11px; resize: vertical;\
    }\
    input[type=text] {\
      width: 100%; padding: 7px 10px; border: 1px solid #dadce0;\
      border-radius: 8px; margin: 4px 0 12px; font-size: 13px;\
    }\
    label { font-size: 12px; color: #5f6368; display: block; margin: 8px 0 2px; }\
    \
    .actions { margin-top: 4px; }\
    .actions button {\
      background: #1a73e8; color: white; border: none; border-radius: 8px;\
      padding: 10px 20px; cursor: pointer; font-size: 14px; width: 100%;\
      margin: 4px 0; font-weight: 500;\
    }\
    .actions button:hover { background: #1765cc; }\
    .actions button.secondary { background: white; color: #1a73e8; border: 1px solid #dadce0; }\
    .actions button.secondary:hover { background: #f8f9fa; }\
    .actions button:disabled { opacity: 0.5; cursor: default; }\
    \
    .status {\
      margin: 12px 0; padding: 10px 12px; border-radius: 8px;\
      font-size: 13px; display: none;\
    }\
    .status.success { display: block; background: #e6f4ea; color: #137333; }\
    .status.error   { display: block; background: #fce8e6; color: #c5221f; }\
    .status.loading { display: block; background: #e8f0fe; color: #1967d2; }\
    .status a { color: inherit; font-weight: 500; }\
  </style>\
</head>\
<body>\
  <h3>SVG &#8594; Slides</h3>\
\
  <div class="file-browser" id="fileBrowser">\
    <div class="search-row">\
      <input type="text" id="searchQuery" placeholder="Search SVG files in Drive\u2026"\
             onkeydown="if(event.key===\'Enter\')loadFiles()">\
      <button onclick="loadFiles()">Search</button>\
    </div>\
    <div class="file-list" id="fileList">\
      <div class="loading-files">Loading SVG files\u2026</div>\
    </div>\
  </div>\
\
  <div class="selected-file" id="selectedFile">\
    <span class="name" id="selectedName"></span>\
    <span class="clear" onclick="clearSelection()" title="Remove">&times;</span>\
  </div>\
\
  <div class="divider">\
    <span class="toggle-paste" onclick="togglePaste()">or paste SVG markup directly</span>\
  </div>\
  <div class="paste-area" id="pasteArea">\
    <textarea id="svg" placeholder="<svg xmlns=&quot;...&quot;>...</svg>"></textarea>\
  </div>\
\
  <label for="filename">Output filename</label>\
  <input type="text" id="filename" value="converted" placeholder="my-diagram">\
\
  <div class="actions">\
    <button onclick="doConvert(false)" id="btnPptx">Save as PowerPoint</button>\
    <button class="secondary" onclick="doConvert(true)" id="btnSlides">Open in Google Slides</button>\
  </div>\
\
  <div id="status" class="status"></div>\
\
  <script>\
    var selectedFileId = null;\
\
    /* ---- Status & buttons ---- */\
    function setStatus(msg, type) {\
      var el = document.getElementById("status");\
      el.className = "status " + type;\
      el.innerHTML = msg;\
    }\
    function setButtons(disabled) {\
      document.getElementById("btnPptx").disabled = disabled;\
      document.getElementById("btnSlides").disabled = disabled;\
    }\
\
    /* ---- Paste toggle ---- */\
    function togglePaste() {\
      document.getElementById("pasteArea").classList.toggle("visible");\
    }\
\
    /* ---- File browser ---- */\
    function loadFiles() {\
      var query = document.getElementById("searchQuery").value;\
      var listEl = document.getElementById("fileList");\
      listEl.innerHTML = \'<div class="loading-files">Searching\u2026</div>\';\
\
      google.script.run\
        .withSuccessHandler(renderFiles)\
        .withFailureHandler(function(err) {\
          listEl.innerHTML = \'<div class="file-list empty">Error: \' + err.message + \'</div>\';\
        })\
        .listSvgFiles(query);\
    }\
\
    function renderFiles(files) {\
      var listEl = document.getElementById("fileList");\
      if (!files || files.length === 0) {\
        listEl.className = "file-list empty";\
        listEl.textContent = "No SVG files found in Drive.";\
        return;\
      }\
      listEl.className = "file-list";\
      var html = "";\
      for (var i = 0; i < files.length; i++) {\
        var f = files[i];\
        var sel = (f.id === selectedFileId) ? " selected" : "";\
        html += \'<div class="file-item\' + sel + \'" onclick="selectFile(\\\'\'\
          + f.id + \'\\\', \\\'\' + f.name.replace(/\'/g, "\\\\\'") + \'\\\')" \'\
          + \'data-id="\' + f.id + \'">\'\
          + \'<span class="icon">&#128196;</span>\'\
          + \'<div class="details">\'\
          + \'<div class="fname">\' + f.name + \'</div>\'\
          + \'<div class="fdate">\' + f.updated + \'</div>\'\
          + \'</div>\'\
          + \'<span class="check">&#10003;</span>\'\
          + \'</div>\';\
      }\
      listEl.innerHTML = html;\
    }\
\
    function selectFile(id, name) {\
      selectedFileId = id;\
      document.getElementById("selectedName").textContent = name;\
      document.getElementById("selectedFile").className = "selected-file visible";\
      var fnameInput = document.getElementById("filename");\
      if (fnameInput.value === "converted") {\
        fnameInput.value = name.replace(/\\.svg$/i, "");\
      }\
      /* Update highlight in list */\
      var items = document.querySelectorAll(".file-item");\
      for (var i = 0; i < items.length; i++) {\
        items[i].className = items[i].getAttribute("data-id") === id\
          ? "file-item selected" : "file-item";\
      }\
    }\
\
    function clearSelection() {\
      selectedFileId = null;\
      document.getElementById("selectedFile").className = "selected-file";\
      var items = document.querySelectorAll(".file-item");\
      for (var i = 0; i < items.length; i++) {\
        items[i].className = "file-item";\
      }\
    }\
\
    /* ---- Convert ---- */\
    function doConvert(openInSlides) {\
      var svg = document.getElementById("svg").value.trim();\
      if (!selectedFileId && !svg) {\
        setStatus("Select an SVG file or paste markup first.", "error");\
        return;\
      }\
\
      setStatus("Converting\u2026", "loading");\
      setButtons(true);\
\
      var onSuccess = function(result) {\
        setStatus(\'Created <a href="\' + result.url + \'" target="_blank">\' + result.format + \'</a>\', "success");\
        setButtons(false);\
      };\
      var onError = function(err) {\
        setStatus(err.message, "error");\
        setButtons(false);\
      };\
\
      if (selectedFileId) {\
        google.script.run\
          .withSuccessHandler(onSuccess)\
          .withFailureHandler(onError)\
          .convertDriveFile(selectedFileId, openInSlides);\
      } else {\
        var filename = document.getElementById("filename").value;\
        google.script.run\
          .withSuccessHandler(onSuccess)\
          .withFailureHandler(onError)\
          .convertSvg(svg, filename, openInSlides);\
      }\
    }\
\
    /* ---- Init: load files on open ---- */\
    loadFiles();\
  </script>\
</body>\
</html>';
}
