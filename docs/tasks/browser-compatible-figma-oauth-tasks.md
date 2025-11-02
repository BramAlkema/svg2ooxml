# Browser-Compatible Figma OAuth Flow - Implementation Tasks

**Spec**: `docs/specs/browser-compatible-figma-oauth.md`
**Status**: Not Started
**Estimated Time**: 4-6 hours
**Priority**: High

---

## Task Overview

Implement OAuth flow through external website window to enable Figma plugin to work in both browser and desktop versions.

---

## Phase 1: Firebase Realtime Database Setup

**Estimated Time**: 1 hour

### Task 1.1: Enable Firebase Realtime Database
- [ ] Go to Firebase Console: https://console.firebase.google.com/project/powerful-layout-467812-p1/database
- [ ] Enable Realtime Database
- [ ] Choose location: `europe-west1`
- [ ] Start in production mode (will add rules next)
- [ ] Verify database URL: `https://powerful-layout-467812-p1-default-rtdb.europe-west1.firebasedatabase.app`

**Acceptance Criteria**:
- Database shows as enabled in Firebase Console
- Database URL is accessible
- Can write test data via Console

**Dependencies**: None

---

### Task 1.2: Configure Database Security Rules
- [ ] Create security rules file: `database.rules.json`
- [ ] Define rules for `auth-tokens` path:
  - Allow public read/write
  - Validate required fields (token, email, timestamp, expires)
  - Ensure expires <= now + 5 minutes
  - Index on expires field
- [ ] Deploy rules via Firebase CLI or Console
- [ ] Test rules with sample data

**Acceptance Criteria**:
- Rules file created and documented
- Rules deployed successfully
- Test write succeeds
- Test read succeeds
- Invalid data rejected

**Dependencies**: Task 1.1

**Files**:
- `database.rules.json` (new)

---

### Task 1.3: Test Database Access from Browser
- [ ] Create test HTML page with Firebase SDK
- [ ] Initialize Realtime Database
- [ ] Test writing token data
- [ ] Test reading token data
- [ ] Test deleting token data
- [ ] Verify 5-minute expiration logic
- [ ] Test CORS access

**Acceptance Criteria**:
- Can write to database from browser
- Can read from database
- Can delete after read
- Expired tokens not returned
- CORS works correctly

**Dependencies**: Task 1.2

**Files**:
- `public/test-db.html` (temporary test file)

---

## Phase 2: OAuth Handler Page

**Estimated Time**: 2 hours

### Task 2.1: Create OAuth Page HTML Structure
- [ ] Create `public/auth.html`
- [ ] Add Firebase SDK imports (Auth + Database)
- [ ] Create UI layout:
  - Header with logo
  - "Sign in with Google" button
  - Loading spinner
  - Success message
  - Error message area
- [ ] Add responsive CSS styling
- [ ] Match branding from main website

**Acceptance Criteria**:
- HTML page loads correctly
- UI is responsive
- Styling matches main site
- All states visible (loading, success, error)

**Dependencies**: None

**Files**:
- `public/auth.html` (new)

---

### Task 2.2: Implement OAuth Logic
- [ ] Create `public/auth.js`
- [ ] Parse URL parameters (key)
- [ ] Initialize Firebase Auth
- [ ] Initialize Realtime Database
- [ ] Implement Google OAuth sign-in:
  - Create GoogleAuthProvider
  - Add Drive and Slides scopes
  - Call signInWithPopup()
  - Handle success
  - Handle errors
- [ ] Get Firebase ID token after sign-in
- [ ] Store token in database with key

**Acceptance Criteria**:
- OAuth popup appears on button click
- User can sign in with Google
- Token retrieved successfully
- Token stored in database with correct key
- Error handling works

**Dependencies**: Task 2.1, Task 1.2

**Files**:
- `public/auth.js` (new)

