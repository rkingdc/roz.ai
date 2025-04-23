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
    logger.info(f"WebSocket client connected: {sid}")
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
