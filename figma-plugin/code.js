// SVG to Google Slides - Figma Plugin Backend
// This code runs in the Figma plugin sandbox

// Show the plugin UI
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

    if (msg.type === 'export-complete') {
      figma.notify('✅ Exported to Google Slides!');
    }

    if (msg.type === 'show-notification') {
      figma.notify(msg.message);
    }

    if (msg.type === 'close-plugin') {
      figma.closePlugin();
    }

  } catch (error) {
    figma.ui.postMessage({
      type: 'error',
      message: error.message
    });
  }
};

// Get SVG content from selected frames
async function handleGetSVGContent() {
  // Get selected frames
  const selection = figma.currentPage.selection;
  const frames = selection.filter(node => node.type === 'FRAME');

  if (frames.length === 0) {
    figma.ui.postMessage({
      type: 'error',
      message: 'Please select at least one frame to export'
    });
    return;
  }

  figma.ui.postMessage({
    type: 'status',
    message: `Exporting ${frames.length} frame(s)...`
  });

  // Export each frame as SVG
  const svgFrames = [];

  for (const frame of frames) {
    try {
      // Export frame as SVG
      const svg = await frame.exportAsync({
        format: 'SVG',
        svgIdAttribute: true,
        svgOutlineText: false
      });

      // Convert to string
      const svgString = new TextDecoder().decode(svg);

      svgFrames.push({
        name: frame.name,
        svg_content: svgString,
        width: Math.round(frame.width),
        height: Math.round(frame.height)
      });

    } catch (error) {
      console.error(`Error exporting frame "${frame.name}":`, error);
      figma.ui.postMessage({
        type: 'error',
        message: `Failed to export frame "${frame.name}": ${error.message}`
      });
      return;
    }
  }

  // Send SVG content to UI
  figma.ui.postMessage({
    type: 'svg-content',
    frames: svgFrames,
    fileKey: figma.fileKey || 'unknown',
    fileName: figma.root.name || 'Untitled'
  });
}
