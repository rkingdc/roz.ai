// js/config.js
import { marked } from 'https://cdn.jsdelivr.net/npm/marked/lib/marked.esm.js';

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
    console.log('[DEBUG Marked Renderer] code() called. Language param:', language, '(type:', typeof language, '), Code (start):', String(code).substring(0, 70), 'IsEscaped:', isEscaped);

    // Extract the actual code text, handling potential object input from marked
    let codeString = '';
    let detectedLang = language; // Prioritize the language parameter

    if (typeof code === 'object' && code !== null) {
        if (typeof code.text === 'string') {
            codeString = code.text;
        } else {
            codeString = String(code); // Fallback if code.text is not a string
        }
        // If language parameter is undefined, check if the code object has a lang property
        if (detectedLang === undefined && typeof code.lang === 'string') {
            console.log('[DEBUG Marked Renderer] Language param was undefined, using code.lang:', code.lang);
            detectedLang = code.lang;
        }
    } else {
        codeString = String(code); // Fallback to string conversion if code is not an object
    }


    // The 'language' parameter from marked.js indicates the fenced language.
    // Ensure it's a string and clean it up.
    const lang = (typeof detectedLang === 'string' ? detectedLang : '').toLowerCase().trim();
    console.log('[DEBUG Marked Renderer] Derived lang:', lang);

    // Check for Draw.io XML signature using the extracted string
    // Also check if the language is explicitly 'xml' or 'drawio' for Drawio diagrams
    const isDrawioXmlSignature = /<(diagram|mxGraphModel)(\s|>)/.test(codeString);
    const isDrawioLanguage = lang === 'xml' || lang === 'drawio';

    if (isDrawioXmlSignature || (isDrawioLanguage && codeString.includes('<mxfile'))) {
        // Prepare data for GraphViewer.processElements()
        const graphData = { xml: codeString };
        const jsonGraphData = JSON.stringify(graphData);
        const escapedJsonData = escapeHtml(jsonGraphData);

        // Return the specific div structure with the escaped JSON string in data-mxgraph
        return `<div class="mxgraph my-4 border border-gray-300 rounded"
                     style="min-height: 150px; max-width: 100%;"
                     data-mxgraph="${escapedJsonData}">
                     <p class="text-center text-gray-500 p-4">Processing diagram...</p>
                </div>`;
    } else {
        // For other languages, including Mermaid, use a standard <pre><code> structure
        // and ensure the language class is applied to the <code> element.
        const className = lang ? `language-${escapeHtml(lang)}` : '';
        console.log('[DEBUG Marked Renderer] Derived className for code block:', className);
        const escapedCode = escapeHtml(codeString);
        // Note: Marked.js usually handles escaping if isEscaped is false.
        // Here, we are manually escaping for safety.
        // The default renderer might do more sophisticated highlighting if we called it.
        // For simplicity and direct control for Mermaid, we construct it directly.
        return `<pre class="bg-gray-800 text-white p-2 rounded mt-1 overflow-x-auto text-sm font-mono"><code class="${className}">${escapedCode}\n</code></pre>`;
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
