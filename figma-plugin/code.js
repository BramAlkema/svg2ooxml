// SVG to Google Slides - Figma Plugin Backend
// This code runs in the Figma plugin sandbox

const EXPORTABLE_TYPES = new Set([
  'FRAME',
  'GROUP',
  'COMPONENT',
  'COMPONENT_SET',
  'INSTANCE',
  'SECTION'
]);
const textDecoder = typeof TextDecoder !== 'undefined'
  ? new TextDecoder('utf-8')
  : null;

figma.showUI(__html__, {
  width: 400,
  height: 600,
  themeColors: true
});

// Handle messages from the UI
figma.ui.onmessage = async (msg) => {
  try {
    if (msg.type === 'get-svg-content') {
      await handleGetSVGContent();
    }

    if (msg.type === 'save-session') {
      // Save session to Figma's clientStorage
      await figma.clientStorage.setAsync('auth_token', msg.token);
      await figma.clientStorage.setAsync('auth_refresh_token', msg.refreshToken);
      await figma.clientStorage.setAsync('auth_email', msg.email);
    }

    if (msg.type === 'clear-session') {
      // Clear session from Figma's clientStorage
      await figma.clientStorage.deleteAsync('auth_token');
      await figma.clientStorage.deleteAsync('auth_refresh_token');
      await figma.clientStorage.deleteAsync('auth_email');
    }

    if (msg.type === 'restore-session') {
      // Restore session from Figma's clientStorage
      const token = await figma.clientStorage.getAsync('auth_token');
      const refreshToken = await figma.clientStorage.getAsync('auth_refresh_token');
      const email = await figma.clientStorage.getAsync('auth_email');
      figma.ui.postMessage({
        type: 'session-restored',
        token: token,
        refreshToken: refreshToken,
        email: email
      });
    }

    if (msg.type === 'export-complete') {
      figma.notify('✅ Exported to Google Slides!');
    }

    if (msg.type === 'open-url') {
      // Open external URL (for OAuth flow)
      if (typeof msg.url === 'string') {
        figma.openExternal(msg.url);
      }
    }

    if (msg.type === 'show-notification') {
      figma.notify(msg.message);
    }

    if (msg.type === 'close-plugin') {
      figma.closePlugin();
    }

  } catch (error) {
    const message = normalizeError(error);
    figma.ui.postMessage({
      type: 'error',
      message
    });
  }
};

// Get SVG content from selected frames
async function handleGetSVGContent() {
  const selection = figma.currentPage.selection;
  if (!selection.length) {
    figma.notify('Select at least one frame, group, component, or instance.');
    figma.ui.postMessage({
      type: 'error',
      message: 'Please select at least one frame to export'
    });
    return;
  }

  const frames = selection.filter(node => EXPORTABLE_TYPES.has(node.type));

  if (frames.length === 0) {
    figma.notify('Selection does not contain exportable nodes.');
    figma.ui.postMessage({
      type: 'error',
      message: 'Selection does not contain exportable frames'
    });
    return;
  }

  figma.ui.postMessage({
    type: 'status',
    message: `Exporting ${frames.length} frame(s)...`
  });

  // Export each frame as SVG
  const svgFrames = [];

  for (let index = 0; index < frames.length; index += 1) {
    const frame = frames[index];
    try {
      // Export frame as SVG
      const svg = await frame.exportAsync({
        format: 'SVG',
        svgIdAttribute: true,
        svgOutlineText: false
      });

      let svgString;
      if (textDecoder) {
        svgString = textDecoder.decode(svg);
      } else {
        let buffer = '';
        const chunkSize = 8192;
        for (let i = 0; i < svg.length; i += chunkSize) {
          const chunk = svg.slice(i, i + chunkSize);
          buffer += String.fromCharCode.apply(null, chunk);
        }
        svgString = buffer;
      }

      svgFrames.push({
        name: frame.name || `Frame ${index + 1}`,
        svg_content: svgString,
        width: Math.round(frame.width),
        height: Math.round(frame.height)
      });
      figma.ui.postMessage({
        type: 'status',
        message: `Exported ${index + 1}/${frames.length}`
      });

    } catch (error) {
      const message = normalizeError(error);
      console.error(`Error exporting frame "${frame.name}":`, message);
      figma.ui.postMessage({
        type: 'error',
        message: `Failed to export frame "${frame.name}": ${message}`
      });
      figma.ui.postMessage({
        type: 'status',
        message: 'Export cancelled'
      });
      return;
    }
  }

  if (svgFrames.length === 0) {
    figma.ui.postMessage({
      type: 'error',
      message: 'Unable to export the current selection'
    });
    return;
  }

  // Send SVG content to UI
  figma.ui.postMessage({
    type: 'svg-content',
    frames: svgFrames,
    fileKey: figma.fileKey || 'unknown',
    fileName: figma.root.name || 'Untitled'
  });

  figma.ui.postMessage({
    type: 'status',
    message: 'Frames exported'
  });
}

function normalizeError(error) {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === 'string') {
    return error;
  }
  try {
    return JSON.stringify(error);
  } catch (stringifyError) {
    return 'Unknown error';
  }
}
