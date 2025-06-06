# app/routes/file_routes.py
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from .. import (
    database as database_module,
)  # Use alias to avoid conflict with SQLAlchemy db instance
from .. import ai_services  # Use relative import for ai services
from .. import file_utils  # Use relative import for file utils
from ..plugins import web_search
import validators  # Import validators library for URL validation
from sqlalchemy.exc import SQLAlchemyError  # Import SQLAlchemyError
from .. import db  # Import the db instance
from ..models import File  # Import the File model
import base64 # Import for base64 encoding

# Configure logging
import logging

# logging.basicConfig(level=logging.INFO) # Basic config is likely done elsewhere
logger = logging.getLogger(__name__)  # Get the logger configured by Flask app

# Create Blueprint for file API, using '/api' prefix
bp = Blueprint("file_api", __name__, url_prefix="/api")


@bp.route("/files", methods=["GET"])
def get_files():
    """API endpoint to get the list of uploaded files (metadata only)."""
    logger.info("Received GET request for /api/files")
    try:
        files = database_module.get_uploaded_files_from_db()
        logger.info(f"Successfully retrieved {len(files)} files.")
        return jsonify(files)
    except Exception as e:
        logger.error(f"Error retrieving files: {e}", exc_info=True)
        return jsonify({"error": "Failed to retrieve files"}), 500


