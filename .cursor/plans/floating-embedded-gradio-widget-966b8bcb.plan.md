<!-- 966b8bcb-959e-489f-b56e-949ff4ba1fd9 00d87ee9-3325-4d55-98f8-d74325673b63 -->
# Floating Embedded Gradio Widget

Create a floating chat widget that combines the full-featured Gradio web component (`<gradio-app>`) with JavaScript widget styling (floating button, collapsible panel, positioned in corner).

## Implementation

### 1. HTML Structure (`gradio.html`)

- Wrap `<gradio-app>` in a floating container div
- Add toggle button (chat icon in bottom-right corner)
- Add close button in widget header
- Structure: `chat-widget` container → `chat-toggle` button + `chat-container` (hidden by default) → `<gradio-app>` inside container

### 2. CSS Styling

- Position widget: `position: fixed; bottom: 20px; right: 20px; z-index: 1000;`
- Toggle button: circular button with chat icon (50x50px, rounded)
- Widget container: card-style panel (width: 400px, height: 600px initially, resizable)
- Show/hide toggle with CSS classes (`.hidden` class for display:none)
- Smooth transitions for open/close animations
- Ensure `<gradio-app>` fits within container (height: 100%, overflow handling)

### 3. JavaScript Functionality

- Toggle visibility on button click
- Close button handler
- Auto-resize `<gradio-app>` to fit container
- Optional: localStorage to remember open/closed state
- Ensure Gradio app loads lazily (only when widget is opened)

### 4. Gradio App Configuration

- Use `gradio_server_name` and `gradio_server_port` from settings (or environment variable) to construct URL
- Format: `http://${GRADIO_SERVER_NAME}:${GRADIO_SERVER_PORT}` or `https://...` for production
- Fallback to `<host>:7860` if settings not available
- Load Gradio JS from CDN (latest stable version)

### 5. Features Preserved

- Full ChatInterface functionality (streaming, history, citations, copy button)
- Session management (salted session IDs work automatically)
- Resizable chatbot component
- All existing Gradio features

## Files to Modify/Create

1. **`ui/gradio-embedded.html`** - Update with floating widget structure, CSS, and JavaScript (already exists, will be enhanced)
2. **Optional: `ui/widget-template.html`** - Reusable template for embedding in other sites (if needed)

## Design Considerations

- Widget should not interfere with main page content (high z-index, positioned fixed)
- Responsive: smaller on mobile devices (max-width: 100vw - 40px on small screens)
- Theme: match Comindware brand colors if possible, or neutral modern design
- Accessibility: keyboard navigation, ARIA labels for screen readers