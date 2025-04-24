import logging
from flask import Blueprint, request, jsonify, current_app
# Import voice_services directly
from app import voice_services, ai_services # Import ai_services and voice_services

logger = logging.getLogger(__name__)
bp = Blueprint('voice_api', __name__, url_prefix='/api/voice')

@bp.route('/transcribe', methods=['POST'])
def handle_transcribe():
    """
    API endpoint to receive audio data and return its transcription.
    Expects audio data in request.files['audio_file'].
    """
    logger.info("Received request at /api/voice/transcribe")

    if 'audio_file' not in request.files:
        logger.warning("No audio file found in the request.")
        return jsonify({"error": "No audio file part in the request"}), 400

    file = request.files['audio_file']

    if file.filename == '':
        logger.warning("No selected file.")
        return jsonify({"error": "No selected file"}), 400

    if file:
        try:
            audio_content = file.read()
            logger.info(f"Received audio file: {file.filename}, size: {len(audio_content)} bytes, mimetype: {file.mimetype}")

            # TODO: Potentially get language_code and sample_rate from request if needed
            # For now, using defaults from voice_services
            # sample_rate = int(request.form.get('sampleRate', 16000)) # Example if sent from frontend

            # Call the transcription service (OLD METHOD - Now handled by WebSockets)
            # transcript = transcribe_audio(audio_content) # Add params if needed
            # logger.info(f"Received audio file for non-streaming transcription (DEPRECATED): {file.filename}")
            # For now, return an error or a message indicating streaming should be used.
            logger.warning(f"Received request on deprecated HTTP endpoint for {file.filename}. Use WebSocket for streaming.")
            return jsonify({"error": "This endpoint is deprecated. Use WebSocket for streaming transcription."}), 405 # Method Not Allowed

            # --- Old logic ---
            # if transcript is not None:
            #     logger.info(f"Transcription successful for {file.filename}")
            #     return jsonify({"transcript": transcript}), 200
            # else:
            #     logger.error(f"Transcription failed for {file.filename}")
            #     return jsonify({"error": "Transcription failed"}), 500 # Internal Server Error or specific code
            # --- End Old logic ---

        except Exception as e: # Keep general error handling for file reading issues etc.
            logger.error(f"Error processing audio file {file.filename}: {e}", exc_info=True)
            return jsonify({"error": "Error processing audio file"}), 500
    else:
        # This case should technically be caught by checks above, but included for completeness
        logger.warning("File object was present but empty or invalid.")
        return jsonify({"error": "Invalid file"}), 400


@bp.route('/cleanup', methods=['POST'])
def handle_cleanup():
    """
    API endpoint to receive raw transcript text and return a cleaned version.
    Expects JSON body: {"transcript": "raw text..."}
    """
    logger.info("Received request at /api/voice/cleanup")

    if not request.is_json:
        logger.warning("Cleanup request is not JSON.")
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    raw_transcript = data.get('transcript')

    if not raw_transcript or not isinstance(raw_transcript, str):
        logger.warning("Missing or invalid 'transcript' field in cleanup request.")
        return jsonify({"error": "Missing or invalid 'transcript' field"}), 400

    if raw_transcript.isspace():
        logger.info("Received empty transcript for cleanup, returning empty.")
        return jsonify({"cleaned_transcript": ""}), 200

    try:
        # Call the cleanup function from ai_services
        # This function handles its own AI readiness check and error handling
        cleaned_transcript = ai_services.clean_up_transcript(raw_transcript)

        # Check if the cleanup function returned the original transcript (indicating a fallback/error)
        if cleaned_transcript == raw_transcript:
            logger.warning("Transcript cleanup failed or resulted in no change. Returning original.")
            # Optionally return a specific status or flag? For now, just return original.
            # Consider if frontend needs to know if cleanup *actually* happened.
            # Returning 200 but with original text might be confusing.
            # Let's return an error status if it failed internally.
            # We need a way for clean_up_transcript to signal failure vs. no change needed.
            # For now, assume if it returns the original, it might have failed.
            # Let's refine clean_up_transcript later if needed.
            # For this implementation, we'll return success but with potentially unchanged text.
            return jsonify({"cleaned_transcript": cleaned_transcript}), 200
        else:
            logger.info("Transcript cleaned successfully.")
            return jsonify({"cleaned_transcript": cleaned_transcript}), 200

    except Exception as e:
        logger.error(f"Unexpected error during transcript cleanup: {e}", exc_info=True)
        return jsonify({"error": "Internal server error during cleanup"}), 500