**Code Structure**:
```javascript
// Parse URL params
const urlParams = new URLSearchParams(window.location.search);
const authKey = urlParams.get('key');

// Initialize Firebase
const firebaseConfig = { ... };
firebase.initializeApp(firebaseConfig);
const auth = firebase.auth();
const db = firebase.database();

// OAuth flow
async function signInWithGoogle() {
  const provider = new firebase.auth.GoogleAuthProvider();
  provider.addScope('https://www.googleapis.com/auth/drive.file');
  provider.addScope('https://www.googleapis.com/auth/presentations');

  const result = await auth.signInWithPopup(provider);
  const token = await result.user.getIdToken();

  // Store in database
  await db.ref(`auth-tokens/${authKey}`).set({
    token: token,
    email: result.user.email,
    timestamp: Date.now(),
    expires: Date.now() + 300000 // 5 minutes
  });
}
```

---

### Task 2.3: Add UI State Management
- [ ] Show loading state during OAuth
- [ ] Show success state after token stored
- [ ] Show error state on failure
- [ ] Add auto-close after success (2 second delay)
- [ ] Add manual close button
- [ ] Update button states (disabled during loading)

**Acceptance Criteria**:
- Loading spinner shows during OAuth
- Success message shows after completion
- Error messages clear and helpful
- Window auto-closes after success
- User can manually close window

**Dependencies**: Task 2.2

**Files**:
- `public/auth.js` (update)

---

### Task 2.4: Test OAuth Page End-to-End
- [ ] Open `/auth?key=test123` in browser
- [ ] Click "Sign in with Google"
- [ ] Complete OAuth flow
- [ ] Verify token stored in database
- [ ] Verify success message shows
- [ ] Verify window auto-closes
- [ ] Test error scenarios:
  - User cancels OAuth
  - Network error
  - Invalid key parameter
  - Database write failure

**Acceptance Criteria**:
- OAuth flow completes successfully
- Token appears in database
- Success UI shows
- Window closes automatically
- All error scenarios handled gracefully

**Dependencies**: Task 2.3

---

## Phase 3: Token Status Endpoint

**Estimated Time**: 1 hour

### Task 3.1: Create Status Endpoint Page
- [ ] Create `public/auth-status.html`
- [ ] Add minimal HTML structure (no UI needed)
- [ ] Add Firebase SDK (Database only)
- [ ] Add CORS headers meta tag
- [ ] Style as JSON API response page

**Acceptance Criteria**:
- Page loads and returns JSON
- CORS headers present
- No visible UI (API only)

**Dependencies**: None

**Files**:
- `public/auth-status.html` (new)

---

### Task 3.2: Implement Token Retrieval Logic
- [ ] Create `public/auth-status.js`
- [ ] Parse URL parameter (key)
- [ ] Initialize Realtime Database
- [ ] Query for token by key
- [ ] Check if token exists
- [ ] Check if token expired
- [ ] Return appropriate JSON response:
  - `status: "ready"` + token + email
  - `status: "pending"`
  - `status: "expired"`
  - `status: "not_found"`
- [ ] Delete token after successful retrieval (single-use)

**Acceptance Criteria**:
- Returns correct status for each scenario
- Token deleted after first read
- Expired tokens not returned
- JSON response properly formatted
- CORS allows cross-origin access

**Dependencies**: Task 3.1, Task 1.2

**Files**:
- `public/auth-status.js` (new)

**Code Structure**:
```javascript
const urlParams = new URLSearchParams(window.location.search);
const authKey = urlParams.get('key');

firebase.initializeApp(firebaseConfig);
const db = firebase.database();

async function checkTokenStatus() {
  const snapshot = await db.ref(`auth-tokens/${authKey}`).once('value');

  if (!snapshot.exists()) {
    return { status: 'not_found' };
  }

  const data = snapshot.val();
  const now = Date.now();

  if (data.expires < now) {
    await db.ref(`auth-tokens/${authKey}`).remove();
    return { status: 'expired' };
  }

  // Delete token (single-use)
  await db.ref(`auth-tokens/${authKey}`).remove();

  return {
    status: 'ready',
    token: data.token,
    email: data.email
  };
}
```

---

### Task 3.3: Test Status Endpoint
- [ ] Store test token in database
- [ ] Call `/auth/status?key=test123`
- [ ] Verify returns "ready" with token
- [ ] Verify token deleted from database
- [ ] Call again with same key → "not_found"
- [ ] Test expired token scenario
- [ ] Test missing key scenario
- [ ] Test CORS from different origin

**Acceptance Criteria**:
- Returns token on first call
- Returns not_found on second call
- Handles expired tokens correctly
- Handles missing keys correctly
- CORS works from plugin origin

