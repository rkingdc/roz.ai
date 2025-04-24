
let toastContainer = null; // Module-level variable to hold the container
let toastCounter = 0;

// --- REMOVED Self-Initialization ---

/**
 * Initializes the toast notification system with a container element.
 * MUST be called after the container element exists in the DOM.
 * @param {HTMLElement} containerElement - The DOM element to append toasts to.
 */
export function initializeToastContainer(containerElement) { // Added export back
    if (!containerElement) {
        console.error("[DEBUG] initializeToastContainer: containerElement parameter was null or undefined.");
    }
    toastContainer = containerElement;
    // Log whether the assignment was successful
    if (toastContainer) {
        console.log("[DEBUG] Toast container initialized successfully via initializeToastContainer:", toastContainer);
    } else {
        console.error("[DEBUG] Toast container initialization FAILED via initializeToastContainer. toastContainer variable is still null.");
    }
}

/**
 * Displays a toast notification.
 * @param {string} content - The HTML or text content of the toast.
 * @param {object} [options={}] - Options for the toast.
 * @param {'info' | 'success' | 'warning' | 'error'} [options.type='info'] - Toast type for styling.
 * @param {number | false} [options.autoClose=5000] - Duration in ms before auto-closing. False to disable.
 * @returns {string | null} The unique ID of the created toast, or null if container not ready.
 */
export function showToast(content, options = {}) {
    // ADD LOG: Check the current value of the module-level variable when showToast is called
    console.log(`[DEBUG] showToast entered. Current toastContainer value:`, toastContainer);
    if (!toastContainer) {
        console.error("Toast container not initialized. Call initializeToastContainer first.");
        return null;
    }
    console.log(`[DEBUG] showToast called. Content: "${content.substring(0,50)}...", Options:`, options); // Add log

    const { type = 'info', autoClose = 5000 } = options; // Default autoClose to 5s
    const toastId = `toast-${toastCounter++}`;

    const toastElement = document.createElement('div');
    toastElement.id = toastId;
    toastElement.dataset.toastId = toastId; // Store ID for removal
    // Base classes
    let classes = 'toast p-3 rounded shadow-md text-sm max-w-sm mb-2';
    // Get color info
    const colorInfo = getToastColorInfo(type);

    // Apply background color
    if (colorInfo.variable) {
        toastElement.style.backgroundColor = `var(${colorInfo.variable})`;
    } else if (colorInfo.class) {
        classes += ` ${colorInfo.class}`;
    }

    // Apply text color class
    classes += ` ${colorInfo.textColorClass}`;

    toastElement.className = classes;
    toastElement.setAttribute('role', 'alert');
    toastElement.innerHTML = content; // Allow HTML content for buttons

    // Prepend toast so newest appears on top (optional, could append)
    toastContainer.prepend(toastElement);
    console.log(`[DEBUG] Toast ${toastId} added to container.`); // Add log

    // Auto-close logic (unless autoClose is false or 0)
    if (autoClose !== false && autoClose > 0) {
        setTimeout(() => {
            removeToast(toastId);
        }, autoClose);
    }

    return toastId; // Return the ID so it can be managed (e.g., for persistent toasts)
}

/**
 * Removes a toast notification by its ID.
 * @param {string} toastId - The ID of the toast to remove.
 */
export function removeToast(toastId) { // Added export keyword
    if (!toastContainer || !toastId) return;
    const toastElement = toastContainer.querySelector(`#${toastId}`);
    if (toastElement) {
        console.log(`[DEBUG] Removing toast ${toastId}`); // Add log
        // Optional: Add fade-out animation class
        toastElement.classList.add('animate-fadeOut'); // Assuming you define a fadeOut animation
        // Remove after animation or timeout
        setTimeout(() => {
             if (toastElement.parentNode === toastContainer) { // Check if still attached
                 toastContainer.removeChild(toastElement);
             }
        }, 500); // Adjust timeout based on animation duration (e.g., 0.5s)
    } else {
        console.warn(`[DEBUG] removeToast: Toast with ID ${toastId} not found.`); // Add log
    }
}

/**
 * Updates the content of an existing toast.
 * @param {string} toastId - The ID of the toast to update.
 * @param {string} newContent - The new HTML or text content.
 */
export function updateToast(toastId, newContent) { // Added export keyword
     if (!toastContainer || !toastId) return;
     const toastElement = toastContainer.querySelector(`#${toastId}`);
     if (toastElement) {
         toastElement.innerHTML = newContent;
         console.log(`[DEBUG] Updated toast ${toastId}`); // Add log
     } else {
         console.warn(`[DEBUG] updateToast: Toast with ID ${toastId} not found.`); // Add log
     }
}

/**
 * Gets the background color class based on the toast type.
 * Uses CSS variables defined in style.css :root.
 * Gets the background color (CSS variable or class) and text color class based on the toast type.
 * @param {'info' | 'success' | 'warning' | 'error'} type - The toast type.
 * @returns {{variable: string|null, class: string|null, textColorClass: string}} Color information.
 */
function getToastColorInfo(type) {
    // Default text color
    let textColorClass = 'text-white'; // Default text color

    switch (type) {
        case 'success':
            // Use Gold background, Dark Maroon text
            textColorClass = 'text-[--rz-toolbar-field]'; // Use CSS var for text color
            return { variable: '--rz-toolbar-text', class: null, textColorClass: textColorClass };
        case 'warning':
             // Use Gold background, Dark Maroon text (same as success for now)
            textColorClass = 'text-[--rz-toolbar-field]'; // Use CSS var for text color
            return { variable: '--rz-toolbar-text', class: null, textColorClass: textColorClass };
        case 'error':
            // Keep distinct red background for errors, white text
            return { variable: null, class: 'bg-red-600', textColorClass: 'text-white' };
        case 'info':
        default:
            // Use Maroon background, white text
            return { variable: '--rz-toolbar-opaque', class: null, textColorClass: 'text-white' };
    }
    // --- Old implementation using Tailwind classes ---
    // switch (type) {
    //     case 'success': return 'bg-green-600';
    //     case 'error': return 'bg-red-600';
    //     case 'warning': return 'bg-yellow-500 text-black'; // Needs specific text color
    //     case 'info': default: return 'bg-blue-600';
    // }
    // --- If using CSS variables for background ---
    // switch (type) {
    //     case 'success': return 'var(--rz-success-bg)'; // Define --rz-success-bg etc.
    //     case 'error': return 'var(--rz-error-bg)';
    //     case 'warning': return 'var(--rz-warning-bg)';
    //     case 'info': default: return 'var(--rz-info-bg)'; // e.g., map to --rz-toolbar-opaque
    // }
    // And then apply with toastElement.style.backgroundColor = getToastBgColor(type);
}

// --- Optional: Add fade-out animation ---
// You would need to add this keyframes rule to your style.css
/*
@keyframes fadeOut {
    from { opacity: 1; }
    to { opacity: 0; }
}
.animate-fadeOut {
    animation: fadeOut 0.5s ease-out forwards;
}
*/
