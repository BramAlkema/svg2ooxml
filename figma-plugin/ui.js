// SVG to Google Slides - Figma Plugin UI Logic

// API Configuration
const API_URL = 'https://svg2ooxml-export-sghya3t5ya-ew.a.run.app';
const API_TIMEOUT = 180000; // 3 minutes
const POLL_INTERVAL = 3000; // 3 seconds

// Current user state
let currentUser = null;
let currentToken = null;

// UI Elements
const signInBtn = document.getElementById('sign-in-btn');
const signOutBtn = document.getElementById('sign-out-btn');
const userInfo = document.getElementById('user-info');
const userEmail = document.getElementById('user-email');
const authSection = document.getElementById('auth-section');
const exportSection = document.getElementById('export-section');
const exportBtn = document.getElementById('export-btn');
const statusDiv = document.getElementById('status');
const progressDiv = document.getElementById('progress');
const progressBar = document.getElementById('progress-bar');

// ============================================================================
// Authentication
// ============================================================================

// Sign in with Google
signInBtn.addEventListener('click', async () => {
  try {
    showStatus('Opening sign-in window...', 'info');

    const provider = new window.GoogleAuthProvider();

    // Request required OAuth scopes
    provider.addScope('https://www.googleapis.com/auth/drive.file');
    provider.addScope('https://www.googleapis.com/auth/presentations');

    // Show Google sign-in popup
    const result = await window.signInWithPopup(window.firebaseAuth, provider);

    // Get user info
    currentUser = result.user;
    currentToken = await result.user.getIdToken();

    // Update UI
    updateUIForSignedInUser();
    showStatus('Signed in successfully!', 'success');
    setTimeout(() => hideStatus(), 2000);

    console.log('User signed in:', currentUser.email);

  } catch (error) {
    console.error('Sign-in error:', error);

    if (error.code === 'auth/popup-blocked') {
      showStatus('Popup blocked. Please allow popups for this plugin and try again.', 'error');
    } else if (error.code === 'auth/popup-closed-by-user') {
      showStatus('Sign-in cancelled.', 'info');
      setTimeout(() => hideStatus(), 2000);
    } else if (error.code === 'auth/cancelled-popup-request') {
      // User closed popup - this is fine, don't show error
      hideStatus();
    } else {
      showStatus(`Sign-in failed: ${error.message}`, 'error');
    }
  }
});

// Sign out
signOutBtn.addEventListener('click', async () => {
  try {
    await window.signOut(window.firebaseAuth);
    currentUser = null;
    currentToken = null;
    updateUIForSignedOutUser();
    showStatus('Signed out successfully', 'info');
    setTimeout(() => hideStatus(), 2000);
  } catch (error) {
    console.error('Sign-out error:', error);
    showStatus(`Sign-out failed: ${error.message}`, 'error');
  }
});

// Update UI for signed-in state
function updateUIForSignedInUser() {
  signInBtn.style.display = 'none';
  userInfo.style.display = 'block';
  userEmail.textContent = currentUser.email;
  exportSection.style.display = 'block';
}

// Update UI for signed-out state
function updateUIForSignedOutUser() {
  signInBtn.style.display = 'block';
  userInfo.style.display = 'none';
  exportSection.style.display = 'none';
}

// Check for existing session on load
window.firebaseAuth.onAuthStateChanged(async (user) => {
  if (user) {
    currentUser = user;
    currentToken = await user.getIdToken();
    updateUIForSignedInUser();
    console.log('Session restored:', user.email);
  } else {
    updateUIForSignedOutUser();
  }
});

// ============================================================================
// Export to Slides
// ============================================================================

// Export button handler
exportBtn.addEventListener('click', async () => {
  if (!currentUser || !currentToken) {
    showStatus('Please sign in first', 'error');
    return;
  }

  // Request SVG content from Figma
  parent.postMessage({
    pluginMessage: { type: 'get-svg-content' }
  }, '*');
});

// Handle messages from Figma plugin backend (code.js)
window.onmessage = async (event) => {
  const message = event.data.pluginMessage;

  if (message.type === 'svg-content') {
    // Received SVG content from Figma
    await handleExport(message.frames, message.fileKey, message.fileName);
  }

  if (message.type === 'error') {
    showStatus(message.message, 'error');
    hideProgress();
  }

  if (message.type === 'status') {
    showStatus(message.message, 'info');
  }
};

