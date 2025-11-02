# Browser-Compatible Figma Plugin OAuth Flow

## Overview

**Problem**: Current Figma plugin only works in Desktop app because it uses Firebase Auth popup directly from the plugin iframe, which requires `networkAccess` permissions unavailable in browser.

**Solution**: Implement OAuth flow through an external website window that works in both Desktop and Browser versions of Figma.

**Status**: Proposed
**Priority**: High
**Estimated Effort**: 4-6 hours

---

## Background

### Current Implementation (Desktop Only)

```
Figma Plugin (ui.html)
  ↓
Firebase signInWithPopup()
  ↓
Google OAuth popup
  ↓
Token returned to plugin
  ↓
API calls with token
```

**Limitation**: `signInWithPopup()` requires network access, only available in Desktop.

### How Other Plugins Do It

Popular Figma plugins (Tokens Studio, Anima, etc.) use this pattern:

```
Figma Plugin
  ↓
window.open("https://yoursite.com/auth")
  ↓
External website handles OAuth
  ↓
Token passed back via postMessage/polling
  ↓
Plugin uses token for API calls
```

**Benefits**:
- ✅ Works in browser and desktop
- ✅ No network permissions needed in plugin
- ✅ Better user experience (full-page OAuth)
- ✅ More secure (OAuth handled server-side)

---

## Technical Specification

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Figma Plugin                             │
│                                                                   │
│  1. User clicks "Sign in with Google"                           │
│  2. Plugin opens: window.open("/auth?key=XXX", "_blank")       │
│  3. Plugin polls: GET /auth/status?key=XXX                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│              Firebase Hosting Website                            │
│              (powerful-layout-467812-p1.web.app)                │
│                                                                   │
│  /auth Page:                                                     │
│  1. Initialize Firebase Auth                                     │
│  2. Trigger Google OAuth (signInWithPopup)                      │
│  3. Get Firebase ID token                                        │
│  4. Store token temporarily with key                             │
│  5. Show success message                                         │
│  6. Window closes automatically                                  │
│                                                                   │
│  /auth/status API:                                              │
│  1. Check if token available for key                            │
│  2. Return token if ready                                        │
│  3. Delete token after retrieval (single-use)                   │
└─────────────────────────────────────────────────────────────────┘
```

### Components

#### 1. OAuth Handler Page (`public/auth.html`)

**Purpose**: Full-page OAuth flow that works in new window

**Features**:
- Firebase Auth initialization
- Google OAuth sign-in
- Token storage with unique key
- Auto-close after success
- Error handling

**URL**: `https://powerful-layout-467812-p1.web.app/auth?key=<random-key>`

#### 2. Token Status API (`public/auth-status.html`)

**Purpose**: Endpoint for plugin to poll for token

**Features**:
- Check token availability by key
- Return token once available
- Single-use tokens (deleted after retrieval)
- Expiration (5 minute timeout)

**URL**: `https://powerful-layout-467812-p1.web.app/auth/status?key=<random-key>`

#### 3. Token Storage (Firebase Realtime Database)

**Purpose**: Temporary token storage between OAuth window and plugin

**Schema**:
```json
{
  "auth-tokens": {
    "<random-key>": {
      "token": "eyJhbG...",
      "email": "user@example.com",
      "timestamp": 1730556789000,
      "expires": 1730557089000
    }
  }
}
```

**Rules**:
- Tokens expire after 5 minutes
- Single read (deleted after retrieval)
- Public write, authenticated read

#### 4. Updated Plugin UI (`figma-plugin/ui.html` & `ui.js`)

**Changes**:
- Replace `signInWithPopup()` with `window.open()`
- Add polling mechanism for token
- Handle window close detection
- Fallback to Desktop flow if needed

---

## Implementation Plan

### Phase 1: Firebase Realtime Database Setup

**Tasks**:
1. Enable Firebase Realtime Database in project
2. Configure security rules for token storage
3. Test read/write from browser

**Deliverables**:
- Database enabled
- Security rules deployed
- Test script validates access

**Time**: 1 hour

### Phase 2: OAuth Handler Page

**Tasks**:
1. Create `public/auth.html` with Firebase Auth
2. Implement OAuth flow with token storage
3. Add success/error UI
4. Test in browser window

**Deliverables**:
- `public/auth.html` - OAuth page
- `public/auth.js` - OAuth logic
- Visual feedback for user

**Time**: 2 hours

### Phase 3: Token Status Endpoint

**Tasks**:
1. Create `public/auth-status.html` as simple API
2. Implement token retrieval logic
3. Add CORS headers
4. Test polling from browser

**Deliverables**:
- `public/auth-status.html` - Status endpoint
- Token cleanup after retrieval
- Error responses for missing tokens

**Time**: 1 hour

### Phase 4: Plugin Integration

**Tasks**:
1. Update `figma-plugin/ui.js` with new auth flow
2. Add polling mechanism
3. Add timeout handling
4. Keep backward compatibility with Desktop

**Deliverables**:
- Updated `ui.js` with window.open() flow
- Polling with visual feedback
- Works in browser and desktop

