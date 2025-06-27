import logging
from flask import current_app, g
from google.api_core.exceptions import GoogleAPIError, ClientError, InvalidArgument, DeadlineExceeded, NotFound
from .. import database
from .generation_services import generate_text # Import generate_text
from .summary_services import generate_note_diff_summary # Import generate_note_diff_summary

logger = logging.getLogger(__name__)

def get_note_content_for_ai(note_id: int) -> str:
    """
    Retrieves note content from the database for AI processing.
    Returns the note content as a string or an error message.
    """
    logger.info(f"Fetching note content for AI for note_id: {note_id}")
    try:
        note = database.get_note_from_db(note_id)
        if note and note.get('content'):
            return note['content']
        else:
            logger.warning(f"Note {note_id} not found or has no content.")
            return f"[System Note: Note {note_id} not found or is empty.]"
    except Exception as e:
        logger.error(f"Error fetching note {note_id} for AI: {e}", exc_info=True)
        return f"[System Error: Failed to retrieve note content for AI: {type(e).__name__}]"

def generate_note_summary(note_id: int, flask_app) -> str: # Added flask_app parameter
    """
    Generates a summary of a note using an LLM.
    """
    logger.info(f"Generating summary for note_id: {note_id}")

    with flask_app.app_context(): # Push context here
        # --- AI Readiness Check ---
        try:
            try:
                _ = current_app.config # Simple check that raises RuntimeError if no context
                logger.debug("generate_note_summary: Flask request context is active.")
            except RuntimeError:
                logger.error("generate_note_summary called outside of active Flask app/request context.", exc_info=True)
                return "[Error: AI Service called outside request context]"

            api_key = current_app.config.get("API_KEY")
            if not api_key:
                logger.error("API_KEY is missing from current_app.config.")
                return "[Error: AI Service API Key not configured]"

            try:
                # Use client caching via Flask's 'g' object if in request context
                if "genai_client" not in g:
                    logger.info("Creating new genai.Client and caching in 'g'.")
                    g.genai_client = genai.Client(api_key=api_key)
                else:
                    logger.debug("Using cached genai.Client from 'g'.")
                client = g.genai_client
                logger.info("Successfully obtained genai.Client for note summary.")
            except (GoogleAPIError, ClientError, ValueError, Exception) as e:
                logger.error(f"Failed to initialize/get genai.Client for note summary: {e}", exc_info=True)
                if "api key not valid" in str(e).lower():
                    return "[Error: Invalid Gemini API Key]"
                return "[Error: Failed to initialize AI client]"

        except Exception as e:
            # Catch any unexpected errors during the readiness check itself
            logger.error(f"generate_note_summary: Unexpected error during readiness check: {type(e).__name__} - {e}", exc_info=True)
            return f"[CRITICAL Unexpected Error during AI Service readiness check: {type(e).__name__}]"
        # --- End AI Readiness Check ---

        note_content = get_note_content_for_ai(note_id)
        if note_content.startswith(("[System Note", "[System Error", "[Error")):
            return f"[Error: Could not retrieve note content for summary: {note_content}]"

        prompt = f"""
        Summarize the following note content concisely and accurately.
        Focus on the main points, key ideas, and any actionable information.
        The summary should be suitable for a quick overview.

        Note Content:
        ---
        {note_content}
        ---

        Concise Summary:
        """
        try:
            summary = generate_text(prompt)
            if summary and not summary.startswith(("[Error", "[System Note")):
                logger.info(f"Successfully generated summary for note {note_id}.")
                return summary
            else:
                logger.error(f"LLM failed to generate summary for note {note_id}: {summary}")
                return f"[Error: Failed to generate summary for note {note_id}. {summary}]"
        except Exception as e:
            logger.error(f"Error in generate_note_summary for note {note_id}: {e}", exc_info=True)
            return f"[Error: Exception during note summary generation: {e}]"

