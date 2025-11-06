/**
 * Token Auto-Refresh Utilities for Figma Plugin
 *
 * Add this to your ui.html to enable automatic token refresh.
 * This prevents expired tokens from causing API failures.
 */

// Firebase configuration (replace with your values)
const FIREBASE_API_KEY = 'REDACTED_FIREBASE_API_KEY';

/**
 * Check if a JWT token is expired or expiring soon (within 5 minutes)
 * @param {string} token - JWT token to check
 * @returns {boolean} - True if token is expired or expiring soon
 */
function isTokenExpiring(token) {
  if (!token) return true;

  try {
    // JWT format: header.payload.signature
    const payload = JSON.parse(atob(token.split('.')[1]));
    const exp = payload.exp * 1000; // Convert to milliseconds
    const now = Date.now();
    const fiveMinutes = 5 * 60 * 1000;

    // Token expires within 5 minutes
    return exp - now < fiveMinutes;
  } catch (e) {
    console.error('Failed to parse token:', e);
    return true; // If we can't parse, assume expired
  }
}

/**
 * Get token expiration time
 * @param {string} token - JWT token
 * @returns {Date|null} - Expiration date or null if invalid
 */
function getTokenExpiration(token) {
  if (!token) return null;

  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return new Date(payload.exp * 1000);
  } catch (e) {
    return null;
  }
}

/**
 * Refresh Firebase ID token using refresh token
 * @param {string} refreshToken - Firebase refresh token
 * @returns {Promise<{idToken: string, refreshToken: string}>} - New tokens
 */
async function refreshFirebaseToken(refreshToken) {
  if (!refreshToken) {
    throw new Error('No refresh token provided');
  }

  console.log('🔄 Refreshing Firebase ID token...');

  const response = await fetch(
    `https://securetoken.googleapis.com/v1/token?key=${FIREBASE_API_KEY}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        grant_type: 'refresh_token',
        refresh_token: refreshToken,
      }),
    }
  );

  if (!response.ok) {
    const error = await response.text();
    console.error('Token refresh failed:', error);
    throw new Error(`Failed to refresh token: ${response.status}`);
  }

  const data = await response.json();

  console.log('✅ Token refreshed successfully');
  console.log(`   New token expires: ${getTokenExpiration(data.id_token)}`);

  return {
    idToken: data.id_token,
    refreshToken: data.refresh_token,
  };
}

/**
 * Token manager class with automatic refresh
 */
class TokenManager {
  constructor() {
    this.idToken = null;
    this.refreshToken = null;
    this.email = null;
    this.refreshTimer = null;
  }

  /**
   * Set tokens and start auto-refresh timer
   */
  setTokens(idToken, refreshToken, email) {
    this.idToken = idToken;
    this.refreshToken = refreshToken;
    this.email = email;

    // Clear any existing timer
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
    }

    // Start auto-refresh timer (check every 5 minutes)
    this.refreshTimer = setInterval(() => {
      this.autoRefresh();
    }, 5 * 60 * 1000);

    console.log('🔐 Token manager initialized');
    console.log(`   Token expires: ${getTokenExpiration(idToken)}`);
  }

  /**
   * Clear tokens and stop auto-refresh
   */
  clearTokens() {
    this.idToken = null;
    this.refreshToken = null;
    this.email = null;

    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }

    console.log('🔓 Token manager cleared');
  }

  /**
   * Auto-refresh if token is expiring
   */
  async autoRefresh() {
    if (!this.idToken || !this.refreshToken) {
      return;
    }

    if (isTokenExpiring(this.idToken)) {
      console.log('⏰ Token expiring soon, auto-refreshing...');
      try {
        const { idToken, refreshToken } = await refreshFirebaseToken(this.refreshToken);
        this.idToken = idToken;
        this.refreshToken = refreshToken;

        // Save to storage
        if (typeof saveSession === 'function') {
          await saveSession(idToken, refreshToken, this.email);
        }

        console.log('✅ Auto-refresh successful');
      } catch (error) {
        console.error('❌ Auto-refresh failed:', error);
        // User will need to re-authenticate on next API call
      }
    }
  }

  /**
   * Get valid token (refresh if needed)
   * @returns {Promise<string>} - Valid ID token
   */
  async getValidToken() {
    // No token available
    if (!this.idToken || !this.refreshToken) {
      throw new Error('No tokens available. Please sign in.');
    }

    // Token is still valid
    if (!isTokenExpiring(this.idToken)) {
      return this.idToken;
    }

    // Token expired/expiring - refresh it
    console.log('🔄 Token expired, refreshing...');
    try {
      const { idToken, refreshToken } = await refreshFirebaseToken(this.refreshToken);
      this.idToken = idToken;
      this.refreshToken = refreshToken;

      // Save to storage
      if (typeof saveSession === 'function') {
        await saveSession(idToken, refreshToken, this.email);
      }

      console.log('✅ Token refreshed on-demand');
      return idToken;
    } catch (error) {
      console.error('❌ Token refresh failed:', error);
      this.clearTokens();
      throw new Error('Session expired. Please sign in again.');
    }
  }

  /**
   * Get refresh token
   * @returns {string|null}
   */
  getRefreshToken() {
    return this.refreshToken;
  }
}

// Export for use in plugin
if (typeof window !== 'undefined') {
  window.TokenManager = TokenManager;
  window.isTokenExpiring = isTokenExpiring;
  window.getTokenExpiration = getTokenExpiration;
  window.refreshFirebaseToken = refreshFirebaseToken;
}