# --- NEW Route for Long Recording Transcription ---
@bp.route('/transcribe_long', methods=['POST'])
def transcribe_long_audio_route():
    """
    API endpoint to receive a complete audio file (blob) and return its transcription
    using the non-streaming API.
    Expects 'audio_blob' in files and 'languageCode', 'mimeType' in form data.
    """
    logger.info("Received request at /api/voice/transcribe_long")

    if 'audio_blob' not in request.files:
        logger.warning("Missing 'audio_blob' in request files.")
        return jsonify({"error": "Missing audio file part ('audio_blob')"}), 400

    audio_file = request.files['audio_blob']
    language_code = request.form.get('languageCode', 'en-US')
    # Get MIME type to determine encoding - crucial for Google API config
    mime_type = request.form.get('mimeType')

    if not mime_type:
        logger.warning("Missing 'mimeType' in request form data.")
        return jsonify({"error": "Missing mimeType parameter"}), 400

    # Map MIME type to the encoding string expected by voice_services.transcribe_audio_file
    # Ensure this mapping aligns with the frontend's MIME_TYPE and voice_services expectations
    # Use lowercase keys for case-insensitive matching after normalizing the input mime_type
    encoding_map = {
        "audio/webm": "WEBM_OPUS", # Match base type after splitting
        "audio/ogg": "OGG_OPUS",   # Match base type after splitting
        "audio/wav": "LINEAR16",   # Example if you support WAV
        # Add other base types as needed
    }
    # Normalize mime_type (lowercase, ignore parameters after ';')
    normalized_mime_type = mime_type.split(';')[0].lower()
    encoding = encoding_map.get(normalized_mime_type) # Look up using the normalized base type

    if not encoding:
        logger.error(f"Unsupported or unmapped MIME type received: {mime_type} (Normalized base type: {normalized_mime_type})")
        return jsonify({"error": f"Unsupported MIME type: {mime_type}"}), 400

    # Log file size (using content_length is an estimate, reading is more accurate)
    # file_size = request.content_length # Approximate size
    # logger.info(f"Processing audio file: name='{audio_file.filename}', approx size='{file_size}', language='{language_code}', mime='{mime_type}', mapped encoding='{encoding}'")
    logger.info(f"Processing audio file: name='{audio_file.filename}', language='{language_code}', mime='{mime_type}', mapped encoding='{encoding}'")


    try:
        audio_bytes = audio_file.read()
        actual_size = len(audio_bytes)
        logger.info(f"Read {actual_size} bytes from audio file.")

        if not audio_bytes:
            logger.warning("Received empty audio file.")
            return jsonify({"error": "Empty audio file received"}), 400

        # Call the non-streaming transcription service
        # Use the directly imported voice_services
        transcript = voice_services.transcribe_audio_file(
            audio_bytes=audio_bytes,
            language_code=language_code,
            encoding=encoding # Pass the determined encoding
        )

        if transcript is None:
            logger.error("Transcription failed (transcribe_audio_file returned None).")
            return jsonify({"error": "Transcription failed"}), 500

        logger.info("Successfully transcribed long audio.")
        # Optional: Clean the transcript here if desired
        # cleaned_transcript = ai_services.clean_up_transcript(transcript)
        # return jsonify({"transcript": cleaned_transcript}), 200
        return jsonify({"transcript": transcript}), 200

    except Exception as e:
        logger.error(f"Error processing long audio transcription request: {e}", exc_info=True)
        return jsonify({"error": "Internal server error during transcription"}), 500
