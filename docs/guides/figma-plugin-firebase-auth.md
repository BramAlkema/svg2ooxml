# Figma Plugin Firebase Authentication Integration Guide

**Purpose**: This guide shows how to integrate Firebase Authentication into your Figma plugin to enable Google Slides export for users.

**Audience**: Figma plugin developers
**Time to Implement**: ~2 hours

---

## Overview

To export SVG content to Google Slides, users must authenticate with their Google account. This allows the svg2ooxml API to create presentations in the user's Google Drive.

### Authentication Flow

```
User clicks "Export to Slides" in Figma
  ↓
Plugin shows "Sign in with Google" button
  ↓
User authenticates with Google (Firebase Auth popup)
  ↓
Plugin receives Firebase ID token
  ↓
Plugin calls svg2ooxml API with token in Authorization header
  ↓
API creates Slides presentation in user's Drive
  ↓
Plugin shows success message with link to presentation
```

---

## Prerequisites

Before starting, you need:

1. **Firebase Web Config**: Get this from the backend team or Firebase Console
   ```json
   {
     "apiKey": "AIzaSyD...",
     "authDomain": "svg2ooxml.firebaseapp.com",
     "projectId": "svg2ooxml"
   }
   ```

2. **svg2ooxml API URL**: Cloud Run service URL
   ```
   https://svg2ooxml-export-sghya3t5ya-ew.a.run.app
   ```

3. **Figma Plugin Setup**: Existing Figma plugin with SVG export functionality

---

## Installation

### 1. Install Firebase SDK

Add Firebase to your plugin project:

```bash
npm install firebase
```

### 2. Update manifest.json

Figma plugins need network access permissions:

```json
{
  "name": "SVG to Slides",
  "id": "your-plugin-id",
  "api": "1.0.0",
  "main": "code.js",
  "ui": "ui.html",
  "networkAccess": {
    "allowedDomains": [
      "https://svg2ooxml-export-sghya3t5ya-ew.a.run.app",
      "https://*.googleapis.com",
      "https://*.firebaseapp.com",
      "https://*.google.com"
    ]
  }
}
```

---

## Implementation

### 1. Initialize Firebase in UI Code

**File**: `ui.html` or `ui.js` (plugin UI)

```html
<!DOCTYPE html>
<html>
<head>
  <script type="module">
    // Import Firebase modules
    import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js';
    import {
      getAuth,
      signInWithPopup,
      GoogleAuthProvider,
      signOut
    } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js';

    // Firebase configuration (get from backend team)
    const firebaseConfig = {
      apiKey: "AIzaSyD...",
      authDomain: "svg2ooxml.firebaseapp.com",
      projectId: "svg2ooxml",
      storageBucket: "svg2ooxml.appspot.com",
      messagingSenderId: "123456789",
      appId: "1:123456789:web:abc123"
    };

    // Initialize Firebase
    const app = initializeApp(firebaseConfig);
    const auth = getAuth(app);

    // Make auth available globally
    window.firebaseAuth = auth;
    window.GoogleAuthProvider = GoogleAuthProvider;
    window.signInWithPopup = signInWithPopup;
    window.signOut = signOut;

    console.log("Firebase initialized successfully");
  </script>
</head>
<body>
  <!-- Your plugin UI -->
  <div id="auth-section">
    <button id="sign-in-btn">Sign in with Google</button>
    <div id="user-info" style="display: none;">
      <p>Signed in as: <span id="user-email"></span></p>
      <button id="sign-out-btn">Sign out</button>
    </div>
  </div>

  <div id="export-section" style="display: none;">
    <button id="export-to-slides-btn">Export to Google Slides</button>
    <div id="status"></div>
  </div>

  <script src="ui.js"></script>
</body>
</html>
```

### 2. Implement Authentication Logic

**File**: `ui.js`

