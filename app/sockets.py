import logging
from flask import request  # Removed current_app, not used here
from flask_socketio import emit, join_room, leave_room, disconnect  # Added disconnect
import base64 # Import base64 for decoding session files

# Removed OutOfRange, threading, queue - they are handled within voice_services
# from google.api_core.exceptions import OutOfRange
# import threading
# import queue

from app import socketio

# Import the necessary functions from voice_services
from app.voice_services import (
    transcribe_stream,
    send_audio_chunk_to_queue,
    signal_end_of_stream,
)

logger = logging.getLogger(__name__)  # Use the standard logger name

# --- Global State for Cancellation ---
# Stores SIDs that have requested cancellation for ongoing tasks
# NOTE: Assumes gevent/eventlet concurrency model handles basic set operations safely.
# If using threading backend or experiencing issues, consider using threading.Lock.
_cancelled_sids = set()
# ------------------------------------

# No need for queue management here, it's in voice_services


@socketio.on("connect")
def handle_connect():
    """Handles new client connections."""
    sid = request.sid
    logger.info(f"****** WebSocket client connected: SID={sid} ******")  # MODIFIED LOG
    # Join a room specific to the session ID so we can emit directly to this client
    join_room(sid)
    logger.info(f"Client {sid} joined its room.")


@socketio.on("disconnect")
def handle_disconnect():
    """Handles client disconnections."""
    sid = request.sid
    logger.info(f"WebSocket client disconnected: {sid}")
    # Signal cancellation and end of stream if the client disconnects abruptly
    logger.warning(f"Client {sid} disconnected abruptly. Requesting cancellation.")
    _cancelled_sids.add(sid)  # Mark as cancelled
    # The listener thread in voice_services will handle queue cleanup.
    logger.info(f"Signaling end of stream due to disconnect for SID: {sid}")
    signal_end_of_stream(sid) # This should trigger cleanup in voice_services if active
    # Leave the room associated with the session
    leave_room(sid)
    logger.info(f"Client {sid} left its room.")
    # Clean up cancellation flag if the background task didn't get to it
    if sid in _cancelled_sids:
        logger.debug(f"Removing {sid} from cancellation set during disconnect.")
        _cancelled_sids.discard(sid)


@socketio.on("start_transcription")
def handle_start_transcription(data):
    """
    Starts a new transcription stream when requested by the client.
    Expects data like {'languageCode': 'en-US', 'audioFormat': 'WEBM_OPUS'}
    """
    sid = request.sid
    logger.info(f"Received start_transcription request from {sid}. Data: {data}")

    # Clean up any previous stream for this SID just in case
    logger.info(
        f"Signaling end of any previous stream for SID: {sid} before starting new one."
    )
    signal_end_of_stream(sid)  # Ensure any lingering listener thread cleans up

    language_code = data.get("languageCode", "en-US")
    # We know the frontend sends WEBM_OPUS based on previous fixes
    encoding = "WEBM_OPUS"
    # Sample rate and channel count are determined by Google API for WEBM_OPUS

    try:
        # Call the streaming transcription service function
        # It now sets up the queue and listener thread internally
        audio_queue, config = transcribe_stream(
            language_code=language_code,
            encoding=encoding,
        )
        # Note: audio_queue is managed within voice_services now, we don't store it here.
        logger.info(f"Transcription stream setup initiated for client: {sid}")
        # Send confirmation back to the specific client
        emit(
            "transcription_started",
            {"message": "Streaming transcription ready."},
            room=sid,
        )

    except Exception as e:
        logger.error(
            f"Error starting transcription stream for {sid}: {e}", exc_info=True
        )
        # Send error back to the specific client
        emit(
            "transcription_error",
            {"error": f"Failed to start transcription: {e}"},
            room=sid,
        )


@socketio.on("audio_chunk")
def handle_audio_chunk(chunk):
    """Receives an audio chunk from the client and sends it to the appropriate queue."""
    sid = request.sid
    # logger.debug(f"Received audio chunk from {sid}, size: {len(chunk)} bytes") # Verbose

    # Use the function from voice_services to put the chunk in the correct queue
    if not send_audio_chunk_to_queue(sid, chunk):
        # Error sending (queue didn't exist, stream likely not started or already stopped)
        logger.warning(
            f"Failed to send audio chunk for SID {sid}: No active queue found."
        )
        # Notify the client that the stream isn't active
        emit(
            "transcription_error",
            {"error": "No active transcription stream found. Please start first."},
            room=sid,
        )
        # Consider disconnecting the client if they send chunks without starting
        # disconnect(sid)


