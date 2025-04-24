import logging
from flask import Blueprint, request, jsonify
from app import database, db # Import db instance
from app.models import NoteHistory # Import NoteHistory model

# Configure logging
logger = logging.getLogger(__name__)

bp = Blueprint('notes_api', __name__, url_prefix='/api')

@bp.route('/notes', methods=['GET'])
def get_all_notes():
    """API endpoint to retrieve a list of all notes."""
    logger.info("Received GET request for /api/notes")
    try:
        notes_list = database.get_saved_notes_from_db()
        if notes_list is None:
            # If get_saved_notes_from_db returns None, it indicates a database error
            logger.error("Failed to retrieve notes list from database.")
            return jsonify({"error": "Failed to retrieve notes list"}), 500

        logger.info(f"Successfully retrieved {len(notes_list)} notes.")
        return jsonify(notes_list)

    except Exception as e:
        logger.error(f"An unexpected error occurred while getting notes list: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500

@bp.route('/notes', methods=['POST'])
def create_new_note():
    """API endpoint to create a new note."""
    logger.info("Received POST request for /api/notes")
    try:
        new_note_id = database.create_new_note_entry()
        if new_note_id is None:
            logger.error("Failed to create new note entry in database.")
            return jsonify({"error": "Failed to create new note"}), 500

        # Fetch the newly created note details to return
        new_note = database.get_note_from_db(new_note_id)
        if new_note is None:
             logger.error(f"Failed to retrieve details for newly created note ID {new_note_id}.")
             # Still return success but maybe with minimal info or an error about fetching details
             return jsonify({"message": "Note created, but failed to fetch details", "id": new_note_id}), 201 # Created
        logger.info(f"Successfully created new note with ID: {new_note_id}")
        return jsonify(new_note), 201 # Created

    except Exception as e:
        logger.error(f"An unexpected error occurred while creating note: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500


@bp.route('/note/<int:note_id>', methods=['GET'])
def get_note(note_id):
    """API endpoint to retrieve a specific note content by ID."""
    logger.info(f"Received GET request for /api/note/{note_id}")
    try:
        note_details = database.get_note_from_db(note_id)
        if note_details is None:
            logger.warning(f"Note with ID {note_id} not found.")
            return jsonify({"error": "Note not found"}), 404

        logger.info(f"Successfully retrieved note with ID: {note_id}.")
        return jsonify(note_details)

    except Exception as e:
        logger.error(f"An unexpected error occurred while getting note {note_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500

@bp.route('/note/<int:note_id>', methods=['PUT'])
def save_note(note_id):
    """API endpoint to save a specific note content by ID."""
    logger.info(f"Received PUT request for /api/note/{note_id}")
    data = request.get_json()
    if not data or 'content' not in data or 'name' not in data:
        logger.warning(f"PUT request for /api/note/{note_id} missing 'name' or 'content' in body.")
        return jsonify({"error": "Missing 'name' or 'content' in request body"}), 400

    note_name = data['name']
    note_content = data['content']
    logger.info(f"Attempting to save note ID: {note_id} (name: '{note_name}', content length: {len(note_content)})...")

    try:
        success = database.save_note_to_db(note_id, note_name, note_content)
        if not success:
            # Check if the failure was because the note ID wasn't found
            # This requires checking the database function's return or adding a specific check
            # For now, assume generic failure or note not found if update affected 0 rows
            # A more robust implementation might check rowcount in save_note_to_db
            note_exists = database.get_note_from_db(note_id) is not None
            if not note_exists:
                 logger.warning(f"Attempted to save note ID {note_id} but it was not found.")
                 return jsonify({"error": "Note not found"}), 404
            else:
                 logger.error(f"Failed to save note content to database for ID {note_id}.")
                 return jsonify({"error": "Failed to save note content"}), 500


        logger.info(f"Successfully saved note ID: {note_id}.")
        # Optionally return the updated note details or just a success message
        return jsonify({"message": "Note saved successfully"})

    except Exception as e:
        logger.error(f"An unexpected error occurred while saving note {note_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500

@bp.route('/note/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    """API endpoint to delete a specific note by ID."""
    logger.info(f"Received DELETE request for /api/note/{note_id}")
    try:
        success = database.delete_note_from_db(note_id)
        if not success:
            # Check if the failure was because the note ID wasn't found
            note_exists = database.get_note_from_db(note_id) is not None # Check *before* attempting delete for clearer error
            if not note_exists:
                 logger.warning(f"Attempted to delete note ID {note_id} but it was not found.")
                 return jsonify({"error": "Note not found"}), 404
            else:
                 logger.error(f"Failed to delete note from database for ID {note_id}.")
                 return jsonify({"error": "Failed to delete note"}), 500

        logger.info(f"Successfully deleted note ID: {note_id}.")
        return jsonify({"message": "Note deleted successfully"})

    except Exception as e:
        logger.error(f"An unexpected error occurred while deleting note {note_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500

# --- NEW: API endpoint to retrieve note history by ID ---
@bp.route('/notes/<int:note_id>/history', methods=['GET'])
def get_note_history(note_id):
    """API endpoint to retrieve the history of a specific note by ID."""
    logger.info(f"Received GET request for /api/notes/{note_id}/history")
    try:
        # First, check if the note itself exists
        note_exists = database.get_note_from_db(note_id) is not None
        if not note_exists:
            logger.warning(f"Note with ID {note_id} not found when requesting history.")
            return jsonify({"error": "Note not found"}), 404

        # If the note exists, fetch its history
        history_list = database.get_note_history_from_db(note_id)
        if history_list is None:
            # If get_note_history_from_db returns None, it indicates a database error
            logger.error(f"Failed to retrieve note history from database for ID {note_id}.")
            return jsonify({"error": "Failed to retrieve note history"}), 500

        logger.info(f"Successfully retrieved {len(history_list)} history entries for note ID: {note_id}.")
        return jsonify(history_list)

    except Exception as e:
        logger.error(f"An unexpected error occurred while getting note history for {note_id}: {e}", exc_info=True)
        logger.error(f"An unexpected error occurred while getting note history for {note_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500

# --- Removed generate_and_save_note_diff_summary endpoint ---
# Summary generation is now handled within the PUT /api/note/<note_id> endpoint (via database.save_note_to_db)

# --- NEW: API endpoint to generate summary for a specific history item ON DEMAND ---
@bp.route('/notes/<int:note_id>/history/<int:history_id>/generate_summary', methods=['POST'])
def generate_history_item_summary(note_id, history_id):
    """
    API endpoint to generate an AI summary for a specific note history entry
    on demand (e.g., when clicking a 'pending' item).
    """
    logger.info(f"Received POST request for /api/notes/{note_id}/history/{history_id}/generate_summary")

    try:
        # 1. Get the target history entry
        target_entry_dict = database.get_note_history_entry_from_db(history_id)
        if not target_entry_dict or target_entry_dict['note_id'] != note_id:
            logger.warning(f"Target history entry {history_id} not found or doesn't belong to note {note_id}.")
            return jsonify({"error": "History entry not found"}), 404

        # Check if summary already exists (maybe generated by another request)
        if target_entry_dict.get('note_diff') and not target_entry_dict['note_diff'].startswith("["):
             logger.info(f"Summary already exists for history entry {history_id}. Skipping generation.")
             return jsonify({"summary": target_entry_dict['note_diff'], "message": "Summary already existed."})


        # 2. Get the *previous* history entry
        # Need to query the model directly here
        target_entry_obj = db.session.get(NoteHistory, history_id) # Get the SQLAlchemy object
        if not target_entry_obj: # Should not happen if dict fetch worked, but check anyway
             return jsonify({"error": "History entry object not found"}), 404

        previous_entry = NoteHistory.query.filter(
            NoteHistory.note_id == note_id,
            NoteHistory.saved_at < target_entry_obj.saved_at # Use object's saved_at
        ).order_by(NoteHistory.saved_at.desc()).first()

        summary_to_save = None
        # If no previous entry, this is the initial version.
        if not previous_entry:
            logger.info(f"Marking history entry {history_id} as initial version (on-demand generation).")
            summary_to_save = "[Initial version]"
        else:
            # 3. Get content for both versions
            version_1_content = previous_entry.content if previous_entry.content is not None else ""
            version_2_content = target_entry_obj.content if target_entry_obj.content is not None else "" # Use object's content

            # Check if content actually changed (maybe only name changed previously)
            if version_1_content == version_2_content:
                 logger.info(f"Content identical between history {previous_entry.id} and {history_id}. Marking as metadata change.")
                 summary_to_save = "[Metadata change only]"
            else:
                # 4. Call AI service to generate summary
                from app import ai_services # Import inside function or at top if preferred
                logger.info(f"Calling AI service to generate diff summary between history {previous_entry.id} and {history_id} (on-demand).")
                generated_summary = ai_services.generate_note_diff_summary(version_1_content, version_2_content)

                # Check for AI errors
                if generated_summary.startswith(("[Error", "[AI Error", "[System Note")):
                    logger.error(f"AI service failed to generate diff summary for history {history_id} (on-demand): {generated_summary}")
                    summary_to_save = "[AI summary generation failed]" # Save error marker
                else:
                    summary_to_save = generated_summary
                    logger.info(f"AI summary generated successfully for history entry {history_id} (on-demand).")

        # 5. Save the generated summary/marker to the target history entry using the new DB function
        if database.update_note_history_diff(history_id, summary_to_save):
            logger.info(f"Successfully saved generated summary/marker for history ID: {history_id}")
            return jsonify({"summary": summary_to_save})
        else:
            logger.error(f"Failed to save generated summary/marker for history ID: {history_id}")
            # Return the summary anyway, but indicate save failure
            return jsonify({"summary": summary_to_save, "error": "Failed to save generated summary"}), 500

    except Exception as e:
        logger.error(f"An unexpected error occurred while generating/saving on-demand diff summary for history {history_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500
# -------------------------------------------------------