```javascript
// Current user and token
let currentUser = null;
let currentToken = null;

// UI elements
const signInBtn = document.getElementById('sign-in-btn');
const signOutBtn = document.getElementById('sign-out-btn');
const userInfo = document.getElementById('user-info');
const userEmail = document.getElementById('user-email');
const authSection = document.getElementById('auth-section');
const exportSection = document.getElementById('export-section');
const exportBtn = document.getElementById('export-to-slides-btn');
const statusDiv = document.getElementById('status');

// Sign in with Google
signInBtn.addEventListener('click', async () => {
  try {
    const provider = new window.GoogleAuthProvider();

    // Request required OAuth scopes for Drive/Slides access
    provider.addScope('https://www.googleapis.com/auth/drive.file');
    provider.addScope('https://www.googleapis.com/auth/presentations');

    // Show Google sign-in popup
    const result = await window.signInWithPopup(window.firebaseAuth, provider);

    // Get user info
    currentUser = result.user;

    // Get ID token for API authentication
    currentToken = await result.user.getIdToken();

    // Update UI
    updateUIForSignedInUser();

    console.log('User signed in:', currentUser.email);

  } catch (error) {
    console.error('Sign-in error:', error);
    showStatus(`Sign-in failed: ${error.message}`, 'error');
  }
});

// Sign out
signOutBtn.addEventListener('click', async () => {
  try {
    await window.signOut(window.firebaseAuth);
    currentUser = null;
    currentToken = null;
    updateUIForSignedOutUser();
    console.log('User signed out');
  } catch (error) {
    console.error('Sign-out error:', error);
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
  currentToken = null;
  currentUser = null;
}

// Check for existing session on load
window.firebaseAuth.onAuthStateChanged(async (user) => {
  if (user) {
    currentUser = user;
    currentToken = await user.getIdToken();
    updateUIForSignedInUser();
  } else {
    updateUIForSignedOutUser();
  }
});

// Show status message
function showStatus(message, type = 'info') {
  statusDiv.textContent = message;
  statusDiv.className = type;
  statusDiv.style.display = 'block';
}
```

### 3. Export to Slides with Authentication

**File**: `ui.js` (continued)

```javascript
// Export to Google Slides
exportBtn.addEventListener('click', async () => {
  if (!currentToken) {
    showStatus('Please sign in first', 'error');
    return;
  }

  try {
    // Get SVG content from Figma (communicate with code.js)
    parent.postMessage({ pluginMessage: { type: 'get-svg-content' } }, '*');

  } catch (error) {
    console.error('Export error:', error);
    showStatus(`Export failed: ${error.message}`, 'error');
  }
});

// Handle messages from code.js (Figma plugin backend)
window.onmessage = async (event) => {
  const message = event.data.pluginMessage;

  if (message.type === 'svg-content') {
    // Received SVG content from Figma
    const frames = message.frames;

    try {
      // Create export job via API
      await createExportJob(frames);
    } catch (error) {
      showStatus(`Export failed: ${error.message}`, 'error');
    }
  }
};

// Create export job via svg2ooxml API
async function createExportJob(frames) {
  showStatus('Creating export job...', 'info');

  const API_URL = 'https://svg2ooxml-export-sghya3t5ya-ew.a.run.app';

  // Prepare request
  const requestData = {
    frames: frames.map(frame => ({
      name: frame.name,
      svg_content: frame.svg_content,
      width: frame.width,
      height: frame.height
    })),
    output_format: 'slides',
    figma_file_id: 'figma-export',
    figma_file_name: 'Figma Design'
  };

  // Call API with authentication
  const response = await fetch(`${API_URL}/api/v1/export`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${currentToken}`  // ← Include Firebase ID token
    },
    body: JSON.stringify(requestData)
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Export failed');
  }

  const data = await response.json();
  const jobId = data.job_id;

  showStatus('Export job created. Processing...', 'info');

  // Poll for job completion
  await pollJobStatus(jobId);
}

