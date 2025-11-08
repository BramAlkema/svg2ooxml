// SVG to Google Slides - Figma Plugin UI Logic

try {
  window.debugLog('🟢 ui.js TOP - before anything');
} catch(e) {
  console.error('debugLog error:', e);
}

const log = window.debugLog || console.log.bind(console);
log('🟢🟢🟢 ui.js is loading!');

function readConfigOverride({ storageKey, queryKey, globalVar, label }) {
  try {
    if (queryKey) {
      const params = new URLSearchParams(window.location.search || '');
      const valueFromQuery = params.get(queryKey);
      if (valueFromQuery) {
        log(`🟣 ${label} override via query "${queryKey}": ${valueFromQuery}`);
        return valueFromQuery;
      }
    }
  } catch (error) {
    console.warn(`Failed to parse query params for ${label}:`, error);
  }

  try {
    if (storageKey && window.localStorage) {
      const valueFromStorage = window.localStorage.getItem(storageKey);
      if (valueFromStorage) {
        log(`🟣 ${label} override via localStorage "${storageKey}": ${valueFromStorage}`);
        return valueFromStorage;
      }
    }
  } catch (error) {
    console.warn(`Failed to read localStorage for ${label}:`, error);
  }

  if (globalVar && typeof window[globalVar] === 'string') {
    log(`🟣 ${label} override via window.${globalVar}: ${window[globalVar]}`);
    return window[globalVar];
  }

  return null;
}

function normalizeBaseUrl(url) {
  if (!url) return url;
  return url.endsWith('/') ? url.slice(0, -1) : url;
}

// API Configuration (supports dev overrides)
const API_URL = (() => {
  const override = readConfigOverride({
    storageKey: 'svg2ooxml_api_url',
    queryKey: 'api',
    globalVar: 'SVG2OOXML_API_URL',
    label: 'API_URL'
  });
  if (override) return normalizeBaseUrl(override);
  return 'https://svg2ooxml-export-sghya3t5ya-ew.a.run.app';
})();

const AUTH_URL = (() => {
  const override = readConfigOverride({
    storageKey: 'svg2ooxml_auth_url',
    queryKey: 'auth',
    globalVar: 'SVG2OOXML_AUTH_URL',
    label: 'AUTH_URL'
  });
  if (override) return normalizeBaseUrl(override);
  return 'https://powerful-layout-467812-p1.web.app';
})();

log('🟢 API_URL: ' + API_URL);
log('🟢 AUTH_URL: ' + AUTH_URL);
const API_TIMEOUT = 180000; // 3 minutes
const POLL_INTERVAL = 3000; // 3 seconds
const AUTH_POLL_INTERVAL = 2000; // 2 seconds for auth polling
const AUTH_TIMEOUT = 120000; // 2 minutes for auth

// Current user state
let currentUser = null;
let currentToken = null;
let currentRefreshToken = null;
let currentSubscription = null;

// UI Elements
log('🟢 Looking for UI elements...');
const signInBtn = document.getElementById('sign-in-btn');
const signOutBtn = document.getElementById('sign-out-btn');
const userInfo = document.getElementById('user-info');
const userEmail = document.getElementById('user-email');
const authSection = document.getElementById('auth-section');
const subscriptionSection = document.getElementById('subscription-section');
const exportSection = document.getElementById('export-section');
const exportDivider = document.getElementById('export-divider');
const exportBtn = document.getElementById('export-btn');
const statusDiv = document.getElementById('status');
const progressDiv = document.getElementById('progress');
const progressBar = document.getElementById('progress-bar');
const tierBadge = document.getElementById('tier-badge');
const tierName = document.getElementById('tier-name');
const usageBar = document.getElementById('usage-bar');
const usageText = document.getElementById('usage-text');
const upgradeBtn = document.getElementById('upgrade-btn');
const manageSubscriptionBtn = document.getElementById('manage-subscription-btn');

