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
import { escapeHtml } from './utils.js'; // Make sure escapeHtml is available

// Create a custom renderer
export const markedRenderer = new marked.Renderer();
const originalCodeRenderer = markedRenderer.code.bind(markedRenderer);

markedRenderer.code = function(code, language, isEscaped) {
    let codeString = String(code); // Ensure it's a string

    // Check for Draw.io XML signature
    const isDrawioXml = /<(diagram|mxGraphModel)(\s|>)/.test(codeString);

    if (isDrawioXml) {
        // Prepare data for GraphViewer.processElements()
        // viewer.min.js expects the raw XML data in the attribute.
        // WARNING: This assumes the XML doesn't contain characters that break HTML attributes (like quotes).
        // If issues arise, we might need to escape quotes specifically or use a different embedding method.
        const rawXmlData = codeString;

        // Return the specific div structure with raw XML
        return `<div class="mxgraph my-4 border border-gray-300 rounded"
                     style="min-height: 150px; max-width: 100%;"
                     data-mxgraph="${rawXmlData}">
                     <p class="text-center text-gray-500 p-4">Processing diagram...</p>
                </div>`;
    } else {
        // Fallback for non-Draw.io code blocks: Basic escaping and pre/code tags.
        // Check if 'code' is actually a string before processing.
        if (typeof code !== 'string') {
            console.warn("[Marked Renderer] Received non-string code for fallback:", code);
            codeString = JSON.stringify(code); // Attempt to stringify if not a string
        }
        const escapedCode = escapeHtml(codeString);
        return `<pre class="bg-gray-800 text-white p-2 rounded mt-1 overflow-x-auto text-sm font-mono"><code>${escapedCode}\n</code></pre>`;
    }
};

// Marked.js Options (to be used with marked.setOptions)
// We pass the renderer directly in ui.js now, so this isn't strictly needed,
// but keep basic options.
export const markedOptions = {
    // renderer: markedRenderer, // Renderer is applied in ui.js
    breaks: true,
    gfm: true // Ensure GitHub Flavored Markdown is enabled
};