// Poll job status until complete
async function pollJobStatus(jobId) {
  const API_URL = 'https://svg2ooxml-export-sghya3t5ya-ew.a.run.app';
  const MAX_WAIT_TIME = 180000; // 3 minutes
  const POLL_INTERVAL = 3000; // 3 seconds

  const startTime = Date.now();

  while (Date.now() - startTime < MAX_WAIT_TIME) {
    // Check job status
    const response = await fetch(`${API_URL}/api/v1/export/${jobId}`, {
      headers: {
        'Authorization': `Bearer ${currentToken}`
      }
    });

    if (!response.ok) {
      throw new Error('Failed to check job status');
    }

    const data = await response.json();

    // Update progress
    const progress = Math.round(data.progress || 0);
    showStatus(`Processing: ${progress}%`, 'info');

    // Check if complete
    if (data.status === 'completed') {
      handleExportSuccess(data);
      return;
    }

    if (data.status === 'failed') {
      throw new Error(data.error || 'Export failed');
    }

    // Wait before next poll
    await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL));
  }

  throw new Error('Export timed out');
}

// Handle successful export
function handleExportSuccess(data) {
  const slidesUrl = data.slides_url;
  const editUrl = slidesUrl.replace('/pub', '/edit');

  showStatus(
    `✅ Export complete! <a href="${editUrl}" target="_blank">Open in Google Slides</a>`,
    'success'
  );

  // Optionally notify code.js
  parent.postMessage({
    pluginMessage: {
      type: 'export-complete',
      slides_url: editUrl
    }
  }, '*');
}
```

### 4. Get SVG Content from Figma

**File**: `code.js` (Figma plugin backend)

```javascript
// Handle messages from UI
figma.ui.onmessage = async (msg) => {
  if (msg.type === 'get-svg-content') {
    try {
      // Get selected frames or all frames
      const frames = figma.currentPage.selection.filter(
        node => node.type === 'FRAME'
      );

      if (frames.length === 0) {
        figma.ui.postMessage({
          type: 'error',
          message: 'Please select at least one frame'
        });
        return;
      }

      // Export frames to SVG
      const svgFrames = await Promise.all(
        frames.map(async (frame) => {
          // Export frame as SVG
          const svg = await frame.exportAsync({
            format: 'SVG',
            svgIdAttribute: true
          });

          // Convert to string
          const svgString = new TextDecoder().decode(svg);

          return {
            name: frame.name,
            svg_content: svgString,
            width: Math.round(frame.width),
            height: Math.round(frame.height)
          };
        })
      );

      // Send to UI
      figma.ui.postMessage({
        type: 'svg-content',
        frames: svgFrames
      });

    } catch (error) {
      figma.ui.postMessage({
        type: 'error',
        message: error.message
      });
    }
  }

  if (msg.type === 'export-complete') {
    // Show success notification
    figma.notify('✅ Exported to Google Slides!');
  }
};
```

---

## OAuth Scopes Explained

### Required Scopes

```javascript
provider.addScope('https://www.googleapis.com/auth/drive.file');
provider.addScope('https://www.googleapis.com/auth/presentations');
```

**Why these scopes?**

1. **`drive.file`**: Allows creating new files in the user's Google Drive
   - ✅ Can create new files
   - ❌ Cannot access existing files
   - ❌ Cannot view user's drive contents
   - Most restrictive Drive scope

2. **`presentations`**: Allows creating and editing Google Slides presentations
   - ✅ Can create presentations
   - ✅ Can update presentations
   - ❌ Cannot access other Google services

### What Users See

During sign-in, users will see a consent screen like this:

```
svg2ooxml wants to:

✓ See, edit, create, and delete only the specific Google Drive files you use with this app
✓ See, edit, create, and delete all your Google Slides presentations

