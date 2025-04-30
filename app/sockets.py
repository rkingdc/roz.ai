import logging
from flask import request # Removed current_app, not used here
from flask_socketio import emit, join_room, leave_room, disconnect # Added disconnect
# Removed OutOfRange, threading, queue - they are handled within voice_services
# from google.api_core.exceptions import OutOfRange
# import threading
# import queue

from app import socketio
# Import the necessary functions from voice_services
from app.voice_services import transcribe_stream, send_audio_chunk_to_queue, signal_end_of_stream

logger = logging.getLogger(__name__) # Use the standard logger name

# No need for queue management here, it's in voice_services

@socketio.on('connect')
def handle_connect():
    """Handles new client connections."""
    sid = request.sid
    logger.info(f"****** WebSocket client connected: SID={sid} ******") # MODIFIED LOG
    # Join a room specific to the session ID so we can emit directly to this client
    join_room(sid)
    logger.info(f"Client {sid} joined its room.")


@socketio.on('disconnect')
def handle_disconnect():
    """Handles client disconnections."""
    sid = request.sid
    logger.info(f"WebSocket client disconnected: {sid}")
    # Signal the end of the stream if the client disconnects abruptly
    # The listener thread in voice_services will handle queue cleanup.
    logger.info(f"Signaling end of stream due to disconnect for SID: {sid}")
    signal_end_of_stream(sid)
    # Leave the room associated with the session
    leave_room(sid)
    logger.info(f"Client {sid} left its room.")


@socketio.on('start_transcription')
def handle_start_transcription(data):
    """
    Starts a new transcription stream when requested by the client.
    Expects data like {'languageCode': 'en-US', 'audioFormat': 'WEBM_OPUS'}
    """
    sid = request.sid
    logger.info(f"Received start_transcription request from {sid}. Data: {data}")

    # Clean up any previous stream for this SID just in case
    logger.info(f"Signaling end of any previous stream for SID: {sid} before starting new one.")
    signal_end_of_stream(sid) # Ensure any lingering listener thread cleans up

    language_code = data.get('languageCode', 'en-US')
    # We know the frontend sends WEBM_OPUS based on previous fixes
    encoding = 'WEBM_OPUS'
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
        emit('transcription_started', {'message': 'Streaming transcription ready.'}, room=sid)

    except Exception as e:
        logger.error(f"Error starting transcription stream for {sid}: {e}", exc_info=True)
        # Send error back to the specific client
        emit('transcription_error', {'error': f'Failed to start transcription: {e}'}, room=sid)


@socketio.on('audio_chunk')
def handle_audio_chunk(chunk):
    """Receives an audio chunk from the client and sends it to the appropriate queue."""
    sid = request.sid
    # logger.debug(f"Received audio chunk from {sid}, size: {len(chunk)} bytes") # Verbose

    # Use the function from voice_services to put the chunk in the correct queue
    if not send_audio_chunk_to_queue(sid, chunk):
         # Error sending (queue didn't exist, stream likely not started or already stopped)
         logger.warning(f"Failed to send audio chunk for SID {sid}: No active queue found.")
         # Notify the client that the stream isn't active
         emit('transcription_error', {'error': 'No active transcription stream found. Please start first.'}, room=sid)
         # Consider disconnecting the client if they send chunks without starting
         # disconnect(sid)


@socketio.on('stop_transcription')
def handle_stop_transcription():
    """Client explicitly signals the end of audio transmission."""
    sid = request.sid
    logger.info(f"Received stop_transcription signal from {sid}")

    # Use the function from voice_services to signal the end (puts None in queue)
    if signal_end_of_stream(sid):
        # Acknowledge receipt of the stop signal to the client
        emit('transcription_stop_acknowledged', {'message': 'Stop signal received.'}, room=sid)
        # The listener thread in voice_services handles sending final results and cleanup.
    else:
        logger.warning(f"Received stop_transcription from {sid} but no active stream found.")
        # Optionally notify the client if no stream was active
        # emit('transcription_error', {'error': 'No active transcription stream to stop.'}, room=sid)

# Note: Functions to emit transcription results ('transcript_update', 'transcription_error')
# are called directly from the background listener thread in voice_services.py
# using the imported `socketio` instance and `room=sid`.


# --- Chat Message Handling ---

# Import necessary modules for chat handling
from . import database as db # Use relative import
from . import ai_services
from . import deep_research
# from .app import socketio # socketio is already imported at the top
from flask import current_app # Import current_app