@socketio.on("stop_transcription")
def handle_stop_transcription():
    """Client explicitly signals the end of audio transmission."""
    sid = request.sid
    logger.info(f"Received stop_transcription signal from {sid}")

    # Use the function from voice_services to signal the end (puts None in queue)
    if signal_end_of_stream(sid):
        # Acknowledge receipt of the stop signal to the client
        emit(
            "transcription_stop_acknowledged",
            {"message": "Stop signal received."},
            room=sid,
        )
        # The listener thread in voice_services handles sending final results and cleanup.
    else:
        logger.warning(
            f"Received stop_transcription from {sid} but no active stream found."
        )
        # Optionally notify the client if no stream was active
        # emit('transcription_error', {'error': 'No active transcription stream to stop.'}, room=sid)


# Note: Functions to emit transcription results ('transcript_update', 'transcription_error')
# are called directly from the background listener thread in voice_services.py
# using the imported `socketio` instance and `room=sid`.


# --- Cancellation Handling ---

@socketio.on("cancel_generation")
def handle_cancel_generation(data):
    """Handles request from client to cancel ongoing generation."""
    sid = request.sid
    chat_id = data.get("chat_id", "Unknown") # Get chat_id for logging
    logger.info(f"Received 'cancel_generation' request from SID: {sid} for Chat ID: {chat_id}")
    _cancelled_sids.add(sid)
    # Optional: Acknowledge receipt
    emit("cancel_request_received", {"message": "Cancellation request received."}, room=sid)
    # The actual stopping happens within the generation loop checking _cancelled_sids


# --- Chat Message Handling ---

# Import necessary modules for chat handling
from . import database as db_module # Use alias to avoid conflict with db instance
from . import ai_services
from .ai_services import prompt_improver  # Import the specific function
from . import deep_research

# from .app import socketio # socketio is already imported at the top
from flask import current_app  # Import current_app


def _process_chat_message_async(app, sid, data, message_attachments_metadata): # Add metadata param
    """
    Runs in a background task to process chat messages (AI or Deep Research).
    Emits results back to the client via SocketIO.
    Requires an active application context.
    """
    chat_id = data.get("chat_id")
    user_message = data.get("message", "")
    attached_files = data.get("attached_files", []) # References to existing files
    session_files = data.get("session_files", []) # New files with content
    calendar_context = data.get("calendar_context")
    enable_web_search = data.get("enable_web_search", False)
    enable_streaming = data.get("enable_streaming", False)
    mode = data.get("mode", "chat")

    logger.info(
        f"Background task started for SID {sid}, Chat ID {chat_id}, Mode {mode}."
    )

    # --- Check for Pre-Cancellation ---
    # Handle race condition where cancel is clicked *just* before task starts processing
    if sid in _cancelled_sids:
        logger.warning(f"Task for SID {sid} cancelled before execution started.")
        _cancelled_sids.discard(sid) # Clean up the flag
        # Optionally emit a specific message? Or just let the UI handle timeout/lack of response.
        return # Exit the background task

    # --- Create App Context ---
    # Use the app instance passed from the main thread
    with app.app_context():
        logger.debug(
            f"App context created successfully for background task (SID: {sid})"
        )
        try:
            # --- Define Cancellation Check Function ---
            # This function will be passed down to the services to check the global set
            def is_cancelled():
                cancelled = sid in _cancelled_sids
                if cancelled:
                    logger.debug(f"Cancellation check positive for SID: {sid}")
                return cancelled

            # --- Execute Task ---
            if mode == "deep_research":
                logger.info(
                    f"Calling deep_research.perform_deep_research for SID {sid}, Chat {chat_id}"
                )
                # Pass socketio and sid for emitting results
                deep_research.perform_deep_research(
                    query=user_message,
                    socketio=socketio,
                    sid=sid,
                    chat_id=chat_id,
                    is_cancelled_callback=is_cancelled # Pass the check function
                )
                # perform_deep_research needs to be updated to accept and use is_cancelled_callback
                logger.info(
                    f"Background task completed for deep research (SID {sid}, Chat {chat_id})."
                )

            else:  # mode is 'chat'
                logger.info(
                    f"Calling ai_services.generate_chat_response for SID {sid}, Chat {chat_id}. Streaming: {enable_streaming}"
                )
                # Pass socketio and sid for emitting results
                # generate_chat_response will handle streaming/non-streaming emits and saving the result
                ai_services.generate_chat_response(
                    chat_id=chat_id,
                    user_message=user_message,
                    attached_files=attached_files, # Pass raw refs
                    session_files=session_files, # Pass raw session data
                    calendar_context=calendar_context,
                    web_search_enabled=enable_web_search,
                    streaming_enabled=enable_streaming,
                    socketio=socketio,
                    sid=sid,
                    is_cancelled_callback=is_cancelled, # Pass the check function
                    message_attachments_metadata=message_attachments_metadata # Pass metadata for DB saving
                )
                # generate_chat_response needs to be updated to accept and use is_cancelled_callback
                logger.info(
                    f"Background task completed for chat (SID {sid}, Chat {chat_id}). Streaming: {enable_streaming}"
                )

        except Exception as e:
            # Catch-all for unexpected errors during the background task execution
            logger.error(
                f"Unexpected error in background task for SID {sid}, Chat {chat_id}: {e}",
                exc_info=True,
            )
            try:
                # Emit an error message back to the specific client
                error_msg = (
                    f"[Unexpected Server Error in background task: {type(e).__name__}]"
                )
                socketio.emit("task_error", {"error": error_msg}, room=sid)

                # Attempt to save the error message to the chat history as well
                logger.info(
                    f"Attempting to save background task error message for chat {chat_id}."
                )
                # Use the aliased db_module here
                db_module.add_message_to_db(
                    chat_id, "assistant", error_msg, attached_data_json=None # Error messages don't have attachments
                )
            except Exception as emit_save_err:
                logger.error(
                    f"CRITICAL: Failed to emit or save background task error for SID {sid}, Chat {chat_id}: {emit_save_err}",
                    exc_info=True,
                )
        finally:
            # --- Cleanup Cancellation Flag ---
            # Ensure the flag is removed whether the task succeeded, failed, or was cancelled
            if sid in _cancelled_sids:
                logger.info(f"Removing SID {sid} from cancellation set after task completion/error.")
                _cancelled_sids.discard(sid)


