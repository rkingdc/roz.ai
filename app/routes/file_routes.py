# app/routes/file_routes.py
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from .. import database as db # Use relative import for database module
from .. import ai_services # Use relative import for ai services
from .. import file_utils # Use relative import for file utils
from ..plugins import web_search
import validators # Import validators library for URL validation
from sqlalchemy.exc import SQLAlchemyError # Import SQLAlchemyError

# Configure logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    try:
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
                         errors.append(f"File '{filename}' ({filesize} bytes) exceeds size limit ({max_size // 1024 // 1024} MB).")
                         continue # Skip this file

                    # Save record and blob to DB - DO NOT COMMIT YET
                    # save_file_record_to_db now returns the File object or None on add error
                    file_obj = db.save_file_record_to_db(filename, content_blob, mimetype, filesize, commit=False)

                    if file_obj:
                        # Add the file object to a temporary list to get its ID after commit
                        # We can't get the ID reliably until after the commit
                        # For now, just track that it was added to the session successfully
                        # We'll retrieve details after the commit
                        pass # File object is in the session now

                    else:
                        # save_file_record_to_db logs its own error on add failure
                        errors.append(f"Failed to add file '{filename}' to database session.")

                except Exception as e:
                    errors.append(f"Error processing file '{filename}': {e}")
                    current_app.logger.error(f"Error processing upload for '{filename}': {e}", exc_info=True)

            elif file: # File submitted but extension not allowed
                allowed_ext_str = ', '.join(current_app.config.get('ALLOWED_EXTENSIONS', []))
                errors.append(f"File type not allowed for '{file.filename}'. Allowed: {allowed_ext_str}")

        # --- Commit the transaction after processing all files ---
        db.session.commit()
        logger.info("Database session committed after file uploads.")

        # --- Collect data for successfully uploaded files AFTER commit ---
        # We need to query the database to get the IDs and other details
        # of the files that were just committed.
        # A simple way is to re-fetch the list, but that might be inefficient
        # if there are many files. A better way is to query for files added
        # within a recent time window or based on filenames processed in this request.
        # For simplicity and to match the previous structure, let's just indicate success
        # and rely on the frontend to reload the list.
        # However, the frontend expects a list of uploaded_files_data.
        # Let's refactor to collect the file objects added to the session
        # and then get their IDs after commit.

        # Re-structure the loop to collect file objects added to session
        files_added_to_session = []
        request_errors = [] # Separate errors during request processing vs file processing

        for file in request.files.getlist('file'):
             if file.filename == '':
                 continue

             if file and file_utils.allowed_file(file.filename):
                 filename = secure_filename(file.filename)
                 mimetype = file.mimetype

                 try:
                     content_blob = file.read()
                     filesize = len(content_blob)

                     if filesize > max_size:
                          request_errors.append(f"File '{filename}' ({filesize} bytes) exceeds size limit ({max_size // 1024 // 1024} MB).")
                          continue

                     # save_file_record_to_db adds to session, returns File object or None
                     file_obj = db.save_file_record_to_db(filename, content_blob, mimetype, filesize, commit=False)

                     if file_obj:
                         files_added_to_session.append(file_obj) # Collect the object
                     else:
                         # Error logged in db function
                         request_errors.append(f"Failed to add file '{filename}' to database session.")

                 except Exception as e:
                     request_errors.append(f"Error processing file '{filename}': {e}")
                     current_app.logger.error(f"Error processing upload for '{filename}': {e}", exc_info=True)

             elif file:
                 allowed_ext_str = ', '.join(current_app.config.get('ALLOWED_EXTENSIONS', []))
                 request_errors.append(f"File type not allowed for '{file.filename}'. Allowed: {allowed_ext_str}")

        # --- Commit the transaction after processing all files ---
        db.session.commit()
        logger.info(f"Database session committed after processing {len(files_added_to_session)} files.")

        # --- Collect data for successfully uploaded files AFTER commit ---
        # The file_obj now has its ID assigned after the commit
        uploaded_files_data = [
            {
                "id": file_obj.id,
                "filename": file_obj.filename,
                "mimetype": file_obj.mimetype,
                "filesize": file_obj.filesize,
                "uploaded_at": file_obj.uploaded_at.isoformat(), # Use the timestamp from the object
                "has_summary": file_obj.summary is not None
            } for file_obj in files_added_to_session if file_obj.id is not None # Ensure ID was assigned
        ]

        errors.extend(request_errors) # Combine errors

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

    except SQLAlchemyError as e:
        db.session.rollback() # Rollback the entire transaction on DB error
        logger.error(f"Database error during file upload transaction: {e}", exc_info=True)
        errors.append(f"Database error during upload: {e}")
        return jsonify({"error": "; ".join(errors)}), 500
    except Exception as e:
        # Catch any other unexpected errors during the request processing
        db.session.rollback() # Ensure rollback even on non-DB errors if session was modified
        logger.error(f"Unexpected error during file upload route processing: {e}", exc_info=True)
        errors.append(f"An unexpected error occurred: {e}")
        return jsonify({"error": "; ".join(errors)}), 500