def _process_chat_message_async(app, sid, data): # Add app argument
    """
    Runs in a background task to process chat messages (AI or Deep Research).
    Emits results back to the client via SocketIO.
    Requires an active application context.
    """
    chat_id = data.get("chat_id")
    user_message = data.get("message", "")
    attached_files = data.get("attached_files", [])
    session_files = data.get("session_files", [])
    calendar_context = data.get("calendar_context")
    enable_web_search = data.get("enable_web_search", False)
    enable_streaming = data.get("enable_streaming", False)
    mode = data.get("mode", "chat")

    logger.info(f"Background task started for SID {sid}, Chat ID {chat_id}, Mode {mode}.")

    # --- Create App Context ---
    # Use the app instance passed from the main thread
    with app.app_context():
        logger.debug(f"App context created successfully for background task (SID: {sid})")
        try:
            if mode == 'deep_research':
                logger.info(f"Calling deep_research.perform_deep_research for SID {sid}, Chat {chat_id}")
                # Pass socketio and sid for emitting results
                deep_research.perform_deep_research(
                    query=user_message,
                    socketio=socketio,
                    sid=sid,
                    chat_id=chat_id # Pass chat_id for saving the result
                )
                # perform_deep_research now handles emitting 'deep_research_result' or 'task_error'
                # and saving the result to the database.
                logger.info(f"Background task completed for deep research (SID {sid}, Chat {chat_id}).")

            else: # mode is 'chat'
                logger.info(f"Calling ai_services.generate_chat_response for SID {sid}, Chat {chat_id}. Streaming: {enable_streaming}")
                # Pass socketio and sid for emitting results
                # generate_chat_response will handle streaming/non-streaming emits and saving the result
                ai_services.generate_chat_response(
                    chat_id=chat_id,
                    user_message=user_message,
                    attached_files=attached_files,
                    session_files=session_files,
                    calendar_context=calendar_context,
                    web_search_enabled=enable_web_search,
                    streaming_enabled=enable_streaming,
                    socketio=socketio, # Pass socketio instance
                    sid=sid           # Pass client's session ID
                )
                # generate_chat_response now handles emitting 'chat_response', 'stream_chunk', 'stream_end', or 'task_error'
                # and saving the result to the database.
                logger.info(f"Background task completed for chat (SID {sid}, Chat {chat_id}). Streaming: {enable_streaming}")

        except Exception as e:
            # Catch-all for unexpected errors during the background task execution
            logger.error(f"Unexpected error in background task for SID {sid}, Chat {chat_id}: {e}", exc_info=True)
            try:
                # Emit an error message back to the specific client
                error_msg = f"[Unexpected Server Error in background task: {type(e).__name__}]"
                socketio.emit('task_error', {'error': error_msg}, room=sid)

                # Attempt to save the error message to the chat history as well
                logger.info(f"Attempting to save background task error message for chat {chat_id}.")
                db.add_message_to_db(chat_id, "assistant", error_msg) # Role is assistant for system errors
            except Exception as emit_save_err:
                logger.error(f"CRITICAL: Failed to emit or save background task error for SID {sid}, Chat {chat_id}: {emit_save_err}", exc_info=True)