// Handle export process
async function handleExport(frames, fileKey, fileName) {
  try {
    exportBtn.disabled = true;
    showStatus(`Preparing to export ${frames.length} frame(s)...`, 'info');

    // Create export job
    const jobId = await createExportJob(frames, fileKey, fileName);

    // Poll for completion
    await pollJobStatus(jobId);

  } catch (error) {
    console.error('Export error:', error);
    showStatus(`Export failed: ${error.message}`, 'error');
    hideProgress();

  } finally {
    exportBtn.disabled = false;
  }
}

// Create export job via API
async function createExportJob(frames, fileKey, fileName) {
  showStatus('Creating export job...', 'info');
  showProgress(10);

  // Refresh token to ensure it's valid
  if (currentUser) {
    currentToken = await currentUser.getIdToken(true);
  }

  const response = await fetch(`${API_URL}/api/v1/export`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${currentToken}`
    },
    body: JSON.stringify({
      frames: frames.map(frame => ({
        name: frame.name,
        svg_content: frame.svg_content,
        width: frame.width,
        height: frame.height
      })),
      output_format: 'slides',
      figma_file_id: fileKey,
      figma_file_name: fileName
    })
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API error: ${response.status}`);
  }

  const data = await response.json();
  showProgress(20);

  return data.job_id;
}

// Poll job status until complete
async function pollJobStatus(jobId) {
  const startTime = Date.now();

  while (Date.now() - startTime < API_TIMEOUT) {
    // Check job status
    const response = await fetch(`${API_URL}/api/v1/export/${jobId}`, {
      headers: {
        'Authorization': `Bearer ${currentToken}`
      }
    });

    if (!response.ok) {
      throw new Error(`Failed to check job status: ${response.status}`);
    }

    const data = await response.json();

    // Update progress
    const progress = Math.round(data.progress || 20);
    showProgress(progress);

    if (data.status === 'processing') {
      const progressMsg = data.current_step
        ? `Processing: ${data.current_step}`
        : `Processing: ${progress}%`;
      showStatus(progressMsg, 'info');
    }

    // Check if complete
    if (data.status === 'completed') {
      handleExportSuccess(data);
      return;
    }

    if (data.status === 'failed') {
      throw new Error(data.error || 'Export failed');
    }

    // Wait before next poll
    await sleep(POLL_INTERVAL);
  }

  throw new Error('Export timed out after 3 minutes');
}

// Handle successful export
function handleExportSuccess(data) {
  hideProgress();

  const slidesUrl = data.slides_url;
  const editUrl = slidesUrl.replace('/pub', '/edit');

  showStatus(
    `✅ Export complete! <a href="${editUrl}" target="_blank">Open in Google Slides</a>`,
    'success'
  );

  // Notify Figma plugin
  parent.postMessage({
    pluginMessage: {
      type: 'export-complete',
      slides_url: editUrl
    }
  }, '*');
}

// ============================================================================
// UI Helpers
// ============================================================================

// Show status message
function showStatus(message, type = 'info') {
  statusDiv.innerHTML = message;
  statusDiv.className = `status ${type} visible`;
}

// Hide status message
function hideStatus() {
  statusDiv.className = 'status';
}

// Show progress bar
function showProgress(percent) {
  progressDiv.className = 'progress visible';
  progressBar.style.width = `${percent}%`;
}

// Hide progress bar
function hideProgress() {
  progressDiv.className = 'progress';
  progressBar.style.width = '0%';
}

// Sleep helper
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================================================
// Error Handling
// ============================================================================

// Global error handler
window.addEventListener('error', (event) => {
  console.error('Global error:', event.error);
  showStatus(`Unexpected error: ${event.error?.message || 'Unknown error'}`, 'error');
  hideProgress();
});

// Unhandled promise rejection handler
window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled promise rejection:', event.reason);
  showStatus(`Error: ${event.reason?.message || 'Unknown error'}`, 'error');
  hideProgress();
});
