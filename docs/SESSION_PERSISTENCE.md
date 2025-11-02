# Session Persistence & Token Refresh

## Overview
The Figma plugin now supports **indefinite session persistence** using Firebase refresh tokens. Users stay signed in until they explicitly sign out or revoke access.

## How It Works

### Token Types

1. **ID Token** (1-hour expiration)
   - Used for API authentication
   - JWT format
   - Automatically refreshed before each API call

2. **Refresh Token** (never expires*)
   - Used to obtain new ID tokens
   - Long-lived credential
   - Stored securely in Figma's clientStorage

*Refresh tokens remain valid until:
- User explicitly signs out
- User revokes app access in Google Account settings
- User changes their Google password
- Token inactive for 6 months (Google policy)

### Session Flow

#### First Sign-In
1. User clicks "Sign in with Google"
2. Completes OAuth in external window
3. Plugin receives both ID token + refresh token
4. Both tokens saved to Figma's `clientStorage`
5. User stays signed in

#### Subsequent Plugin Opens
1. Plugin loads
2. Requests session restoration from backend
3. Backend retrieves tokens from `clientStorage`
4. Session restored automatically
5. No re-authentication required

#### API Calls (Auto-Refresh)
1. User clicks "Export Selected Frames"
2. Plugin checks if ID token is fresh
3. If needed, refreshes ID token using refresh token
4. New ID token saved to storage
5. API call made with fresh token

#### Sign Out
1. User clicks "Sign out"
2. All tokens cleared from storage
3. Session terminated

## Implementation Details

### Files Modified

#### `figma-plugin/ui.js`
- Added `currentRefreshToken` variable
- Added `refreshIdToken()` function
- Modified `saveSession()` to store refresh token
- Modified `createExportJob()` to auto-refresh token

#### `figma-plugin/code.js`
- Modified session handlers to save/restore refresh token
- Uses Figma's `clientStorage` API (encrypted storage)

#### `public/auth.html`
- Modified to capture refresh token from Firebase Auth
- Stores refresh token in database alongside ID token

#### `public/auth-status.html`
- Modified to return refresh token to plugin

#### `database.rules.json`
- Updated validation to require `refreshToken` field

### Security Considerations

#### What's Secure ✅
- Refresh tokens stored in Figma's encrypted clientStorage
- Tokens isolated per-plugin, per-user
- Automatic token rotation on each refresh
- Standard OAuth 2.0 refresh token flow

#### What's Not Stored ❌
- No tokens in localStorage (vulnerable to XSS)
- No tokens in cookies
- No tokens in URL parameters
- No tokens in console logs

### Token Refresh API

The plugin uses Firebase's secure token endpoint:

```javascript
POST https://securetoken.googleapis.com/v1/token?key={API_KEY}
Content-Type: application/json

{
  "grant_type": "refresh_token",
  "refresh_token": "{REFRESH_TOKEN}"
}

Response:
{
  "id_token": "{NEW_ID_TOKEN}",
  "refresh_token": "{NEW_REFRESH_TOKEN}",
  "expires_in": "3600",
  "token_type": "Bearer",
  "user_id": "{USER_ID}"
}
```

## User Experience

### Before (Original Implementation)
- Sign in every time plugin opens ❌
- Session lost when plugin closes ❌
- Re-authentication every ~5 minutes ❌

### After (With Refresh Tokens)
- Sign in once ✅
- Stay signed in indefinitely ✅
- Automatic token refresh ✅
- No interruptions ✅

## Session Duration

| Scenario | Duration |
|----------|----------|
| **Normal Usage** | Indefinite (until sign out) |
| **Inactive for 6 months** | Session expires (Google policy) |
| **Password changed** | Session expires (security) |
| **Access revoked** | Session expires immediately |
| **Plugin uninstalled** | Tokens deleted with plugin data |

## Revoking Access

Users can revoke access at any time:

1. **From Plugin**: Click "Sign out" button
2. **From Google Account**: https://myaccount.google.com/permissions
3. **Delete Plugin**: Uninstall from Figma

## Testing

### Test Session Persistence
1. Sign in to plugin
2. Close plugin
3. Reopen plugin
4. Verify: User still signed in ✅

### Test Token Refresh
1. Sign in to plugin
2. Wait 1+ hour
3. Try to export frames
4. Verify: Export succeeds (token auto-refreshed) ✅

### Test Sign Out
1. Sign in to plugin
2. Click "Sign out"
3. Close and reopen plugin
4. Verify: User needs to sign in again ✅

## Troubleshooting

### Session Not Persisting
**Symptom**: User signed out after closing plugin

**Possible Causes**:
- Browser blocking third-party storage
- Figma plugin storage quota exceeded
- Code.js not saving tokens

**Check**:
```javascript
// In browser console (Figma plugin DevTools)
parent.postMessage({ pluginMessage: { type: 'restore-session' } }, '*');
// Check console for session-restored message
```

### Token Refresh Failing
**Symptom**: "Session expired. Please sign in again" error

**Possible Causes**:
- Refresh token revoked by user
- Refresh token expired (6 months inactive)
- Network error

**Solution**: User needs to sign in again

### Infinite Refresh Loop
**Symptom**: Token keeps refreshing on every action

**Possible Causes**:
- System clock out of sync
- Token validation failing

**Check**: Decode ID token at https://jwt.io and verify `exp` claim

## Migration from Old Implementation

Users who signed in with the old implementation (no refresh tokens) will need to sign in again once to get a refresh token.

**Migration Flow**:
1. User opens plugin with old session
2. Plugin detects missing refresh token
3. User sees sign-in screen
4. User signs in again
5. New session with refresh token established

No data loss occurs during migration.

## Future Improvements

1. **Proactive Token Refresh**: Refresh token 5 minutes before expiration
2. **Background Refresh**: Refresh token in background to avoid delays
3. **Token Expiry UI**: Show user when their session will expire
4. **Remember Me**: Option to not persist session (sign out on close)

## API Reference

### JavaScript Functions

#### `refreshIdToken(): Promise<string>`
Refreshes the ID token using the refresh token.

**Returns**: New ID token

**Throws**: Error if refresh fails (user needs to re-authenticate)

**Example**:
```javascript
try {
  const newToken = await refreshIdToken();
  console.log('Token refreshed successfully');
} catch (error) {
  console.error('Token refresh failed:', error);
  // Show sign-in screen
}
```

#### `saveSession(token, refreshToken, email): Promise<void>`
Saves session to Figma's clientStorage.

**Parameters**:
- `token`: Firebase ID token (1-hour validity)
- `refreshToken`: Firebase refresh token (long-lived)
- `email`: User's email address

#### `clearSession(): Promise<void>`
Clears session from Figma's clientStorage.

## Security Best Practices

✅ **Do**:
- Store refresh tokens in secure storage (Figma clientStorage)
- Rotate tokens on each refresh
- Clear tokens on sign out
- Use HTTPS for all token operations

❌ **Don't**:
- Log refresh tokens to console
- Send refresh tokens to analytics
- Store tokens in localStorage
- Share tokens between plugins

## Resources

- [Firebase Auth REST API](https://firebase.google.com/docs/reference/rest/auth)
- [OAuth 2.0 Refresh Tokens](https://oauth.net/2/refresh-tokens/)
- [Figma Plugin Storage](https://www.figma.com/plugin-docs/api/figma-clientStorage/)
- [Google Token Expiration](https://developers.google.com/identity/protocols/oauth2#expiration)