@bp.route("/files", methods=["POST"])
def upload_file_route():
    """API endpoint to upload new files (handles multiple). Saves as BLOB."""
    logger.info("Received POST request for /api/files (file upload)")
    if "file" not in request.files:
        logger.warning("No 'file' part in the request.")
        return jsonify({"error": "No file part in the request"}), 400

    uploaded_files_data = []
    errors = []
    max_size = current_app.config["MAX_FILE_SIZE_BYTES"]

    files_added_to_session = []
    request_errors = []

    try:
        files_list = request.files.getlist("file")
        logger.info(
            f"Processing {len(files_list)} files from request.files.getlist('file')."
        )

        for i, file in enumerate(files_list):
            logger.info(f"Processing file {i+1}/{len(files_list)}: {file.filename}")

            if file.filename == "":
                logger.warning(f"Skipping file {i+1}: Empty filename.")
                continue

            if file and file_utils.allowed_file(file.filename):
                filename = secure_filename(file.filename)
                mimetype = file.mimetype
                # Attempt to get size before reading, though this might not be reliable for all file types/werkzeug versions
                # size_before_read = file.content_length if hasattr(file, 'content_length') else 'N/A'
                # logger.debug(f"File {i+1} ('{filename}'): Mimetype='{mimetype}', Size before read='{size_before_read}'.")

                try:
                    # Read the content - this consumes the stream
                    content_blob = file.read()
                    filesize = len(content_blob)
                    logger.info(f"File {i+1} ('{filename}'): Read {filesize} bytes.")

                    if filesize == 0:
                        # This might indicate the file stream was already consumed or the file was empty
                        logger.warning(
                            f"Skipping file {i+1} ('{filename}'): Read 0 bytes. File might be empty or stream already read."
                        )
                        request_errors.append(
                            f"File '{filename}' is empty or could not be read."
                        )
                        continue

                    if filesize > max_size:
                        logger.warning(
                            f"Skipping file {i+1} ('{filename}'): Size {filesize} exceeds limit {max_size}."
                        )
                        request_errors.append(
                            f"File '{filename}' ({filesize} bytes) exceeds size limit ({max_size // 1024 // 1024} MB)."
                        )
                        continue

                    # save_file_record_to_db adds to session, returns File object or None
                    # Pass commit=False to defer commit until after the loop
                    logger.debug(
                        f"Calling database_module.save_file_record_to_db for '{filename}' with commit=False."
                    )
                    file_obj = database_module.save_file_record_to_db(
                        filename, content_blob, mimetype, filesize, commit=False
                    )

                    if file_obj:
                        logger.debug(
                            f"database_module.save_file_record_to_db returned file object (ID before commit: {file_obj.id}). Appending to files_added_to_session."
                        )
                        files_added_to_session.append(file_obj)  # Collect the object
                        logger.debug(
                            f"files_added_to_session now has {len(files_added_to_session)} items."
                        )
                    else:
                        # Error logged in database_module function
                        logger.error(
                            f"database_module.save_file_record_to_db returned None for '{filename}'."
                        )
                        request_errors.append(
                            f"Failed to add file '{filename}' to database session."
                        )

                except Exception as e:
                    logger.error(
                        f"Error processing file '{filename}': {e}", exc_info=True
                    )
                    request_errors.append(f"Error processing file '{filename}': {e}")

            elif file:
                allowed_ext_str = ", ".join(
                    current_app.config.get("ALLOWED_EXTENSIONS", [])
                )
                logger.warning(
                    f"Skipping file {i+1} ('{file.filename}'): File type not allowed."
                )
                request_errors.append(
                    f"File type not allowed for '{file.filename}'. Allowed: {allowed_ext_str}"
                )

        logger.info(
            f"Finished processing files loop. {len(files_added_to_session)} files added to session."
        )
        logger.info(f"Attempting to commit database session.")
        # --- Commit the transaction after processing all files ---
        # Use the imported SQLAlchemy db instance directly
        db.session.commit()
        logger.info(
            f"Database session committed. {len(files_added_to_session)} file objects were in the list before commit."
        )

        # --- Collect data for successfully uploaded files AFTER commit ---
        # The file_obj now has its ID assigned after the commit
        uploaded_files_data = []
        for file_obj in files_added_to_session:
            if file_obj.id is not None:  # Ensure ID was assigned after commit
                uploaded_files_data.append(
                    {
                        "id": file_obj.id,
                        "filename": file_obj.filename,
                        "mimetype": file_obj.mimetype,
                        "filesize": file_obj.filesize,
                        "uploaded_at": file_obj.uploaded_at.isoformat(),  # Use the timestamp from the object
                        "has_summary": file_obj.summary is not None,
                    }
                )
                logger.debug(
                    f"Collected data for uploaded file ID: {file_obj.id}, Filename: '{file_obj.filename}'."
                )
            else:
                logger.error(
                    f"File object in files_added_to_session did not get an ID after commit: '{file_obj.filename}'."
                )
                # This shouldn't happen if commit was successful for this object
                request_errors.append(
                    f"Failed to retrieve details for uploaded file '{file_obj.filename}'."
                )

        errors.extend(request_errors)  # Combine errors

        logger.info(
            f"Prepared response data: {len(uploaded_files_data)} successful uploads, {len(errors)} errors."
        )

        # --- Response Handling ---
        if not uploaded_files_data and errors:
            # Only errors occurred
            logger.warning(f"Upload failed: {'; '.join(errors)}")
            return jsonify({"error": "; ".join(errors)}), 400
        elif uploaded_files_data:
            # Return data for successfully uploaded files, potentially with errors for others
            response_data = {"uploaded_files": uploaded_files_data}
            if errors:
                response_data["errors"] = errors
                logger.warning(
                    f"Upload partially successful. Errors: {'; '.join(errors)}"
                )
            else:
                logger.info("Upload successful.")
            return (
                jsonify(response_data),
                201,
            )  # Return 201 Created (even if some failed)
        else:
            # Should not happen if loop runs unless no files were sent or all failed validation before try block
            # This case means files_added_to_session was empty AND request_errors was empty.
            # This implies no files were processed successfully or unsuccessfully, which contradicts the DB logs.
            # Let's add a specific error message here.
            logger.error(
                "Upload route finished without processing any valid files or recording errors."
            )
            return (
                jsonify(
                    {"error": "No valid files processed or an internal issue occurred."}
                ),
                400,
            )

    except SQLAlchemyError as e:
        # Use the imported SQLAlchemy db instance directly
        db.session.rollback()  # Rollback the entire transaction on DB error
        logger.error(
            f"Database error during file upload transaction: {e}", exc_info=True
        )
        errors.append(f"Database error during upload: {e}")
        return jsonify({"error": "; ".join(errors)}), 500
    except Exception as e:
        # Catch any other unexpected errors during the request processing
        # Use the imported SQLAlchemy db instance directly
        db.session.rollback()  # Ensure rollback even on non-DB errors if session was modified
        logger.error(
            f"Unexpected error during file upload route processing: {e}", exc_info=True
        )
        errors.append(f"An unexpected error occurred: {e}")
        return jsonify({"error": "; ".join(errors)}), 500