**Dependencies**: Task 3.2

---

## Phase 4: Plugin Integration

**Estimated Time**: 2 hours

### Task 4.1: Add Browser Detection
- [ ] Update `figma-plugin/ui.js`
- [ ] Add function to detect if running in browser vs desktop
- [ ] Check for `networkAccess` availability
- [ ] Set flag for which auth flow to use

**Acceptance Criteria**:
- Correctly detects browser environment
- Correctly detects desktop environment
- Flag set appropriately

**Dependencies**: None

**Files**:
- `figma-plugin/ui.js` (update)

**Code Structure**:
```javascript
function isFigmaBrowser() {
  // Check if network access is available
  // Desktop has networkAccess, browser doesn't
  return !('networkAccess' in figma.manifest);
}

const useBrowserFlow = isFigmaBrowser();
```

---

### Task 4.2: Implement window.open() Auth Flow
- [ ] Add `generateAuthKey()` function (crypto.getRandomValues)
- [ ] Add `openAuthWindow()` function:
  - Generate random key
  - Open window to `/auth?key=<key>`
  - Store window reference
  - Return key
- [ ] Add window close detection
- [ ] Add timeout handling (5 minutes)

**Acceptance Criteria**:
- Generates secure random keys
- Opens auth window correctly
- Detects when window closes
- Handles timeout appropriately

**Dependencies**: Task 4.1

**Files**:
- `figma-plugin/ui.js` (update)