log('🟢 signInBtn: ' + (signInBtn ? 'FOUND ✓' : 'MISSING ✗'));
log('🟢 exportBtn: ' + (exportBtn ? 'FOUND ✓' : 'MISSING ✗'));

// ============================================================================
// Authentication
// ============================================================================

// Generate secure random auth key
function generateAuthKey() {
  const array = new Uint8Array(16);
  crypto.getRandomValues(array);
  return Array.from(array, byte =>
    byte.toString(16).padStart(2, '0')
  ).join('');
}

// Browser-compatible sign-in flow
async function signInBrowserFlow() {
  console.log('🔵 signInBrowserFlow started');
  const authKey = generateAuthKey();
  console.log('🔵 Generated auth key:', authKey);

  // Open auth window
  console.log('🔵 Opening popup window...');
  const authWindow = window.open(
    `${AUTH_URL}/auth.html?key=${authKey}`,
    '_blank',
    'width=500,height=600,menubar=no,toolbar=no,location=no'
  );
  console.log('🔵 Window.open returned:', authWindow);

  if (!authWindow) {
    console.error('❌ Popup was blocked');
    throw new Error('Popup blocked. Please allow popups and try again.');
  }
  console.log('✅ Popup opened successfully');

  showStatus('Complete sign-in in the popup window...', 'info');

  // Poll for token
  const result = await pollForAuthToken(authKey, authWindow);

  currentUser = { email: result.email };
  currentToken = result.token;
  currentRefreshToken = result.refreshToken;
}

// Desktop sign-in flow (fallback)
async function signInDesktopFlow() {
  const provider = new window.GoogleAuthProvider();

  // Request required OAuth scopes
  provider.addScope('https://www.googleapis.com/auth/drive.file');
  provider.addScope('https://www.googleapis.com/auth/presentations');

  // Show Google sign-in popup
  const result = await window.signInWithPopup(window.firebaseAuth, provider);

  // Get user info
  currentUser = result.user;
  currentToken = await result.user.getIdToken();
}

// Poll for auth token
async function pollForAuthToken(authKey, authWindow) {
  const startTime = Date.now();
  let attempts = 0;
  const maxAttempts = AUTH_TIMEOUT / AUTH_POLL_INTERVAL;

  while (Date.now() - startTime < AUTH_TIMEOUT) {
    attempts++;

    // Check if window was closed
    if (authWindow.closed) {
      throw new Error('Sign-in window was closed before completing authentication');
    }

    try {
      const response = await fetch(`${AUTH_URL}/auth-status.html?key=${authKey}`);
      const data = await response.json();

      if (data.status === 'ready') {
        // Close auth window
        if (!authWindow.closed) {
          authWindow.close();
        }
        return {
          token: data.token,
          refreshToken: data.refreshToken,
          email: data.email
        };
      }

      if (data.status === 'expired' || data.status === 'not_found') {
        if (!authWindow.closed) {
          authWindow.close();
        }
        throw new Error('Authentication failed or expired');
      }

    } catch (error) {
      // Ignore polling errors, continue trying
      if (error.message.includes('failed') || error.message.includes('expired')) {
        throw error;
      }
    }

    showStatus(`Waiting for authentication... (${attempts}/${maxAttempts})`, 'info');
    await sleep(AUTH_POLL_INTERVAL);
  }

  if (!authWindow.closed) {
    authWindow.close();
  }
  throw new Error('Authentication timeout');
}

