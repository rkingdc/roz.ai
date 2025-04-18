import os
import sqlite3
import json
from flask import Flask, request, jsonify, render_template, g
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv
import time
from werkzeug.utils import secure_filename
import tempfile  # Needed for temporary files for API upload
import io  # Needed potentially for BytesIO if API changes

# --- Configuration ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
DB_NAME = "assistant_chat_v7.db"  # New DB version for schema change
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
DEFAULT_MODEL = "gemini-1.5-flash"
# UPLOAD_FOLDER is no longer needed as we store in DB
ALLOWED_EXTENSIONS = {
    "txt",
    "py",
    "js",
    "html",
    "css",
    "md",
    "json",
    "csv",
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "mp3",
}

AVAILABLE_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro-latest",
    "gemini-pro",
]

if not API_KEY:
    print(
        "Warning: GEMINI_API_KEY environment variable not set. AI features will be disabled."
    )
    gemini_configured = False
else:
    genai.configure(api_key=API_KEY)
    gemini_configured = True
    print("Gemini API configured.")

# --- Flask App Setup ---
app = Flask(__name__)
# Remove UPLOAD_FOLDER config, set max content length for request body
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_BYTES + (
    1 * 1024 * 1024
)  # Add buffer for JSON etc.


# --- Helper Function ---
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# --- Database Setup ---
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_NAME)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    cursor = db.cursor()
    # Chats table (Unchanged from v3)
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT DEFAULT 'New Chat',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            model_name TEXT DEFAULT '{DEFAULT_MODEL}'
        )
    """
    )
    # Messages table (Unchanged)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
        )
    """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id)"
    )

    # Uploaded Files table (Schema Change: filepath -> content BLOB)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content BLOB NOT NULL,        -- Store file content as BLOB
            mimetype TEXT NOT NULL,
            filesize INTEGER NOT NULL,
            summary TEXT,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_files_filename ON uploaded_files (filename)"
    )

    # --- Schema Migrations ---
    # Check and add model_name column to chats if needed
    try:
        cursor.execute("SELECT model_name FROM chats LIMIT 1")
    except sqlite3.OperationalError:
        print("Adding 'model_name' column to 'chats' table.")
        cursor.execute(
            f"ALTER TABLE chats ADD COLUMN model_name TEXT DEFAULT '{DEFAULT_MODEL}'"
        )

    # Check for old 'filepath' column and migrate to 'content BLOB'
    # This is a simplified migration - assumes we start fresh or lose old file data
    try:
        cursor.execute("SELECT content FROM uploaded_files LIMIT 1")
        # Check if it's actually a BLOB (this check isn't perfect)
        # A better check might involve PRAGMA table_info(uploaded_files)
        test_fetch = cursor.fetchone()
        if test_fetch and not isinstance(test_fetch["content"], bytes):
            raise sqlite3.OperationalError  # Treat non-blob 'content' as needing migration
    except sqlite3.OperationalError:
        print(
            "Applying schema changes to 'uploaded_files' (content BLOB). This WILL remove old file data."
        )
        cursor.execute("DROP TABLE IF EXISTS uploaded_files")
        cursor.execute(
            """
            CREATE TABLE uploaded_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                content BLOB NOT NULL,
                mimetype TEXT NOT NULL,
                filesize INTEGER NOT NULL,
                summary TEXT,
                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        cursor.execute("CREATE INDEX idx_files_filename ON uploaded_files (filename)")
        print("Recreated 'uploaded_files' table with BLOB schema.")

    db.commit()
    print(
        f"Database initialized. Storing uploads in DB. Default model: {DEFAULT_MODEL}"
    )


# --- Database Interaction Functions (Chats & Messages - Unchanged from v3) ---
def create_new_chat_entry():
    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    cursor.execute(
        "INSERT INTO chats (created_at, last_updated_at, model_name) VALUES (?, ?, ?)",
        (now, now, DEFAULT_MODEL),
    )
    db.commit()
    new_chat_id = cursor.lastrowid
    print(f"Created new chat with ID: {new_chat_id}, Model: {DEFAULT_MODEL}")
    return new_chat_id


def update_chat_timestamp(chat_id):
    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    cursor.execute("UPDATE chats SET last_updated_at = ? WHERE id = ?", (now, chat_id))
    db.commit()


def add_message_to_db(chat_id, role, content):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        db.commit()
        update_chat_timestamp(chat_id)
        return True
    except sqlite3.Error as e:
        print(f"Database error adding message: {e}")
        return False


def get_chat_history_from_db(chat_id, limit=100):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT role, content, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp ASC LIMIT ?",
            (chat_id, limit),
        )
        history = cursor.fetchall()
        return [dict(row) for row in history]
    except sqlite3.Error as e:
        print(f"Database error getting history for chat {chat_id}: {e}")
        return []


def get_chat_details_from_db(chat_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, created_at, last_updated_at, model_name FROM chats WHERE id = ?",
            (chat_id,),
        )
        chat_details = cursor.fetchone()
        return dict(chat_details) if chat_details else None
    except sqlite3.Error as e:
        print(f"Database error getting details for chat {chat_id}: {e}")
        return None


def get_saved_chats_from_db():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, last_updated_at FROM chats ORDER BY last_updated_at DESC"
        )
        chats = cursor.fetchall()
        return [dict(row) for row in chats]
    except sqlite3.Error as e:
        print(f"Database error getting saved chats: {e}")
        return []


def save_chat_name_in_db(chat_id, name):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE chats SET name = ?, last_updated_at = ? WHERE id = ?",
            (name, datetime.now(), chat_id),
        )
        db.commit()
        print(f"Updated name for chat {chat_id} to '{name}'")
        return True
    except sqlite3.Error as e:
        print(f"Database error saving chat name for {chat_id}: {e}")
        return False


def update_chat_model(chat_id, model_name):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE chats SET model_name = ?, last_updated_at = ? WHERE id = ?",
            (model_name, datetime.now(), chat_id),
        )
        db.commit()
        print(f"Updated model for chat {chat_id} to '{model_name}'")
        return True
    except sqlite3.Error as e:
        print(f"Database error updating model for chat {chat_id}: {e}")
        return False


def delete_chat_from_db(chat_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        db.commit()
        print(f"Deleted chat with ID: {chat_id}")
        return True
    except sqlite3.Error as e:
        print(f"Database error deleting chat {chat_id}: {e}")
        return False


# --- Database Interaction Functions (Files - Modified for BLOB) ---


def save_file_record_to_db(filename, content_blob, mimetype, filesize):
    """Saves file metadata and content blob to the database."""
    try:
        db = get_db()
        cursor = db.cursor()
        # Insert BLOB content directly
        cursor.execute(
            "INSERT INTO uploaded_files (filename, content, mimetype, filesize, summary) VALUES (?, ?, ?, ?, NULL)",
            (filename, content_blob, mimetype, filesize),
        )
        db.commit()
        file_id = cursor.lastrowid
        print(
            f"Saved file record & BLOB: ID {file_id}, Name '{filename}', Type '{mimetype}', Size {filesize}"
        )
        return file_id
    # Cannot check for unique content BLOB easily, rely on other constraints or logic if needed
    except sqlite3.Error as e:
        print(f"Database error saving file record/BLOB for '{filename}': {e}")
        return None


def get_uploaded_files_from_db():
    """Retrieves metadata for all uploaded files (excluding BLOB)."""
    try:
        db = get_db()
        cursor = db.cursor()
        # Exclude the large 'content' BLOB from this list query
        cursor.execute(
            """
            SELECT id, filename, mimetype, filesize, uploaded_at, (summary IS NOT NULL) as has_summary
            FROM uploaded_files ORDER BY uploaded_at DESC
        """
        )
        files = cursor.fetchall()
        return [dict(row) for row in files]
    except sqlite3.Error as e:
        print(f"Database error getting file list: {e}")
        return []


def get_file_details_from_db(file_id, include_content=False):
    """Retrieves details for a specific file ID, optionally including the content BLOB."""
    try:
        db = get_db()
        cursor = db.cursor()
        columns = "id, filename, mimetype, filesize, summary, (summary IS NOT NULL) as has_summary"
        if include_content:
            columns += ", content"  # Add content column if requested

        cursor.execute(f"SELECT {columns} FROM uploaded_files WHERE id = ?", (file_id,))
        file_data = cursor.fetchone()
        if file_data:
            return dict(file_data)
        else:
            print(f"File details not found for ID: {file_id}")
            return None
    except sqlite3.Error as e:
        print(f"Database error getting details for file {file_id}: {e}")
        return None


# read_file_content is no longer needed as we fetch BLOB directly


def get_summary_from_db(file_id):
    # (Unchanged logic)
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT summary FROM uploaded_files WHERE id = ?", (file_id,))
        result = cursor.fetchone()
        return result["summary"] if result and result["summary"] else None
    except sqlite3.Error as e:
        print(f"Database error getting summary for file {file_id}: {e}")
        return None


def save_summary_in_db(file_id, summary):
    # (Unchanged logic)
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE uploaded_files SET summary = ? WHERE id = ?", (summary, file_id)
        )
        db.commit()
        print(f"Saved summary for file ID: {file_id}")
        return True
    except sqlite3.Error as e:
        print(f"Database error saving summary for file {file_id}: {e}")
        return False


# --- Summary Generation (Modified for BLOB input) ---


def generate_summary(content_blob, filename="", mimetype="text/plain"):
    """Generates summary only for text-based MIME types from BLOB."""
    if not gemini_configured:
        return "[Error: AI model not configured]"
    if not mimetype.startswith("text/"):
        print(
            f"Skipping summary generation for non-text file '{filename}' (type: {mimetype})"
        )
        return "[Summary not applicable for this file type]"
    if not content_blob:
        return "[Error: No content BLOB provided for summary]"

    try:
        # Decode text content from BLOB
        text_content = content_blob.decode("utf-8", errors="ignore")
    except Exception as decode_err:
        print(f"Error decoding text content for summary ({filename}): {decode_err}")
        return "[Error: Could not decode text content for summary]"

    prompt = f"Please provide a concise summary of the following text file content (from file '{filename}'). Focus on the main points and key information:\n\n--- File Content Start ---\n{text_content}\n--- File Content End ---"
    try:
        print(f"Requesting summary generation for text file '{filename}'...")
        summary_model = genai.GenerativeModel(DEFAULT_MODEL)
        response = summary_model.generate_content(prompt)
        summary = response.text
        print(f"Summary generated successfully for '{filename}'.")
        return summary
    except Exception as e:
        print(f"Error generating summary for file '{filename}': {e}")
        if "prompt was blocked" in str(e).lower():
            return "[Error: Summary generation blocked due to safety settings]"
        return f"[Error generating summary: {e}]"


def get_or_generate_summary(file_id):
    """Gets summary from DB or generates+saves it if not present (for text files from BLOB)."""
    # Fetch details including content BLOB needed for generation
    file_details = get_file_details_from_db(file_id, include_content=True)
    if not file_details:
        return "[Error: File details not found]"

    # Check if summary already exists
    if file_details["has_summary"] and file_details["summary"]:
        print(f"Retrieved existing summary for file ID: {file_id}")
        return file_details["summary"]

    # Only generate for text files
    mimetype = file_details["mimetype"]
    if not mimetype.startswith("text/"):
        print(
            f"Summary generation skipped for non-text file ID: {file_id} (Type: {mimetype})"
        )
        save_summary_in_db(file_id, "[Summary not applicable for this file type]")
        return "[Summary not applicable for this file type]"

    # Generate for text file using the content BLOB
    print(f"No summary found for text file ID: {file_id}. Attempting generation...")
    content_blob = file_details.get("content")
    if content_blob:
        new_summary = generate_summary(content_blob, file_details["filename"], mimetype)
        if save_summary_in_db(file_id, new_summary):
            return new_summary
        else:
            return "[Error: Failed to save generated summary]"
    else:
        # Content could not be retrieved (shouldn't happen if include_content=True worked)
        save_summary_in_db(
            file_id, "[Error: Could not retrieve file content for summary generation]"
        )
        return "[Error: Could not retrieve file content to generate summary]"


# --- Flask Routes ---
@app.route("/")
def index():
    return render_template(
        "main.html", available_models=AVAILABLE_MODELS, default_model=DEFAULT_MODEL
    )


# --- Chat API Endpoints (Unchanged GET, POST, PUT name/model, DELETE) ---
@app.route("/api/chats", methods=["GET"])
def get_saved_chats():
    chats = get_saved_chats_from_db()
    return jsonify(chats)


@app.route("/api/chat", methods=["POST"])
def create_new_chat():
    try:
        new_chat_id = create_new_chat_entry()
        chat_details = get_chat_details_from_db(new_chat_id)
        return jsonify(chat_details), 201
    except Exception as e:
        print(f"Error creating new chat: {e}")
        return jsonify({"error": "Failed to create new chat"}), 500


@app.route("/api/chat/<int:chat_id>", methods=["GET"])
def get_chat(chat_id):
    details = get_chat_details_from_db(chat_id)
    if not details:
        return jsonify({"error": "Chat not found"}), 404
    history = get_chat_history_from_db(chat_id)
    return jsonify({"details": details, "history": history})


@app.route("/api/chat/<int:chat_id>/name", methods=["PUT"])
def save_chat_name(chat_id):
    data = request.json
    new_name = data.get("name", "").strip()
    if not new_name:
        new_name = "New Chat"
        if save_chat_name_in_db(chat_id, new_name):
            return jsonify({"message": "Chat name updated successfully."})
        else:
            return jsonify({"error": "Failed to update chat name"}), 500


@app.route("/api/chat/<int:chat_id>/model", methods=["PUT"])
def save_chat_model(chat_id):
    data = request.json
    new_model_name = data.get("model_name")
    if not new_model_name:
        return jsonify({"error": "Model name not provided"}), 400
    if new_model_name not in AVAILABLE_MODELS:
        print(
            f"Warning: Saving potentially unknown model '{new_model_name}' for chat {chat_id}."
        )
        if update_chat_model(chat_id, new_model_name):
            return jsonify({"message": f"Chat model updated to {new_model_name}."})
        else:
            return jsonify({"error": "Failed to update chat model"}), 500


@app.route("/api/chat/<int:chat_id>", methods=["DELETE"])
def delete_chat(chat_id):
    if delete_chat_from_db(chat_id):
        return jsonify({"message": "Chat deleted successfully."})
    else:
        return jsonify({"error": "Failed to delete chat"}), 500


# --- File API Endpoints (Modified POST; GET/Summary unchanged logic) ---
@app.route("/api/files", methods=["GET"])
def get_files():
    # Returns metadata only (no blob)
    files = get_uploaded_files_from_db()
    return jsonify(files)


@app.route("/api/files", methods=["POST"])
def upload_file():
    """Handles file uploads via FormData, saves content as BLOB."""
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    uploaded_files_data = []
    errors = []

    for file in request.files.getlist("file"):  # Handle multiple files
        if file.filename == "":
            errors.append("No selected file name found.")
            continue

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            mimetype = file.mimetype

            try:
                content_blob = file.read()  # Read file content into bytes
                filesize = len(content_blob)

                # Check size after reading
                if filesize > app.config["MAX_CONTENT_LENGTH"]:
                    errors.append(
                        f"File '{filename}' exceeds size limit ({MAX_FILE_SIZE_MB} MB)."
                    )
                    continue

                file_id = save_file_record_to_db(
                    filename, content_blob, mimetype, filesize
                )

                if file_id:
                    # Return metadata (no blob)
                    uploaded_files_data.append(
                        {
                            "id": file_id,
                            "filename": filename,
                            "mimetype": mimetype,
                            "filesize": filesize,
                            "uploaded_at": datetime.now().isoformat(),
                            "has_summary": False,
                        }
                    )
                else:
                    errors.append(f"Failed to save file '{filename}' to database.")

            except Exception as e:
                errors.append(f"Error processing file '{filename}': {e}")
                print(f"Error processing upload for '{filename}': {e}")

        elif file:  # File submitted but extension not allowed
            errors.append(
                f"File type not allowed for '{file.filename}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )

    # --- Response Handling ---
    if not uploaded_files_data and errors:
        return jsonify({"error": "; ".join(errors)}), 400
    elif uploaded_files_data:
        response_data = {"uploaded_files": uploaded_files_data}
        if errors:
            response_data["errors"] = errors
        return jsonify(response_data), 201
    else:
        return jsonify({"error": "No valid files processed."}), 400


@app.route("/api/files/<int:file_id>/summary", methods=["GET"])
def get_summary(file_id):
    summary = get_or_generate_summary(file_id)
    if summary:
        return jsonify({"summary": summary})
    else:
        return jsonify({"error": "Could not retrieve or generate summary"}), 500


@app.route("/api/files/<int:file_id>/summary", methods=["PUT"])
def update_summary(file_id):
    details = get_file_details_from_db(file_id)  # Fetch details to check mimetype
    if not details:
        return jsonify({"error": "File not found"}), 404
    if not details["mimetype"].startswith("text/"):
        return jsonify({"error": "Summaries can only be saved for text files."}), 400
    data = request.json
    new_summary = data.get("summary")
    if new_summary is None:
        return jsonify({"error": "Summary content not provided"}), 400
    if save_summary_in_db(file_id, new_summary):
        return jsonify({"message": "Summary updated successfully."})
    else:
        return jsonify({"error": "Failed to update summary"}), 500


# --- Modified Message Sending Endpoint ---
@app.route("/api/chat/<int:chat_id>/message", methods=["POST"])
def send_message(chat_id):
    """Handles messages, uses chat-specific model, uploads files (from BLOB via temp file) to Gemini API."""
    if not gemini_configured:
        return jsonify({"reply": "[Error: Gemini API Key not configured]"}), 503

    data = request.json
    user_message = data.get("message", "")
    attached_files = data.get("attached_files", [])  # Expecting [{id, type}]

    if not user_message and not attached_files:
        return jsonify({"error": "No message or attached files provided"}), 400

    # --- Get Chat-Specific Model ---
    chat_details = get_chat_details_from_db(chat_id)
    if not chat_details:
        return jsonify({"error": "Chat not found"}), 404
    model_name = chat_details.get("model_name", DEFAULT_MODEL)
    print(f"Using model '{model_name}' for chat {chat_id}.")

    # --- Prepare content parts for Gemini API ---
    gemini_parts = []
    files_info_for_history = []  # Markers for saving in DB
    temp_files_to_clean = []  # Keep track of temp files

    try:  # Outer try for resource cleanup
        if attached_files:
            print(f"Processing {len(attached_files)} attached files for Gemini...")
            for file_info in attached_files:
                file_id = file_info.get("id")
                attach_type = file_info.get("type", "full")
                if not file_id:
                    continue

                # Fetch details including content BLOB
                file_details = get_file_details_from_db(file_id, include_content=True)
                if not file_details or "content" not in file_details:
                    print(
                        f"Warning: File details/content not found for ID {file_id}. Skipping attachment."
                    )
                    files_info_for_history.append(
                        f"[Error: File ID {file_id} not found or content missing]"
                    )
                    continue

                filename = file_details["filename"]
                mimetype = file_details["mimetype"]
                content_blob = file_details["content"]
                history_marker = f"[Attached File: '{filename}' (ID: {file_id}, Type: {attach_type})]"

                try:
                    if attach_type == "full":
                        # --- Upload ALL supported types via File API using temp file ---
                        print(
                            f"Preparing file '{filename}' (Type: {mimetype}) for API upload..."
                        )
                        # Create a temporary file
                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=f"_{filename}"
                        ) as temp_file:
                            temp_file.write(content_blob)
                            temp_filepath = temp_file.name
                            temp_files_to_clean.append(
                                temp_filepath
                            )  # Schedule for cleanup

                        print(
                            f"Uploading temp file '{temp_filepath}' for '{filename}' via API..."
                        )
                        # Use genai.upload_file with the temp file path
                        # Handle potential errors during upload
                        try:
                            uploaded_file = genai.upload_file(
                                path=temp_filepath,
                                display_name=filename,
                                mime_type=mimetype,
                            )
                            gemini_parts.append(uploaded_file)  # Add file reference
                            print(
                                f"File '{filename}' uploaded, URI: {uploaded_file.uri}"
                            )
                            files_info_for_history.append(history_marker)
                        except Exception as api_upload_err:
                            print(
                                f"Error uploading file '{filename}' to Gemini API: {api_upload_err}"
                            )
                            files_info_for_history.append(
                                f"[Error uploading file to AI: '{filename}']"
                            )
                            gemini_parts.append(
                                f"[System: Error processing file '{filename}'. Upload failed.]"
                            )

                    elif attach_type == "summary":
                        if mimetype.startswith("text/"):
                            print(f"Getting/Generating summary for '{filename}'")
                            # Use the blob fetched earlier
                            summary = get_or_generate_summary(
                                file_id
                            )  # This function now expects ID and fetches blob internally
                            gemini_parts.append(
                                f"--- Summary of file '{filename}' ---\n{summary}\n--- End of Summary ---"
                            )
                            files_info_for_history.append(history_marker)
                        else:
                            print(f"Summary skipped for non-text file '{filename}'")
                            history_marker = f"[Attached File: '{filename}' (ID: {file_id}, Type: Summary - N/A)]"
                            gemini_parts.append(
                                f"[System: Summary requested for non-text file '{filename}', not applicable.]"
                            )
                            files_info_for_history.append(history_marker)

                except Exception as processing_err:
                    print(
                        f"Error processing file ID {file_id} ('{filename}') for Gemini: {processing_err}"
                    )
                    files_info_for_history.append(
                        f"[Error processing file: '{filename}' (ID: {file_id})]"
                    )
                    gemini_parts.append(
                        f"[System: Error processing file '{filename}'.]"
                    )

        # --- Add user text message to parts ---
        if user_message:
            gemini_parts.append(user_message)

        # --- Save history message to DB ---
        history_message = (
            "\n".join(files_info_for_history)
            + ("\n" if files_info_for_history else "")
            + user_message
        )
        if not add_message_to_db(chat_id, "user", history_message):
            # If DB save fails, we might have uploaded files to Gemini already.
            # Ideally, we'd delete them, but that adds complexity. Log it for now.
            print(
                f"Warning: Failed to save user message for chat {chat_id} after potentially processing files."
            )
            # Don't return error yet, try getting AI response anyway? Or return error here?
            # Let's return error to be safe.
            return jsonify({"error": "Failed to save user message"}), 500

        assistant_reply = "[AI response error occurred]"

        # --- Gemini Interaction ---
        try:
            # Instantiate the specific model
            try:
                chat_model = genai.GenerativeModel(model_name)
            except Exception as model_init_error:
                print(
                    f"Error initializing model '{model_name}': {model_init_error}. Falling back to default '{DEFAULT_MODEL}'."
                )
                chat_model = genai.GenerativeModel(DEFAULT_MODEL)
                assistant_reply = f"[System: Model '{model_name}' not found, using default '{DEFAULT_MODEL}'.] "

            # Build context from history (markers only)
            history_for_gemini_raw = get_chat_history_from_db(chat_id, limit=20)
            gemini_context = []
            for msg in history_for_gemini_raw:
                role = "model" if msg["role"] == "assistant" else "user"
                gemini_context.append({"role": role, "parts": [msg["content"]]})
            if gemini_context and gemini_context[-1]["role"] == "user":
                gemini_context.pop()

            print(
                f"--- Sending to Gemini (Chat ID: {chat_id}, Model: {model_name}) ---"
            )
            print(f"Content Parts Type: {type(gemini_parts)}")
            print(
                f"Content Parts: {[str(p)[:100]+'...' if isinstance(p, str) else type(p) for p in gemini_parts]}"
            )  # Log types/start of parts
            print("--- End Gemini Send ---")

            # Generate content using the prepared parts
            full_request_content = gemini_context + [
                {"role": "user", "parts": gemini_parts}
            ]
            response = chat_model.generate_content(
                full_request_content
            )  # Send list of parts

            # Prepend system message if model fallback occurred
            current_reply = response.text
            if assistant_reply != "[AI response error occurred]":
                assistant_reply += current_reply
            else:
                assistant_reply = current_reply

            print(f"Gemini Response: {assistant_reply[:100]}...")

        except Exception as e:
            print(
                f"Error calling Gemini API for chat {chat_id} with model {model_name}: {e}"
            )
            error_message = f"[Error communicating with AI: {e}]"
            # More specific error handling
            if "API key not valid" in str(e):
                error_message = "[Error: Invalid Gemini API Key.]"
            elif (
                "token" in str(e).lower()
                or "size" in str(e).lower()
                or "request payload size" in str(e).lower()
            ):
                error_message = (
                    "[Error: Request too large. Try summaries or fewer/smaller files.]"
                )
            elif "prompt was blocked" in str(e).lower():
                error_message = "[Error: Request blocked by safety settings.]"
            elif "resource has been exhausted" in str(e).lower():
                error_message = "[Error: API quota exceeded. Please try again later.]"
            elif "429" in str(e):
                error_message = "[Error: Too many requests. Please try again later.]"
            # Append specific error to any fallback message
            if assistant_reply != "[AI response error occurred]":
                assistant_reply += "\n" + error_message
            else:
                assistant_reply = error_message

        # Add assistant reply to DB
        add_message_to_db(chat_id, "assistant", assistant_reply)

        return jsonify({"reply": assistant_reply})

    finally:
        # --- Clean up temporary files ---
        print(f"Cleaning up {len(temp_files_to_clean)} temporary files...")
        for temp_path in temp_files_to_clean:
            try:
                os.remove(temp_path)
                print(f"Removed temp file: {temp_path}")
            except OSError as e:
                print(f"Error removing temp file {temp_path}: {e}")


# --- Main Execution ---
if __name__ == "__main__":
    with app.app_context():
        print("Initializing database...")
        init_db()
    print(f"Starting Flask server on http://127.0.0.1:5000 (DB: {DB_NAME})")
    app.run(debug=True, host="127.0.0.1", port=5000)
