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

// File Settings
export const MAX_FILE_SIZE_MB = 10;
export const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

// Text Decoder (can be instantiated where needed or passed)
// export const textDecoder = new TextDecoder();

// Marked.js Renderer Configuration (can be done in app.js or ui.js)
// Helper function for basic HTML escaping within code
function escapeHtml(html) {
    // Ensure input is a string
    const strHtml = String(html);
    return strHtml
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// Create a custom renderer
export const markedRenderer = new marked.Renderer();

markedRenderer.code = function(code, language) {
    let codeString = typeof code === 'object' && code !== null && typeof code.text === 'string' ? code.text : String(code);
    const escapedCode = escapeHtml(codeString);
    return `<pre class="bg-gray-800 text-white p-2 rounded mt-1 overflow-x-auto text-sm font-mono"><code>${escapedCode}</code></pre>`;
};

markedRenderer.codespan = function(text) {
    let textString = typeof text === 'object' && text !== null && typeof text.text === 'string' ? text.text : String(text);
    const escapedText = escapeHtml(textString);
    return `<code class="bg-gray-200 px-1 rounded text-sm font-mono">${escapedText}</code>`;
};

// Marked.js Options (to be used with marked.setOptions)
export const markedOptions = {
    renderer: markedRenderer,
    breaks: true,
    gfm: true // Ensure GitHub Flavored Markdown is enabled
};
