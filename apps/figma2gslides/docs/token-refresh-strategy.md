# Token Auto-Refresh Strategy

**Status**: Historical integration note
**Scope**: Token types and refresh approach captured during the initial Firebase/Google auth integration work.

This document explains how tokens are automatically refreshed in the svg2ooxml system.

Use this as implementation context for the original auth flow, not as the active source of truth for frontend auth behavior or operational hardening. Related active docs:
- `apps/figma2gslides/figma-plugin-firebase-auth.md`
- `docs/specs/hardening-backlog.md`

## Token Types

### 1. Firebase ID Token
- **Lifetime**: 1 hour
- **Purpose**: Authenticates user to our backend API
- **Refresh Method**: Use Firebase Refresh Token via Firebase Auth REST API

### 2. Firebase Refresh Token
- **Lifetime**: Long-lived (~60 days of inactivity)
- **Purpose**: Get new Firebase ID tokens without re-authentication
- **Refresh Method**: N/A (doesn't expire unless revoked or unused for 60+ days)

### 3. Google OAuth Access Token
- **Lifetime**: 1 hour (created from Firebase ID token)
- **Purpose**: Access Google Drive/Slides APIs
- **Refresh Method**: Automatically refreshed by `google-auth` library

## Auto-Refresh Implementation

### Backend (Server-Side) ✅ IMPLEMENTED

**File**: `src/figma2gslides/api/services/slides_publisher.py`

The Google OAuth2 library handles automatic token refresh:

```python
credentials = UserCredentials(
    token=id_token,                    # Initial access token (expires in 1h)
    refresh_token=refresh_token,        # Long-lived refresh token
    token_uri="https://oauth2.googleapis.com/token",
    client_id=os.getenv("FIREBASE_WEB_CLIENT_ID"),
    client_secret=os.getenv("FIREBASE_WEB_CLIENT_SECRET"),
    scopes=SLIDES_SCOPES,
)
```

**How it works**:
1. User makes API request with expired ID token
2. Google API client detects 401 Unauthorized
3. Client uses refresh_token + client_id + client_secret to get new access token
4. Original request retries with new token
5. **All automatic - no code needed!**

**Requirements**:
- ✅ `FIREBASE_WEB_CLIENT_ID` environment variable
- ✅ `FIREBASE_WEB_CLIENT_SECRET` environment variable
- ✅ Refresh token passed from frontend

### Frontend (Client-Side) - Gap Noted At Time Of Writing

**Current state**: Tokens stored but not automatically refreshed

**What needs to be added**:

1. **Token Expiration Detection**
   - Check ID token expiration before API calls
   - Automatically refresh if expired or expiring soon

2. **Proactive Token Refresh**
   - Refresh tokens 5 minutes before expiration
   - Prevents failed API calls due to expired tokens

3. **Session Persistence**
   - Store tokens in Figma's clientStorage
   - Restore session on plugin reload

## Reference Implementation Sketch

### Frontend Token Refresh

Add to `apps/figma2gslides/figma-plugin/ui.html`:

```javascript
// Check if token is expired or expiring soon (within 5 minutes)
function isTokenExpiring(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    const exp = payload.exp * 1000; // Convert to milliseconds
    const now = Date.now();
    const fiveMinutes = 5 * 60 * 1000;
    return exp - now < fiveMinutes;
  } catch (e) {
    return true; // If we can't parse, assume expired
  }
}

// Refresh Firebase ID token using refresh token
async function refreshIdToken() {
  if (!currentRefreshToken) {
    throw new Error('No refresh token available');
  }

  const response = await fetch(
    `https://securetoken.googleapis.com/v1/token?key=${FIREBASE_API_KEY}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        grant_type: 'refresh_token',
        refresh_token: currentRefreshToken,
      }),
    }
  );

  if (!response.ok) {
    throw new Error('Failed to refresh token');
  }

  const data = await response.json();
  currentToken = data.id_token;
  currentRefreshToken = data.refresh_token;

  // Update stored session
  await saveSession(currentToken, currentRefreshToken, currentUser.email);

  return currentToken;
}

// Get valid token (refresh if needed)
async function getValidToken() {
  if (!currentToken || isTokenExpiring(currentToken)) {
    currentToken = await refreshIdToken();
  }
  return currentToken;
}