[Cancel] [Allow]
```

**How to explain to users**:
> "We need access to create a Google Slides presentation in your Drive. We only create new files—we never access your existing files."

---

## Error Handling

### Common Errors and Solutions

#### 1. "Popup blocked"

**Cause**: Browser blocked the Google sign-in popup

**Solution**:
```javascript
try {
  const result = await signInWithPopup(auth, provider);
} catch (error) {
  if (error.code === 'auth/popup-blocked') {
    showStatus(
      'Popup blocked. Please allow popups for this plugin and try again.',
      'error'
    );
  }
}
```

#### 2. "User denied scopes"

**Cause**: User clicked "Cancel" on OAuth consent screen

**Solution**:
```javascript
try {
  const result = await signInWithPopup(auth, provider);
} catch (error) {
  if (error.code === 'auth/popup-closed-by-user') {
    showStatus(
      'Sign-in cancelled. Google Slides export requires Drive access.',
      'error'
    );
  }
}
```

#### 3. "Unauthorized (401)"

**Cause**: Token expired or invalid

**Solution**:
```javascript
async function callAPI(url, options) {
  // Refresh token if needed
  if (currentUser) {
    currentToken = await currentUser.getIdToken(true); // Force refresh
  }

  const response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${currentToken}`
    }
  });

  if (response.status === 401) {
    // Token expired, re-authenticate
    showStatus('Session expired. Please sign in again.', 'error');
    await signOut(auth);
    return;
  }

  return response;
}
```

#### 4. "Network error"

**Cause**: API unreachable or CORS issue

**Solution**:
```javascript
try {
  const response = await fetch(API_URL + '/api/v1/export', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${currentToken}`
    },
    body: JSON.stringify(requestData)
  });
} catch (error) {
  if (error instanceof TypeError) {
    showStatus(
      'Network error. Please check your internet connection.',
      'error'
    );
  } else {
    showStatus(`Error: ${error.message}`, 'error');
  }
}
```

---

## Testing

### 1. Local Testing

**Test Firebase Auth**:
1. Load plugin in Figma
2. Click "Sign in with Google"
3. Verify popup appears
4. Sign in with test Google account
5. Verify UI updates with user email

**Test API Call**:
1. Select frames in Figma
2. Click "Export to Google Slides"
3. Check browser console for API request
4. Verify Authorization header includes token

### 2. Test with Mock API

For development without hitting the real API:

```javascript
// Mock API for testing
const MOCK_MODE = true;

async function createExportJob(frames) {
  if (MOCK_MODE) {
    showStatus('Creating export job... (mock)', 'info');

    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Simulate success
    handleExportSuccess({
      slides_url: 'https://docs.google.com/presentation/d/mock-id/pub',
      status: 'completed'
    });

    return;
  }

  // Real API call
  // ...
}
```

### 3. Test Error Scenarios

**Test token expiration**:
```javascript
// Manually expire token by waiting 1 hour, then try export
// Should re-authenticate user
```

**Test popup blocker**:
```javascript
// Disable popup permissions in browser
// Should show helpful error message
```

**Test network failure**:
```javascript
// Use browser DevTools to throttle network to offline
// Should show network error message
```

---

## Security Best Practices

### 1. Never Store Tokens Persistently

❌ **Don't do this**:
```javascript
// BAD: Don't store in localStorage
localStorage.setItem('firebase_token', currentToken);
```

✅ **Do this instead**:
```javascript
// GOOD: Store only in memory
let currentToken = null;

