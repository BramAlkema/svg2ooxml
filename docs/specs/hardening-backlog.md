# Hardening Backlog

Issues deferred from code review. Acceptable at current scale but should be
addressed before high-traffic use.

---

## 1. Unbounded `_pending_auth` dict

**File:** `main.py:73`

**Current:** In-memory dict stores auth tokens with 2-min TTL. Cleanup only
runs when `store_auth()` or `poll_auth()` is called. Abandoned auth flows
(user closes popup without completing) leave orphaned entries until the next
call triggers cleanup.

**Risk:** Memory leak on long-running deployments with many abandoned auth
attempts. Each entry is ~200 bytes, so 10k abandoned sessions = ~2MB. Low
risk at current scale but grows linearly.

**Fix:** Add a background cleanup task using FastAPI's lifespan:

```python
from contextlib import asynccontextmanager
import asyncio

async def _periodic_cleanup():
    while True:
        await asyncio.sleep(60)
        _cleanup_expired()

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_periodic_cleanup())
    yield
    task.cancel()
```

**Alternative:** Replace the dict with `cachetools.TTLCache(maxsize=1000,
ttl=120)` which handles expiry and bounds automatically. Add `cachetools` to
the `api` extra.

---

## 2. Unbounded rate limiter store

**File:** `src/svg2ooxml/api/middleware/rate_limit.py:17`

**Current:** `RateLimiter._store` is a dict keyed by client IP. Entries are
overwritten on each request but never removed. After the rate window expires,
the entry remains in memory with stale data.

**Risk:** Memory grows with O(unique IPs). A service seeing 100k unique IPs
accumulates ~100k dict entries (~10MB). Not a concern for a Figma plugin with
a small user base, but matters if exposed publicly.

**Fix:** Add periodic sweep to evict entries with expired `reset` timestamps:

```python
def _sweep(self) -> None:
    now = time.time()
    expired = [k for k, (_, reset) in self._store.items() if now >= reset]
    for k in expired:
        del self._store[k]
```

Call `_sweep()` every N requests (e.g., every 100th call) or on a timer.

**Alternative:** Use `cachetools.TTLCache(maxsize=10000, ttl=window_seconds)`
as the backing store.

---

## 3. Hardcoded URLs in Figma plugin

**File:** `figma-plugin/ui-v2.html:218-221`

**Current:**
```javascript
const API_URL = 'https://svg2ooxml.tactcheck.com';
const AUTH_URL = 'https://auth.supabase.tactcheck.com';
```

Also hardcoded in `manifest.json` allowed domains.

**Risk:** Can't test locally or run against staging without editing source.
Not an issue for single-environment production use.

**Fix:** Add a config endpoint and fetch URLs at startup:

```javascript
// Fetch config from API
const config = await fetch(`${API_URL}/config`).then(r => r.json());
// { api_url: "...", auth_url: "..." }
```

Or simpler: check for a dev override via URL parameter or local storage:

```javascript
const API_URL = localStorage.getItem('svg2ooxml_api_url')
  || 'https://svg2ooxml.tactcheck.com';
```

The `manifest.json` allowed domains must still list all possible domains.
For dev, add `http://localhost:*` to the allowlist.

---

## 4. Session key duplication in code.js

**File:** `figma-plugin/code.js:29-47`

**Current:** Four storage keys (`supabase_jwt`, `google_access_token`,
`google_refresh_token`, `email`) are repeated in `save-session`,
`clear-session`, and `restore-session` handlers — 12 occurrences total.
Renaming a key requires updating 3 places.

**Risk:** Key mismatch on rename. Low risk since keys rarely change.

**Fix:** Extract a shared constant:

```javascript
const SESSION_KEYS = {
  supabaseJwt: 'supabase_jwt',
  googleAccessToken: 'google_access_token',
  googleRefreshToken: 'google_refresh_token',
  email: 'email',
};

if (msg.type === 'save-session') {
  for (const [prop, key] of Object.entries(SESSION_KEYS)) {
    await figma.clientStorage.setAsync(key, msg[prop]);
  }
}

if (msg.type === 'clear-session') {
  for (const key of Object.values(SESSION_KEYS)) {
    await figma.clientStorage.deleteAsync(key);
  }
}

if (msg.type === 'restore-session') {
  const session = {};
  for (const [prop, key] of Object.entries(SESSION_KEYS)) {
    session[prop] = await figma.clientStorage.getAsync(key);
  }
  figma.ui.postMessage({ type: 'session-restored', ...session });
}
```
