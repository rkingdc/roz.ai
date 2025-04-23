import logging
from flask import Blueprint, request, jsonify, current_app
from app.voice_services import transcribe_audio

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

            # Call the transcription service
            transcript = transcribe_audio(audio_content) # Add params if needed

            if transcript is not None:
                logger.info(f"Transcription successful for {file.filename}")
                return jsonify({"transcript": transcript}), 200
            else:
                logger.error(f"Transcription failed for {file.filename}")
                return jsonify({"error": "Transcription failed"}), 500 # Internal Server Error or specific code

        except Exception as e:
            logger.error(f"Error processing audio file {file.filename}: {e}", exc_info=True)
            return jsonify({"error": "Error processing audio file"}), 500
    else:
        # This case should technically be caught by checks above, but included for completeness
        logger.warning("File object was present but empty or invalid.")
        return jsonify({"error": "Invalid file"}), 400