// Use in API calls
async function callAPI(endpoint, data) {
  const token = await getValidToken(); // Auto-refresh if needed

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  return response;
}
```

### Background Token Refresh

Optionally, add periodic token refresh:

```javascript
// Refresh token every 50 minutes (before 1 hour expiration)
setInterval(async () => {
  if (currentToken && currentRefreshToken) {
    try {
      await refreshIdToken();
      console.log('Token refreshed automatically');
    } catch (error) {
      console.error('Auto-refresh failed:', error);
    }
  }
}, 50 * 60 * 1000); // 50 minutes
```

## Token Refresh Flow Diagram

```
Frontend (Figma Plugin)
│
├─> Check token expiration
│   │
│   ├─> Token valid → Use existing token
│   │
│   └─> Token expired/expiring
│       │
│       └─> Refresh ID token using Firebase REST API
│           ├─> Update currentToken
│           ├─> Update currentRefreshToken
│           └─> Save to clientStorage
│
└─> Make API call with current token
    │
    └─> Backend (Cloud Run)
        │
        ├─> Validate Firebase ID token
        │
        └─> Create Google OAuth credentials
            ├─> token: Firebase ID token
            ├─> refresh_token: Firebase refresh token
            ├─> client_id: FIREBASE_WEB_CLIENT_ID
            └─> client_secret: FIREBASE_WEB_CLIENT_SECRET
            │
            └─> Google API Client (auto-refresh)
                │
                ├─> Access token valid → Make API call
                │
                └─> Access token expired
                    │
                    └─> Automatically refresh using:
                        ├─> POST https://oauth2.googleapis.com/token
                        ├─> grant_type: refresh_token
                        ├─> refresh_token: <token>
                        ├─> client_id: <id>
                        └─> client_secret: <secret>
                        │
                        └─> Get new access token
                            │
                            └─> Retry original API call
```

## Testing Token Refresh

### Test Backend Auto-Refresh

1. Create export job with valid tokens
2. Wait 1 hour (or set short token expiration for testing)
3. Backend should automatically refresh and complete job

### Test Frontend Auto-Refresh

1. Open Figma plugin and sign in
2. Wait 1 hour (or mock expired token)
3. Try to export - should auto-refresh before API call
4. Export should succeed without re-authentication

## Troubleshooting

### Backend: "credentials do not contain the necessary fields"

**Cause**: Missing `FIREBASE_WEB_CLIENT_ID` or `FIREBASE_WEB_CLIENT_SECRET`

**Solution**:
```bash
gcloud run services describe svg2ooxml-export --region=europe-west1 | grep FIREBASE_WEB_CLIENT
```

Should show:
```
FIREBASE_WEB_CLIENT_ID firebase-web-client-id:latest
FIREBASE_WEB_CLIENT_SECRET firebase-web-client-secret:latest
```

### Frontend: "Failed to refresh token"

**Cause**: Invalid or expired refresh token

**Solution**: User must sign in again
- Refresh tokens expire after 60 days of inactivity
- User revoked access in Google account settings
- Invalid API key

### Refresh Token Not Being Sent

**Cause**: Frontend not passing `user_refresh_token` in API request

**Solution**: Check request body includes:
```javascript
{
  frames: [...],
  user_refresh_token: currentRefreshToken  // Required!
}
```

## Security Considerations

1. **Never log tokens**: Tokens should never appear in logs
2. **Use HTTPS only**: All token exchanges must be over HTTPS
3. **Rotate secrets**: Periodically rotate OAuth client secrets
4. **Validate tokens**: Always validate tokens on backend before use
5. **Short-lived tokens**: ID tokens expire after 1 hour (cannot be extended)

## Operational Follow-On Topics

1. **Token revocation**: Implement endpoint to revoke refresh tokens
2. **Rate limiting**: Limit token refresh attempts to prevent abuse
3. **Token introspection**: Add endpoint to check token validity
4. **Metrics**: Track token refresh success/failure rates
5. **Alerting**: Alert on high token refresh failure rates

Track prioritization and current decisions for those items in the auth guide/backlog rather than extending this historical integration note.