@bp.route('/files/from_url', methods=['POST'])
def add_file_from_url_route():
    """API endpoint to fetch content from a URL and save it as a file."""
    data = request.json
    url = data.get('url')

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    # Basic URL validation
    if not validators.url(url):
         return jsonify({"error": "Invalid URL format"}), 400

    max_size = current_app.config['MAX_FILE_SIZE_BYTES']

    try:
        # Fetch content from the URL
        # fetch_web_content returns (content, title) or (None, None) on failure
        content = web_search.fetch_web_content(url)
        title = url # Use URL as a fallback title

        if content is None:
             # fetch_web_content logs its own errors, just return a generic failure
             return jsonify({"error": f"Failed to fetch content from URL: {url}"}), 500

        # Convert content to bytes (assuming fetch_web_content returns string)
        content_blob = content.encode('utf-8') # Or detect encoding if possible
        filesize = len(content_blob)

        # Check size after fetching
        if filesize > max_size:
             return jsonify({"error": f"Content from URL ({filesize} bytes) exceeds size limit ({max_size // 1024 // 2024} MB)."}), 400 # Corrected MB calculation

        # Determine filename (use URL as requested, maybe truncate if too long)
        # Using the full URL as filename might be problematic for some DBs/filesystems,
        # but sticking to the request for now. A safer approach might be a hash or truncated URL.
        # Let's use the full URL for now.
        filename = url # As requested

        # Determine mimetype (default to text/plain for fetched web content)
        mimetype = 'text/plain' # Or 'text/html' if you want to preserve HTML structure

        # Save record and blob to DB - Commit immediately for single file from URL
        file_id = db.save_file_record_to_db(filename, content_blob, mimetype, filesize, commit=True) # Ensure commit=True here

        if file_id:
            # Retrieve the saved file details to return in the response
            # This ensures we get the correct uploaded_at timestamp from the DB
            saved_file_details = db.get_file_details_from_db(file_id)
            if saved_file_details:
                 return jsonify({
                     "id": saved_file_details['id'],
                     "filename": saved_file_details['filename'],
                     "mimetype": saved_file_details['mimetype'],
                     "filesize": saved_file_details['filesize'],
                     "uploaded_at": saved_file_details['uploaded_at'].isoformat(), # Use the timestamp from the DB object
                     "has_summary": saved_file_details['has_summary']
                 }), 201 # Return 201 Created
            else:
                 # Should not happen if save_file_record_to_db returned an ID
                 return jsonify({"error": f"Failed to retrieve details for saved file from URL '{url}'."}), 500
        else:
            # DB function already logs error
            return jsonify({"error": f"Failed to save content from URL '{url}' to database."}), 500

    except Exception as e:
        # Ensure rollback in case of error before commit
        db.session.rollback()
        current_app.logger.error(f"Error adding file from URL '{url}': {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred while processing the URL: {e}"}), 500


@bp.route('/files/<int:file_id>/summary', methods=['GET'])
def get_summary_route(file_id):
    """Gets or generates a summary for a specific file."""
    try:
        summary = ai_services.get_or_generate_summary(file_id)
        if isinstance(summary, str) and summary.startswith("[Error"): # Check if the result is an error message
            # Determine appropriate status code based on error type if possible
            status_code = 500 if "API" in summary or "generating" in summary else 404 if "not found" in summary else 400
            return jsonify({"error": summary}), status_code
        else:
            return jsonify({"summary": summary})
    except Exception as e:
        current_app.logger.error(f"Error getting/generating summary for file {file_id}: {e}", exc_info=True)
        return jsonify({"error": "Could not retrieve or generate summary due to server error"}), 500

@bp.route('/files/<int:file_id>/summary', methods=['PUT'])
def update_summary_route(file_id):
    """Manually updates the summary for a specific file."""
    # Allow saving summary for ANY file type now (user might manually summarize non-text)
    data = request.json
    new_summary = data.get('summary')
    if new_summary is None: # Check for None explicitly, allow empty string
        return jsonify({"error": "Summary content not provided"}), 400

    if db.save_summary_in_db(file_id, new_summary):
        return jsonify({"message": "Summary updated successfully."})
    else:
        # DB function already logs error
        return jsonify({"error": "Failed to update summary"}), 500

@bp.route('/files/<int:file_id>', methods=['DELETE'])
def delete_file_route(file_id):
    """API endpoint to delete a file record and its content."""
    # Optional: Add authentication/authorization checks here

    # Attempt to delete the file record from the database
    deleted = db.delete_file_record_from_db(file_id)

    if deleted:
        return jsonify({"message": f"File ID {file_id} deleted successfully."})
    else:
        # Check if the file simply wasn't found or if another DB error occurred
        # For simplicity, returning 404 if delete function indicated not found (returned False)
        # A more robust check might involve querying first before deleting
        details = db.get_file_details_from_db(file_id) # Check if it existed
        if not details:
             return jsonify({"error": f"File ID {file_id} not found."}), 404
        else:
             # If it exists but delete failed, it's likely a server error
             return jsonify({"error": f"Failed to delete file ID {file_id}."}), 500

