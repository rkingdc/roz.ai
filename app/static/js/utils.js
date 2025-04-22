// js/utils.js

/**
 * Formats file size in bytes to a human-readable string (KB, MB, GB).
 * @param {number} bytes - The file size in bytes.
 * @returns {string} Human-readable file size.
 */
export function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Basic HTML escaping.
 * @param {string} html - The string to escape.
 * @returns {string} Escaped HTML string.
 */
export function escapeHtml(html) {
    const strHtml = String(html); // Ensure input is a string
    return strHtml
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Note: The marked.js renderer configuration is moved to config.js
// Note: updateStatus and setLoadingState are moved to ui.js as they directly manipulate the DOM.
