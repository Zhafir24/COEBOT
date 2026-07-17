"""PNM-branded CSS for the COEBOT shell.

White background, black text, Plus Jakarta Sans typography (warmer and
more character than Inter). PNM logo at the very top of the sidebar,
hero centered, chat input pinned bottom.
"""

from __future__ import annotations

CUSTOM_CSS = """
<style>
/* Plus Jakarta Sans loaded from local static/ — NO Google Fonts CDN.
   Files live at static/fonts/pjs-*.woff2 and are served by Streamlit
   at /app/static/fonts/... when enableStaticServing=true in
   .streamlit/config.toml. This makes the app fully offline-capable. */
@font-face {
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url('/app/static/fonts/pjs-400.woff2') format('woff2');
}
@font-face {
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url('/app/static/fonts/pjs-500.woff2') format('woff2');
}
@font-face {
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 600;
  font-display: swap;
  src: url('/app/static/fonts/pjs-600.woff2') format('woff2');
}
@font-face {
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url('/app/static/fonts/pjs-700.woff2') format('woff2');
}
@font-face {
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 800;
  font-display: swap;
  src: url('/app/static/fonts/pjs-800.woff2') format('woff2');
}

:root {
  --bg: #FFFFFF;
  --panel: #FAFAFA;
  --panel-2: #F1F2F4;
  --text: #111111;
  --muted: #6B7280;
  --primary: #0C5BA8;
  --primary-dark: #084480;
  --primary-soft: #D6E4F2;
  --accent: #7CB342;
  --border: #ECECEC;
}

/* ---------- Animated background orbs ---------- */
/* Three softly drifting, heavily-blurred PNM-colored discs sit behind
   the whole app. Low opacity keeps text legible; long, offset
   animations keep them from ever syncing into a static look. */
.bg-orb {
  position: fixed;
  border-radius: 50%;
  filter: blur(90px);
  pointer-events: none;
  z-index: 0;
  will-change: transform;
}

.bg-orb-blue {
  width: 540px;
  height: 540px;
  background: #0C5BA8;
  opacity: 0.20;
  top: -180px;
  left: -180px;
  animation: drift-blue 28s ease-in-out infinite alternate;
}

.bg-orb-green {
  width: 460px;
  height: 460px;
  background: #7CB342;
  opacity: 0.22;
  bottom: -150px;
  right: -120px;
  animation: drift-green 34s ease-in-out infinite alternate;
}

.bg-orb-sky {
  width: 400px;
  height: 400px;
  background: #4A90D9;
  opacity: 0.14;
  top: 28%;
  right: 22%;
  animation: drift-sky 24s ease-in-out infinite alternate;
}

@keyframes drift-blue {
  0%   { transform: translate(0, 0) scale(1); }
  50%  { transform: translate(18vw, 14vh) scale(1.08); }
  100% { transform: translate(32vw, 28vh) scale(1.15); }
}

@keyframes drift-green {
  0%   { transform: translate(0, 0) scale(1); }
  50%  { transform: translate(-15vw, -14vh) scale(1.07); }
  100% { transform: translate(-28vw, -26vh) scale(1.12); }
}

@keyframes drift-sky {
  0%   { transform: translate(0, 0) scale(1); }
  50%  { transform: translate(-10vw, 12vh) scale(1.1); }
  100% { transform: translate(-22vw, 24vh) scale(1.2); }
}

/* Make sure real content stacks above the orbs.
   The sidebar is intentionally excluded — it manages its own
   positioning for slide-in/out, and forcing position:relative
   on it breaks the open/close toggle. */
[data-testid="stAppViewContainer"],
[data-testid="stPopover"],
[data-testid="stPopoverBody"] {
  position: relative;
  z-index: 1;
}

/* ---------- Global font + background ---------- */
html, body, [class*="css"], .stApp,
.stMarkdown, .stMarkdown *,
.stTextInput input, .stTextInput textarea,
[data-testid="stChatInput"] textarea,
button, input, select, textarea {
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont,
               'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif !important;
  font-feature-settings: 'cv11', 'ss01';
  -webkit-font-smoothing: antialiased;
}

.stApp {
  background-color: var(--bg) !important;
  color: var(--text);
}

header[data-testid="stHeader"] {
  background: transparent !important;
}

/* Nuke the entire right-side header chrome: Deploy button, main menu,
   status widget, header actions. This is a fully local chatbot —
   nothing to deploy. The sidebar toggle lives outside the toolbar so
   it's unaffected. */
[data-testid="stToolbar"],
[data-testid="stToolbarActions"],
[data-testid="stHeaderActionElements"],
[data-testid="stHeaderActions"],
[data-testid="stStatusWidget"],
[data-testid="stDeployButton"],
[data-testid="stMainMenu"],
header [data-testid*="Deploy"],
header [data-testid*="deploy"],
header button[title*="Deploy"],
header button[title*="deploy"],
header a[title*="Deploy"],
.stDeployButton {
  display: none !important;
  visibility: hidden !important;
  width: 0 !important;
  height: 0 !important;
  pointer-events: none !important;
}

/* Force-show the native sidebar toggle controls if they exist. */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
button[kind="headerNoPadding"] {
  display: inline-flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  z-index: 1000 !important;
}

/* Collapse button: just the chevron, no white pill / box / shadow. */
[data-testid="stSidebarCollapseButton"],
section[data-testid="stSidebar"] button[kind="header"] {
  background: transparent !important;
  color: #0C5BA8 !important;
  border: none !important;
  box-shadow: none !important;
  padding: 4px !important;
  align-items: center !important;
  justify-content: center !important;
}

[data-testid="stSidebarCollapseButton"]:hover,
section[data-testid="stSidebar"] button[kind="header"]:hover {
  background: transparent !important;
  opacity: 0.65 !important;
}

[data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebarCollapseButton"] span,
section[data-testid="stSidebar"] button[kind="header"] svg {
  color: #0C5BA8 !important;
  fill: #0C5BA8 !important;
  stroke: #0C5BA8 !important;
}

.main .block-container {
  padding-top: 2rem !important;
  padding-bottom: 9rem !important;
  padding-left: 3rem !important;
  padding-right: 3rem !important;
  max-width: 100% !important;
}

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {
  background-color: var(--panel) !important;
  border-right: 1px solid var(--border);
}

/* Pull the sidebar's first child flush to the top so the logo can sit
   high in the panel as requested. */
section[data-testid="stSidebar"] > div:first-child {
  padding-top: 0 !important;
}

.sidebar-logo {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 0 1rem 0.5rem 1rem;
  /* -42px was calibrated for the old 168px logo; the 120px logo is
     shorter and gets clipped into the header at that offset. */
  margin: -8px -0.5rem 0.25rem -0.5rem;
  border-bottom: 1px solid var(--border);
}

.sidebar-logo svg {
  width: 145px;
  height: auto;
  display: block;
}

/* ---------- App canvas clamp (Streamlit 1.58 sizing bug) ----------
   Streamlit 1.58 sizes stAppViewContainer from screen-derived
   dimensions instead of the window, so whenever the browser window is
   shorter than the physical screen (taskbar, non-maximized window)
   the canvas is TALLER than the window and stApp's overflow:hidden
   clips the bottom strip — including the sidebar's profile group.
   Clamp the canvas to the real viewport; inner scrollers handle
   overflow as designed. */
[data-testid="stAppViewContainer"] {
  height: 100vh !important;
  max-height: 100vh !important;
}

/* ---------- Claude-style sidebar layout (single inner scroller) ----
   Design contract, matching claude.ai's sidebar:
   - The sidebar itself NEVER scrolls (no outer scrollbar).
   - The recents list is the one flexible region: it absorbs exactly
     the leftover vertical space and scrolls internally.
   - Logo, "+ New Chat", RECENTS header, Memory, and the profile
     group (user-row + Sign out) are always visible; the profile is
     welded to the bottom.

   The recents list comes from st.container(height=320) in app.py;
   the inline 320px is overridden here (flex sizing wins via
   !important) so the region is elastic instead of fixed.

   Selectors are written for both sidebar DOM shapes: pre-1.58
   (stSidebarUserContent > stVerticalBlock) and 1.58+ (an anonymous
   wrapper div in between). */

/* 1. Sidebar column: fill and clip — no outer scrollbar, ever. */
[data-testid="stSidebarContent"] {
  display: flex !important;
  flex-direction: column !important;
  overflow: hidden !important;
}
[data-testid="stSidebarUserContent"] {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  overflow: hidden !important;
  /* Streamlit 1.58 ships ~6rem bottom padding here; with the sidebar
     height chain that renders as dead space under Sign out. */
  padding-bottom: 0.75rem !important;
}

/* 2. Height chain down to the main vertical block (covers the 1.58
   anonymous wrapper and the older direct-child shape). */
[data-testid="stSidebarUserContent"] > div {
  height: 100% !important;
}
[data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"],
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
  min-height: 0 !important;
}

/* 3. Fixed rows stay their natural size (logo, New Chat, header,
   Memory, profile) — never squashed by the flex column. */
[data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"] > *,
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] > * {
  flex: 0 0 auto;
}

/* 4. The recents wrapper is the elastic scroll region. Identified by
   containing chat-row buttons (key=f"open_chat_{cid}" → class
   st-key-open_chat_*). CRITICAL: the :has() must be anchored as a
   DIRECT CHILD of the sidebar's main vertical block — every chat
   row's own stLayoutWrapper also :has() an open_chat button, and an
   unanchored selector flattens all rows to height 0. Its inner
   stVerticalBlock carries st.container's inline height:320px —
   height:100% !important beats the inline style, and the region
   scrolls internally. */
[data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"]
  > [data-testid="stLayoutWrapper"]:has([class*="st-key-open_chat"]),
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"]
  > [data-testid="stLayoutWrapper"]:has([class*="st-key-open_chat"]) {
  flex: 1 1 0 !important;
  min-height: 0 !important;
}
[data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"]
  > [data-testid="stLayoutWrapper"]:has([class*="st-key-open_chat"]) > div,
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"]
  > [data-testid="stLayoutWrapper"]:has([class*="st-key-open_chat"]) > div {
  height: 100% !important;
  max-height: 100% !important;
  overflow-y: auto !important;
}

/* 5. Profile group welded to the bottom. With the outer scrollbar
   gone this is pure flex — no sticky, no viewport math, no JS. */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]
  > [data-testid="stVerticalBlock"] > *:has(.user-row),
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]
  > div > [data-testid="stVerticalBlock"] > *:has(.user-row) {
  margin-top: auto !important;
}

/* 6. Density pass — Claude-reference proportions. The recents region
   only gets whatever the fixed elements leave over, so the fixed
   elements must be compact: tight column gaps, single-line rows. */
[data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"],
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {
  gap: 0.25rem !important;
}

/* Chat rows: compact, single-line with ellipsis, left-aligned —
   like claude.ai's recents. Applies to the title button; the ×
   delete button stays its natural size beside it. */
section[data-testid="stSidebar"] [class*="st-key-open_chat"] button {
  justify-content: flex-start !important;
  text-align: left !important;
  min-height: 34px !important;
  padding: 0.2rem 0.6rem !important;
}
section[data-testid="stSidebar"] [class*="st-key-open_chat"] button p {
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  max-width: 100% !important;
  /* The button aligns flex-start, but the inner <p> carries its own
     centering — both must be left for the Claude-style row. */
  text-align: left !important;
}
section[data-testid="stSidebar"] [class*="st-key-del_chat"] button {
  min-height: 34px !important;
  padding: 0.2rem 0.4rem !important;
}

/* Tighter vertical rhythm between rows inside the recents scroller. */
[data-testid="stSidebarUserContent"] [data-testid="stLayoutWrapper"]:has([class*="st-key-open_chat"])
  [data-testid="stVerticalBlock"] {
  gap: 0.125rem !important;
}

.recents-header {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #9CA3AF;
  padding: 6px 8px 2px 8px;
  margin-top: 0;
}

/* JS-injected chip rail sitting just above the textarea inside the
   chat input container. Streamlit styles direct children of
   stChatInput as input boxes (white bg + border + shadow); we
   explicitly strip that so the rail blends in as a thin pill row. */
.cc-chip-rail {
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  padding: 6px 12px 0 12px !important;
  margin: 0 !important;
  min-height: 0 !important;
}



/* DOCX preview body styling. */
.docx-preview {
  font-size: 0.95rem;
  line-height: 1.6;
  padding: 0.5rem 0.25rem;
  color: var(--text);
  max-height: 70vh;
  overflow-y: auto;
}

/* Hide the file_uploader widget entirely — we trigger its hidden
   <input type="file"> via a paperclip button injected into the chat bar.
   The element must stay in the DOM so Streamlit's submit pipeline works. */
[data-testid="stFileUploader"] {
  position: absolute !important;
  left: -9999px !important;
  width: 1px !important;
  height: 1px !important;
  overflow: hidden !important;
  visibility: hidden !important;
  pointer-events: none !important;
}

.user-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.6rem 0.5rem 0.35rem 0.5rem;
  border-top: 1px solid var(--border);
  margin-top: 0.5rem;
}

.user-row .left {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  color: var(--text);
  font-size: 0.9rem;
  font-weight: 500;
}

.user-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--primary);
  color: white;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.82rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.user-row .gear {
  color: var(--muted);
  font-size: 1rem;
  cursor: pointer;
  padding: 0.25rem;
}

.user-row .gear:hover {
  color: var(--text);
}

/* ---------- Hero (centered) ---------- */
.hero {
  text-align: center;
  padding-top: 22vh;
  padding-bottom: 1rem;
}

.hero-title {
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--text);
  margin: 0;
  letter-spacing: -0.025em;
  line-height: 1.1;
}

.hero-tagline {
  margin: 0.65rem 0 2rem 0;
  color: var(--text);
  font-size: 1rem;
  font-weight: 400;
}

.hero-tip {
  color: var(--muted);
  font-size: 0.875rem;
  margin: 0 auto 1.5rem auto;
  max-width: 28rem;
  line-height: 1.55;
  font-weight: 400;
}

/* ---------- Privacy popover (operational pill) ---------- */
/* Center the popover under the hero. */
[data-testid="stPopover"] {
  display: flex !important;
  justify-content: center !important;
  margin-top: 0.25rem !important;
}

/* Style the popover trigger as a pill. */
[data-testid="stPopover"] > div > button,
[data-testid="stPopover"] > button {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 0.55rem !important;
  padding: 0.45rem 1.25rem !important;
  border-radius: 999px !important;
  border: 1px solid var(--border) !important;
  background: white !important;
  color: var(--muted) !important;
  font-size: 0.85rem !important;
  font-weight: 500 !important;
  font-family: 'Plus Jakarta Sans', sans-serif !important;
  box-shadow: none !important;
  width: auto !important;
  min-width: 0 !important;
  transition: all 0.15s ease !important;
}

[data-testid="stPopover"] > div > button:hover,
[data-testid="stPopover"] > button:hover {
  background: var(--panel) !important;
  border-color: var(--primary) !important;
  color: var(--text) !important;
}

/* Popover content panel: clean white card. */
[data-testid="stPopoverBody"] {
  background: white !important;
  border: 1px solid var(--border) !important;
  border-radius: 12px !important;
  padding: 1rem !important;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08) !important;
  min-width: 260px !important;
}

[data-testid="stPopoverBody"] h5 {
  margin-top: 0 !important;
  margin-bottom: 0.35rem !important;
  font-weight: 600 !important;
  color: var(--text) !important;
}

[data-testid="stPopoverBody"] button {
  background: transparent !important;
  color: var(--text) !important;
  border: 1px solid transparent !important;
  border-radius: 8px !important;
  text-align: left !important;
  justify-content: flex-start !important;
  padding: 0.5rem 0.65rem !important;
  font-weight: 500 !important;
  margin-top: 0.3rem !important;
}

[data-testid="stPopoverBody"] button:hover {
  background: var(--panel) !important;
  border-color: var(--border) !important;
}

/* ---------- Model picker popover ---------- */
/* Overrides applied only to the popover that contains our
   .cc-model-picker marker div. The mode-pill popover keeps the
   default styling above. */

/* Compact card sized to the reference (~340px), softer shadow,
   tighter padding. */
[data-testid="stPopoverBody"]:has(.cc-model-picker) {
  min-width: 340px !important;
  max-width: 380px !important;
  padding: 0.65rem !important;
  border-radius: 14px !important;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.08),
              0 2px 6px rgba(0, 0, 0, 0.04) !important;
}

/* Search input styled as a subtle rounded field, matching the
   reference's warm off-white background. */
[data-testid="stPopoverBody"]:has(.cc-model-picker)
  [data-testid="stTextInput"] input {
  background: #FAFAFA !important;
  border: 1px solid #EAEAEA !important;
  border-radius: 10px !important;
  padding: 0.5rem 0.85rem !important;
  font-size: 0.88rem !important;
}
[data-testid="stPopoverBody"]:has(.cc-model-picker)
  [data-testid="stTextInput"] input:focus {
  border-color: var(--primary) !important;
  background: white !important;
  box-shadow: 0 0 0 3px var(--primary-soft) !important;
}

/* Row buttons — compact, monospace filename, right-aligned size.
   No border by default; a soft grey highlight on hover. */
[data-testid="stPopoverBody"]:has(.cc-model-picker) button {
  background: transparent !important;
  color: var(--text) !important;
  border: 1px solid transparent !important;
  border-radius: 8px !important;
  padding: 0.5rem 0.65rem !important;
  margin-top: 0.15rem !important;
  font-family: 'Menlo', 'Consolas', 'Courier New', monospace !important;
  font-size: 0.82rem !important;
  font-weight: 500 !important;
  letter-spacing: 0 !important;
  white-space: pre !important;   /* preserve the alignment spaces in labels */
}
[data-testid="stPopoverBody"]:has(.cc-model-picker) button:hover {
  background: #F5F5F5 !important;
  border-color: #EEEEEE !important;
}

/* Selected row — subtle blue tint, no bright primary fill. */
[data-testid="stPopoverBody"]:has(.cc-model-picker)
  button[kind="primary"] {
  background: var(--primary-soft) !important;
  color: var(--primary) !important;
  border-color: var(--primary-soft) !important;
}
[data-testid="stPopoverBody"]:has(.cc-model-picker)
  button[kind="primary"]:hover {
  background: #C5DBEE !important;
}

/* Empty state — centered muted text with a subtle code chip. */
.cc-model-empty {
  color: var(--muted);
  font-size: 0.85rem;
  text-align: center;
  padding: 1.5rem 0.5rem;
  line-height: 1.55;
}
.cc-model-empty .cc-code {
  background: #F1F3F5;
  color: #4A5568;
  padding: 0.1rem 0.4rem;
  border-radius: 5px;
  font-family: 'Menlo', 'Consolas', monospace;
  font-size: 0.8rem;
}

/* ---------- Chat input ---------- */
[data-testid="stChatInput"] {
  background: var(--bg) !important;
  border-top: none !important;
  padding: 0 6% 1.5rem 6% !important;
}

[data-testid="stChatInput"] > div {
  border: 1px solid var(--border) !important;
  border-radius: 16px !important;
  background: var(--bg) !important;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03), 0 4px 12px rgba(0, 0, 0, 0.02) !important;
  height: auto !important;
  min-height: 0 !important;
  max-height: none !important;
  /* Anchor for the absolutely-positioned send button overlay (and a
     deterministic anchor for the JS-injected paperclip/model pill,
     which otherwise rely on JS setting this at runtime). */
  position: relative !important;
}

[data-testid="stChatInput"] {
  height: auto !important;
  min-height: 0 !important;
}

/* Wrappers stay content-sized (defensive; verified no inline heights
   in practice). */
[data-testid="stChatInput"] > div div {
  height: auto !important;
  min-height: 0 !important;
}

/* Kill the empty band under the textarea. DOM inspection (2026-07)
   showed the pill contains a COLUMN with two rows: the textarea row
   and a 32px row holding only the send button — Streamlit's designed
   multiline layout. Since our paperclip/model-pill overlay elsewhere,
   that second row reads as dead space. Fix: float the send row as a
   bottom-right overlay so the pill hugs the text. The selector is
   structural (first content column → its last child = the send
   container in BOTH single-line and multiline layouts), not tied to
   Streamlit's unstable emotion class hashes. */
[data-testid="stChatInput"] > div > div:first-child {
  /* Must NOT be a positioned ancestor — the send overlay anchors to
     the PILL (see above) so its inset is measured from the pill's
     rounded corner, not from the inner content column. */
  position: static !important;
}
/* Send control: vertically CENTERED at the right edge, matching the
   paperclip/model-pill cluster, instead of hanging at the bottom
   corner detached from the input surface. */
[data-testid="stChatInput"] > div > div:first-child > div:last-child {
  position: absolute !important;
  right: 12px !important;
  top: 50% !important;
  bottom: auto !important;
  transform: translateY(-50%) !important;
  height: auto !important;
  width: auto !important;
  margin: 0 !important;
}

/* The grey input surface must span the full pill width so the whole
   control cluster (paperclip, model pill, send) sits ON it as one
   continuous surface — Streamlit otherwise reserves a right-side
   strip for the send button it thinks is still in the flow. */
[data-testid="stChatInput"] [data-baseweb="textarea"],
[data-testid="stChatInput"] [data-baseweb="base-input"] {
  width: 100% !important;
  flex: 1 1 auto !important;
  max-width: none !important;
}

[data-testid="stChatInput"] textarea {
  background: transparent !important;
  color: var(--text) !important;
  font-size: 0.95rem !important;
  /* Reserve room on the right for the absolutely-positioned controls.
     The paperclip is the leftmost control: right:280px + 26px width
     = text must clear 306px from the right edge. 20rem = 320px gives
     a 14px gap. (17rem = 272px caused text to run under the clip.) */
  padding: 0.6rem 20rem 0.6rem 1.4rem !important;
  /* Force very long UNBREAKABLE strings (e.g. a pasted token with no
     spaces) to wrap. Without this the textarea overflows horizontally
     and confuses Streamlit's auto-grow, producing a runaway-tall box.
     NOTE: no min/max-height overrides here — Streamlit's auto-grow JS
     measures the textarea and sizes the surrounding pill from that
     measurement; overriding heights in CSS desyncs the two and leaves
     dead space inside the pill. Wrapping alone fixes the root cause. */
  overflow-wrap: anywhere !important;
  word-break: break-word !important;
}

[data-testid="stChatInput"] textarea::placeholder {
  color: var(--muted) !important;
  font-weight: 400;
}

[data-testid="stChatInput"] button {
  background: var(--primary) !important;
  color: white !important;
  border-radius: 999px !important;
  border: none !important;
  transition: background 0.15s ease;
}

[data-testid="stChatInput"] button:hover {
  background: var(--primary-dark) !important;
}

/* ---------- Selection ---------- */
::selection {
  background: var(--primary-soft);
  color: var(--text);
}

/* ============================================================ */
/* Login / signup page                                          */
/* ============================================================ */
.login-card {
  background: white;
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 2rem 2rem 1.25rem 2rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06),
              0 2px 6px rgba(0, 0, 0, 0.04);
  margin-top: 10vh;
  margin-bottom: 1.5rem;
}

/* Hide Streamlit's "Press Enter to submit form" hint that floats off
   the right edge of text inputs inside a form. */
[data-testid="InputInstructions"],
[data-testid="stWidgetInstructions"] {
  display: none !important;
}

.login-logo {
  display: flex;
  justify-content: center;
  margin-bottom: 0.25rem;
}

.login-logo svg {
  width: 130px;
  height: auto;
  display: block;
}

.login-title {
  text-align: center;
  font-size: 1.7rem;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.02em;
  margin-top: 0.4rem;
}

.login-subtitle {
  text-align: center;
  color: var(--muted);
  font-size: 0.9rem;
  margin-top: 0.25rem;
  margin-bottom: 0;
}

.form-label {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text);
  margin: 0.85rem 0 0.35rem 0;
  letter-spacing: 0.01em;
}

/* Style the inputs on the login form. */
[data-testid="stTextInput"] input {
  background: var(--panel) !important;
  border: 1px solid var(--border) !important;
  border-radius: 10px !important;
  padding: 0.55rem 0.85rem !important;
  font-size: 0.95rem !important;
  color: var(--text) !important;
  transition: border-color 0.15s ease, background 0.15s ease !important;
}

[data-testid="stTextInput"] input:focus {
  border-color: var(--primary) !important;
  background: white !important;
  box-shadow: 0 0 0 3px var(--primary-soft) !important;
  outline: none !important;
}

/* Primary form submit (Sign In / Create Account). */
[data-testid="stForm"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {
  background: var(--primary) !important;
  color: white !important;
  border: none !important;
  border-radius: 10px !important;
  padding: 0.65rem 1rem !important;
  font-weight: 600 !important;
  font-size: 0.95rem !important;
  margin-top: 1.25rem !important;
  transition: background 0.15s ease !important;
}

[data-testid="stForm"] button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
  background: var(--primary-dark) !important;
}

/* Small "Create one" / "Sign in" toggle link below the form. */
[data-testid="stCaptionContainer"] + [data-testid="stButton"] button {
  background: transparent !important;
  color: var(--primary) !important;
  border: none !important;
  padding: 0.15rem 0.25rem !important;
  font-weight: 500 !important;
  font-size: 0.85rem !important;
  text-decoration: underline !important;
  box-shadow: none !important;
  width: auto !important;
}

/* Sign-out button in the sidebar. */
section[data-testid="stSidebar"] [data-testid="stButton"] button {
  background: transparent !important;
  color: var(--muted) !important;
  border: 1px solid transparent !important;
  border-radius: 8px !important;
  padding: 0.45rem 0.75rem !important;
  font-size: 0.85rem !important;
  font-weight: 500 !important;
  margin-top: 0.4rem !important;
  text-align: left !important;
}

section[data-testid="stSidebar"] [data-testid="stButton"] button:hover {
  background: var(--panel-2) !important;
  color: var(--text) !important;
  border-color: var(--border) !important;
}

/* Version tag in the bottom-right corner of the login page. */
.version-tag {
  position: fixed;
  bottom: 12px;
  right: 18px;
  color: var(--muted);
  font-size: 0.72rem;
  font-weight: 500;
  letter-spacing: 0.04em;
  pointer-events: none;
}

/* Streamlit paints a white background on the sticky bottom container
   that wraps st.chat_input — it creates a horizontal white strip
   between the hero gradient and the chat input bar. Strip it from
   every level of the wrapper tree so the background orbs/gradient
   extend cleanly down to the input bar. */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottom"] > div > div,
[data-testid="stBottom"] > div > div > div,
[data-testid="stBottomBlockContainer"],
[data-testid="stBottomBlockContainer"] > div,
[data-testid="stBottomBlockContainer"] > div > div,
[data-testid="stChatInputContainer"],
.stBottom,
.stBottomContainer,
.stBottomBlockContainer,
.stChatFloatingInputContainer,
section.main > div:last-child,
section.main > div:last-child > div:last-child,
section[data-testid="stMain"] > div:last-child,
section[data-testid="stMain"] > div:last-child > div:last-child {
  background: transparent !important;
  background-color: transparent !important;
  background-image: none !important;
}
</style>
"""