**Code Structure**:
```javascript
function generateAuthKey() {
  const array = new Uint8Array(16);
  crypto.getRandomValues(array);
  return Array.from(array, byte =>
    byte.toString(16).padStart(2, '0')
  ).join('');
}

function openAuthWindow(key) {
  const url = `https://powerful-layout-467812-p1.web.app/auth?key=${key}`;
  const authWindow = window.open(url, '_blank', 'width=500,height=600');
  return authWindow;
}
```

---

### Task 4.3: Implement Token Polling
- [ ] Add `pollForToken(key)` function
- [ ] Poll every 2 seconds
- [ ] Maximum 60 attempts (2 minutes timeout)
- [ ] Parse JSON response
- [ ] Handle different status responses:
  - "ready" → return token
  - "pending" → continue polling
  - "expired" → throw error
  - "not_found" → throw error
- [ ] Show progress in UI
- [ ] Update progress bar during polling

**Acceptance Criteria**:
- Polls every 2 seconds
- Stops when token received
- Stops on timeout
- Shows progress to user
- Handles all error scenarios

**Dependencies**: Task 4.2

**Files**:
- `figma-plugin/ui.js` (update)

**Code Structure**:
```javascript
async function pollForToken(key, maxAttempts = 60) {
  for (let i = 0; i < maxAttempts; i++) {
    showStatus(`Waiting for authentication... (${i + 1}/${maxAttempts})`, 'info');

    const response = await fetch(
      `https://powerful-layout-467812-p1.web.app/auth/status?key=${key}`
    );
    const data = await response.json();

    if (data.status === 'ready') {
      return { token: data.token, email: data.email };
    }

    if (data.status === 'expired' || data.status === 'not_found') {
      throw new Error('Authentication failed or expired');
    }

    await sleep(2000);
  }

  throw new Error('Authentication timeout');
}
```

---

### Task 4.4: Update Sign-In Handler
- [ ] Modify `signInBtn` click handler
- [ ] Check if browser or desktop flow
- [ ] Browser flow:
  - Generate auth key
  - Open auth window
  - Poll for token
  - Store token and user info
  - Update UI
- [ ] Desktop flow:
  - Keep existing Firebase popup flow
  - No changes needed
- [ ] Add error handling for both flows
- [ ] Add user feedback messages

**Acceptance Criteria**:
- Browser flow works end-to-end
- Desktop flow still works
- Correct flow chosen based on environment
- User sees clear progress messages
- Errors handled gracefully

**Dependencies**: Task 4.3

**Files**:
- `figma-plugin/ui.js` (update)

**Code Structure**:
```javascript
signInBtn.addEventListener('click', async () => {
  try {
    if (useBrowserFlow) {
      // New browser-compatible flow
      showStatus('Opening sign-in window...', 'info');

      const authKey = generateAuthKey();
      const authWindow = openAuthWindow(authKey);

      showStatus('Complete sign-in in the popup window...', 'info');

      const result = await pollForToken(authKey);

      currentToken = result.token;
      currentUser = { email: result.email };

      updateUIForSignedInUser();
      showStatus('Signed in successfully!', 'success');

    } else {
      // Existing desktop flow with Firebase popup
      const provider = new window.GoogleAuthProvider();
      provider.addScope('https://www.googleapis.com/auth/drive.file');
      provider.addScope('https://www.googleapis.com/auth/presentations');

      const result = await window.signInWithPopup(window.firebaseAuth, provider);
      currentUser = result.user;
      currentToken = await result.user.getIdToken();

      updateUIForSignedInUser();
      showStatus('Signed in successfully!', 'success');
    }
  } catch (error) {
    console.error('Sign-in error:', error);
    showStatus(`Sign-in failed: ${error.message}`, 'error');
  }
});
```

---

### Task 4.5: Update Plugin Manifest
- [ ] Review `figma-plugin/manifest.json`
- [ ] Ensure `networkAccess` still present for desktop
- [ ] Add comments explaining dual-mode support
- [ ] Update plugin description/version if needed

**Acceptance Criteria**:
- Manifest supports both modes
- Network access preserved for desktop
- Documentation clear

**Dependencies**: None

**Files**:
- `figma-plugin/manifest.json` (update)

---

### Task 4.6: Test Plugin in Both Environments
- [ ] Test in Figma Browser:
  - Load plugin
  - Click sign in
  - Complete OAuth in popup
  - Verify signed in
  - Test export functionality
- [ ] Test in Figma Desktop:
  - Load plugin
  - Click sign in
  - Complete OAuth (should use desktop flow)
  - Verify signed in
  - Test export functionality
- [ ] Test error scenarios:
  - User closes auth window early
  - Network timeout
  - Popup blocked
  - Invalid token

**Acceptance Criteria**:
- Plugin works in browser
- Plugin works in desktop
- Both flows tested successfully
- Exports work in both environments
- All error scenarios handled

**Dependencies**: Task 4.4

---

## Phase 5: Testing & Documentation

**Estimated Time**: 1 hour

### Task 5.1: Cross-Browser Testing
- [ ] Test in Chrome (browser + desktop)
- [ ] Test in Firefox (browser + desktop)
- [ ] Test in Safari (browser + desktop)
- [ ] Test in Edge (browser + desktop)
- [ ] Document any browser-specific issues
- [ ] Add browser compatibility notes

**Acceptance Criteria**:
- Works in all major browsers
- Browser-specific issues documented
- Workarounds implemented if needed

**Dependencies**: Task 4.6

---

### Task 5.2: Update Plugin Documentation
- [ ] Update `figma-plugin/README.md`:
  - Add "Browser Support" section
  - Explain both auth flows
  - Update requirements (remove "Desktop only")
- [ ] Update `figma-plugin/QUICKSTART.md`:
  - Remove desktop-only warnings
  - Add browser-specific instructions
  - Update troubleshooting
- [ ] Update `docs/guides/figma-plugin-firebase-auth.md`:
  - Add browser auth flow documentation
  - Add architecture diagrams
  - Add code examples

**Acceptance Criteria**:
- All documentation updated
- Browser support clearly documented
- Troubleshooting covers both modes
- Examples provided for both flows

**Dependencies**: Task 5.1

**Files**:
- `figma-plugin/README.md` (update)
- `figma-plugin/QUICKSTART.md` (update)
- `docs/guides/figma-plugin-firebase-auth.md` (update)

---

### Task 5.3: Create Migration Guide
- [ ] Create `docs/guides/browser-auth-migration.md`
- [ ] Document changes for existing users
- [ ] Explain why browser now works
- [ ] List any breaking changes (none expected)
- [ ] Add rollback instructions if needed

**Acceptance Criteria**:
- Migration guide complete
- Covers user impact
- No breaking changes introduced
- Rollback plan documented

**Dependencies**: Task 5.2

**Files**:
- `docs/guides/browser-auth-migration.md` (new)

---

### Task 5.4: Deploy to Production
- [ ] Deploy Firebase Realtime Database rules
- [ ] Deploy website updates (`auth.html`, `auth-status.html`)
- [ ] Test deployed auth flow in browser
- [ ] Test deployed auth flow in desktop
- [ ] Monitor Firebase Console for errors
- [ ] Monitor database usage

**Acceptance Criteria**:
- Database rules deployed
- Website updates live
- Auth works in production
- No errors in Firebase Console
- Usage within expected limits

**Dependencies**: Task 5.3

**Deployment Commands**:
```bash
# Deploy database rules
firebase deploy --only database

