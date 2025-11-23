# Figma Plugin UI V2 - Architecture

This document describes the redesigned plugin UI architecture implemented in Phase 1.

## Overview

The new UI is a complete redesign of the Figma plugin interface with:
- **Professional tab-based layout** with 4 main tabs (Deck, Options, Progress, Console)
- **Component-based CSS architecture** using Figma design tokens
- **Centralized state management** with reactive updates
- **Modular JavaScript** with clear separation of concerns

## File Structure

```
figma-plugin/
├── ui-v2.html              # New plugin UI (tab-based layout, all CSS/JS inlined)
├── ui.html                 # Legacy UI (kept for reference, inline assets)
├── test-ui.html            # Minimal smoke-test UI
└── code.js                 # Plugin controller (Figma sandbox)
```

> All previous `/styles` and `/js` modules have been folded directly into `ui-v2.html` so the plugin ships as a single HTML document, matching Figma's packaging requirements.

## Design System

### CSS Variables (Figma Design Tokens)

All colors, spacing, and typography follow Figma's official design system:

**Colors:**
- `--figma-color-bg` - Background colors (primary, secondary, tertiary)
- `--figma-color-text` - Text colors (primary, secondary, tertiary)
- `--figma-color-border` - Border colors
- `--figma-color-icon` - Icon colors
- `--figma-color-bg-brand` - Brand color (#18a0fb)
- Status colors: success, warning, danger

**Spacing:**
- 4px base grid: `--spacing-1` (4px) through `--spacing-12` (48px)

**Typography:**
- Font family: Inter (matches Figma UI)
- Font sizes: 11px - 24px
- Font weights: normal (400), medium (500), semibold (600), bold (700)

**Dark Mode:**
- Automatic support via `@media (prefers-color-scheme: dark)`

### Component Library

#### Buttons

```html
<button class="btn btn-primary">Primary</button>
<button class="btn btn-secondary">Secondary</button>
<button class="btn btn-tertiary">Tertiary</button>
<button class="btn btn-danger">Danger</button>

<!-- Sizes -->
<button class="btn btn-small">Small</button>
<button class="btn btn-medium">Medium (default)</button>
<button class="btn btn-large">Large</button>

<!-- States -->
<button class="btn btn-primary is-loading">Loading</button>
<button class="btn btn-primary" disabled>Disabled</button>

<!-- Modifiers -->
<button class="btn btn-primary btn-block">Full Width</button>
<button class="btn btn-icon">Icon Only</button>
```

#### Cards

```html
<div class="card">
  <div class="card-header">
    <div class="card-title">Title</div>
    <div class="card-subtitle">Subtitle</div>
  </div>
  <div class="card-body">
    Content
  </div>
  <div class="card-footer">
    <button class="btn btn-secondary">Cancel</button>
    <button class="btn btn-primary">Save</button>
  </div>
</div>

<!-- Frame card for preview grid -->
<div class="frame-card">
  <div class="frame-thumbnail">
    <img src="..." alt="Frame preview">
  </div>
  <div class="frame-name">Slide 1</div>
  <div class="frame-meta">
    <span class="frame-dimensions">1920x1080</span>
    <span class="frame-number">1</span>
  </div>
</div>

<!-- Empty state -->
<div class="empty-state">
  <svg class="empty-state-icon">...</svg>
  <div class="empty-state-title">No data</div>
  <div class="empty-state-description">Description</div>
</div>
```

#### Form Inputs

```html
<!-- Text input -->
<div class="field">
  <label class="field-label">Label</label>
  <input type="text" class="input" placeholder="Placeholder">
  <div class="field-hint">Hint text</div>
</div>

<!-- Checkbox -->
<label class="checkbox">
  <input type="checkbox" checked>
  <span class="checkbox-label">Option</span>
</label>

<!-- Radio -->
<label class="radio">
  <input type="radio" name="group" value="1">
  <span class="radio-label">Option 1</span>
</label>

<!-- Select -->
<select class="select">
  <option>Option 1</option>
  <option>Option 2</option>
</select>
```

#### Tabs

```html
<div class="tab-bar">
  <ul class="tab-list" role="tablist">
    <li class="tab-item">
      <button class="tab-button" role="tab" data-tab="deck" aria-selected="true">
        <span class="tab-icon">...</span>
        <span class="tab-label">Deck</span>
      </button>
    </li>
  </ul>
</div>

<div class="tab-panels">
  <div class="tab-panel" role="tabpanel" aria-hidden="false">
    <div class="tab-panel-content scrollable">
      Content
    </div>
  </div>
</div>
```

#### Progress & Status

```html
<!-- Progress bar -->
<div class="progress">
  <div class="progress-bar" style="width: 60%"></div>
</div>

<!-- Indeterminate progress -->
<div class="progress indeterminate">
  <div class="progress-bar"></div>
</div>

<!-- Spinner -->
<span class="spinner"></span>

<!-- Badges -->
<span class="badge badge-primary">Pro</span>
<span class="badge badge-success">Active</span>
<span class="badge badge-warning">Warning</span>
<span class="badge badge-danger">Error</span>

<!-- Status dot -->
<span class="status-dot online"></span>

<!-- Timeline -->
<div class="timeline">
  <div class="timeline-item completed">
    <div class="timeline-marker"></div>
    <div class="timeline-content">
      <div class="timeline-title">Step completed</div>
      <div class="timeline-time">2m ago</div>
    </div>
  </div>
</div>
```

## State Management

The `AppState` class provides centralized, reactive state management:

```javascript
// Get state
const user = appState.get('user');
const frames = appState.get('frames');

// Update state
appState.setState({ user: userData });
appState.set('activeTab', 'options');

// Subscribe to changes
const unsubscribe = appState.subscribe((oldState, newState) => {
  console.log('State changed', newState);
});

// Watch specific property
appState.watch('exportProgress', (newValue, oldValue) => {
  updateProgressBar(newValue);
});

// Add console log
appState.addLog('info', 'Export started', { frameCount: 5 });

// Update export progress
appState.updateExportProgress(50, {
  name: 'converting',
  status: 'active',
  message: 'Converting frames...'
});

// Persistence
await appState.load();  // Load from clientStorage
appState.save();        // Save to clientStorage
```

### State Structure

```javascript
{
  // Authentication
  user: { email: 'user@example.com' },
  token: 'firebase-id-token',
  refreshToken: 'firebase-refresh-token',

  // Subscription
  subscription: { tier: 'pro', usage: {...} },

  // Selected frames
  frames: [{ id, name, svg_content, width, height }],
  selectedFrameIds: Set(['frame-1', 'frame-2']),

  // Export options
  exportOptions: {
    textHandling: 'editable',
    preserveVectors: true,
    slideFormat: '16:9',
  },

  // Export progress
  exportJob: 'job-id',
  exportStatus: 'processing',
  exportProgress: 75,
  exportSteps: [{...}],

  // UI state
  activeTab: 'deck',
  isLoading: false,

  // Console
  logs: [{timestamp, level, message, data}],
  apiOverrides: { apiUrl, authUrl },
}
```

## Tab Navigation

The `TabController` class handles tab switching with full keyboard support:

```javascript
// Programmatic tab switching
tabController.switchTo('progress');

// Add badge to tab
tabController.setBadge('console', 5); // Shows "5" badge

// Enable/disable tab
tabController.setTabEnabled('progress', false);

// Get active tab
const activeTab = tabController.getActiveTab();

// Listen to tab changes
container.addEventListener('tabchange', (e) => {
  console.log('Tab changed to', e.detail.tabId);
});
```

**Keyboard Support:**
- Arrow keys: Navigate between tabs
- Home/End: Jump to first/last tab
- Tab key: Standard focus behavior

## Integration with Existing Code

The new UI is designed to coexist with the current implementation:

1. **Keep current auth logic**: Copy authentication code from `ui.js`
2. **Keep export logic**: Integrate export flow with new state management
3. **Add state persistence**: Use existing `clientStorage` messages
4. **Preserve API overrides**: Developer settings work the same way

### Next Steps

To complete the integration:

1. Extract and adapt authentication logic from `ui.js`
2. Integrate export flow with new state management
3. Implement frame selection and preview grid
4. Add export progress tracking with timeline
5. Implement console logging with real-time updates
6. Test with local API server
7. Update `manifest.json` to use `ui-v2.html`

## Testing

To test the new UI:

1. Update `manifest.json`:
   ```json
   {
     "ui": "ui-v2.html"
   }
   ```

2. Reload plugin in Figma

3. Test tab navigation with keyboard

4. Test responsive behavior

5. Test dark mode (System Preferences → Appearance → Dark)

## Browser Support

- Chrome (Figma Desktop & Browser)
- Safari (Figma Browser)
- Firefox (Figma Browser)
- Edge (Figma Browser)

All modern browsers with CSS Grid and ES6+ support.

## Accessibility

- Full keyboard navigation
- ARIA labels for screen readers
- Focus indicators
- Color contrast meets WCAG AA standards
- Semantic HTML

## Performance

- CSS variables for minimal repaints
- Debounced state updates
- Efficient DOM updates
- Lazy rendering for large frame lists
- Smooth 60fps animations
