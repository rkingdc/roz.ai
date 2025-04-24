
let toastContainer = null;
let toastCounter = 0;

/**
 * Initializes the toast notification system with a container element.
 * @param {HTMLElement} containerElement - The DOM element to append toasts to.
 */
export function initializeToastContainer(containerElement) {
    if (!containerElement) {
        console.error("Toast container element not provided or not found.");
        // Optionally create one dynamically if needed
        // containerElement = document.createElement('div');
        // containerElement.id = 'toast-container';
        // containerElement.className = 'fixed bottom-5 right-5 z-50 space-y-2 w-auto max-w-sm'; // Match HTML
        // document.body.appendChild(containerElement);
    }
    toastContainer = containerElement;
    console.log("[DEBUG] Toast container initialized:", toastContainer); // Add log
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
    // Apply base and type-specific styles using theme variables
    toastElement.className = `toast p-3 rounded shadow-md text-sm max-w-sm mb-2 ${getToastBgColor(type)} text-white`; // Added mb-2 for spacing
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
 * @param {'info' | 'success' | 'warning' | 'error'} type - The toast type.
 * @returns {string} Tailwind background color class.
 */
function getToastBgColor(type) {
    // Using Tailwind classes directly for simplicity here.
    // You could map these to your --rz variables if preferred,
    // but that would require setting background-color directly via style attribute.
    switch (type) {
        case 'success': return 'bg-green-600'; // Example: Green
        case 'error': return 'bg-red-600';     // Example: Red
        case 'warning': return 'bg-yellow-500 text-black'; // Example: Yellow (added text-black)
        case 'info':
        default: return 'bg-blue-600';      // Example: Blue
    }
    // If using CSS variables:
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
