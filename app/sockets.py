import logging
from flask import request, current_app
from flask_socketio import emit, join_room, leave_room, disconnect
from google.api_core.exceptions import OutOfRange
import threading # Import threading
import queue # Import queue

from app import socketio
# Import the necessary functions from voice_services
from app.voice_services import transcribe_stream, send_audio_chunk_to_queue, signal_end_of_stream

logger = logging.getLogger(__name__)

# Dictionary to hold audio queues keyed by session ID (sid)
# Moved to voice_services.py to be shared with the listener thread
# client_audio_queues = {}
# _queue_lock = threading.Lock() # Lock also moved

@socketio.on('connect')
def handle_connect():
    """Handles new client connections."""
    logger.info(f"WebSocket client connected: {request.sid}")
    # Optionally join a room specific to the user/session if needed later
    # join_room(request.sid)


@socketio.on('disconnect')
def handle_disconnect():
    """Handles client disconnections."""
    sid = request.sid
    logger.info(f"WebSocket client disconnected: {sid}")
    # Signal the end of the stream if the client disconnects abruptly
    # The listener thread in voice_services will handle queue cleanup
    logger.info(f"Signaling end of stream due to disconnect for SID: {sid}")
    signal_end_of_stream(sid)
    # Optionally leave rooms if joined


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
        # Send confirmation back to client
        emit('transcription_started', {'message': 'Streaming transcription ready.'})

    except Exception as e:
        logger.error(f"Error starting transcription stream for {sid}: {e}", exc_info=True)
        emit('transcription_error', {'error': f'Failed to start transcription: {e}'})


@socketio.on('audio_chunk')
def handle_audio_chunk(chunk):
    """Receives an audio chunk from the client and sends it to the appropriate queue."""
    sid = request.sid
    # logger.debug(f"Received audio chunk from {sid}, size: {len(chunk)} bytes") # Very verbose

    if not send_audio_chunk_to_queue(sid, chunk):
         # Error sending (queue didn't exist)
         logger.warning(f"Failed to send audio chunk for SID {sid}: No active queue found.")
         emit('transcription_error', {'error': 'No active transcription stream found. Please start first.'})
         # Consider disconnecting the client if they send chunks without starting
         # disconnect(sid)


@socketio.on('stop_transcription')
def handle_stop_transcription():
    """Client explicitly signals the end of audio transmission."""
    sid = request.sid
    logger.info(f"Received stop_transcription request from {sid}")
    # Signal the end of the stream
    if not signal_end_of_stream(sid):
        logger.warning(f"Received stop_transcription from {sid} but no active stream found.")
    # The listener thread will send the final transcription result and clean up.
    # We can send a confirmation that the stop signal was received.
    emit('transcription_stop_acknowledged', {'message': 'Stop signal received.'})

# Note: Functions to emit results are now called directly from the background thread
# in voice_services.py using the imported `socketio` instance.