def generate_note_history_summary(note_history_id: int, flask_app) -> str: # Added flask_app parameter
    """
    Generates a summary for a specific note history entry.
    This function is called by the notes_routes.
    """
    logger.info(f"Generating summary for note history ID: {note_history_id}")

    with flask_app.app_context(): # Push context here
        # --- AI Readiness Check ---
        try:
            # Check for Flask request context
            try:
                _ = current_app.config # Simple check that raises RuntimeError if no context
                logger.debug("generate_note_history_summary: Flask request context is active.")
            except RuntimeError:
                logger.error("generate_note_history_summary called outside of active Flask app/request context.", exc_info=True)
                return "[Error: AI Service called outside request context]"

            api_key = current_app.config.get("API_KEY")
            if not api_key:
                logger.error("API_KEY is missing from current_app.config.")
                return "[Error: AI Service API Key not configured]"

            try:
                # Use client caching via Flask's 'g' object if in request context
                if "genai_client" not in g:
                    logger.info("Creating new genai.Client for note history summary.")
                    g.genai_client = genai.Client(api_key=api_key)
                else:
                    logger.debug("Using cached genai.Client for note history summary.")
                client = g.genai_client
                logger.info("Successfully obtained genai.Client for note history summary.")
            except (GoogleAPIError, ClientError, ValueError, Exception) as e:
                logger.error(f"Failed to initialize/get genai.Client for note history summary: {e}", exc_info=True)
                if "api key not valid" in str(e).lower():
                    return "[Error: Invalid Gemini API Key]"
                return "[Error: Failed to initialize AI client]"

        except Exception as e:
            # Catch any unexpected errors during the readiness check itself
            logger.error(f"generate_note_history_summary: Unexpected error during readiness check: {type(e).__name__} - {e}", exc_info=True)
            return f"[CRITICAL Unexpected Error during AI Service readiness check: {type(e).__name__}]"
        # --- End AI Readiness Check ---

        history_entry = database.get_note_history_entry_from_db(note_history_id)
        if not history_entry:
            logger.warning(f"Note history entry {note_history_id} not found.")
            return f"[Error: Note history entry {note_history_id} not found.]"

        note_id = history_entry.get('note_id')
        note_content = history_entry.get('content')
        note_diff = history_entry.get('note_diff') # This is the diff string

        if note_diff:
            logger.info(f"Generating diff summary for note history {note_history_id}.")
            summary = generate_note_diff_summary(note_diff) # Call the diff summary service
            if summary and not summary.startswith(("[Error", "[System Note")):
                return summary
            else:
                logger.error(f"Diff summary generation failed for history {note_history_id}: {summary}")
                return f"[Error: Failed to generate diff summary for history {note_history_id}. {summary}]"
        elif note_content:
            logger.info(f"Generating full content summary for note history {note_history_id}.")
            prompt = f"""
            Summarize the following note content concisely and accurately.
            Focus on the main points, key ideas, and any actionable information.
            The summary should be suitable for a quick overview.

            Note Content (from history ID {note_history_id}):
            ---
            {note_content}
            ---

            Concise Summary:
            """
            try:
                summary = generate_text(prompt)
                if summary and not summary.startswith(("[Error", "[System Note")):
                    logger.info(f"Successfully generated full content summary for note history {note_history_id}.")
                    return summary
                else:
                    logger.error(f"LLM failed to generate full content summary for note history {note_history_id}: {summary}")
                    return f"[Error: Failed to generate full content summary for note history {note_history_id}. {summary}]"
            except Exception as e:
                logger.error(f"Error in generate_note_history_summary (full content) for history {note_history_id}: {e}", exc_info=True)
                return f"[Error: Exception during note history full content summary generation: {e}]"
        else:
            logger.warning(f"Note history entry {note_history_id} has no content or diff to summarize.")
            return f"[System Note: No content or diff found for history entry {note_history_id} to summarize.]"