@socketio.on('send_chat_message')
def handle_send_chat_message(data):
    """
    Handles incoming chat messages from the client via SocketIO.
    Saves the user message and starts a background task for processing.
    """
    sid = request.sid
    logger.info(f"****** Received 'send_chat_message' event from SID: {sid} ******") # ADDED LOG
    logger.debug(f"Raw data received for 'send_chat_message': {data}") # ADDED LOG

    chat_id = data.get("chat_id")
    user_message = data.get("message", "")
    mode = data.get("mode", "chat")
    # Get other fields needed for validation/saving
    attached_files = data.get("attached_files", [])
    session_files = data.get("session_files", [])
    calendar_context = data.get("calendar_context")
    enable_web_search = data.get("enable_web_search", False)

    logger.info(f"Processing 'send_chat_message' from SID {sid} for Chat ID {chat_id}. Mode: {mode}") # Modified log

    # --- Input Validation (similar to old HTTP route) ---
    logger.debug(f"Starting input validation for SID {sid}...") # ADDED LOG
    is_valid_input = False
    try:
        if mode == 'deep_research':
            if user_message and not user_message.isspace():
                is_valid_input = True
            else:
                error_msg = "Deep Research mode requires a text query."
                logger.warning(f"Invalid input for SID {sid}, Chat {chat_id}: {error_msg}")
                emit('task_error', {'error': error_msg}, room=sid)
                return # Stop processing
        else: # mode is 'chat'
            # Check if any relevant input exists for chat mode
            # Use state values passed from client payload
            files_plugin_enabled = data.get("enable_files_plugin", False)
            calendar_plugin_enabled = data.get("enable_calendar_plugin", False)
            web_search_plugin_enabled = data.get("enable_web_search_plugin", False)

            has_file_input = files_plugin_enabled and (attached_files or session_files)
            has_calendar_input = calendar_plugin_enabled and calendar_context
            has_web_search_input = web_search_plugin_enabled and enable_web_search

            if user_message or has_file_input or has_calendar_input or has_web_search_input:
                is_valid_input = True
            else:
                error_msg = "No message, files, context, or search request provided."
                logger.warning(f"Invalid input for SID {sid}, Chat {chat_id}: {error_msg}")
                emit('task_error', {'error': error_msg}, room=sid)
                return # Stop processing

        if not is_valid_input: # Should not be reached if logic above is correct, but defensive check
            logger.error(f"Input validation failed unexpectedly for SID {sid}, Chat {chat_id}.")
            emit('task_error', {'error': "Invalid input provided."}, room=sid)
            return

    except Exception as validation_err:
         logger.error(f"Error during input validation for SID {sid}, Chat {chat_id}: {validation_err}", exc_info=True)
         emit('task_error', {'error': f"Server error during input validation: {type(validation_err).__name__}"}, room=sid)
         return

    # --- Save User Message (Synchronously) ---
    logger.debug(f"Input validation passed for SID {sid}. Proceeding to save user message...") # ADDED LOG
    # Save the user message immediately before starting the background task
    user_save_success = False
    if user_message:
        logger.info(f"Attempting to save user message for chat {chat_id} (SID: {sid}).")
        try:
            user_save_success = db.add_message_to_db(chat_id, "user", user_message)
            if user_save_success:
                logger.info(f"Successfully saved user message for chat {chat_id} (SID: {sid}).")
                # Optional: Notify client that message was saved
                # emit('message_saved', {'role': 'user'}, room=sid)
            else:
                # Log the error, but proceed with the background task anyway.
                # The AI might still work, but history will be incomplete.
                logger.error(f"Failed to save user message for chat {chat_id} (SID: {sid}) to database.")
        except Exception as db_err:
             logger.error(f"Database error saving user message for chat {chat_id} (SID: {sid}): {db_err}", exc_info=True)
             # Emit error back to client and stop processing
             emit('task_error', {'error': f"Database error saving your message: {type(db_err).__name__}"}, room=sid)
             return # Stop here if user message save fails

    # --- Start Background Task ---
    logger.debug(f"User message saved (or skipped). Proceeding to start background task for SID {sid}...") # ADDED LOG
    logger.info(f"Starting background task for SID {sid}, Chat ID {chat_id}, Mode {mode}.")
    app_instance = current_app._get_current_object() # Get app instance HERE
    try:
        # Optional: Notify client that processing has started
        emit('task_started', {'message': 'Processing your request...'}, room=sid)
    except Exception as emit_err:
         # Handle potential error during emit itself (less likely)
         logger.error(f"Error emitting 'task_started' for SID {sid}: {emit_err}", exc_info=True)
         # Don't stop the whole process, but log it.

    try:
        socketio.start_background_task(
            _process_chat_message_async,
            app=app_instance, # Pass the app instance
            sid=sid,
            data=data # Pass the full data dictionary received
        )
    except Exception as task_start_err:
        logger.error(f"Failed to start background task for SID {sid}, Chat {chat_id}: {task_start_err}", exc_info=True)
        emit('task_error', {'error': f"Server error: Failed to start processing task ({type(task_start_err).__name__})."}, room=sid)
        # Attempt to save an error message to DB as well
        try:
            db.add_message_to_db(chat_id, "assistant", f"[Server Error: Failed to start background task: {type(task_start_err).__name__}]")
        except Exception as db_save_err:
            logger.error(f"Failed to save task start error to DB for chat {chat_id}: {db_save_err}", exc_info=True)

    # The handler returns immediately, letting the background task run.
    logger.debug(f"Exiting 'send_chat_message' handler for SID {sid}.")