// Sign in with Google (unified handler)
signInBtn.addEventListener('click', async () => {
  console.log('🔵 Sign-in button clicked');
  try {
    console.log('🔵 Starting sign-in flow...');
    showStatus('Opening sign-in window...', 'info');
    signInBtn.disabled = true;

    // Use browser-compatible flow (works in both browser and desktop)
    await signInBrowserFlow();

    // Save session for future plugin opens
    await saveSession(currentToken, currentRefreshToken, currentUser.email);

    // Update UI
    updateUIForSignedInUser();
    showStatus('Signed in successfully!', 'success');
    setTimeout(() => hideStatus(), 2000);

    console.log('User signed in:', currentUser.email);

  } catch (error) {
    console.error('Sign-in error:', error);

    if (error.message.includes('Popup blocked')) {
      showStatus('Popup blocked. Please allow popups for this plugin and try again.', 'error');
    } else if (error.message.includes('closed before completing')) {
      showStatus('Sign-in cancelled.', 'info');
      setTimeout(() => hideStatus(), 2000);
    } else {
      showStatus(`Sign-in failed: ${error.message}`, 'error');
    }

  } finally {
    signInBtn.disabled = false;
  }
});

// Sign out
signOutBtn.addEventListener('click', async () => {
  try {
    // Clear session from storage
    await clearSession();

    // Clear user state
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
async function updateUIForSignedInUser() {
  signInBtn.style.display = 'none';
  userInfo.style.display = 'block';
  userEmail.textContent = currentUser.email;
  subscriptionSection.style.display = 'block';
  exportDivider.style.display = 'block';
  exportSection.style.display = 'block';

  // Fetch subscription status
  await fetchSubscriptionStatus();
}

// Update UI for signed-out state
function updateUIForSignedOutUser() {
  signInBtn.style.display = 'block';
  userInfo.style.display = 'none';
  subscriptionSection.style.display = 'none';
  exportDivider.style.display = 'none';
  exportSection.style.display = 'none';
}

// ============================================================================
// Session Persistence
// ============================================================================

// Save session to Figma storage
async function saveSession(token, refreshToken, email) {
  parent.postMessage({
    pluginMessage: {
      type: 'save-session',
      token: token,
      refreshToken: refreshToken,
      email: email
    }
  }, '*');
}

// Clear session from Figma storage
async function clearSession() {
  parent.postMessage({
    pluginMessage: { type: 'clear-session' }
  }, '*');
}

// Request session restoration on load
parent.postMessage({
  pluginMessage: { type: 'restore-session' }
}, '*');

// ============================================================================
// Subscription Management
// ============================================================================

// Fetch subscription status from API
async function fetchSubscriptionStatus() {
  try {
    // Refresh token to ensure it's fresh
    try {
      await refreshIdToken();
    } catch (error) {
      console.error('Token refresh failed:', error);
      throw new Error('Session expired. Please sign in again.');
    }

    const response = await fetch(`${API_URL}/api/v1/subscription/status`, {
      headers: {
        'Authorization': `Bearer ${currentToken}`
      }
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch subscription: ${response.status}`);
    }

    const data = await response.json();
    currentSubscription = data;

    // Update UI with subscription info
    updateSubscriptionUI(data);

  } catch (error) {
    console.error('Subscription fetch error:', error);
    // Show error but don't block the UI
    showStatus(`Could not load subscription status: ${error.message}`, 'error');
    setTimeout(() => hideStatus(), 3000);
  }
}

// Update subscription UI with fetched data
function updateSubscriptionUI(subscription) {
  const tier = subscription.tier || 'free';
  const usage = subscription.usage || {};
  const current = usage.exports_this_month || 0;
  const limit = usage.limit || 5;
  const unlimited = usage.unlimited || false;

  // Update tier badge and name
  tierBadge.className = `badge ${tier}`;
  tierBadge.textContent = tier.toUpperCase();

  if (tier === 'free') {
    tierName.textContent = 'Free Plan';
  } else if (tier === 'pro') {
    tierName.textContent = 'Pro Plan';
  } else if (tier === 'enterprise') {
    tierName.textContent = 'Enterprise Plan';
  }

  // Update usage bar and text
  if (unlimited) {
    usageBar.className = 'usage-bar unlimited';
    usageBar.style.width = '100%';
    usageText.textContent = '∞ Unlimited exports';
  } else {
    const percentage = Math.min((current / limit) * 100, 100);
    usageBar.style.width = `${percentage}%`;

    // Change color based on usage
    if (percentage >= 100) {
      usageBar.className = 'usage-bar danger';
    } else if (percentage >= 80) {
      usageBar.className = 'usage-bar warning';
    } else {
      usageBar.className = 'usage-bar';
    }

    usageText.textContent = `${current} / ${limit} exports this month`;
  }

  // Show/hide upgrade button
  if (tier === 'free') {
    upgradeBtn.style.display = 'block';
    manageSubscriptionBtn.style.display = 'none';
  } else {
    upgradeBtn.style.display = 'none';
    manageSubscriptionBtn.style.display = 'block';
  }
}

// Handle upgrade button click
upgradeBtn.addEventListener('click', async () => {
  try {
    upgradeBtn.disabled = true;
    showStatus('Opening checkout...', 'info');

    // Refresh token
    await refreshIdToken();

    // Create checkout session
    const response = await fetch(`${API_URL}/api/v1/subscription/checkout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`
      },
      body: JSON.stringify({
        tier: 'pro',
        success_url: `${AUTH_URL}/payment-success.html`,
        cancel_url: `${AUTH_URL}/payment-cancel.html`
      })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Checkout failed: ${response.status}`);
    }

    const data = await response.json();

    // Open Stripe checkout in new window
    window.open(data.checkout_url, '_blank');

    showStatus('Complete checkout in the new window. Refresh to see your new plan.', 'info');

  } catch (error) {
    console.error('Upgrade error:', error);
    showStatus(`Upgrade failed: ${error.message}`, 'error');
  } finally {
    upgradeBtn.disabled = false;
  }
});

// Handle manage subscription button click
manageSubscriptionBtn.addEventListener('click', async () => {
  try {
    manageSubscriptionBtn.disabled = true;
    showStatus('Opening subscription management...', 'info');

    // Refresh token
    await refreshIdToken();

    // Create portal session
    const response = await fetch(`${API_URL}/api/v1/subscription/portal`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`
      },
      body: JSON.stringify({
        return_url: `${AUTH_URL}/index.html`
      })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Portal failed: ${response.status}`);
    }

    const data = await response.json();

    // Open Stripe portal in new window
    window.open(data.portal_url, '_blank');

    showStatus('Manage your subscription in the new window.', 'info');
    setTimeout(() => hideStatus(), 3000);

  } catch (error) {
    console.error('Manage subscription error:', error);
    showStatus(`Failed to open portal: ${error.message}`, 'error');
  } finally {
    manageSubscriptionBtn.disabled = false;
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

  if (message.type === 'session-restored') {
    // Restore session from storage
    if (message.token && message.refreshToken && message.email) {
      currentToken = message.token;
      currentRefreshToken = message.refreshToken;
      currentUser = { email: message.email };
      updateUIForSignedInUser();
      console.log('Session restored:', currentUser.email);
    } else {
      updateUIForSignedOutUser();
    }
  }

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

    // Don't show duplicate errors for quota exceeded or OAuth required (already shown)
    if (error.message !== 'QUOTA_EXCEEDED' && error.message !== 'OAUTH_REQUIRED') {
      showStatus(`Export failed: ${error.message}`, 'error');
    }

    hideProgress();

  } finally {
    exportBtn.disabled = false;
  }
}

// Refresh ID token using refresh token
async function refreshIdToken() {
  if (!currentRefreshToken) {
    throw new Error('No refresh token available');
  }

  const response = await fetch(
    'https://securetoken.googleapis.com/v1/token?key=AIzaSyBO14gjDcansf4U7Ue9D_A28fEC_ur_5cY',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        grant_type: 'refresh_token',
        refresh_token: currentRefreshToken
      })
    }
  );

  if (!response.ok) {
    throw new Error('Failed to refresh token');
  }

  const data = await response.json();
  currentToken = data.id_token;
  currentRefreshToken = data.refresh_token;

  // Save updated tokens
  await saveSession(currentToken, currentRefreshToken, currentUser.email);

  return currentToken;
}

