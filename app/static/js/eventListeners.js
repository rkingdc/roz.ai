// js/eventListeners.js
// This module sets up all event listeners and acts as the orchestrator.
// It captures user interactions, calls API functions or state setters,
// and subscribes UI rendering functions to state changes.

import { elements } from './dom.js';
import * as ui from './ui.js'; // Import ui to call rendering functions
import * as api from './api.js'; // Import api to call backend functions
import * as state from './state.js'; // Import state to update state directly for UI-only changes or read values
import * as config from './config.js'; // Import config
import * as voice from './voice.js'; // Import voice recording functions
import { MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB } from './config.js'; // Import file size constants
import { formatFileSize, debounce, escapeHtml } from './utils.js'; // Import debounce and escapeHtml
// --- NEW: Import toast functions ---
import { showToast, removeToast, updateToast } from './toastNotifications.js'; // Adjust path if needed
// -----------------------------------

/**
 * Sets up all event listeners for the application.
 * MUST be called after DOMContentLoaded and populateElements.
 */
export function setupEventListeners() {
    // --- Subscribe UI Renderers to State Changes ---
    subscribeStateChangeListeners();

    // --- Global Keyboard Shortcuts ---
    document.addEventListener('keydown', async (event) => {
        // Check for Ctrl+S or Cmd+S
        if ((event.ctrlKey || event.metaKey) && event.key === 's') {
            event.preventDefault(); // Prevent the default browser save action

            if (state.isLoading) {
                state.setStatusMessage("Cannot save while busy.", true);
                return;
            }

            if (state.currentTab === 'notes' && state.currentNoteId !== null) {
                await api.saveNote(); // Save the current note
                // --- NEW: Return focus to notes textarea after save ---
                elements.notesTextarea?.focus();
                // ----------------------------------------------------
            } else if (state.currentTab === 'chat' && state.currentChatId !== null) {
                 // Trigger the save chat name button click, which handles getting the name from the input
                 // Use the correct element reference from dom.js
                 if (elements.saveChatNameButton) {
                     elements.saveChatNameButton.click();
                     // --- NEW: Return focus to message input after save ---
                     elements.messageInput?.focus();
                     // ----------------------------------------------------
                 } else {
                     console.error("Save chat name button element not found!");
                     state.setStatusMessage("Error: Save button element missing.", true);
                 }
            }
            // else {
                // console.log("[DEBUG] Ctrl+S detected, but no active chat or note to save.");
                // state.setStatusMessage("Nothing to save.", true); // Avoid noisy status messages
            // }
        }

        // --- NEW: Notes Mode Switching Shortcuts ---
        if (state.currentTab === 'notes' && event.ctrlKey) {
            if (event.key === 'ArrowLeft') {
                event.preventDefault(); // Prevent potential browser back navigation
                elements.editNoteButton?.click(); // Switch to Edit mode
            } else if (event.key === 'ArrowRight') {
                event.preventDefault(); // Prevent potential browser forward navigation
                elements.viewNoteButton?.click(); // Switch to View mode
            }
        }
        // -----------------------------------------

        // --- NEW: Sidebar List Navigation Shortcuts (Ctrl + Up/Down) ---
        // Only handle this shortcut if the user is NOT currently typing in a text input or textarea
        const activeElement = document.activeElement;
        const isTypingInput = activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA');

        if ((event.ctrlKey || event.metaKey) && (event.key === 'ArrowUp' || event.key === 'ArrowDown') && !isTypingInput) {
            event.preventDefault(); // Prevent default scrolling behavior

            const currentTab = state.currentTab;
            let items = [];
            let currentId = null;
            let listElement = null;
            let idAttribute = '';
            let loadItemFunction = null; // Use API load function
            let itemClass = ''; // Class to select list items

            if (currentTab === 'chat') {
                listElement = elements.savedChatsList;
                currentId = state.currentChatId;
                idAttribute = 'chatId';
                loadItemFunction = api.loadChat; // Use loadChat API function
                itemClass = '.chat-list-item';
            } else if (currentTab === 'notes') {
                listElement = elements.savedNotesList;
                currentId = state.currentNoteId;
                idAttribute = 'noteId';
                loadItemFunction = api.loadNote; // Use loadNote API function
                itemClass = '.note-list-item';
            } else {
                // Not on a tab with a navigable list
                return;
            }

            // Ensure we have the list element and there are items in the list
            if (!listElement || listElement.children.length === 0) {
                 console.log(`[DEBUG] Keyboard navigation: No list element or list is empty for tab ${currentTab}.`);
                return;
            }

            // Get all list items
            items = Array.from(listElement.querySelectorAll(itemClass));

            // If no item is currently selected, find the index of the first/last item
            let currentIndex = -1;
            if (currentId !== null) {
                 currentIndex = items.findIndex(item => parseInt(item.dataset[idAttribute]) === currentId);
            }

            let newIndex = currentIndex;

            if (event.key === 'ArrowUp') {
                // If no item is selected, select the last one when pressing Up
                if (currentIndex === -1) {
                    newIndex = items.length - 1;
                } else {
                    newIndex = currentIndex - 1;
                }
            } else if (event.key === 'ArrowDown') {
                 // If no item is selected, select the first one when pressing Down
                 if (currentIndex === -1) {
                     newIndex = 0;
                 } else {
                     newIndex = currentIndex + 1;
                 }
            }

            // Check if the new index is within bounds
            if (newIndex >= 0 && newIndex < items.length) {
                const newItem = items[newIndex];
                const newId = parseInt(newItem.dataset[idAttribute]);

                // Load the new item using the API function
                if (loadItemFunction) {
                    console.log(`[DEBUG] Keyboard navigation: Loading new ${idAttribute} ${newId}`);
                    loadItemFunction(newId); // Call the API function
                    // State update and UI rendering will happen via API's state changes
                } else {
                     console.error(`API function to load ${idAttribute} is not available.`);
                }
            } else {
                // Boundary reached (top or bottom) - do nothing
                console.log(`[DEBUG] Keyboard navigation: Boundary reached. Current index: ${currentIndex}, New index attempt: ${newIndex}`);
            }
        }
        // -------------------------------------------------------------
    });
    // console.log("Global keyboard listeners set up.");


    // --- Chat Input & Sending ---
    elements.sendButton?.addEventListener('click', async () => {
        await api.sendMessage(); // Updates state (chatHistory, isLoading, statusMessage, sessionFile)
        // UI updates are triggered by state notifications within api.sendMessage
    });
    elements.messageInput?.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            await elements.sendButton?.click(); // Trigger send button click
        }
    });
  // --- UPDATED: Auto-resize textarea on input ---
  elements.messageInput?.addEventListener('input', () => {
      ui.autoResizeTextarea(elements.messageInput); // Call the reusable UI function
  });
  // --- NEW: Auto-resize textarea on paste ---
  elements.messageInput?.addEventListener('paste', () => {
      // Use setTimeout to allow the paste operation to complete before resizing
      setTimeout(() => {
          ui.autoResizeTextarea(elements.messageInput);
      }, 0);
  });
  // ------------------------------------------
    elements.modelSelector?.addEventListener('change', async () => {
        await api.handleModelChange(); // Updates state (currentChatModel, isLoading, statusMessage)
        // UI updates are triggered by state notifications within api.handleModelChange
    });
    elements.micButton?.addEventListener('click', () => {
        // console.log("[DEBUG] Chat Mic Button CLICKED!"); // Log mic click too
        if (state.currentTab !== 'chat') return; // Only allow in chat

        if (state.isRecording) {
            voice.stopRecording(); // Will update state internally
        } else {
            voice.startRecording('chat'); // Will update state internally
        }
        // UI updates are triggered by state notifications (isRecording)
    });

    // --- Chat Cleanup Button Listener ---
    const chatCleanupButton = elements.cleanupTranscriptButton;
    if (chatCleanupButton) {
        // console.log("[DEBUG] Attaching mousedown/click listeners to Chat Cleanup Button:", chatCleanupButton);

        // Capture selection on mousedown
        chatCleanupButton.addEventListener('mousedown', (event) => {
            // Prevent the button click from stealing focus and clearing selection prematurely
            event.preventDefault();

            const inputField = elements.messageInput;
            if (inputField && inputField.selectionStart !== inputField.selectionEnd) {
                const selectionStart = inputField.selectionStart;
                const selectionEnd = inputField.selectionEnd;
                const selectedText = inputField.value.substring(selectionStart, selectionEnd);
                // Store selection details on the button element itself
                chatCleanupButton.dataset.selectedTextForCleanup = selectedText;
                chatCleanupButton.dataset.selectionStart = selectionStart;
                chatCleanupButton.dataset.selectionEnd = selectionEnd;
                // console.log(`[DEBUG] Chat mousedown: Stored selected text: "${selectedText}"`);
            } else {
                // Clear stored data if no selection on mousedown
                delete chatCleanupButton.dataset.selectedTextForCleanup;
                delete chatCleanupButton.dataset.selectionStart;
                delete chatCleanupButton.dataset.selectionEnd;
            }
        });

        chatCleanupButton.addEventListener('click', async () => {
            // Log button state *immediately* on click attempt
            // console.log(`[DEBUG] Chat Cleanup Button CLICKED! Disabled: ${chatCleanupButton.disabled}`);

            // Read selection details stored during mousedown
            const selectedText = chatCleanupButton.dataset.selectedTextForCleanup;
            const selectionStart = parseInt(chatCleanupButton.dataset.selectionStart, 10);
            const selectionEnd = parseInt(chatCleanupButton.dataset.selectionEnd, 10);

            // Clear the stored data immediately after reading
            delete chatCleanupButton.dataset.selectedTextForCleanup;
            delete chatCleanupButton.dataset.selectionStart;
            delete chatCleanupButton.dataset.selectionEnd;

            // Check button state and if we actually captured text
            if (state.isLoading || chatCleanupButton.disabled || !elements.messageInput) { // Check the variable directly
                 // console.log(`[DEBUG] Chat Cleanup: Click ignored (isLoading: ${state.isLoading}, isDisabled: ${chatCleanupButton.disabled}, hasInput: ${!!elements.messageInput}).`);
                 return;
            }

            // Use the selectedText captured during mousedown
            if (!selectedText || isNaN(selectionStart) || isNaN(selectionEnd)) {
                // console.log("[DEBUG] Chat Cleanup: Click ignored (no text selected or indices missing from mousedown).");
                state.setStatusMessage("No text selected to clean.", true);
                // Ensure button is disabled if somehow clicked without selection
                if (elements.cleanupTranscriptButton) elements.cleanupTranscriptButton.disabled = true;
                return;
            }

            // Disable button during processing (handled by global isLoading state via ui.updateChatCleanupButtonState)
            // state.setIsLoading(true); // api.cleanupTranscript handles this

            // console.log(`[DEBUG] Chat Cleanup: Selected text: "${selectedText}"`);
            const inputField = elements.messageInput; // Get reference again
            // console.log(`[DEBUG] Chat Cleanup: Selected text from mousedown: "${selectedText}"`);
            try {
                // Call the existing API function with the selected text
                const cleanedText = await api.cleanupTranscript(selectedText);
                // console.log(`[DEBUG] Chat Cleanup: Received cleaned text: "${cleanedText}"`);

                // Get the potentially updated text *after* API call returns
                const currentFullText = inputField.value;

                // --- Smart Replacement (Basic) - Use indices from mousedown ---
                // Replace based on original indices. Assumes text outside selection didn't change drastically.
                const textBefore = currentFullText.substring(0, selectionStart);
                const textAfter = currentFullText.substring(selectionEnd);
                const newFullText = textBefore + cleanedText + textAfter;
                // console.log(`[DEBUG] Chat Cleanup: Replacing with new full text: "${newFullText}"`);

                // Update the input field directly
                // console.log("[DEBUG] Chat Cleanup: Replacing text in input field.");
                inputField.value = newFullText;

                // Restore selection around the newly inserted text (optional but good UX)
                inputField.focus();
                inputField.setSelectionRange(selectionStart, selectionStart + cleanedText.length);

                // Check if the text actually changed
                if (cleanedText === selectedText) {
                    state.setStatusMessage("Cleanup did not change the selected text.");
                } else {
                    state.setStatusMessage("Selected text cleaned.");
                }

            } catch (error) {
                // Error status is set by api.cleanupTranscript
                console.error("Error cleaning selected text:", error);
                // Optionally display a more specific error to the user if needed
            } finally {
                // Loading state is handled by api.cleanupTranscript
                // Re-evaluate button state after operation (selection might have changed)
                ui.updateChatCleanupButtonState();
            }
        });
    }

    // --- Chat Input Listeners for Cleanup Button State ---
    if (elements.messageInput) {
        const updateCleanupState = () => ui.updateChatCleanupButtonState(); // Alias for brevity
        // Update button state when selection changes within the document
        document.addEventListener('selectionchange', () => {
            // Check if the message input is the active element when selection changes
            if (document.activeElement === elements.messageInput) {
                // Log the button element reference *when selection changes*
                // console.log("[DEBUG] selectionchange (Chat): Checking chatCleanupButton ref:", elements.cleanupTranscriptButton);
                updateCleanupState();
            } else {
                // If selection changes outside the input, disable the button
                if (elements.cleanupTranscriptButton) elements.cleanupTranscriptButton.disabled = true;
            }
        });
        // Also update when typing or clicking within the input might clear selection
        elements.messageInput.addEventListener('input', updateCleanupState);
        elements.messageInput.addEventListener('click', updateCleanupState); // Handle clicks that might clear selection
        elements.messageInput.addEventListener('focus', updateCleanupState); // Update on focus
        elements.messageInput.addEventListener('blur', () => { // Disable when focus leaves
             if (elements.cleanupTranscriptButton) elements.cleanupTranscriptButton.disabled = true;
        });
    }
    // -------------------------------------------------------


    // --- Notes Textarea Listeners for Cleanup Button State ---
    if (elements.notesTextarea) {
        const updateCleanupState = () => ui.updateNotesCleanupButtonState(); // Alias for brevity
        // Update button state when selection changes within the document
        document.addEventListener('selectionchange', () => {
            // Check if the notes textarea is the active element when selection changes
            if (document.activeElement === elements.notesTextarea) {
                 // Log the button element reference *when selection changes*
                // console.log("[DEBUG] selectionchange (Notes): Checking notesCleanupButton ref:", elements.cleanupTranscriptButtonNotes);
                updateCleanupState();
            } else {
                // If selection changes outside the textarea, disable the button
                if (elements.cleanupTranscriptButtonNotes) elements.cleanupTranscriptButtonNotes.disabled = true;
            }
        });
        // Also update when typing or clicking within the textarea might clear selection
        elements.notesTextarea.addEventListener('input', updateCleanupState);
        elements.notesTextarea.addEventListener('click', updateCleanupState); // Handle clicks that might clear selection
        elements.notesTextarea.addEventListener('focus', updateCleanupState); // Update on focus
        elements.notesTextarea.addEventListener('blur', () => { // Disable when focus leaves
             if (elements.cleanupTranscriptButtonNotes) elements.cleanupTranscriptButtonNotes.disabled = true;
        });
        // Initial state check might be needed after elements are populated, or rely on tab switch
    }
    // -------------------------------------------------------

    elements.micButtonNotes?.addEventListener('click', () => {
        // console.log("[DEBUG] Notes Mic Button CLICKED!"); // Log mic click too
        if (state.currentTab !== 'notes') return; // Only allow in notes

        if (state.isRecording) {
            voice.stopRecording(); // Will update state internally
        } else {
            voice.startRecording('notes'); // Will update state internally
        }
        // UI updates are triggered by state notifications (isRecording)
    });

    // --- NEW: Listener for Long Record Button ---
    console.log("[DEBUG] Attempting to add listener to longRecButtonNotes. Element:", elements.longRecButtonNotes); // ADD LOGGING
    if (elements.longRecButtonNotes) {
        elements.longRecButtonNotes.addEventListener('click', () => {
            console.log("[DEBUG] Long Record Button CLICKED!"); // Keep this log
            if (state.currentTab !== 'notes') {
                console.log("[DEBUG] Long Record Button: Ignored (not on notes tab).");
                return;
            }
            // Button should be disabled if already active, but handle defensively
            if (!state.isLongRecordingActive) {
                console.log("[DEBUG] Long Record Button: Calling voice.startLongRecording()."); // Keep this log
                voice.startLongRecording();
            } else {
                console.warn("Long record button clicked while already active.");
                // Stop is handled via toast
            }
            // UI update happens via state change reaction in ui.js
        });
    } else {
        console.warn("Long Record button (notes) not found during listener setup.");
    }
    // -----------------------------------------


    // --- NEW: Delegated Listener for Toast Buttons ---
    console.log("[DEBUG] Attempting to add listener to toastContainer. Element:", elements.toastContainer); // ADD LOGGING
    if (elements.toastContainer) {
        elements.toastContainer.addEventListener('click', (event) => {
            console.log("[DEBUG] Click detected inside toast container. Target:", event.target);
            const stopLongRecButton = event.target.closest('.toast-stop-long-rec-button');
            const copyButton = event.target.closest('.toast-copy-button');
            const closeButton = event.target.closest('.toast-close-button'); // Find close button

            console.log("[DEBUG] stopLongRecButton found:", stopLongRecButton);
            console.log("[DEBUG] copyButton found:", copyButton);
            console.log("[DEBUG] closeButton found:", closeButton); // Log if close button found

            if (stopLongRecButton) {
                console.log("[DEBUG] Stop long recording button identified. Calling voice.stopLongRecording().");
                voice.stopLongRecording();
            } else if (copyButton) {
                console.log("[DEBUG] Copy transcript button identified.");
                const target = copyButton.dataset.transcriptTarget; // Check if it's for long transcript
                if (target === 'long') {
                    const transcriptToCopy = state.lastLongTranscript; // Get from state
                    if (transcriptToCopy) {
                        navigator.clipboard.writeText(transcriptToCopy)
                            .then(() => {
                                console.log("Long transcript copied to clipboard.");
                                copyButton.textContent = 'Copied!';
                                copyButton.disabled = true; // Keep disabled briefly for visual feedback
                                // --- REMOVED: Do not automatically remove toast after copy ---
                                // setTimeout(() => {
                                //     const toastElement = copyButton.closest('.toast');
                                //     if (toastElement && toastElement.dataset.toastId) {
                                //         removeToast(toastElement.dataset.toastId);
                                //     }
                                // }, 1000);
                                // ---------------------------------------------------------
                            })
                            .catch(err => {
                                console.error('Failed to copy long transcript: ', err);
                                showToast("Failed to copy transcript.", { type: 'error' });
                            });
                    } else {
                         console.warn("No long transcript found in state to copy.");
                         showToast("No transcript available to copy.", { type: 'warning' });
                    }
                }
                // Add else if for other potential copy targets if needed
            } else if (closeButton) { // Handle close button click
                console.log("[DEBUG] Close toast button identified.");
                const toastElement = closeButton.closest('.toast');
                if (toastElement && toastElement.dataset.toastId) {
                    console.log(`[DEBUG] Removing toast ID: ${toastElement.dataset.toastId}`);
                    removeToast(toastElement.dataset.toastId); // Remove the specific toast
                } else {
                    console.warn("[DEBUG] Could not find toast element or toast ID for close button.");
                }
            }
        });
    } else {
        console.warn("Toast container not found, cannot add delegated listener for toast buttons.");
    }
    // ----------------------------------------------


    // --- Notes Cleanup Button Listener ---
    const notesCleanupButton = elements.cleanupTranscriptButtonNotes;
    if (notesCleanupButton) {
        // console.log("[DEBUG] Attaching mousedown/click listeners to Notes Cleanup Button:", notesCleanupButton);

        // Capture selection on mousedown
        notesCleanupButton.addEventListener('mousedown', (event) => {
            // Prevent the button click from stealing focus and clearing selection prematurely
            event.preventDefault();

            const textarea = elements.notesTextarea;
            if (textarea && textarea.selectionStart !== textarea.selectionEnd) {
                const selectionStart = textarea.selectionStart;
                const selectionEnd = textarea.selectionEnd;
                const selectedText = textarea.value.substring(selectionStart, selectionEnd);
                // Store selection details on the button element itself
                notesCleanupButton.dataset.selectedTextForCleanup = selectedText;
                notesCleanupButton.dataset.selectionStart = selectionStart;
                notesCleanupButton.dataset.selectionEnd = selectionEnd;
                // console.log(`[DEBUG] Notes mousedown: Stored selected text: "${selectedText}"`);
            } else {
                // Clear stored data if no selection on mousedown
                delete notesCleanupButton.dataset.selectedTextForCleanup;
                delete notesCleanupButton.dataset.selectionStart;
                delete notesCleanupButton.dataset.selectionEnd;
            }
        });

        notesCleanupButton.addEventListener('click', async () => {
             // Log button state *immediately* on click attempt
            // console.log(`[DEBUG] Notes Cleanup Button CLICKED! Disabled: ${notesCleanupButton.disabled}`);

            // Read selection details stored during mousedown
            const selectedText = notesCleanupButton.dataset.selectedTextForCleanup;
            const selectionStart = parseInt(notesCleanupButton.dataset.selectionStart, 10);
            const selectionEnd = parseInt(notesCleanupButton.dataset.selectionEnd, 10);

            // Clear the stored data immediately after reading
            delete notesCleanupButton.dataset.selectedTextForCleanup;
            delete notesCleanupButton.dataset.selectionStart;
            delete notesCleanupButton.dataset.selectionEnd;

            // Check button state and if we actually captured text
            if (state.isLoading || notesCleanupButton.disabled || !elements.notesTextarea) { // Check the variable directly
                 // console.log(`[DEBUG] Notes Cleanup: Click ignored (isLoading: ${state.isLoading}, isDisabled: ${notesCleanupButton.disabled}, hasTextarea: ${!!elements.notesTextarea}).`);
                 return;
            }

            // Use the selectedText captured during mousedown
            if (!selectedText || isNaN(selectionStart) || isNaN(selectionEnd)) {
                // console.log("[DEBUG] Notes Cleanup: Click ignored (no text selected or indices missing from mousedown).");
                state.setStatusMessage("No text selected to clean.", true);
                // Ensure button is disabled if somehow clicked without selection
                if (elements.cleanupTranscriptButtonNotes) elements.cleanupTranscriptButtonNotes.disabled = true;
                return;
            }

            // Disable button during processing (handled by global isLoading state via ui.updateNotesCleanupButtonState)
            // state.setIsLoading(true); // api.cleanupTranscript handles this

            // console.log(`[DEBUG] Notes Cleanup: Selected text: "${selectedText}"`);
            const textarea = elements.notesTextarea; // Get reference again
            // console.log(`[DEBUG] Notes Cleanup: Selected text from mousedown: "${selectedText}"`);
            try {
                // Call the existing API function with the selected text
                const cleanedText = await api.cleanupTranscript(selectedText);
                // console.log(`[DEBUG] Notes Cleanup: Received cleaned text: "${cleanedText}"`);

                // Get the potentially updated text *after* API call returns
                const currentFullText = textarea.value;

                // --- Smart Replacement (Basic) - Use indices from mousedown ---
                // Replace based on original indices. Assumes text outside selection didn't change drastically.
                const textBefore = currentFullText.substring(0, selectionStart);
                const textAfter = currentFullText.substring(selectionEnd);
                const newFullText = textBefore + cleanedText + textAfter;
                // console.log(`[DEBUG] Notes Cleanup: Replacing with new full text: "${newFullText}"`);

                // Update the textarea directly
                // console.log("[DEBUG] Notes Cleanup: Replacing text in textarea.");
                textarea.value = newFullText;

                // Update the application state AFTER updating the DOM value
                // console.log("[DEBUG] Notes Cleanup: Updating state.noteContent.");
                state.setNoteContent(newFullText); // Update state for notes

                // Check if the text actually changed
                if (cleanedText === selectedText) {
                    state.setStatusMessage("Cleanup did not change the selected text.");
                } else {
                    state.setStatusMessage("Selected text cleaned.");
                }

                // Restore selection around the newly inserted text (optional but good UX)
                textarea.focus();
                textarea.setSelectionRange(selectionStart, selectionStart + cleanedText.length);

                // Trigger auto-resize after modifying content
                ui.autoResizeTextarea(textarea);

                // Status message is already set based on whether text changed.

                // Optionally trigger auto-save or mark note as dirty
                // await api.saveNote(); // Or just let the user save manually

            } catch (error) {
                // Error status is set by api.cleanupTranscript
                console.error("Error cleaning selected text:", error);
                // Optionally display a more specific error to the user if needed
            } finally {
                // Loading state is handled by api.cleanupTranscript
                // Re-evaluate button state after operation (selection might have changed)
                ui.updateNotesCleanupButtonState();
            }
        });
    }

    // --- NEW: Notes TOC Drawer Listeners ---
    elements.notesTocHeader?.addEventListener('click', ui.toggleNotesTocDrawer); // Toggle on header click
    elements.notesTocList?.addEventListener('click', (event) => {
        const link = event.target.closest('.toc-link');
        if (!link) return;

        event.preventDefault(); // Prevent default anchor jump

        const targetId = link.dataset.targetId;
        if (!targetId) return;

        // Find the target heading element within the notes preview area OR notes textarea
        let targetElement = null;
        if (state.currentNoteMode === 'view') {
            targetElement = elements.notesPreview?.querySelector(`#${targetId}`);
            if (targetElement && elements.notesPreview) {
                // --- UPDATED: Use scrollTop for more reliable scrolling in view mode ---
                const targetOffsetTop = targetElement.offsetTop;
                elements.notesPreview.scrollTop = targetOffsetTop;
                // ---------------------------------------------------------------------
            } else {
                console.warn(`[DEBUG] TOC link clicked, but target heading #${targetId} not found in view mode.`);
            }
        } else { // 'edit' mode
            // In edit mode, we need to find the corresponding line in the textarea
            // This is tricky and less reliable than scrolling the rendered view.
            // We'll try a basic text search for the heading content.
            const headingText = link.textContent;
            const textareaValue = elements.notesTextarea?.value || '';
            const lines = textareaValue.split('\n');
            // Find the line that starts with '#' characters followed by the heading text
            const lineIndex = lines.findIndex(line => {
                const trimmedLine = line.trim();
                // Match lines like '# Heading', '## Heading', etc.
                return trimmedLine.match(/^#+\s+/) && trimmedLine.substring(trimmedLine.indexOf(' ')+1).trim() === headingText.trim();
            });

            if (lineIndex !== -1 && elements.notesTextarea) {
                // --- Calculate character position of the start of the line ---
                // Sum lengths of previous lines + newline characters
                let position = 0;
                for (let i = 0; i < lineIndex; i++) {
                    position += lines[i].length + 1; // +1 for the newline character
                }

                // --- Set cursor position and focus ---
                try {
                    elements.notesTextarea.focus(); // Focus first
                    // Set selection start and end to the same point to place the cursor
                    elements.notesTextarea.setSelectionRange(position, position);

                    // --- Optional: Attempt scrollIntoView (might not be perfect) ---
                    // This is less reliable than focus/setSelectionRange for bringing
                    // the exact line into view, but can help in some browsers.
                    // elements.notesTextarea.scrollIntoView({ block: 'nearest' });

                    state.setStatusMessage(`Jumped to heading in editor.`);
                } catch (e) {
                    console.error("Error setting cursor position or focusing:", e);
                    state.setStatusMessage("Error jumping to heading in editor.", true);
                }

            } else {
                state.setStatusMessage("Could not find heading in editor.", true);
            }
        }
    });
    // ---------------------------------------

    // --- Sidebar & Chat Management ---
    // Use the new tab button ID
    document.getElementById('sidebar-toggle-tab')?.addEventListener('click', ui.toggleLeftSidebar);
    elements.newChatButton?.addEventListener('click', async () => {
        await api.startNewChat(); // Updates state (currentChatId, savedChats, chatHistory, isLoading, statusMessage, etc.)
        // UI updates are triggered by state notifications within api.startNewChat
    });
    elements.saveChatNameButton?.addEventListener('click', async () => {
        // Name is updated in state by input handler or here before API call
        const newName = elements.currentChatNameInput?.value.trim() || 'New Chat';
        state.setCurrentChatName(newName); // Update state immediately (notifies currentChatName, currentChat)

        await api.handleSaveChatName(); // Updates state (savedChats, isLoading, statusMessage)
        // UI updates are triggered by state notifications within api.handleSaveChatName
    });
    elements.currentChatNameInput?.addEventListener('input', (e) => { // Add input listener for name
        state.setCurrentChatName(e.target.value); // Update state (notifies currentChatName, currentChat)
        // UI updates are triggered by state notifications
    });
    elements.currentChatNameInput?.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            elements.saveChatNameButton?.click(); // Trigger save button click
        }
    });
    // Add click listener for chat list items (delegated)
    elements.savedChatsList?.addEventListener('click', async (event) => {
        const listItem = event.target.closest('.chat-list-item');
        if (!listItem) return;
        const chatId = parseInt(listItem.dataset.chatId);
        if (isNaN(chatId)) return;

        // Prevent loading the same chat again
        if (chatId === state.currentChatId) return;

        await api.loadChat(chatId); // Updates state (currentChatId, chatHistory, etc.)
        // UI updates are triggered by state notifications within api.loadChat
    });
    // Add click listener for delete chat button (delegated)
    elements.savedChatsList?.addEventListener('click', async (event) => {
        const deleteButton = event.target.closest('.delete-btn');
        if (!deleteButton) return;
        event.stopPropagation(); // Prevent triggering the list item click

        const listItem = deleteButton.closest('.chat-list-item');
        if (!listItem) return;
        const chatId = parseInt(listItem.dataset.chatId);
        if (isNaN(chatId)) return;

        await api.handleDeleteChat(chatId); // Updates state (savedChats, currentChatId, etc.)
        // UI updates are triggered by state notifications within api.handleDeleteChat
    });


    // --- Plugins Sidebar & Sections ---
    // Use the new tab button ID
    document.getElementById('plugins-toggle-tab')?.addEventListener('click', ui.toggleRightSidebar);
    elements.filePluginHeader?.addEventListener('click', ui.toggleFilePlugin); // UI-only toggle
    elements.calendarPluginHeader?.addEventListener('click', ui.toggleCalendarPlugin); // UI-only toggle
    // Add listener for history plugin header if it's collapsible
    if (elements.historyPluginHeader && elements.historyPluginContent) {
         elements.historyPluginHeader.addEventListener('click', () => {
             const isCollapsed = elements.historyPluginContent.classList.contains('hidden');
             ui.setPluginSectionCollapsed(elements.historyPluginHeader, elements.historyPluginContent, !isCollapsed, config.HISTORY_PLUGIN_COLLAPSED_KEY); // Assuming a new config key
         });
    }


    // --- File Plugin Interactions ---
    elements.attachFullButton?.addEventListener('click', () => {
        api.attachSelectedFilesFull(); // Updates state (attachedFiles, sidebarSelectedFiles)
        // UI updates are triggered by state notifications within api.attachSelectedFilesFull
    });
    elements.attachSummaryButton?.addEventListener('click', () => {
        api.attachSelectedFilesSummary(); // Updates state (attachedFiles, sidebarSelectedFiles)
        // UI updates are triggered by state notifications within api.attachSelectedFilesSummary
    });
    elements.manageFilesButton?.addEventListener('click', () => {
        ui.showModal(elements.manageFilesModal, 'files', 'chat'); // UI-only modal show
        // File list rendering in modal is handled by ui.renderUploadedFiles,
        // which is triggered by state.uploadedFiles notification (e.g., from api.loadUploadedFiles)
    });

    // Session File Upload (Paperclip)
    elements.fileUploadSessionLabel?.addEventListener('click', () => {
        if (state.isFilePluginEnabled && state.currentTab === 'chat') { // Use getters
            elements.fileUploadSessionInput?.click();
        } else if (!state.isFilePluginEnabled) { // Use getter
            state.setStatusMessage("Files plugin is disabled in settings.", true); // Update state (notifies statusMessage)
            // UI update is triggered by statusMessage notification
        }
    });
    elements.fileUploadSessionInput?.addEventListener('change', handleSessionFileUpload); // Handler updates state and triggers UI

    // Add click listener for sidebar file list items (delegated)
    elements.uploadedFilesList?.addEventListener('click', (event) => {
        const itemDiv = event.target.closest('.file-list-item');
        if (!itemDiv) return;

        const fileId = parseInt(itemDiv.dataset.fileId);
        const filename = itemDiv.dataset.filename;
        const hasSummaryDataset = itemDiv.dataset.hasSummary; // Get raw dataset value
        // Convert to boolean, accepting 'true' or '1' as true
        const hasSummary = hasSummaryDataset === 'true' || hasSummaryDataset === '1';
        if (isNaN(fileId) || !filename) return;

        const isCurrentlySelected = state.sidebarSelectedFiles.some(sf => sf.id === fileId);

        if (isCurrentlySelected) {
            state.removeSidebarSelectedFileById(fileId); // Update state (notifies sidebarSelectedFiles)
        } else {
            const fileToAdd = { id: fileId, filename: filename, has_summary: hasSummary };
            state.addSidebarSelectedFile(fileToAdd); // Update state (notifies sidebarSelectedFiles)
        }
        // UI updates are triggered by sidebarSelectedFiles notification
    });


    // --- Manage Files Modal ---
    elements.closeManageFilesModal?.addEventListener('click', () => ui.closeModal(elements.manageFilesModal)); // UI-only modal close
    elements.manageFilesModal?.addEventListener('click', (event) => {
        if (event.target === elements.manageFilesModal) ui.closeModal(elements.manageFilesModal); // UI-only modal close
    });
    elements.fileUploadModalInput?.addEventListener('change', async (event) => {
        await api.handleFileUpload(event); // Updates state (uploadedFiles, isLoading, statusMessage)
        // UI updates are triggered by state notifications.
        // Closing modal after successful upload should be handled here based on state.
        if (!state.isErrorStatus) { // Check state after API call
             ui.closeModal(elements.manageFilesModal);
        }
    });
    elements.addUrlModalButton?.addEventListener('click', () => {
        ui.showModal(elements.urlModal, 'files', 'chat'); // UI-only modal show
        // Status update for URL modal handled by its own input listener or fetch button handler
        if(elements.urlStatus) {
             elements.urlStatus.textContent = ""; // Clear previous status
             elements.urlStatus.classList.remove('text-red-500');
        }
    });

    // --- URL Modal ---
    elements.closeUrlModal?.addEventListener('click', () => ui.closeModal(elements.urlModal)); // UI-only modal close
    elements.urlModal?.addEventListener('click', (event) => {
        if (event.target === elements.urlModal) ui.closeModal(elements.urlModal); // UI-only modal close
    });
    elements.fetchUrlButton?.addEventListener('click', async () => {
        const url = elements.urlInput?.value;
        // Validation and status updates for modal are handled here before API call
        if (!url || !url.startsWith('http')) {
            if(elements.urlStatus) {
                elements.urlStatus.textContent = "Please enter a valid URL (http/https).";
                elements.urlStatus.classList.add('text-red-500');
            }
            return;
        }
        if(elements.urlStatus) {
            elements.urlStatus.textContent = "Fetching content...";
            elements.urlStatus.classList.remove('text-red-500');
        }
        await api.addFileFromUrl(url); // Updates state (uploadedFiles, isLoading, statusMessage)
        // UI updates are triggered by state notifications.
        // Status update for URL modal is handled by API's setStatus, which updates state.statusMessage
        // We need a way for the modal to specifically show the status related to the URL fetch.
        // This might require adding modal-specific status state or reading the global status carefully.
        // For now, let's rely on the global status bar and close the modal on success.
        if (!state.isErrorStatus) { // Check global state after API call
             ui.closeModal(elements.urlModal);
        } else {
             // If there was an error, update the modal's status text
             if(elements.urlStatus) {
                 elements.urlStatus.textContent = `Error: ${state.statusMessage}`;
                 elements.urlStatus.classList.add('text-red-500');
             }
        }
    });
    elements.urlInput?.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            elements.fetchUrlButton?.click(); // Trigger the fetch button click
        }
    });

    // Add click listener for modal file list summary button (delegated)
    elements.manageFilesList?.addEventListener('click', async (event) => {
        const summaryButton = event.target.closest('.btn i.fa-list-alt')?.parentElement;
        if (!summaryButton) return;
        event.stopPropagation(); // Prevent triggering item click

        const itemDiv = summaryButton.closest('.file-list-item');
        if (!itemDiv) return;
        const fileId = parseInt(itemDiv.dataset.fileId);
        const filename = itemDiv.dataset.filename;
        if (isNaN(fileId) || !filename) return;

        // Show modal immediately (UI concern)
        ui.showModal(elements.summaryModal, 'files', 'chat');

        await api.fetchSummary(fileId); // Updates state (currentEditingFileId, summaryContent, isLoading, statusMessage)
        // UI updates are triggered by state notifications.
        // renderSummaryModalContent is called by currentEditingFileId and summaryContent notifications
    });

    // Add click listener for modal file list delete button (delegated)
    elements.manageFilesList?.addEventListener('click', async (event) => {
        const deleteButton = event.target.closest('.btn i.fa-trash-alt')?.parentElement;
        if (!deleteButton) return;
        event.stopPropagation(); // Prevent triggering item click

        const itemDiv = deleteButton.closest('.file-list-item');
        if (!itemDiv) return;
        const fileId = parseInt(itemDiv.dataset.fileId);
        if (isNaN(fileId)) return;

        await api.deleteFile(fileId); // Updates state (uploadedFiles, sidebarSelectedFiles, attachedFiles, sessionFile, isLoading, statusMessage)
        // UI updates are triggered by state notifications.
    });


    // --- Summary Modal ---
    elements.closeSummaryModal?.addEventListener('click', () => ui.closeModal(elements.summaryModal)); // UI-only modal close
    elements.summaryModal?.addEventListener('click', (event) => {
        if (event.target === elements.summaryModal) ui.closeModal(elements.summaryModal); // UI-only modal close
    });
    elements.saveSummaryButton?.addEventListener('click', async () => {
        // Read content from DOM input for immediate state update
        const updatedSummary = elements.summaryTextarea?.value || '';
        state.setSummaryContent(updatedSummary); // Update state immediately (notifies summaryContent)
        // UI update is triggered by summaryContent notification

        await api.saveSummary(); // Updates state (uploadedFiles, isLoading, statusMessage, summaryContent)
        // UI updates are triggered by state notifications.
        // Closing modal after successful save should be handled here.
        if (!state.isErrorStatus) { // Check global state after API call
             ui.closeModal(elements.summaryModal);
        }
    });
    // Summary textarea input updates state.summaryContent - handler already does this and calls ui.renderSummaryModalContent
    elements.summaryTextarea?.addEventListener('input', (e) => {
        state.setSummaryContent(e.target.value); // Update state (notifies summaryContent)
        // UI update is triggered by summaryContent notification
    });


    // --- Calendar Plugin Interactions ---
    elements.loadCalendarButton?.addEventListener('click', async () => {
        await api.loadCalendarEvents(); // Updates state (calendarContext, isLoading, statusMessage)
        // UI updates are triggered by state notifications.
    });
    elements.calendarToggle?.addEventListener('change', handleCalendarToggleChange); // Handler updates state and triggers UI
    elements.viewCalendarButton?.addEventListener('click', () => {
        ui.showModal(elements.calendarModal, 'calendar', 'chat'); // UI-only modal show
        // Calendar content rendering in modal is handled by UI reacting to state.calendarContext
    });
    elements.closeCalendarModal?.addEventListener('click', () => ui.closeModal(elements.calendarModal)); // UI-only modal close
    elements.calendarModal?.addEventListener('click', (event) => {
        if (event.target === elements.calendarModal) ui.closeModal(elements.calendarModal); // UI-only modal close
    });

    // --- Settings Modal & Toggles ---
    elements.settingsButton?.addEventListener('click', () => ui.showModal(elements.settingsModal)); // UI-only modal show
    elements.closeSettingsModal?.addEventListener('click', () => ui.closeModal(elements.settingsModal)); // UI-only modal close
    elements.settingsModal?.addEventListener('click', (event) => {
        if (event.target === elements.settingsModal) ui.closeModal(elements.settingsModal); // UI-only modal close
    });
    elements.streamingToggle?.addEventListener('change', handleStreamingToggleChange); // Handler updates state and triggers UI
    elements.filesPluginToggle?.addEventListener('change', handleFilesPluginToggleChange); // Handler updates state and triggers UI
    elements.calendarPluginToggle?.addEventListener('change', handleCalendarPluginToggleChange); // Handler updates state and triggers UI
    elements.webSearchPluginToggle?.addEventListener('change', handleWebSearchPluginToggleChange); // Handler updates state and triggers UI
    elements.webSearchToggle?.addEventListener('change', (e) => {
        state.setWebSearchEnabled(e.target.checked); // Update state (notifies isWebSearchEnabled)
        // UI update is triggered by isWebSearchEnabled notification
    });


    // --- Tab Navigation ---
    elements.chatNavButton?.addEventListener('click', () => {
        handleTabSwitchClick('chat'); // Call new handler
    });
    elements.notesNavButton?.addEventListener('click', () => {
        handleTabSwitchClick('notes'); // Call new handler
    });

    // New handler for tab button clicks
    async function handleTabSwitchClick(tab) {
        if (state.currentTab === tab) {
            return; // Already on this tab
        }

        // Save current state before switching (e.g., auto-save note)
        // Auto-save note on tab switch is a potential feature, but not requested yet.
        // If implemented, it would go here:
        // if (state.currentTab === 'notes' && state.currentNoteId) {
        //     console.log("[DEBUG] Auto-saving note before switching tabs...");
        //     await api.saveNote(); // Implement auto-save if needed
        // }

        state.setCurrentTab(tab); // Update state (notifies currentTab)
        localStorage.setItem(config.ACTIVE_TAB_KEY, tab); // Persist

        // UI update for tab switch is triggered by currentTab notification

        // Load data for the new tab if needed
        if (tab === 'chat') {
            // loadInitialChatData checks if currentChatId is null and loads accordingly
            // It also loads savedChats and uploadedFiles if needed
            await api.loadInitialChatData(); // Updates state
            // UI updates triggered by state changes within loadInitialChatData (loadChat, startNewChat)
        } else { // tab === 'notes'
            // loadInitialNotesData checks if currentNoteId is null and loads accordingly
            // It also loads savedNotes if needed
            await api.loadInitialNotesData(); // Updates state
            // UI updates triggered by state changes within loadInitialNotesData (loadNote, startNewNote)
        }
    }

    // --- Notes Interactions ---
    // Note textarea input updates state.noteContent AND triggers auto-resize
    elements.notesTextarea?.addEventListener('input', (e) => {
        state.setNoteContent(e.target.value); // Update state (notifies noteContent, currentNote)
        ui.autoResizeTextarea(elements.notesTextarea); // Call the reusable UI function
        // UI update is triggered by state notifications
    });
    // --- Add paste listener for notes textarea auto-resize ---
    elements.notesTextarea?.addEventListener('paste', () => {
        // Use setTimeout to allow the paste operation to complete before resizing
        setTimeout(() => {
            ui.autoResizeTextarea(elements.notesTextarea);
        }, 0);
    });
    // -------------------------------------------------------
    elements.newNoteButton?.addEventListener('click', async () => {
        await api.startNewNote(); // Updates state (currentNoteId, savedNotes, noteContent, isLoading, statusMessage, etc.)
        // UI updates are triggered by state notifications.
    });
    // Note name input updates state.currentNoteName
    elements.currentNoteNameInput?.addEventListener('input', (e) => {
        state.setCurrentNoteName(e.target.value); // Update state (notifies currentNoteName, currentNote)
        // UI update is triggered by state notifications
    });
    elements.saveNoteNameButton?.addEventListener('click', async () => {
        // Name is already in state from input handler
        await api.saveNote(); // Updates state (savedNotes, isLoading, statusMessage)
        // UI updates are triggered by state notifications.
    });
    elements.currentNoteNameInput?.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            elements.saveNoteNameButton?.click(); // Trigger save button click
        }
    });
    elements.editNoteButton?.addEventListener('click', () => {
        state.setCurrentNoteMode('edit'); // Update state (notifies currentNoteMode)
        // UI update is triggered by currentNoteMode notification
    });
    elements.viewNoteButton?.addEventListener('click', () => {
        state.setCurrentNoteMode('view'); // Update state (notifies currentNoteMode)
        // UI update is triggered by currentNoteMode notification
    });
    elements.markdownTipsButton?.addEventListener('click', () => ui.showModal(elements.markdownTipsModal, null, 'notes')); // UI-only modal show
    elements.closeMarkdownTipsModal?.addEventListener('click', () => ui.closeModal(elements.markdownTipsModal)); // UI-only modal close
    elements.markdownTipsModal?.addEventListener('click', (event) => {
        if (event.target === elements.markdownTipsModal) ui.closeModal(elements.markdownTipsModal); // UI-only modal close
    });

    // Add click listener for note list items (delegated)
    elements.savedNotesList?.addEventListener('click', async (event) => {
        const listItem = event.target.closest('.note-list-item');
        if (!listItem) return;
        const noteId = parseInt(listItem.dataset.noteId);
        if (isNaN(noteId)) return;

        // Prevent loading the same note again
        if (noteId === state.currentNoteId) return;

        await api.loadNote(noteId); // Updates state (currentNoteId, noteContent, isLoading, statusMessage)
        // UI updates are triggered by state notifications.
    });
    // Add click listener for delete note button (delegated)
    elements.savedNotesList?.addEventListener('click', async (event) => {
        const deleteButton = event.target.closest('.delete-btn');
        if (!deleteButton) return;
        event.stopPropagation(); // Prevent triggering the list item click

        const listItem = deleteButton.closest('.note-list-item');
        if (!listItem) return;
        const noteId = parseInt(listItem.dataset.noteId);
        if (isNaN(noteId)) return;

        await api.handleDeleteNote(noteId); // Updates state (savedNotes, currentNoteId, noteContent, isLoading, statusMessage)
        // UI updates are triggered by state notifications.
    });


    // --- NEW: Add click listener for history list items (delegated) ---
    elements.noteHistoryList?.addEventListener('click', async (event) => {
        const listItem = event.target.closest('.history-list-item');
        if (!listItem) return;
        const historyId = parseInt(listItem.dataset.historyId);
        if (isNaN(historyId)) return;

        // Find the history entry in the state
        const historyEntry = state.noteHistory.find(entry => entry.id === historyId);

        if (historyEntry) {
            let proceedToLoad = true;

            // --- NEW: Check if summary needs generation ---
            const needsSummary = !historyEntry.note_diff || historyEntry.note_diff === "[Summary pending...]"; // Check if diff is missing or pending marker
            const isInitial = state.noteHistory.findIndex(entry => entry.id === historyId) === state.noteHistory.length - 1; // Check if it's the initial version

            if (needsSummary && !isInitial) {
                console.log(`[DEBUG] History item ${historyId} needs summary generation. Calling API...`);
                // Disable the list item temporarily to prevent double clicks while generating
                listItem.style.pointerEvents = 'none';
                listItem.style.opacity = '0.7';

                const generationSuccess = await api.generateNoteDiffSummaryForHistoryItem(state.currentNoteId, historyId);

                // Re-enable the list item
                listItem.style.pointerEvents = '';
                listItem.style.opacity = '';

                if (!generationSuccess) {
                    // If generation failed, maybe don't load the content? Or load anyway?
                    // Let's proceed to load the content even if summary generation failed,
                    // but the status message will indicate the error.
                    console.warn(`[WARN] Summary generation failed for history ${historyId}, but proceeding to load content.`);
                    // proceedToLoad = false; // Uncomment to prevent loading content on summary failure
                } else {
                     console.log(`[DEBUG] Summary generation successful (or already existed) for history ${historyId}.`);
                     // History list state is reloaded by the API function, UI will update.
                }
            }
            // ---------------------------------------------

            if (proceedToLoad) {
                // Update the state with the history entry's content and name
                // Use the potentially updated history entry from state after generation/reload
                const updatedHistoryEntry = state.noteHistory.find(entry => entry.id === historyId) || historyEntry; // Fallback to original if not found after reload

                state.setNoteContent(updatedHistoryEntry.content); // Notifies noteContent, currentNote
                state.setCurrentNoteName(updatedHistoryEntry.name); // Notifies currentNoteName, currentNote

                // --- REMOVED: Do NOT change the note mode when loading history ---
                // state.setCurrentNoteMode('edit'); // Notifies currentNoteMode
                // -----------------------------------------------------------------

                state.setStatusMessage(`Loaded history version ${historyId}.`); // Update state
                // UI updates are triggered by state notifications
            }
        } else {
            console.warn(`[DEBUG] History entry with ID ${historyId} not found in state.noteHistory.`);
            state.setStatusMessage(`Error: History version ${historyId} not found.`, true); // Update state
            // UI update is triggered by statusMessage notification
        }
    });
    // -----------------------------------------------------------------

    // --- Removed Generate Diff Summary button listener ---
    // Summary generation is now handled during note save.

    // --- Delegated Click Listener for Collapsible Headings (Hierarchical) ---
    function handleCollapsibleClick(event) {
        // Only apply hierarchical logic within the notes preview
        const notesPreview = event.target.closest('#notes-preview');
        if (!notesPreview) {
            // --- Keep original simple toggle logic for chatbox or other areas ---
            const simpleHeading = event.target.closest('.collapsible-heading');
            if (!simpleHeading) return;
            const targetId = simpleHeading.dataset.target;
            const content = targetId ? document.querySelector(targetId) : null;
            const icon = simpleHeading.querySelector('.collapsible-toggle');
            if (content && icon) {
                const isCollapsed = content.classList.toggle('collapsed'); // Assuming 'collapsed' means hidden for simple toggle
                icon.classList.toggle('fa-chevron-down', !isCollapsed);
                icon.classList.toggle('fa-chevron-right', isCollapsed);
            }
            // --- End simple toggle logic ---
            return;
        }

        // --- Hierarchical Logic for Notes Preview ---
        const heading = event.target.closest('.collapsible-heading');
        if (!heading) return;

        const icon = heading.querySelector('.collapsible-toggle');
        if (!icon) return; // Need an icon to toggle

        const headingTag = heading.tagName.toUpperCase(); // e.g., "H1", "H2"
        if (!headingTag.startsWith('H') || headingTag.length !== 2) return; // Only process H1-H6
        const headingLevel = parseInt(headingTag[1]);

        const isCollapsing = !heading.classList.contains('collapsed'); // Check current state before toggling

        // Toggle the heading's own state class
        heading.classList.toggle('collapsed', isCollapsing);

        // Update the icon
        icon.classList.toggle('fa-chevron-down', !isCollapsing);
        icon.classList.toggle('fa-chevron-right', isCollapsing);

        // Iterate through subsequent siblings
        let nextElement = heading.nextElementSibling;
        while (nextElement) {
            const nextElementTag = nextElement.tagName.toUpperCase();
            let stop = false;

            if (nextElementTag.startsWith('H') && nextElementTag.length === 2) {
                const nextElementLevel = parseInt(nextElementTag[1]);
                if (nextElementLevel <= headingLevel) {
                    stop = true; // Stop when we hit a heading of the same or higher level
                }
            }

            if (stop) {
                break; // Exit the loop
            }

            // Apply/remove 'hidden' class based on the action (collapsing/expanding)
            nextElement.classList.toggle('hidden', isCollapsing);

            // Move to the next sibling
            nextElement = nextElement.nextElementSibling;
        }
    }

    // Add listener to chatbox
    elements.chatbox?.addEventListener('click', handleCollapsibleClick);

    // Add listener to notes preview area
    elements.notesPreview?.addEventListener('click', handleCollapsibleClick);
    // ---------------------------------------------------------


    // --- Update TOC on Note Textarea Input ---
    if (elements.notesTextarea) {
        // Debounce the TOC update function from ui.js
        const debouncedTocUpdate = debounce(() => {
            if (state.currentTab === 'notes') {
                ui.generateAndRenderToc(); // Call the UI function to update TOC
            }
        }, 300); // Use the same debounce delay as in ui.js

        elements.notesTextarea.addEventListener('input', () => {
            // Update state first (already handled by existing listener)
            // Then trigger the debounced TOC update
            debouncedTocUpdate();
        });
    }
    // -----------------------------------------


    // console.log("[DEBUG] setupEventListeners finished."); // Log completion
}