@bp.route("/files/from_url", methods=["POST"])
def add_file_from_url_route():
    """API endpoint to fetch content from a URL and save it as a file."""
    logger.info("Received POST request for /api/files/from_url")
    data = request.json
    url = data.get("url")

    if not url:
        logger.warning("No URL provided in /api/files/from_url request.")
        return jsonify({"error": "No URL provided"}), 400

    # Basic URL validation
    if not validators.url(url):
        logger.warning(f"Invalid URL format provided: {url}")
        return jsonify({"error": "Invalid URL format"}), 400

    max_size = current_app.config["MAX_FILE_SIZE_BYTES"]

    try:
        logger.info(f"Attempting to fetch content from URL: {url}")
        # Fetch content from the URL
        # fetch_web_content returns a dict: {'type': ..., 'content': ..., 'url': ..., 'filename': ...}
        content_dict = web_search.fetch_web_content(url)  # Renamed variable

        # Check for errors from fetch_web_content first
        if content_dict.get("type") == "error":
            error_msg = content_dict.get("content", "Unknown error fetching content")
            logger.error(
                f"Failed to fetch content from URL: {url}. Reason: {error_msg}"
            )
            # Return the specific error from fetch_web_content if available
            return (
                jsonify({"error": f"Failed to fetch content from URL: {error_msg}"}),
                500,
            )

        # Now process the content
        fetched_content = content_dict.get("content")  # Use .get() for safety
        if fetched_content is None:
            # Should not happen if type wasn't 'error', but defensive check
            logger.error(
                f"Content was None in response from fetch_web_content for URL {url}, despite type being '{content_dict.get('type')}'"
            )
            return jsonify({"error": "Internal error processing fetched content."}), 500

        # --- Log type before checking ---
        logger.debug(
            f"Type of fetched_content from URL {url} before encoding check: {type(fetched_content)}"
        )

        # Handle str vs bytes
        if isinstance(fetched_content, str):
            logger.debug(f"Fetched content is string, encoding to UTF-8.")
            content_blob = fetched_content.encode("utf-8")
        elif isinstance(fetched_content, bytes):
            logger.debug(f"Fetched content is bytes, using directly.")
            content_blob = fetched_content
        else:
            # Handle unexpected type
            logger.error(
                f"Unexpected content type fetched from URL {url}: {type(fetched_content)}"
            )
            return jsonify({"error": "Unexpected content type received from URL."}), 500

        filesize = len(content_blob)
        logger.info(f"Processed {filesize} bytes from URL: {url}")

        # Check size after fetching
        if filesize > max_size:
            logger.warning(
                f"Content from URL {url} ({filesize} bytes) exceeds size limit {max_size}."
            )
            # Corrected MB calculation again
            return (
                jsonify(
                    {
                        "error": f"Content from URL ({filesize} bytes) exceeds size limit ({max_size // 1024 // 1024} MB)."
                    }
                ),
                400,
            )

        # Determine filename and mimetype based on content_dict
        filename = content_dict.get("filename")  # Get filename if present (PDFs)
        mimetype = "application/octet-stream"  # Default

        content_type = content_dict.get("type")
        if content_type == "pdf":
            mimetype = "application/pdf"
            # Ensure filename exists for PDF (should be set by fetch_web_content)
            if not filename:
                # Use werkzeug's secure_filename and urlparse for better fallback
                from urllib.parse import urlparse # Import locally if not already global
                parsed_url = urlparse(url)
                base_name = os.path.basename(parsed_url.path)
                fallback_name = (
                    base_name if base_name else parsed_url.netloc
                )  # Use domain if no path
                filename = secure_filename(fallback_name) + ".pdf"
                logger.warning(
                    f"Filename missing/invalid from PDF fetch result for {url}, using fallback: {filename}"
                )
        elif content_type == "html":
            mimetype = "text/html"  # Or text/plain if preferred
            # Use URL as filename for HTML if specific filename wasn't provided
            if not filename:
                filename = url  # Use full URL as filename for HTML
        # Add other type handling here if needed
        else:
            # For other types or if type is missing, use URL as filename if not already set
            if not filename:
                filename = url  # Use full URL as filename

        # Ensure filename is not excessively long (e.g., limit to 255 chars for compatibility)
        max_filename_len = 255
        if len(filename) > max_filename_len:
            # Simple truncation, could be smarter (e.g., keep extension)
            original_filename = filename
            filename = filename[:max_filename_len]
            logger.warning(
                f"Original filename '{original_filename}' exceeded max length {max_filename_len}, truncated to '{filename}'."
            )

        logger.info(f"Using filename: {filename}, mimetype: {mimetype}")

        # Save record and blob to DB - Commit immediately for single file from URL
        logger.debug(
            f"Calling database_module.save_file_record_to_db for filename '{filename}' with commit=True."
        )
        file_id = database_module.save_file_record_to_db(
            filename, content_blob, mimetype, filesize, commit=True
        )  # Ensure commit=True here

        if file_id:
            logger.info(f"Successfully saved file from URL {url} with ID: {file_id}.")
            # Retrieve the newly created File object directly to get all attributes
            saved_file = File.query.get(file_id)
            if saved_file:
                return (
                    jsonify(
                        {
                            "id": saved_file.id,
                            "filename": saved_file.filename,
                            "mimetype": saved_file.mimetype,
                            "filesize": saved_file.filesize,
                            "uploaded_at": saved_file.uploaded_at.isoformat(),  # Access attribute directly
                            "has_summary": saved_file.summary is not None,
                        }
                    ),
                    201,
                )  # Return 201 Created
            else:
                # This case is less likely now, but handle it just in case
                logger.error(
                    f"Failed to retrieve newly saved file object with ID {file_id} from URL '{url}'."
                )
                return (
                    jsonify(
                        {
                            "error": f"Failed to retrieve details for saved file from URL '{url}'."
                        }
                    ),
                    500,
                )
        else:
            # database_module function already logs error
            logger.error(
                f"database_module.save_file_record_to_db returned None for URL '{url}'."
            )
            return (
                jsonify(
                    {"error": f"Failed to save content from URL '{url}' to database."}
                ),
                500,
            )

    except Exception as e:
        # Ensure rollback in case of error before commit
        # Use the imported SQLAlchemy db instance directly
        db.session.rollback()
        logger.error(
            f"Unexpected error adding file from URL '{url}': {e}", exc_info=True
        )
        # Check if the error is the specific encoding error to provide a clearer message
        if isinstance(
            e, AttributeError
        ) and "'bytes' object has no attribute 'encode'" in str(e):
            error_message = "Internal error: Attempted to double-encode content."  # More specific error
        else:
            error_message = (
                f"An unexpected error occurred while processing the URL: {e}"
            )
        return jsonify({"error": error_message}), 500