// Firebase will handle session persistence automatically
```

### 2. Don't Log Tokens

❌ **Don't do this**:
```javascript
console.log('Token:', currentToken);
```

✅ **Do this instead**:
```javascript
console.log('Token obtained:', currentToken ? 'Yes' : 'No');
```

### 3. Validate User State

✅ **Always check authentication before API calls**:
```javascript
async function callAPI() {
  if (!currentUser || !currentToken) {
    throw new Error('User not authenticated');
  }

  // Proceed with API call
}
```

### 4. Handle Token Refresh

✅ **Refresh tokens before they expire**:
```javascript
// Firebase ID tokens expire after 1 hour
// Get fresh token for each API call
async function getFreshToken() {
  if (!currentUser) return null;

  // Force refresh if needed
  return await currentUser.getIdToken(true);
}
```

---

## Troubleshooting

### Plugin not loading?

**Check**:
1. Firebase SDK imported correctly (check browser console for errors)
2. Network permissions in `manifest.json` include Firebase domains
3. Browser allows third-party cookies (required for Firebase Auth)

### Sign-in popup not appearing?

**Check**:
1. Browser popup blocker settings
2. Third-party cookies enabled
3. Firebase config correct (check `authDomain`)

### API returns 401 Unauthorized?

**Check**:
1. Token included in `Authorization: Bearer <token>` header
2. Token not expired (Firebase tokens expire after 1 hour)
3. User has granted required OAuth scopes
4. Firebase project ID matches API configuration

### Export fails with "Drive storage quota exceeded"?

**This is expected for service accounts**. Make sure:
1. User is signed in (not using service account)
2. Token is passed to API correctly
3. API is using user credentials (not service account)

### User sees "App not verified" warning?

**This is normal during development**. To resolve:
1. Keep app in "Testing" mode (100 users max)
2. Add test users in Firebase Console → Authentication → Settings
3. For production: Submit OAuth consent screen for verification (takes 1-2 weeks)

---

## Example: Complete Integration

**File**: `plugin.html` (complete example)

```html
<!DOCTYPE html>
<html>
<head>
  <style>
    body {
      font-family: 'Inter', sans-serif;
      padding: 20px;
      background: #f5f5f5;
    }
    button {
      width: 100%;
      padding: 12px;
      margin: 8px 0;
      border: none;
      border-radius: 6px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }
    .primary {
      background: #1a73e8;
      color: white;
    }
    .primary:hover {
      background: #1557b0;
    }
    .secondary {
      background: #e8f0fe;
      color: #1a73e8;
    }
    .status {
      padding: 12px;
      margin: 12px 0;
      border-radius: 6px;
      font-size: 13px;
    }
    .status.info {
      background: #e8f0fe;
      color: #1a73e8;
    }
    .status.success {
      background: #e6f4ea;
      color: #137333;
    }
    .status.error {
      background: #fce8e6;
      color: #c5221f;
    }
    .user-info {
      padding: 12px;
      background: white;
      border-radius: 6px;
      margin: 12px 0;
    }
    a {
      color: #1a73e8;
      text-decoration: none;
    }
    a:hover {
      text-decoration: underline;
    }
  </style>

  <script type="module">
    import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js';
    import { getAuth, signInWithPopup, signOut, GoogleAuthProvider }
      from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js';

    // Firebase config (replace with your config)
    const firebaseConfig = {
      apiKey: "YOUR_API_KEY",
      authDomain: "svg2ooxml.firebaseapp.com",
      projectId: "svg2ooxml"
    };

    const app = initializeApp(firebaseConfig);
    const auth = getAuth(app);
    window.firebaseAuth = auth;
    window.GoogleAuthProvider = GoogleAuthProvider;
    window.signInWithPopup = signInWithPopup;
    window.signOut = signOut;
  </script>
</head>
<body>
  <h2>Export to Google Slides</h2>

  <div id="auth-section">
    <button id="sign-in-btn" class="primary">Sign in with Google</button>
    <div id="user-info" class="user-info" style="display: none;">
      <div>✓ Signed in as <strong id="user-email"></strong></div>
      <button id="sign-out-btn" class="secondary">Sign out</button>
    </div>
  </div>

  <div id="export-section" style="display: none;">
    <button id="export-btn" class="primary">Export Selected Frames</button>
  </div>

  <div id="status" class="status" style="display: none;"></div>

  <script>
    // ... (use the ui.js code from earlier sections)
  </script>
</body>
</html>
```

---

## Next Steps

After integrating Firebase Auth:

1. **Test thoroughly** with multiple Google accounts
2. **Handle edge cases** (token expiration, network errors, etc.)
3. **Add analytics** to track sign-in success rate
4. **Monitor errors** in Firebase Console
5. **Submit for verification** when ready for public launch

---

## Resources

- [Firebase Authentication Docs](https://firebase.google.com/docs/auth)
- [Google OAuth 2.0 Scopes](https://developers.google.com/identity/protocols/oauth2/scopes)
- [Figma Plugin API](https://www.figma.com/plugin-docs/)
- [svg2ooxml API Documentation](../api/README.md) *(TODO: Create this)*

---

## Support

If you encounter issues:

1. Check browser console for errors
2. Verify Firebase config is correct
3. Check that API URL is reachable
4. Review this guide's troubleshooting section
5. Contact backend team for API issues

---

**Last Updated**: 2025-11-02
**Version**: 1.0.0