**Time**: 2 hours

### Phase 5: Testing & Documentation

**Tasks**:
1. Test in Figma Browser
2. Test in Figma Desktop
3. Test error scenarios
4. Update documentation

**Deliverables**:
- Tested in both environments
- Updated README
- Added troubleshooting guide

**Time**: 1 hour

---

## Detailed API Specifications

### POST /auth (Page)

**Request**:
```
GET /auth?key=abc123xyz&redirect=plugin
```

**Parameters**:
- `key` (required): Unique random key for this auth session
- `redirect` (optional): Where to redirect after auth (default: auto-close)

**Response**:
Full HTML page with:
- Firebase Auth initialization
- Google OAuth button
- Loading states
- Success/error messages
- Auto-close script

**Success Flow**:
1. Page loads and shows "Sign in with Google" button
2. User clicks button → Google OAuth popup
3. User authorizes
4. Token stored in database with key
5. Success message: "✓ Signed in! You can close this window"
6. Window auto-closes after 2 seconds

**Error Flow**:
1. OAuth error occurs
2. Error message shown
3. User can retry or close window

### GET /auth/status

**Request**:
```
GET /auth/status?key=abc123xyz
```

**Parameters**:
- `key` (required): Auth session key

**Response (Token Ready)**:
```json
{
  "status": "ready",
  "token": "eyJhbGciOiJSUzI1...",
  "email": "user@example.com"
}
```

**Response (Pending)**:
```json
{
  "status": "pending"
}
```

**Response (Expired)**:
```json
{
  "status": "expired",
  "error": "Auth session expired after 5 minutes"
}
```

**Response (Not Found)**:
```json
{
  "status": "not_found",
  "error": "Invalid or already used auth key"
}
```

**Behavior**:
- Token is deleted after first successful retrieval (single-use)
- Tokens expire after 5 minutes
- Returns CORS headers to allow plugin access

---

## Security Considerations

### Token Storage

**Risk**: Temporary tokens stored in database could be accessed

**Mitigation**:
- Tokens expire after 5 minutes
- Single-use (deleted after retrieval)
- Random, unguessable keys (128-bit entropy)
- Firebase security rules restrict access

### CORS

**Risk**: Status endpoint must allow cross-origin requests

**Mitigation**:
- Only status endpoint allows CORS
- Token retrieval requires exact key match
- Rate limiting via Firebase rules

### Key Generation

**Risk**: Predictable keys could be guessed

**Mitigation**:
```javascript
// Generate cryptographically secure random key
function generateAuthKey() {
  const array = new Uint8Array(16);
  crypto.getRandomValues(array);
  return Array.from(array, byte =>
    byte.toString(16).padStart(2, '0')
  ).join('');
}
```

### Database Security Rules

```json
{
  "rules": {
    "auth-tokens": {
      "$key": {
        ".read": true,
        ".write": true,
        ".validate": "newData.hasChildren(['token', 'email', 'timestamp', 'expires'])",
        ".indexOn": ["expires"]
      }
    }
  }
}
```

---

## Alternative Approaches Considered

### Alternative 1: postMessage

**Approach**: OAuth window uses `window.opener.postMessage()` to send token back

**Pros**:
- No database needed
- Instant token delivery
- Simpler implementation

**Cons**:
- ❌ Doesn't work reliably in Figma iframe context
- ❌ Browser security restrictions on null origin iframes
- ❌ postMessage blocked in some browsers

**Decision**: Not chosen due to iframe restrictions

### Alternative 2: Service Worker

**Approach**: Use service worker to handle OAuth redirect

**Pros**:
- No external window needed
- Seamless user experience

**Cons**:
- ❌ Figma plugins can't register service workers
- ❌ Complex implementation
- ❌ Browser compatibility issues

**Decision**: Not technically feasible in Figma plugins

### Alternative 3: Keep Desktop-Only

**Approach**: Don't implement browser support, require Desktop app

**Pros**:
- No changes needed
- Current implementation works

**Cons**:
- ❌ Excludes browser users (large user base)
- ❌ Competitive disadvantage vs other plugins
- ❌ Worse user experience

**Decision**: Not chosen - browser support is valuable

---

## Testing Strategy

### Unit Tests

**OAuth Page**:
- ✅ Firebase initializes correctly
- ✅ Google OAuth triggers
- ✅ Token stored with correct key
- ✅ Window closes after success
- ✅ Errors handled gracefully

**Status Endpoint**:
- ✅ Returns pending before token ready
- ✅ Returns token when available
- ✅ Deletes token after retrieval
- ✅ Returns expired after 5 minutes
- ✅ Handles missing keys

**Plugin Integration**:
- ✅ Opens auth window correctly
- ✅ Polls status endpoint
- ✅ Receives and stores token
- ✅ Handles timeout
- ✅ Handles window close

### Integration Tests

**Browser Flow**:
1. Open plugin in Figma Browser
2. Click "Sign in with Google"
3. Auth window opens
4. Complete OAuth
5. Window closes
6. Plugin shows signed-in state
7. Export works with token