/**
 * Subscribes UI rendering functions to state changes.
 * This function is called once during setupEventListeners.
 */
function subscribeStateChangeListeners() {
    // Subscribe UI functions to state changes they should react to
    state.subscribe('isLoading', ui.handleStateChange_isLoading);
    state.subscribe('statusMessage', ui.handleStateChange_statusMessage);

    state.subscribe('savedChats', ui.handleStateChange_savedChats);
    state.subscribe('currentChat', ui.handleStateChange_currentChat); // Combined chat details
    state.subscribe('chatHistory', ui.handleStateChange_chatHistory);
    state.subscribe('isRecording', ui.handleStateChange_isRecording); // Subscribe mic button UI to recording state

    state.subscribe('savedNotes', ui.handleStateChange_savedNotes);
    state.subscribe('currentNote', ui.handleStateChange_currentNote); // Combined note details
    // --- REMOVED REDUNDANT SUBSCRIPTION ---
    // state.subscribe('noteContent', ui.handleStateChange_currentNote); // Note content changes also trigger currentNote handler
    // --------------------------------------
    state.subscribe('currentNoteMode', ui.handleStateChange_currentNoteMode);

    state.subscribe('uploadedFiles', ui.handleStateChange_uploadedFiles);
    state.subscribe('sidebarSelectedFiles', ui.handleStateChange_sidebarSelectedFiles);
    state.subscribe('attachedFiles', ui.handleStateChange_attachedFiles);
    state.subscribe('sessionFile', ui.handleStateChange_sessionFile);

    state.subscribe('currentEditingFileId', ui.handleStateChange_currentEditingFileId);
    state.subscribe('summaryContent', ui.handleStateChange_summaryContent);

    state.subscribe('calendarContext', ui.handleStateChange_calendarContext);
    state.subscribe('isCalendarContextActive', ui.handleStateChange_isCalendarContextActive);
    state.subscribe('isWebSearchEnabled', ui.handleStateChange_isWebSearchEnabled);

    // Generic plugin enabled state change handler
    state.subscribe('pluginEnabled', ui.handleStateChange_pluginEnabled);

    // Subscribe the UI handler to the currentTab state change
    state.subscribe('currentTab', ui.handleStateChange_currentTab); // Corrected event name

    // --- NEW: Subscribe UI to noteHistory state change ---
    state.subscribe('noteHistory', ui.handleStateChange_noteHistory); // Corrected handler name
    // ----------------------------------------------------

    // --- Subscribe UI to streaming transcript state change ---
    state.subscribe('streamingTranscript', ui.handleStateChange_streamingTranscript);
    // -------------------------------------------------------

    // --- Subscribe UI to sidebar collapse state changes ---
    state.subscribe('isSidebarCollapsed', ui.handleStateChange_isSidebarCollapsed);
    state.subscribe('isPluginsCollapsed', ui.handleStateChange_isPluginsCollapsed);
    // ----------------------------------------------------

    // --- NEW: Subscribe UI to TOC drawer collapse state ---
    state.subscribe('isNotesTocCollapsed', ui.handleStateChange_isNotesTocCollapsed);
    // ----------------------------------------------------

    // --- NEW: Delegated Listener for Message Copy Buttons ---
    elements.chatbox?.addEventListener('click', (event) => {
        const copyButton = event.target.closest('.copy-message-button');
        if (!copyButton) return; // Click wasn't on a copy button

        const messageElement = copyButton.closest('.message');
        if (!messageElement) return; // Should not happen if button is inside message

        const rawContent = messageElement.dataset.rawContent;
        if (rawContent) {
            navigator.clipboard.writeText(rawContent)
                .then(() => {
                    console.log("Message content copied to clipboard.");
                    // Provide visual feedback
                    copyButton.innerHTML = '<i class="fas fa-check"></i>'; // Change to checkmark
                    copyButton.disabled = true;
                    setTimeout(() => {
                        copyButton.innerHTML = '<i class="far fa-copy"></i>'; // Revert icon
                        copyButton.disabled = false;
                    }, 1500); // Revert after 1.5 seconds
                })
                .catch(err => {
                    console.error('Failed to copy message content: ', err);
                    showToast("Failed to copy text.", { type: 'error' }); // Use toast for error
                });
        } else {
            console.warn("Could not find raw content to copy for message:", messageElement);
            showToast("Could not find content to copy.", { type: 'warning' });
        }
    });
    // ------------------------------------------------------

}


