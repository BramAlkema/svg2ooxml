# SVG to Google Slides - Figma Plugin

Export selected Figma frames directly to Google Slides presentations with high-fidelity SVG rendering.

## Features

- One-click export of selected frames to Google Slides
- Google OAuth via Supabase Auth
- Multi-frame support (each frame becomes a slide)
- Automatic token refresh for long sessions

## Installation (Development)

1. Open Figma Desktop app
2. Go to **Plugins** > **Development** > **Import plugin from manifest**
3. Select the `manifest.json` file from this directory
4. The plugin will appear in your plugins list

## Usage

1. Open the plugin: **Plugins** > **SVG to Google Slides**
2. Click **Sign in with Google** -- a browser window opens for OAuth
3. Complete sign-in in your browser; the plugin detects it automatically
4. Select one or more frames in Figma
5. Click **Export Selected Frames**
6. Click the link to open your presentation in Google Slides

## Architecture

```
Figma Canvas (user selects frames)
  --> code.js (exports SVG via Figma API)
  --> ui-v2.html (auth + API calls)
  --> svg2ooxml API (svg2ooxml.tactcheck.com)
  --> Google Slides (user's Drive)
```

### Auth Flow

1. Plugin generates a random `auth_key` (16 hex bytes)
2. Opens browser to Supabase GoTrue `/authorize?provider=google` with a `redirect_to` pointing to the API's `/auth/callback?auth_key=<KEY>`
3. Polls `GET /api/v1/auth/poll?key=<KEY>` every 2s (timeout: 2 min)
4. On success, stores `supabase_jwt`, `google_access_token`, `google_refresh_token`, and `email` in Figma's clientStorage
5. On export 401/403, refreshes the Google token via `POST /api/v1/auth/refresh`

### Export Flow

Single synchronous `POST /api/v1/export` request. No job polling. Response contains `slides_url`.

## Files

- `manifest.json` -- plugin configuration
- `code.js` -- Figma plugin backend (runs in Figma sandbox)
- `ui-v2.html` -- plugin UI and logic (single file, no build step)

## Endpoints

- **API**: `https://svg2ooxml.tactcheck.com`
- **Auth**: `https://auth.supabase.tactcheck.com`

## OAuth Scopes

- `https://www.googleapis.com/auth/drive.file` -- create files in Drive
- `https://www.googleapis.com/auth/presentations` -- create/edit Slides

## Troubleshooting

- **"Please select at least one frame"** -- select frames, groups, components, or instances on the canvas.
- **Sign-in times out** -- make sure you completed the Google sign-in in the browser window that opened.
- **Export fails with 401** -- the plugin will auto-retry with a refreshed token. If it still fails, sign out and sign in again.
- **"Popup blocked"** -- allow popups for Figma in your browser settings.