@bp.route("/file_content/<int:file_id>", methods=["GET"])
def get_file_content_route(file_id):
    """API endpoint to get the content of a specific file."""
    logger.info(f"Received GET request for /api/file_content/{file_id}")
    try:
        # Fetch file details including content
        # The database_module.get_file_details_from_db should return a dict
        # or None if not found.
        file_details = database_module.get_file_details_from_db(
            file_id, include_content=True
        )

        if file_details is None:
            logger.warning(f"File with ID {file_id} not found.")
            return jsonify({"error": "File not found"}), 404

        content_blob = file_details.get("content")
        mimetype = file_details.get("mimetype", "application/octet-stream")
        filename = file_details.get("filename", "unknown_file")
        db_id = file_details.get("id")

        if content_blob is None:
            logger.error(
                f"Content blob is None for file ID {file_id} even though record was found."
            )
            return jsonify({"error": "File content not available"}), 500

        # Determine if content is text or binary to decide on base64 encoding
        # Common text mimetypes that can be sent as plain strings
        text_mimetypes = [
            "text/plain",
            "text/html",
            "text/css",
            "text/javascript",
            "application/json",
            "application/xml",
            "text/markdown",
            "text/csv",
            # Add more as needed
        ]
        # Check common text file extensions as a fallback
        text_extensions = (
            ".txt",
            ".py",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".html",
            ".htm",
            ".css",
            ".scss",
            ".less",
            ".md",
            ".json",
            ".csv",
            ".xml",
            ".log",
            ".yaml",
            ".yml",
            ".ini",
            ".cfg",
            ".sh",
            ".bash",
            ".zsh",
            ".ps1",
            ".bat",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".cs",
            ".go",
            ".rb",
            ".php",
            ".swift",
            ".kt",
            ".kts",
            ".dart",
            ".rs",
            ".lua",
            ".pl",
            ".sql",
            ".r",
            ".vbs",
            ".conf",
        )

        is_text_displayable = mimetype.lower() in text_mimetypes or filename.lower().endswith(text_extensions)

        content_to_send = ""
        is_base64_encoded = False

        if is_text_displayable:
            try:
                content_to_send = content_blob.decode("utf-8")
                is_base64_encoded = False
                logger.debug(f"Decoded content for text file ID {file_id} as UTF-8.")
            except UnicodeDecodeError:
                logger.warning(
                    f"UnicodeDecodeError for file ID {file_id} (mimetype: {mimetype}, filename: {filename}). Sending as base64."
                )
                content_to_send = base64.b64encode(content_blob).decode("utf-8")
                is_base64_encoded = True
        else:
            # For binary files (images, pdfs, etc.), encode to base64
            content_to_send = base64.b64encode(content_blob).decode("utf-8")
            is_base64_encoded = True
            logger.debug(f"Base64 encoded content for binary file ID {file_id}.")

        logger.info(f"Successfully retrieved content for file ID {file_id}.")
        return jsonify(
            {
                "id": db_id,
                "filename": filename,
                "content": content_to_send,
                "mimetype": mimetype,
                "is_base64": is_base64_encoded,
            }
        )

    except Exception as e:
        logger.error(
            f"Error retrieving content for file {file_id}: {e}", exc_info=True
        )
        return (
            jsonify(
                {"error": "Failed to retrieve file content due to server error"}
            ),
            500,
        )


