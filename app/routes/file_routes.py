# app/routes/file_routes.py
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from .. import database as db # Use relative import for database module
from .. import ai_services # Use relative import for ai services
from .. import file_utils # Use relative import for file utils

# Create Blueprint for file API, using '/api' prefix
bp = Blueprint('file_api', __name__, url_prefix='/api')

@bp.route('/files', methods=['GET'])
def get_files():
    """API endpoint to get the list of uploaded files (metadata only)."""
    files = db.get_uploaded_files_from_db()
    return jsonify(files)

@bp.route('/files', methods=['POST'])
def upload_file_route():
    """API endpoint to upload new files (handles multiple). Saves as BLOB."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    uploaded_files_data = []
    errors = []
    max_size = current_app.config['MAX_FILE_SIZE_BYTES']

    for file in request.files.getlist('file'): # Handle multiple files with same key 'file'
        if file.filename == '':
            # errors.append("Empty file part submitted.") # Ignore empty parts silently?
            continue

        if file and file_utils.allowed_file(file.filename):
            filename = secure_filename(file.filename)
            mimetype = file.mimetype

            try:
                content_blob = file.read() # Read file content into bytes
                filesize = len(content_blob)

                # Check size after reading
                if filesize > max_size:
                     errors.append(f"File '{filename}' ({filesize} bytes) exceeds size limit ({max_size} bytes).")
                     continue # Skip this file

                # Save record and blob to DB
                file_id = db.save_file_record_to_db(filename, content_blob, mimetype, filesize)

                if file_id:
                    # Return metadata of successfully saved file
                    uploaded_files_data.append({
                        "id": file_id,
                        "filename": filename,
                        "mimetype": mimetype,
                        "filesize": filesize,
                        "uploaded_at": datetime.now().isoformat(),
                        "has_summary": False # New files don't have summaries yet
                    })
                else:
                    errors.append(f"Failed to save file '{filename}' to database.")

            except Exception as e:
                errors.append(f"Error processing file '{filename}': {e}")
                current_app.logger.error(f"Error processing upload for '{filename}': {e}", exc_info=True)

        elif file: # File submitted but extension not allowed
            errors.append(f"File type not allowed for '{file.filename}'.")

    # --- Response Handling ---
    if not uploaded_files_data and errors:
         # Only errors occurred
         return jsonify({"error": "; ".join(errors)}), 400
    elif uploaded_files_data:
         # Return data for successfully uploaded files, potentially with errors for others
         response_data = {"uploaded_files": uploaded_files_data}
         if errors:
             response_data["errors"] = errors
         return jsonify(response_data), 201 # Return 201 Created (even if some failed)
    else:
         # Should not happen if loop runs unless no files were sent or all failed validation before try block
         return jsonify({"error": "No valid files processed."}), 400


@bp.route('/files/<int:file_id>/summary', methods=['GET'])
def get_summary_route(file_id):
    """Gets or generates a summary for a specific file."""
    try:
        summary = ai_services.get_or_generate_summary(file_id)
        if summary.startswith("[Error"): # Check if the result is an error message
            return jsonify({"summary": summary}), 500 # Internal Server Error status for errors
        else:
            return jsonify({"summary": summary})
    except Exception as e:
        current_app.logger.error(f"Error getting/generating summary for file {file_id}: {e}", exc_info=True)
        return jsonify({"error": "Could not retrieve or generate summary"}), 500

@bp.route('/files/<int:file_id>/summary', methods=['PUT'])
def update_summary_route(file_id):
    """Manually updates the summary for a specific file."""
    # Allow saving summary for ANY file type now
    data = request.json
    new_summary = data.get('summary')
    if new_summary is None: # Check for None explicitly, allow empty string
        return jsonify({"error": "Summary content not provided"}), 400

    if db.save_summary_in_db(file_id, new_summary):
        return jsonify({"message": "Summary updated successfully."})
    else:
        # DB function already logs error
        return jsonify({"error": "Failed to update summary"}), 500