# Deploy website
./scripts/update-website.sh

# Or manual:
gcloud builds submit --config=cloudbuild-hosting.yaml --region=europe-west1 --project=powerful-layout-467812-p1 .
```

---

### Task 5.5: User Acceptance Testing
- [ ] Add 5 test users
- [ ] Have users test in browser
- [ ] Have users test in desktop
- [ ] Collect feedback
- [ ] Fix any reported issues
- [ ] Document common issues/questions

**Acceptance Criteria**:
- 5 users tested successfully
- Feedback collected and reviewed
- Critical issues fixed
- Common questions documented

**Dependencies**: Task 5.4

---

## Success Criteria

**Overall Project Success**:
- [ ] Plugin loads in Figma Browser
- [ ] Plugin loads in Figma Desktop
- [ ] Browser auth flow works end-to-end
- [ ] Desktop auth flow still works
- [ ] Export to Slides works in both
- [ ] No breaking changes for existing users
- [ ] Documentation updated
- [ ] Tested in all major browsers
- [ ] Deployed to production
- [ ] Test users validated

**Performance Targets**:
- [ ] Auth completion < 10 seconds (browser)
- [ ] Auth completion < 5 seconds (desktop)
- [ ] 95%+ success rate in both modes
- [ ] Token polling < 5 seconds average

**User Experience**:
- [ ] Clear progress messages
- [ ] Helpful error messages
- [ ] No confusion about which mode
- [ ] Smooth OAuth experience

---

## Risk Mitigation

### High Risk Items

**Risk**: Database costs exceed free tier
- **Mitigation**: Monitor usage daily during rollout
- **Task**: Add usage alert in Firebase Console
- **Owner**: Ops team

**Risk**: Browser popup blockers prevent auth
- **Mitigation**: Detect and show clear instructions
- **Task**: Add popup-blocked detection (Task 4.4)
- **Owner**: Development team

**Risk**: Token security vulnerability
- **Mitigation**: Regular security reviews
- **Task**: Schedule security audit after launch
- **Owner**: Security team

---

## Rollback Plan

If issues arise after deployment:

1. **Immediate Rollback** (< 1 hour):
   - Revert plugin to previous version
   - Keep database and website changes (no harm)
   - Users on desktop continue working

2. **Partial Rollback** (if only browser broken):
   - Add feature flag to disable browser flow
   - Desktop users unaffected
   - Fix browser issues

3. **Database Cleanup** (if needed):
   - Delete all tokens: `firebase database:remove /auth-tokens`
   - Disable database rules
   - No impact on existing functionality

---

## Post-Launch Tasks

After successful deployment:

- [ ] Monitor error rates for 1 week
- [ ] Analyze auth success rates (browser vs desktop)
- [ ] Review user feedback/support tickets
- [ ] Optimize polling interval based on metrics
- [ ] Consider adding analytics events
- [ ] Plan Phase 2 features (token refresh, remember device)

---

## Resources

**Documentation**:
- Spec: `docs/specs/browser-compatible-figma-oauth.md`
- Figma OAuth Guide: https://www.figma.com/plugin-docs/oauth-with-plugins/
- Firebase Realtime Database: https://firebase.google.com/docs/database

**Tools**:
- Firebase Console: https://console.firebase.google.com/project/powerful-layout-467812-p1
- Database: https://console.firebase.google.com/project/powerful-layout-467812-p1/database
- Hosting: https://console.firebase.google.com/project/powerful-layout-467812-p1/hosting

**Testing**:
- Browser Test: Open Figma in Chrome at https://figma.com
- Desktop Test: Open Figma Desktop app

---

**Total Estimated Time**: 6-7 hours
**Priority**: High
**Complexity**: Medium
**Risk Level**: Low

**Ready to Start**: ✅