@socketio.on("send_chat_message")
def handle_send_chat_message(data):
    """
    Handles incoming chat messages from the client via SocketIO.
    Saves the user message and starts a background task for processing.
    """
    sid = request.sid
    logger.info(
        f"****** Received 'send_chat_message' event from SID: {sid} ******"
    )  # ADDED LOG
    logger.debug(f"Raw data received for 'send_chat_message': {data}")  # ADDED LOG

    chat_id = data.get("chat_id")
    user_message = data.get("message", "")
    mode = data.get("mode", "chat")
    improve_prompt_enabled = data.get("improve_prompt", False)  # Get the new flag
    # Get other fields needed for validation/saving
    attached_files_payload = data.get("attached_files", []) # References to existing files
    session_files_payload = data.get("session_files", []) # New files with content
    message_attachments_metadata = data.get("message_attachments_metadata", []) # Metadata for DB
    calendar_context = data.get("calendar_context")
    enable_web_search = data.get("enable_web_search", False)

    logger.info(
        f"Processing 'send_chat_message' from SID {sid} for Chat ID {chat_id}. Mode: {mode}"
    )  # Modified log

    # --- Input Validation (similar to old HTTP route) ---
    logger.debug(f"Starting input validation for SID {sid}...")  # ADDED LOG
    is_valid_input = False
    try:
        if mode == "deep_research":
            if user_message and not user_message.isspace():
                is_valid_input = True
            else:
                error_msg = "Deep Research mode requires a text query."
                logger.warning(
                    f"Invalid input for SID {sid}, Chat {chat_id}: {error_msg}"
                )
                emit("task_error", {"error": error_msg}, room=sid)
                return  # Stop processing
        else:  # mode is 'chat'
            # Check if any relevant input exists for chat mode
            # Use state values passed from client payload
            files_plugin_enabled = data.get("enable_files_plugin", False) # Assuming frontend sends this if needed
            calendar_plugin_enabled = data.get("enable_calendar_plugin", False) # Assuming frontend sends this if needed
            web_search_plugin_enabled = data.get("enable_web_search_plugin", False) # Assuming frontend sends this if needed

            # Check if there are any attachments (session or existing)
            has_file_input = bool(attached_files_payload or session_files_payload)
            has_calendar_input = calendar_plugin_enabled and calendar_context
            has_web_search_input = web_search_plugin_enabled and enable_web_search

            if (
                user_message
                or has_file_input
                or has_calendar_input
                or has_web_search_input
            ):
                is_valid_input = True
            else:
                error_msg = "No message, files, context, or search request provided."
                logger.warning(
                    f"Invalid input for SID {sid}, Chat {chat_id}: {error_msg}"
                )
                emit("task_error", {"error": error_msg}, room=sid)
                return  # Stop processing

        if (
            not is_valid_input
        ):  # Should not be reached if logic above is correct, but defensive check
            logger.error(
                f"Input validation failed unexpectedly for SID {sid}, Chat {chat_id}."
            )
            emit("task_error", {"error": "Invalid input provided."}, room=sid)
            return

    except Exception as validation_err:
        logger.error(
            f"Error during input validation for SID {sid}, Chat {chat_id}: {validation_err}",
            exc_info=True,
        )
        emit(
            "task_error",
            {
                "error": f"Server error during input validation: {type(validation_err).__name__}"
            },
            room=sid,
        )
        return

    # --- Improve Prompt (Optional) ---
    original_user_message = user_message  # Keep original for logging/comparison
    if (
        improve_prompt_enabled and user_message and mode == "chat"
    ):  # Only improve for chat mode with text
        logger.info(
            f"Attempting to improve prompt for chat {chat_id} (SID: {sid}). Original: '{original_user_message[:100]}...'"
        )
        try:
            # prompt_improver uses generate_text which needs app context (available here)
            improved_prompt = ai_services.prompt_improver(prompt=user_message)

            # Check if the improver returned an error or valid text
            if improved_prompt and not improved_prompt.startswith(
                ("[Error", "[System Note", "[AI Error")
            ):
                logger.info(
                    f"Prompt improved successfully for chat {chat_id} (SID: {sid}). New: '{improved_prompt[:100]}...'"
                )

                emit(
                    "prompt_improved",
                    {"original": user_message, "improved": improved_prompt},
                )
                user_message = (
                    improved_prompt  # Replace user_message with the improved version
                )
                # Update the data dictionary so the background task gets the improved message
                data["message"] = user_message
            elif improved_prompt and improved_prompt.startswith(
                ("[Error", "[System Note", "[AI Error")
            ):
                logger.warning(
                    f"Prompt improvement failed for chat {chat_id} (SID: {sid}): {improved_prompt}. Using original prompt."
                )
                # Keep original user_message
            else:
                logger.warning(
                    f"Prompt improvement returned empty or unexpected result for chat {chat_id} (SID: {sid}). Using original prompt."
                )
                # Keep original user_message

        except Exception as improve_err:
            logger.error(
                f"Error calling prompt_improver for chat {chat_id} (SID: {sid}): {improve_err}",
                exc_info=True,
            )
            # Fallback to original user_message, do not stop the process
            logger.warning(
                f"Proceeding with original prompt for chat {chat_id} (SID: {sid}) after improvement error."
            )

    # --- Optional: Save Session Files as Persistent Files ---
    # If session files (from paperclip) should be saved to the main 'files' table
    processed_session_file_ids = []
    if session_files_payload:
        logger.info(f"Processing {len(session_files_payload)} session files for persistence...")
        for sf_data in session_files_payload:
            try:
                # Assuming content is base64 encoded string from JS FileReader
                if "," in sf_data['content']:
                    _, base64_string = sf_data['content'].split(",", 1)
                else:
                    base64_string = sf_data['content']
                file_content_bytes = base64.b64decode(base64_string)
                filesize = len(file_content_bytes)

                # Save to File table (commit each one for simplicity, or batch if needed)
                new_file_id = db_module.save_file_record_to_db(
                    filename=sf_data['filename'],
                    content_blob=file_content_bytes,
                    mimetype=sf_data['mimetype'],
                    filesize=filesize,
                    commit=True # Commit each session file
                )
                if new_file_id:
                    processed_session_file_ids.append(new_file_id)
                    logger.info(f"Saved session file '{sf_data['filename']}' as persistent File ID: {new_file_id}")
                    # Update the corresponding metadata entry with the new file_id
                    for att_meta in message_attachments_metadata:
                        if att_meta.get('type') == 'session' and att_meta.get('filename') == sf_data['filename']:
                            att_meta['file_id'] = new_file_id # Add the persistent file_id
                            att_meta['type'] = 'file' # Optionally change type to 'file' now
                            logger.debug(f"Updated metadata for '{sf_data['filename']}' with file_id: {new_file_id}")
                            break
                else:
                    logger.error(f"Failed to save session file '{sf_data['filename']}' to File table.")
            except base64.BinasciiError as b64_err:
                logger.error(f"Base64 decoding failed for session file '{sf_data['filename']}': {b64_err}")
            except Exception as e:
                logger.error(f"Error processing/saving session file '{sf_data['filename']}': {e}", exc_info=True)
    # --- End Session File Saving ---


    # --- Save User Message (Synchronously) ---
    # Use the potentially modified user_message
    logger.debug(
        f"Input validation passed for SID {sid}. Proceeding to save user message..."
    )  # ADDED LOG
    # Save the user message immediately before starting the background task
    user_save_success = False
    # Determine content for DB (e.g., if message is empty but attachments exist)
    user_message_content_for_db = user_message
    if not user_message_content_for_db and message_attachments_metadata:
        user_message_content_for_db = "[User sent attachments]" # Or similar placeholder

    if user_message_content_for_db: # Save if there's text OR attachments
        logger.info(f"Attempting to save user message for chat {chat_id} (SID: {sid}).")
        try:
            # Pass the potentially updated metadata to be saved in Message.attached_data
            user_save_success = db_module.add_message_to_db(
                chat_id=chat_id,
                role="user",
                content=user_message_content_for_db,
                attached_data_json=message_attachments_metadata if message_attachments_metadata else None
            )
            if user_save_success:
                logger.info(
                    f"Successfully saved user message for chat {chat_id} (SID: {sid}) with attachments metadata."
                )
                # Optional: Notify client that message was saved
                # emit('message_saved', {'role': 'user'}, room=sid)
            else:
                # Log the error, but proceed with the background task anyway.
                # The AI might still work, but history will be incomplete.
                logger.error(
                    f"Failed to save user message for chat {chat_id} (SID: {sid}) to database."
                )
        except Exception as db_err:
            logger.error(
                f"Database error saving user message for chat {chat_id} (SID: {sid}): {db_err}",
                exc_info=True,
            )
            # Emit error back to client and stop processing
            emit(
                "task_error",
                {
                    "error": f"Database error saving your message: {type(db_err).__name__}"
                },
                room=sid,
            )
            return  # Stop here if user message save fails

    # --- Start Background Task ---
    logger.debug(
        f"User message saved (or skipped). Proceeding to start background task for SID {sid}..."
    )  # ADDED LOG
    logger.info(
        f"Starting background task for SID {sid}, Chat ID {chat_id}, Mode {mode}."
    )
    app_instance = (
        current_app._get_current_object()
    )  # Ensure app instance is retrieved HERE
    try:
        # Optional: Notify client that processing has started
        emit("task_started", {"message": "Processing your request..."}, room=sid)
    except Exception as emit_err:
        # Handle potential error during emit itself (less likely)
        logger.error(
            f"Error emitting 'task_started' for SID {sid}: {emit_err}", exc_info=True
        )
        # Don't stop the whole process, but log it.

    try:
        # Pass the potentially updated metadata to the background task
        socketio.start_background_task(
            _process_chat_message_async,
            app=app_instance,  # Ensure app instance is passed
            sid=sid,
            data=data,  # Pass the full original data dictionary received
            message_attachments_metadata=message_attachments_metadata # Pass the metadata separately
        )
    except Exception as task_start_err:
        logger.error(
            f"Failed to start background task for SID {sid}, Chat {chat_id}: {task_start_err}",
            exc_info=True,
        )
        emit(
            "task_error",
            {
                "error": f"Server error: Failed to start processing task ({type(task_start_err).__name__})."
            },
            room=sid,
        )
        # Attempt to save an error message to DB as well
        try:
            db_module.add_message_to_db(
                chat_id,
                "assistant",
                f"[Server Error: Failed to start background task: {type(task_start_err).__name__}]",
                attached_data_json=None # Errors don't have attachments
            )
        except Exception as db_save_err:
            logger.error(
                f"Failed to save task start error to DB for chat {chat_id}: {db_save_err}",
                exc_info=True,
            )

    # The handler returns immediately, letting the background task run.
    logger.debug(f"Exiting 'send_chat_message' handler for SID {sid}.")