// Create export job via API
async function createExportJob(frames, fileKey, fileName) {
  showStatus('Creating export job...', 'info');
  showProgress(10);

  // Refresh token to ensure it's fresh (Firebase ID tokens expire after 1 hour)
  // With refresh token, this allows indefinite session duration
  try {
    await refreshIdToken();
  } catch (error) {
    // If refresh fails, user needs to sign in again
    console.error('Token refresh failed:', error);
    throw new Error('Session expired. Please sign in again.');
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
    let errorData = {};
    try {
      errorData = await response.json();
    } catch (e) {
      console.error('Failed to parse error response:', e);
    }

    // Debug: Log response details
    console.log('🔍 Export failed:', { status: response.status, errorData });

    // Handle OAuth required (403 Forbidden)
    if (response.status === 403 && errorData?.detail?.error === 'oauth_required') {
      const connectUrl = errorData.detail.connect_url;
      const authKey = errorData.detail.auth_key;

      // Store export parameters for retry
      window.pendingExport = { frames, fileKey, fileName };

      // Render Connect UI
      const statusDiv = document.getElementById('status');
      const wrapper = document.createElement('div');
      wrapper.style.marginTop = '12px';
      wrapper.innerHTML = `
        <div style="padding:10px;border:1px solid #eee;border-radius:8px;background:#f9f9f9">
          <div style="font-weight:600;margin-bottom:8px">Google Drive access needed</div>
          <div style="font-size:12px;margin-bottom:10px">
            Click "Connect Google Drive", grant access, then click "Retry Export".
          </div>
          <div style="display:flex;gap:8px;margin-bottom:8px">
            <button id="btn-connect" class="button primary" style="padding:8px 12px;border-radius:6px">Connect Google Drive</button>
            <button id="btn-retry" class="button" style="padding:8px 12px;border-radius:6px" disabled>Retry Export</button>
          </div>
          <div style="font-size:11px;opacity:.7">Auth key: ${authKey || '—'}</div>
        </div>
      `;
      statusDiv.appendChild(wrapper);

      const btnConnect = wrapper.querySelector('#btn-connect');
      const btnRetry = wrapper.querySelector('#btn-retry');

      btnConnect.onclick = () => {
        // Ask main thread to open URL via figma.openExternal()
        parent.postMessage({ pluginMessage: { type: 'open-url', url: connectUrl } }, '*');
        btnRetry.disabled = false;
        btnConnect.textContent = '✓ Opened browser';
        btnConnect.disabled = true;
      };

      btnRetry.onclick = () => {
        wrapper.remove();
        exportBtn.click(); // Trigger export again
      };

      hideProgress();
      throw new Error('OAUTH_REQUIRED'); // Prevent generic error message
    }

    // Handle quota exceeded error (402 Payment Required)
    if (response.status === 402 && errorData?.detail?.error === 'quota_exceeded') {
      const usage = errorData.detail?.usage || {};
      const message = errorData.detail?.message || 'You have reached your monthly export limit.';

      showStatus(
        `<strong>Quota Exceeded</strong><br>${message}<br><br>` +
        `<span style="font-weight: 600;">Current usage: ${usage.current || 0} / ${usage.limit || 5} exports</span>`,
        'error'
      );

      upgradeBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
      throw new Error('QUOTA_EXCEEDED');
    }

    // Fallback error message
    const msg = (errorData && (errorData.detail?.message || errorData.detail || errorData.error || JSON.stringify(errorData))) || 'Export failed';
    throw new Error(`❌ ${msg}`);
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

// Final confirmation that entire file loaded
try {
  window.debugLog('🟢 ui.js END - entire file loaded successfully');
} catch(e) {
  console.error('Error at end of ui.js:', e);
}