@bp.route("/files/<int:file_id>/summary", methods=["GET"])
def get_summary_route(file_id):
    """Gets or generates a summary for a specific file."""
    logger.info(f"Received GET request for /api/files/{file_id}/summary")
    try:
        summary = ai_services.get_or_generate_summary(file_id)
        if isinstance(summary, str) and summary.startswith(
            "[Error"
        ):  # Check if the result is an error message
            logger.warning(
                f"Summary generation/retrieval failed for file {file_id}: {summary}"
            )
            # Determine appropriate status code based on error type if possible
            status_code = (
                500
                if "API" in summary or "generating" in summary
                else 404 if "not found" in summary else 400
            )
            return jsonify({"error": summary}), status_code
        else:
            logger.info(f"Successfully retrieved/generated summary for file {file_id}.")
            return jsonify({"summary": summary})
    except Exception as e:
        logger.error(
            f"Error getting/generating summary for file {file_id}: {e}", exc_info=True
        )
        return (
            jsonify(
                {"error": "Could not retrieve or generate summary due to server error"}
            ),
            500,
        )


@bp.route("/files/<int:file_id>/summary", methods=["PUT"])
def update_summary_route(file_id):
    """Manually updates the summary for a specific file."""
    logger.info(f"Received PUT request for /api/files/{file_id}/summary")
    # Allow saving summary for ANY file type now (user might manually summarize non-text)
    data = request.json
    new_summary = data.get("summary")
    if new_summary is None:  # Check for None explicitly, allow empty string
        logger.warning(f"No summary content provided for file {file_id} update.")
        return jsonify({"error": "Summary content not provided"}), 400

    if database_module.save_summary_in_db(file_id, new_summary):
        logger.info(f"Successfully updated summary for file {file_id}.")
        return jsonify({"message": "Summary updated successfully."})
    else:
        # database_module function already logs error
        logger.error(f"Failed to update summary for file {file_id}.")
        return jsonify({"error": "Failed to update summary"}), 500


@bp.route("/files/<int:file_id>", methods=["DELETE"])
def delete_file_route(file_id):
    """API endpoint to delete a file record and its content."""
    logger.info(f"Received DELETE request for /api/files/{file_id}")
    # Optional: Add authentication/authorization checks here

    # Attempt to delete the file record from the database
    deleted = database_module.delete_file_record_from_db(file_id)

    if deleted:
        logger.info(f"Successfully deleted file ID {file_id}.")
        return jsonify({"message": f"File ID {file_id} deleted successfully."})
    else:
        # Check if the file simply wasn't found or if another DB error occurred
        # For simplicity, returning 404 if delete function indicated not found (returned False)
        # A more robust check might involve querying first before deleting
        details = database_module.get_file_details_from_db(
            file_id
        )  # Check if it existed
        if not details:
            logger.warning(
                f"Attempted to delete file ID {file_id}, but it was not found."
            )
            return jsonify({"error": f"File ID {file_id} not found."}), 404
        else:
            # If it exists but delete failed, it's likely a server error
            logger.error(f"Failed to delete file ID {file_id} despite it existing.")
            return jsonify({"error": f"Failed to delete file ID {file_id}."}), 500
