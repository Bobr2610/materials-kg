# Skill: KB Widget Development

Guidelines for developing and maintaining the AI assistant widget (`ai-assistant.php`) embedded in the Comindware KB (`kb.comindware.ru`).

## Repository Layout

| Repo | Path | Role |
|---|---|---|
| `cmw-rag` | `D:\Repo\cmw-rag\` | Backend (Gradio/FastAPI) + progress reports |
| `kb.comindware.ru` | `D:\Repo\kb.comindware.ru\` | Frontend (PHP KB site + widget) |

## WSL Dev Server Propagation

**Critical:** The KB nginx server in WSL reads from `/var/www/kb/`, NOT from `D:\Repo\kb.comindware.ru\`. After every edit to `ai-assistant.php`:

```bash
wsl bash -c "cp /mnt/d/Repo/kb.comindware.ru/ai-assistant.php /var/www/kb/ai-assistant.php && chown www-data:www-data /var/www/kb/ai-assistant.php"
```

For production, push to the `kb.comindware.ru` git repo and deploy to ennoia separately.

## KB Layout Architecture

### Blue top bar
- `.bg-cmw.top_nav` > `.mainnav.navbar` — height is content-driven (~91px), NOT explicit
- Logo: `.navbar-brand` > `img` — KB's own JS hides at ≤1031px. Widget must NOT hide it.
- Menu: `.xv-menuwrapper .dl-menu` — right-aligned via `justify-content-between`

### Sidebar
- `.left-side` / `.main-sidebar` — collapses at ≤1047px via `xv-menu.js` adding `sidebar-collapse` to `<body>`
- Uses `transform: translate(-330px, 0)` to hide

### KB responsive breakpoints
- **1047px**: Sidebar collapses, menu switches to hamburger
- **1031px**: Hamburger shows, nav gets padding, menu links compact
- Based on `window.innerWidth`, NOT content width. Body `margin-right` from widget does NOT trigger them.

## Widget Pane CSS Architecture

```css
/* When pane is active */
body.cmw-widget-pane-active { transition: margin-right 0.3s ease; }
/* margin-right is JS-driven, NOT CSS */

#cmw-widget-container {
    width: 400px; height: 100vh; right: 0; top: 0; bottom: 0;
    border: none; border-left: 1px solid var(--cmw-border);
    overflow: hidden; box-sizing: border-box;
}
#cmw-widget-container.show { transform: translateX(0); }
```

## CSS Rules When Pane Is Active

```css
/* Compact nav (KB only does this at ≤1031px) */
body.cmw-widget-pane-active .mainnav { padding: 15px; }
body.cmw-widget-pane-active .xv-menuwrapper { margin-left: auto; }
body.cmw-widget-pane-active .xv-menuwrapper .dl-menu > li > a {
    line-height: 60px; font-size: 12px; padding: 0 10px; margin-left: 5px;
}
```

## What NOT to Do

- **Do NOT hide `.navbar-brand`** — KB's JS handles this
- **Do NOT add `overflow: hidden` to `html`/`body`** — kills page scroll
- **Do NOT hardcode `margin-right` in CSS** — must be JS-driven for resizable widget
- **Do NOT save `left`/`bottom` in pane mode** — prevents floating-mode restore on reopen

## JS State Management

### toggleWidget(open)
- Open: adds `cmw-widget-pane-active` + `sidebar-collapse` to body, sets `body.style.marginRight`, calls `restoreContainerSize()`
- Close: removes classes, clears margin, conditionally removes `sidebar-collapse` if viewport > 1047px

### saveState()
- Skips `left`/`bottom` in pane mode (prevents floating-mode restore)

### restoreContainerSize()
- In pane mode: syncs body margin + toggle button position from stored width

### doResize()
- In pane mode: updates widget width + body margin + toggle position only

## Key Height Values

| Element | Height | Source |
|---|---|---|
| KB blue top pane | ~91px | Content-driven (line-height: 90px on menu links) |
| Widget header | 91px | `--cmw-topnav-height` CSS variable |
| Widget container | 100vh | Pane mode CSS |
| JS HEADER_HEIGHT_FALLBACK | 91px | Fallback when header element not found |

## Gradio Integration

- `<gradio-app>` web component requires CDN bundle (6.5.1) to register
- Self-hosted Gradio 6.9.0 does NOT serve web component JS
- `GRADIO_URL` must be full URL (no JS path concatenation)
- Shadow DOM messaging via `_sendWhenReady()` retry loop

## Testing

Use Playwright in headed mode for visual verification:
```bash
playwright-cli open --headed --browser=chrome "http://localhost/article/..."
```

Measure heights via `run-code`:
```js
const data = await page.evaluate(() => {
    const c = document.getElementById('cmw-widget-container');
    return { h: c.offsetHeight, scrollH: c.scrollHeight };
});
```

## File Locations

- Widget code: `kb.comindware.ru/ai-assistant.php` (single file, ~1300 lines)
- Backend: `cmw-rag/rag_engine/api/app.py` (Gradio app at `/kb_assist`)
- Progress reports: `cmw-rag/docs/progress_reports/`
