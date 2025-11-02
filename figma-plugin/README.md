# SVG to Google Slides - Figma Plugin

Export your Figma frames directly to Google Slides presentations with high-fidelity SVG rendering.

## Features

- ✨ **One-Click Export**: Export selected frames to Google Slides
- 🔐 **Secure Authentication**: Sign in with your Google account via Firebase
- 🎨 **High-Fidelity**: Preserves SVG quality and effects
- 📊 **Multi-Frame Support**: Export multiple frames as slides
- 🔄 **Real-Time Progress**: Track export progress with visual feedback

## Installation

### For Development

1. Open Figma Desktop app
2. Go to **Plugins** → **Development** → **Import plugin from manifest**
3. Select the `manifest.json` file from this directory
4. The plugin will appear in your plugins list

### For Users (After Publishing)

1. Find "SVG to Google Slides" in the Figma Community
2. Click **Install** or **Try it out**
3. Access from **Plugins** → **SVG to Google Slides**

## Usage

### 1. Sign In

1. Open the plugin: **Plugins** → **SVG to Google Slides**
2. Click **"Sign in with Google"**
3. Authorize the plugin to access your Google Drive and Slides
4. You'll be signed in and ready to export

### 2. Export Frames

1. **Select** one or more frames in Figma
2. Click **"Export Selected Frames"**
3. Wait for the export to complete (progress shown in plugin)
4. Click the **link** to open your presentation in Google Slides

### 3. View Your Slides

- The exported presentation will open in Google Slides
- Each frame becomes a slide
- All SVG content is preserved with high fidelity

## Requirements

- Figma Desktop app (plugin uses network features)
- Google account for authentication
- Internet connection for API access

## Configuration

The plugin is pre-configured to use the svg2ooxml production API:
- **API**: https://svg2ooxml-export-sghya3t5ya-ew.a.run.app
- **Firebase**: powerful-layout-467812-p1

No additional configuration needed!

## Files

- `manifest.json` - Plugin configuration
- `code.js` - Figma plugin backend (runs in Figma sandbox)
- `ui.html` - Plugin UI layout
- `ui.js` - UI logic and Firebase integration
- `README.md` - This file

## Permissions

### Network Access
The plugin requires network access to:
- `svg2ooxml-export-sghya3t5ya-ew.a.run.app` - API server
- `*.googleapis.com` - Google APIs
- `*.firebaseapp.com` - Firebase Authentication
- `*.google.com` - Google OAuth
- `www.gstatic.com` - Firebase SDK

### OAuth Scopes
When you sign in, the plugin requests:
- `https://www.googleapis.com/auth/drive.file` - Create files in your Drive
- `https://www.googleapis.com/auth/presentations` - Create/edit Slides

**Privacy Note**: The plugin only creates new files. It cannot access your existing files or Drive contents.

## Troubleshooting

### "Please select at least one frame"
- Make sure you have selected frames (not layers or groups)
- Frames must be top-level objects on the canvas

### "Popup blocked" or Sign-in doesn't open
- Allow popups for Figma in your browser
- Check that third-party cookies are enabled
- Try again after allowing popups

### "Sign-in failed"
- Check your internet connection
- Make sure you're using a Google account
- Try signing out and signing in again

### "Export failed"
- Ensure you're signed in (green checkmark next to email)
- Check that frames contain exportable content
- Try exporting fewer frames at once
- Check browser console for detailed error messages

### "Export timed out"
- Large exports may take up to 3 minutes
- Try exporting fewer frames at once
- Check your internet connection

### "Network error"
- Check your internet connection
- Verify the API is accessible
- Try again in a few moments

## Development

### Local Development Setup

1. Clone the svg2ooxml repository
2. Navigate to `figma-plugin/` directory
3. Load the plugin in Figma Development mode
4. Edit files and reload plugin to see changes

### Testing

1. **Test Authentication**:
   - Click "Sign in with Google"
   - Verify popup appears and login works
   - Check that UI updates with your email

2. **Test Export**:
   - Create test frames in Figma
   - Select frames and click "Export"
   - Verify progress updates
   - Check that Slides presentation is created

3. **Test Error Handling**:
   - Try exporting with no frames selected
   - Try exporting without signing in
   - Test with invalid frames

### Modifying Configuration

To change the API URL or Firebase config:

1. **API URL**: Edit `API_URL` in `ui.js`
2. **Firebase Config**: Edit `firebaseConfig` in `ui.html`

### Building for Production

The plugin is built with vanilla JavaScript and requires no build step.

To publish:
1. Ensure all files are present
2. Test thoroughly in development mode
3. Submit to Figma Community via Figma app

## Architecture

```
┌─────────────────┐
│  Figma Canvas   │
│  (User selects  │
│    frames)      │
└────────┬────────┘
         │
         v
┌─────────────────┐
│   code.js       │
│  (Exports SVG)  │
└────────┬────────┘
         │
         v
┌─────────────────┐
│   ui.js         │
│  (Firebase Auth │
│   + API calls)  │
└────────┬────────┘
         │
         v
┌─────────────────┐
│   svg2ooxml API │
│  (Cloud Run)    │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  Google Slides  │
│  (User's Drive) │
└─────────────────┘
```

## Security

- **Tokens**: Firebase ID tokens are stored only in memory, never persisted
- **OAuth**: Uses Firebase Authentication for secure Google OAuth
- **API**: All API requests include Bearer token authentication
- **Privacy**: No data is stored permanently; SVG is processed and discarded

## Support

### Documentation
- Full integration guide: `docs/guides/figma-plugin-firebase-auth.md`
- API documentation: `docs/implementation-summary-firebase-auth.md`

### Issues
- Report bugs: https://github.com/BramAlkema/svg2ooxml/issues
- Check existing issues for solutions

### Privacy & Terms
- Privacy Policy: https://powerful-layout-467812-p1.web.app/privacy.html
- Terms of Service: https://powerful-layout-467812-p1.web.app/terms.html

## License

See the main svg2ooxml repository for license information.

## Credits

Built with:
- [Firebase Authentication](https://firebase.google.com/docs/auth)
- [Figma Plugin API](https://www.figma.com/plugin-docs/)
- [svg2ooxml](https://github.com/BramAlkema/svg2ooxml)

---

**Version**: 1.0.0
**Last Updated**: 2025-11-02
