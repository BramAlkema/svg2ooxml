# OAuth Flow Testing Guide

This guide explains how to test the browser-compatible OAuth flow for the Figma plugin.

## Quick Start

We've implemented a browser-compatible OAuth flow that works in both Figma Desktop and Figma Browser. The implementation includes test pages to verify functionality.

## Test Files

### 1. `testing/oauth/test_oauth_flow.html` - Complete OAuth Flow Test
**What it tests**: The complete end-user OAuth experience

**How to use**:
```bash
# Open in your browser
open testing/oauth/test_oauth_flow.html
```

**Steps**:
1. Click "Test OAuth Flow"
2. Sign in with Google in the popup window
3. Verify token is received and displayed

**What should happen**:
- Popup window opens to auth.html
- You complete Google sign-in
- Popup closes automatically
- Test page displays: ✅ Authentication successful
- Shows your email and token (truncated)

### 2. `testing/oauth/test_database_flow.html` - Database Operations Test
**What it tests**: Firebase Realtime Database token storage and retrieval

**How to use**:
```bash
# Open in your browser
open testing/oauth/test_database_flow.html
```

**Tests included**:

#### Test 1: Store Token
- Manually store a test token in the database
- Verifies write permissions work
- Shows stored data structure

#### Test 2: Check Token Status
- Query the auth-status endpoint
- Verifies token retrieval works
- Shows API response format

#### Test 3: End-to-End
- Complete flow: store token → retrieve token
- Verifies single-use pattern (token deleted after read)
- Confirms data integrity

## Testing in Figma

### Prerequisites
1. Add yourself as a test user in the OAuth consent screen:
   - Go to: https://console.cloud.google.com/auth/audience?project=powerful-layout-467812-p1
   - Add your Google email to test users list

2. Load the plugin in Figma:
   - Open Figma (Desktop or Browser)
   - Go to Plugins → Development → Import plugin from manifest
   - Select `figma-plugin/manifest.json`

### Test in Figma Browser
1. Open https://figma.com in your browser
2. Open any file or create a new one
3. Run the plugin: Plugins → Development → svg2ooxml
4. Click "Sign in with Google"
5. Complete OAuth in the popup window
6. Verify:
   - ✅ Popup closes automatically
   - ✅ Plugin shows "Signed in as [your-email]"
   - ✅ "Export Selected Frames" button is enabled

### Test in Figma Desktop
1. Open Figma Desktop app
2. Open any file
3. Run the plugin: Plugins → Development → svg2ooxml
4. Follow same steps as browser test
5. Verify same results

### Test Export Functionality
1. Create a frame in Figma (press 'F' and draw a rectangle)
2. Select the frame
3. Click "Export Selected Frames" in plugin
4. Wait for export to complete
5. Verify:
   - ✅ Progress bar shows completion
   - ✅ Success message with link to Google Slides
   - ✅ Slides document is created and accessible

## Expected Behaviors

### Sign In Flow
1. **Popup Opens**: External window opens to `auth.html`
2. **Google Consent**: Standard Google OAuth consent screen
3. **Token Storage**: Token stored in Firebase with 5-minute expiration
4. **Polling**: Plugin polls for token every 2 seconds
5. **Token Retrieval**: Plugin receives token and closes popup
6. **UI Update**: Plugin shows signed-in state

### Sign Out Flow
1. **Local Clear**: Clears token and email from plugin state
2. **UI Update**: Returns to sign-in state
3. **Note**: No server-side session to clear

### Token Expiration
- Auth keys expire after 5 minutes if unused
- Firebase ID tokens are valid for 1 hour
- Users need to sign in again after closing plugin

## Troubleshooting

### Popup Blocked
**Symptom**: "Popup blocked" error message

**Solution**:
- Allow popups for the domain
- Try clicking the plugin UI directly (some browsers require user gesture)

### Authentication Timeout
**Symptom**: "Authentication timeout after 2 minutes"

**Possible Causes**:
- User closed popup before completing sign-in
- Network issues preventing database access
- Database rules not deployed

**Check**:
```bash
# Verify database is accessible
curl "https://auth-tokens-db.europe-west1.firebasedatabase.app/.json"
```

### Token Not Found
**Symptom**: `{"status": "not_found"}` from auth-status endpoint

**Possible Causes**:
- Token already used (single-use pattern)
- Token expired (5-minute window)
- Invalid auth key

### CORS Errors
**Symptom**: CORS errors in browser console

**Solution**:
- Ensure you're accessing via proper domains
- Check Firebase Hosting configuration
- Verify `Access-Control-Allow-Origin` headers

## Manual Verification Commands

### Check Database Rules
```bash
curl "https://auth-tokens-db.europe-west1.firebasedatabase.app/.settings/rules.json?access_token=$(gcloud auth print-access-token)" | jq
```

### Store Test Token Manually
```bash
AUTH_KEY="test-$(date +%s)"
curl -X PUT "https://auth-tokens-db.europe-west1.firebasedatabase.app/auth-tokens/${AUTH_KEY}.json" \
  -d '{
    "token": "test-token-123",
    "email": "test@example.com",
    "timestamp": '$(date +%s000)',
    "expires": '$(($(date +%s000) + 300000))'
  }'
echo "Auth key: $AUTH_KEY"
```

### Check Token Status
```bash
# Replace with your auth key
AUTH_KEY="test-1234567890"
curl "https://powerful-layout-467812-p1.web.app/auth-status.html?key=${AUTH_KEY}"
```

### List All Tokens (Debug)
```bash
curl "https://auth-tokens-db.europe-west1.firebasedatabase.app/auth-tokens.json"
```

## Security Notes

### What's Safe
- ✅ Tokens expire after 5 minutes
- ✅ Single-use pattern (deleted after read)
- ✅ Cryptographically secure random keys (128-bit)
- ✅ Standard OAuth 2.0 flow
- ✅ Firebase ID tokens (1-hour validity)

### Known Limitations
- ⚠️ Database allows public read/write (necessary for client-side access)
- ⚠️ No rate limiting on database writes
- ⚠️ Polling creates multiple requests during auth

### Not a Security Issue
- Public Firebase API key (intended for client use)
- Visible auth keys in URLs (single-use + expiration)
- Database accessible via API (protected by validation rules)

## Success Criteria

All tests should pass:
- ✅ `testing/oauth/test_oauth_flow.html` successfully retrieves token
- ✅ `testing/oauth/test_database_flow.html` end-to-end test passes
- ✅ Figma Browser plugin can sign in and export
- ✅ Figma Desktop plugin can sign in and export
- ✅ Export creates Google Slides presentation
- ✅ Slides are editable in user's Drive

## Need Help?

### Documentation
- Specification: `docs/specs/browser-compatible-figma-oauth.md`
- Implementation Summary: `docs/browser-oauth-implementation-summary.md`
- Task Breakdown: `docs/tasks/browser-compatible-figma-oauth-tasks.md`

### Check Status
- Firebase Console: https://console.firebase.google.com/project/powerful-layout-467812-p1
- Website: https://powerful-layout-467812-p1.web.app
- Database: https://console.firebase.google.com/project/powerful-layout-467812-p1/database

### Common Issues
1. **Not a test user**: Add email at OAuth Audience page
2. **Database not created**: Check Firebase console for `auth-tokens-db`
3. **Rules not deployed**: Verify rules at database settings
4. **Website not deployed**: Run `firebase deploy --only hosting`