// --- Event Handler Helper Functions ---
// (Keep these helper functions below setupEventListeners)

/** Handles the session file input change event. */
async function handleSessionFileUpload(e) {
    const file = e.target.files[0];

    state.setSessionFile(null); // Clear state first (notifies sessionFile)
    // UI will react to this state change to remove the old tag

    if (!file) {
        // If no file selected (e.g., user cancelled), state is already null, UI is updated.
        return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
        alert(`Skipping "${file.name}": File is too large (${formatFileSize(file.size)}). Max size is ${MAX_FILE_SIZE_MB} MB.`);
        if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = ''; // Reset file input
        // State is already null, UI is updated.
        return;
    }

    // Show temporary loading state within the container (UI concern)
    // This could be handled by a state variable like `isSessionFileLoading`
    // For now, let's keep the direct DOM manipulation here as it's a very specific UI feedback.
    if(elements.selectedFilesContainer) elements.selectedFilesContainer.classList.remove('hidden');
    const loadingTag = document.createElement('span');
    loadingTag.classList.add('selected-file-tag', 'session-file-tag', 'opacity-75');
    loadingTag.innerHTML = `<span class="text-xs">Loading ${escapeHtml(file.name)}...</span>`;
    elements.selectedFilesContainer?.prepend(loadingTag);


    const reader = new FileReader();
    reader.onload = function(event) {
        loadingTag.remove(); // Remove loading tag
        // Store file details AND content in state
        state.setSessionFile({
            filename: file.name,
            mimetype: file.type,
            content: event.target.result // Base64 content
        });
        // UI update is triggered by sessionFile notification
    }
    reader.onerror = function(error) {
        loadingTag.remove();
        console.error("Error reading session file:", error);
        // Update state with an error status? Or just rely on the alert?
        // Let's add a temporary error tag in the UI for immediate feedback.
        const errorTag = document.createElement('span');
        errorTag.classList.add('selected-file-tag', 'session-file-tag', 'bg-red-100', 'text-red-700', 'border-red-300');
        errorTag.textContent = `Error loading ${escapeHtml(file.name)}`;
        elements.selectedFilesContainer?.prepend(errorTag);
        setTimeout(() => errorTag.remove(), 3000);

        state.setSessionFile(null); // Ensure state is null on error (notifies sessionFile)
        if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = ''; // Reset input
        // UI update is triggered by sessionFile notification
    }
    reader.readAsDataURL(file); // Read as Base64
}


