// js/config.js

// LocalStorage Keys
export const SIDEBAR_COLLAPSED_KEY = 'sidebarCollapsed';
export const PLUGINS_COLLAPSED_KEY = 'pluginsCollapsed';
export const FILE_PLUGIN_COLLAPSED_KEY = 'filePluginCollapsed';
export const CALENDAR_PLUGIN_COLLAPSED_KEY = 'calendarPluginCollapsed';
export const STREAMING_ENABLED_KEY = 'streamingEnabled';
export const FILES_PLUGIN_ENABLED_KEY = 'filesPluginEnabled';
export const CALENDAR_PLUGIN_ENABLED_KEY = 'calendarPluginEnabled';
export const WEB_SEARCH_PLUGIN_ENABLED_KEY = 'webSearchPluginEnabled';
export const ACTIVE_TAB_KEY = 'activeTab';
export const CURRENT_NOTE_ID_KEY = 'currentNoteId';
export const CURRENT_NOTE_MODE_KEY = 'currentNoteMode';
// --- NEW KEY ---
export const HISTORY_PLUGIN_COLLAPSED_KEY = 'historyPluginCollapsed';
export const NOTES_TOC_COLLAPSED_KEY = 'notesTocCollapsed';
// ---------------

// File Settings
export const MAX_FILE_SIZE_MB = 10;
export const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

// Text Decoder (can be instantiated where needed or passed)
// export const textDecoder = new TextDecoder();

// Marked.js Renderer Configuration (can be done in app.js or ui.js)
// Import escapeHtml from utils.js
// import { escapeHtml } from './utils.js'; // No longer needed here

// REMOVED Custom Renderer Definition from config.js
// The custom renderer is now defined and used directly in ui.js

// Marked.js Options (to be used with marked.setOptions)
// We don't set a default renderer here anymore.
// The custom renderer is passed directly in ui.js where marked.parse is called.
export const markedOptions = {
    breaks: true,
    gfm: true // Ensure GitHub Flavored Markdown is enabled
};