**Desktop Flow**:
1. Open plugin in Figma Desktop
2. Same flow as browser
3. Verify works identically

### Edge Cases

- User closes auth window before completing
- Network error during OAuth
- Token expires before retrieval
- Multiple auth attempts simultaneously
- Browser blocks popups

---

## Rollout Plan

### Phase 1: Beta Testing (Week 1)

- Deploy OAuth pages to Firebase Hosting
- Enable for test users only
- Collect feedback
- Monitor error rates

### Phase 2: Gradual Rollout (Week 2)

- Enable for 10% of users
- Monitor metrics
- Fix any issues
- Increase to 50%

### Phase 3: Full Release (Week 3)

- Enable for 100% of users
- Update documentation
- Announce browser support
- Monitor user feedback

---

## Success Metrics

**Adoption**:
- % of users on browser vs desktop
- Sign-in success rate (browser vs desktop)
- Time to complete auth flow

**Performance**:
- Average polling time to get token
- Auth success rate
- Error rate by type

**User Experience**:
- Reduced support tickets about Desktop requirement
- Positive feedback on browser support
- Plugin rating improvement

**Target Goals**:
- 95% auth success rate in browser
- <5 second average auth flow
- <1% error rate

---

## Documentation Updates

### User Documentation

**Update**:
- `figma-plugin/README.md` - Add browser support note
- `figma-plugin/QUICKSTART.md` - Update installation steps
- Add browser-specific troubleshooting

**New Content**:
- "Using the plugin in browser" section
- Comparison table: Browser vs Desktop features
- FAQ about OAuth window

### Developer Documentation

**Update**:
- `docs/guides/figma-plugin-firebase-auth.md` - Add new flow
- Architecture diagrams showing both flows

**New Content**:
- OAuth flow implementation guide
- Token storage security considerations
- Testing browser vs desktop

---

## Dependencies

**Required**:
- Firebase Realtime Database (new)
- Firebase Hosting (existing)
- Firebase Authentication (existing)

**Optional**:
- Analytics to track auth flow metrics
- Error monitoring (Sentry, etc.)

---

## Risks & Mitigation

### Risk 1: Database Costs

**Risk**: Realtime Database usage could incur costs with many users

**Mitigation**:
- Tokens deleted immediately after use
- 5-minute expiration
- Firebase Spark plan includes 1GB storage free
- Monitor usage in Firebase Console

**Estimated Cost**: $0 for <10k monthly active users

### Risk 2: Browser Popup Blockers

**Risk**: Users' browsers may block the auth window

**Mitigation**:
- Detect popup blocked
- Show clear instructions to allow popups
- Fallback message with manual link
- Test in all major browsers

### Risk 3: Token Security

**Risk**: Tokens temporarily stored in database could be accessed

**Mitigation**:
- 5-minute expiration
- Single-use tokens
- Cryptographically secure keys
- Firebase security rules
- Regular security audits

### Risk 4: Backward Compatibility

**Risk**: Changes could break existing Desktop users

**Mitigation**:
- Keep both flows working
- Auto-detect environment
- Gradual rollout
- Comprehensive testing
- Easy rollback plan

---

## Future Enhancements

### Phase 2 Features

1. **Remember Device**: Store encrypted token locally (opt-in)
2. **Token Refresh**: Automatic token refresh before expiration
3. **Multi-Account**: Support multiple Google accounts
4. **Offline Mode**: Cache last successful auth for offline use

### Phase 3 Features

1. **Analytics**: Track auth funnel (start → success)
2. **A/B Testing**: Test different OAuth UX flows
3. **SSO Support**: Enterprise single sign-on
4. **Biometric Auth**: Touch ID / Face ID on supported devices

---

## Appendix

### Code Examples

#### Generate Auth Key
```javascript
function generateAuthKey() {
  const array = new Uint8Array(16);
  crypto.getRandomValues(array);
  return Array.from(array, byte =>
    byte.toString(16).padStart(2, '0')
  ).join('');
}
```

#### Poll for Token
```javascript
async function pollForToken(key, maxAttempts = 60) {
  for (let i = 0; i < maxAttempts; i++) {
    const response = await fetch(
      `https://powerful-layout-467812-p1.web.app/auth/status?key=${key}`
    );
    const data = await response.json();

    if (data.status === 'ready') {
      return data.token;
    }

    if (data.status === 'expired') {
      throw new Error('Auth session expired');
    }

    await sleep(2000); // Poll every 2 seconds
  }

  throw new Error('Auth timeout');
}
```

### Firebase Security Rules
```json
{
  "rules": {
    "auth-tokens": {
      "$key": {
        ".read": true,
        ".write": true,
        ".validate": "newData.hasChildren(['token', 'email', 'timestamp', 'expires']) && newData.child('expires').val() <= now + 300000",
        ".indexOn": ["expires"]
      }
    }
  }
}
```

---

**Last Updated**: 2025-11-02
**Author**: Claude Code
**Status**: Ready for Implementation