/** Handles changes to the calendar context toggle switch. */
function handleCalendarToggleChange() {
    if (!state.isCalendarPluginEnabled || state.currentTab !== 'chat') {
        if(elements.calendarToggle) elements.calendarToggle.checked = false; // Force off
        state.setStatusMessage("Calendar context requires Calendar plugin enabled on Chat tab.", true); // Update state (notifies statusMessage)
        // UI update is triggered by statusMessage notification
        return;
    }
    const isActive = elements.calendarToggle?.checked || false;
    state.setCalendarContextActive(isActive); // Update state (notifies isCalendarContextActive)
    localStorage.setItem('calendarContextActive', isActive); // Persist
    // UI update is triggered by isCalendarContextActive notification
}

/** Handles changes to the streaming toggle switch. */
function handleStreamingToggleChange() {
    const isEnabled = elements.streamingToggle?.checked ?? true;
    state.setStreamingEnabled(isEnabled); // Update state (notifies isStreamingEnabled, pluginEnabled)
    localStorage.setItem('streamingEnabled', isEnabled); // Persist
    state.setStatusMessage(`Streaming responses ${isEnabled ? 'enabled' : 'disabled'}.`); // Update state (notifies statusMessage)
    // UI updates are triggered by state notifications
}

/** Handles changes to the Files plugin toggle switch. */
async function handleFilesPluginToggleChange() {
    const isEnabled = elements.filesPluginToggle?.checked ?? true;
    state.setFilePluginEnabled(isEnabled); // Update state (notifies isFilePluginEnabled, pluginEnabled)
    localStorage.setItem('filesPluginEnabled', isEnabled); // Persist
    state.setStatusMessage(`Files plugin ${isEnabled ? 'enabled' : 'disabled'}.`); // Update state (notifies statusMessage)

    // UI updates are triggered by state notifications (isFilePluginEnabled, statusMessage)

    // If disabling, clear related state
    if (!isEnabled) {
        state.clearSidebarSelectedFiles(); // Update state (notifies sidebarSelectedFiles)
        state.clearAttachedFiles(); // Update state (notifies attachedFiles)
        state.setSessionFile(null); // Update state (notifies sessionFile)
        if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = ''; // Reset input
    } else {
        // If enabling, reload the file lists
        await api.loadUploadedFiles(); // Updates state.uploadedFiles, isLoading, statusMessage
        // UI updates are triggered by state notifications.
    }
}

