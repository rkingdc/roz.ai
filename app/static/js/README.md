# JavaScript Application Architecture

This document outlines the architecture and separation of concerns for the frontend JavaScript application located in the `app/static/js` directory. The goal is to create a maintainable, testable, and understandable codebase by dividing responsibilities among different modules.

The core principle is a unidirectional data flow triggered by user events:

**User Event -> Event Listener -> API Call / State Update -> State Change Notification -> UI Listener -> UI Render**

Here's a breakdown of each module's role:

1.  **`dom.js`**:
    * **Responsibility**: Holds references to all necessary DOM elements.
    * **Details**: This module is populated once after the DOM is loaded (`DOMContentLoaded`) by `app.js`. It serves as a central place to access UI elements without scattering `document.getElementById` calls throughout the codebase.
    * **Dependencies**: None (reads from the global `document`).
    * **Used by**: `app.js` (to populate), `ui.js` (to manipulate DOM elements), `eventListeners.js` (to attach listeners and read input values).

2.  **`state.js`**:
    * **Responsibility**: Manages the entire application state (the single source of truth). Provides functions to get and *set* state variables. Implements a simple observer pattern.
    * **Details**: State variables (`let`) hold the current data (e.g., `currentChatId`, `chatHistory`, `uploadedFiles`, `isLoading`, `statusMessage`, `sidebarSelectedFiles`, `attachedFiles`). Setter functions (`set...`, `add...`, `remove...`, `clear...`) are the *only* way to modify the state. After modifying state, setter functions call `notify()` to alert listeners. The `subscribe()` function allows other modules (specifically `eventListeners.js`) to register callbacks for specific state changes.
    * **Dependencies**: None.
    * **Used by**: `api.js` (to update state based on backend responses), `eventListeners.js` (to update state for UI-only changes and subscribe UI listeners), `ui.js` (to read state for rendering).

3.  **`api.js`**:
    * **Responsibility**: Handles all communication with the backend API.
    * **Details**: Functions in this module make `fetch` calls to the Flask backend endpoints. Upon receiving responses, they *update the relevant state variables* in `state.js`. API functions should *not* directly interact with the DOM or call UI rendering functions in `ui.js`. They rely on `state.js` to notify listeners (including UI) about data changes.
    * **Dependencies**: `state.js`, `dom.js` (to read input values before sending to backend), `config.js`, `utils.js`.
    * **Used by**: `eventListeners.js`.

4.  **`ui.js`**:
    * **Responsibility**: Renders the application's user interface based *only* on the current state. Provides functions to update specific parts of the DOM.
    * **Details**: Functions in this module read data from `state.js` and manipulate elements from `dom.js` to display the current application state. It contains rendering functions (e.g., `renderChatHistory`, `renderSavedChats`, `updateLoadingState`, `renderAttachedAndSessionFiles`) and UI-specific logic like showing/hiding modals (`showModal`, `closeModal`) or toggling sidebar sections. It also contains `handleStateChange_...` functions which are designed to be registered as listeners for state changes via `state.subscribe`.
    * **Dependencies**: `state.js`, `dom.js`, `config.js`, `utils.js`.
    * **Used by**: `eventListeners.js` (to trigger rendering via `handleStateChange_...` or `switchTab`, and for UI-only toggles/modals), `app.js` (for initial rendering).

5.  **`eventListeners.js`**:
    * **Responsibility**: Connects user interactions (DOM events) to the application logic and orchestrates the flow.
    * **Details**: This module contains event handlers attached to DOM elements. Handlers read necessary input from the DOM (via `elements`), call the appropriate function in `api.js` (for backend interaction) or `state.js` (for direct state updates like sidebar selection). Crucially, it registers the `ui.handleStateChange_...` functions as listeners with `state.js` using `state.subscribe`. When state changes are notified by `state.js`, the corresponding UI handler in `ui.js` is automatically called, triggering a UI update.
    * **Dependencies**: `dom.js`, `state.js`, `api.js`, `ui.js`, `config.js`, `utils.js`.
    * **Used by**: `app.js`.

6.  **`app.js`**:
    * **Responsibility**: The main entry point for the application. Handles initial setup.
    * **Details**: Waits for the DOM to load, populates the `elements` object, calls `setupEventListeners` to wire up interactions and state observers, loads initial persisted state from `localStorage`, loads initial data from the backend via `api.js`, and triggers the initial UI render via `ui.switchTab`.
    * **Dependencies**: `dom.js`, `state.js`, `ui.js`, `api.js`, `eventListeners.js`, `config.js`.
    * **Used by**: None (it's the top-level script).

7.  **`config.js`**:
    * **Responsibility**: Stores application-wide configuration constants (e.g., API endpoints, max file sizes, localStorage keys, Marked.js options).
    * **Dependencies**: None.
    * **Used by**: `api.js`, `ui.js`, `eventListeners.js`, `app.js`.

8.  **`utils.js`**:
    * **Responsibility**: Provides general utility functions (e.g., HTML escaping, file size formatting).
    * **Dependencies**: None.
    * **Used by**: `ui.js`, `api.js`, `eventListeners.js`.

This architecture ensures that modules have specific, limited responsibilities, reducing coupling and making the codebase easier to understand, debug, and extend. The state module acts as the central hub for data changes, and the observer pattern ensures that the UI automatically reflects these changes without direct dependencies between API and UI logic.