/** Handles changes to the Calendar plugin toggle switch. */
async function handleCalendarPluginToggleChange() {
    const isEnabled = elements.calendarPluginToggle?.checked ?? true;
    state.setCalendarPluginEnabled(isEnabled); // Update state (notifies isCalendarPluginEnabled, pluginEnabled)
    localStorage.setItem('calendarPluginEnabled', isEnabled); // Persist
    state.setStatusMessage(`Calendar plugin ${isEnabled ? 'enabled' : 'disabled'}.`); // Update state (notifies statusMessage)

    // UI updates are triggered by state notifications (isCalendarPluginEnabled, statusMessage)

    // If disabling, clear calendar context state
    if (!isEnabled) {
        state.setCalendarContext(null); // Update state (notifies calendarContext)
        state.setCalendarContextActive(false); // Update state (notifies isCalendarContextActive)
        if(elements.calendarToggle) elements.calendarToggle.checked = false; // Update DOM directly for immediate feedback
    }
    // No need to reload anything when enabling, just allows usage.
}

/** Handles changes to the Web Search plugin toggle switch. */
async function handleWebSearchPluginToggleChange() {
    const isEnabled = elements.webSearchPluginToggle?.checked ?? true;
    state.setWebSearchPluginEnabled(isEnabled); // Update state (notifies isWebSearchPluginEnabled, pluginEnabled)
    localStorage.setItem('webSearchPluginEnabled', isEnabled); // Persist
    state.setStatusMessage(`Web Search plugin ${isEnabled ? 'enabled' : 'disabled'}.`); // Update state (notifies statusMessage)

    // UI updates are triggered by state notifications (isWebSearchPluginEnabled, statusMessage)

    // If disabling, ensure the input area toggle state is also off
    if (!isEnabled) {
        state.setWebSearchEnabled(false); // Update state (notifies isWebSearchEnabled)
        if (elements.webSearchToggle) {
            elements.webSearchToggle.checked = false; // Update DOM directly for immediate feedback
        }
    }
}
