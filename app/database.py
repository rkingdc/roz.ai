# Configure logging
import logging
import os # Import os to get process ID
import sqlite3
import click
from flask import current_app, g
from datetime import datetime

# Configure logging
# Ensure basicConfig is only called once if this file is imported multiple times
if not logging.getLogger(__name__).handlers:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Database Connection ---

def get_db():
    """Connects to the application's configured database. The connection
    is unique for each request and will be reused if this is called
    again.
    Also ensures the schema is applied for in-memory databases if needed.
    """
    if 'db' not in g:
        try:
            db_name = current_app.config['DB_NAME']
            # Use uri=True to allow file: URIs for absolute paths
            g.db = sqlite3.connect(
                db_name,
                detect_types=sqlite3.PARSE_DECLTYPES,
                uri=True # Added uri=True
            )
            g.db.row_factory = sqlite3.Row
            logger.info(f"Database connection opened: {db_name} in process {os.getpid()}")

            # --- Schema Initialization for In-Memory DB ---
            # For in-memory databases, the schema needs to be applied
            # per connection/worker if it hasn't been already.
            # Check if the 'chats' table exists as a proxy for schema presence.
            # This block is now only relevant if DB_NAME is explicitly ':memory:'
            # which should not happen with the Makefile change, but kept for robustness.
            # Also check for 'notes' table now.
            if db_name == ':memory:':
                cursor = g.db.cursor()
                try:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chats';")
                    chats_table_exists = cursor.fetchone()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notes';")
                    notes_table_exists = cursor.fetchone()


                    if not chats_table_exists or not notes_table_exists:
                        logger.info(f"In-memory database '{db_name}' is empty or incomplete in process {os.getpid()}. Applying schema...")
                        # Execute the schema creation SQL directly using executescript
                        # Ensure this matches the schema.sql content
                        schema_sql = f'''
                            PRAGMA foreign_keys = ON; -- Ensure foreign keys are enforced

                            CREATE TABLE IF NOT EXISTS chats (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                name TEXT NOT NULL DEFAULT 'New Chat',
                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                model_name TEXT DEFAULT '{current_app.config.get("DEFAULT_MODEL", "gemini-pro")}'
                            );
                            CREATE INDEX IF NOT EXISTS idx_chats_last_updated ON chats (last_updated_at DESC); -- Added index

                            CREATE TABLE IF NOT EXISTS messages (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                chat_id INTEGER NOT NULL,
                                role TEXT NOT NULL,
                                content TEXT NOT NULL,
                                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
                            );
                            CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id);
                            CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages (timestamp ASC); -- Added index

                            CREATE TABLE IF NOT EXISTS files (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                filename TEXT NOT NULL,
                                content BLOB NOT NULL,
                                mimetype TEXT NOT NULL,
                                filesize INTEGER NOT NULL,
                                summary TEXT,
                                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS idx_files_filename ON files (filename);
                            CREATE INDEX IF NOT EXISTS idx_files_uploaded_at ON files (uploaded_at DESC); -- Added index

                            -- Create the notes table (for multiple notes)
                            CREATE TABLE IF NOT EXISTS notes (
                                id INTEGER PRIMARY KEY AUTOINCREMENT, -- Allow multiple notes
                                name TEXT NOT NULL DEFAULT 'New Note', -- Add name field
                                content TEXT NOT NULL DEFAULT '',
                                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                last_saved_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS idx_notes_last_saved ON notes (last_saved_at DESC); -- Add index for ordering

                            -- No initial insert needed for multiple notes
                        '''
                        cursor.executescript(schema_sql)

                        g.db.commit()
                        logger.info(f"Schema applied to in-memory database in process {os.getpid()}.")
                except sqlite3.Error as schema_e:
                     logger.error(f"Error applying schema to in-memory database in process {os.getpid()}: {schema_e}", exc_info=True)
                     # Depending on desired behavior, you might want to raise here
                     # or handle it differently. For now, log and let the original
                     # error (if any) propagate.

            # Ensure foreign keys are enabled for this connection
            g.db.execute("PRAGMA foreign_keys = ON;")


        except sqlite3.Error as e:
            logger.error(f"Error connecting to database '{current_app.config['DB_NAME']}' in process {os.getpid()}: {e}", exc_info=True)
            raise # Re-raise the error after logging
    else:
        logger.info(f"Using existing database connection for '{current_app.config['DB_NAME']}' in process {os.getpid()}")
    return g.db

def close_db(e=None):
    """Closes the database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()
        logger.info(f"Database connection closed in process {os.getpid()}.")

# --- Database Initialization ---

def init_db():
    """Clears existing data and creates new tables."""
    logger.info(f"init_db called in process {os.getpid()}") # Log process ID
    db = get_db() # Use get_db to ensure connection is open
    cursor = db.cursor()

    db_name = current_app.config['DB_NAME']
    logger.info(f"Initializing database schema for {db_name}...")

    try:
        # Drop tables (safe for :memory: or file db init)
        cursor.execute("DROP TABLE IF EXISTS messages")
        cursor.execute("DROP TABLE IF EXISTS files")
        cursor.execute("DROP TABLE IF EXISTS chats")
        cursor.execute("DROP TABLE IF EXISTS notes") # Drop notes table
        logger.info("Dropped existing tables (if any).")

        # Ensure foreign keys are enforced during schema creation
        cursor.execute("PRAGMA foreign_keys = ON;")

        # Create chats table - Added IF NOT EXISTS
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT 'New Chat',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                model_name TEXT DEFAULT '{current_app.config.get("DEFAULT_MODEL", "gemini-pro")}'
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chats_last_updated ON chats (last_updated_at DESC)') # Added IF NOT EXISTS
        logger.info("Created 'chats' table and index.")


        # Create messages table - Added IF NOT EXISTS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id)') # Added IF NOT EXISTS
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages (timestamp ASC)') # Added IF NOT EXISTS
        logger.info("Created 'messages' table and indexes.")

        # Create files table (with BLOB) - Added IF NOT EXISTS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                content BLOB NOT NULL,
                mimetype TEXT NOT NULL,
                filesize INTEGER NOT NULL,
                summary TEXT,
                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_filename ON files (filename)') # Added IF NOT EXISTS
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_uploaded_at ON files (uploaded_at DESC)') # Added IF NOT EXISTS
        logger.info("Created 'files' table and indexes.")

        # Create the notes table (for multiple notes) - Added IF NOT EXISTS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, -- Allow multiple notes
                name TEXT NOT NULL DEFAULT 'New Note', -- Add name field
                content TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_saved_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_last_saved ON notes (last_saved_at DESC)') # Add index for ordering
        logger.info("Created 'notes' table and index.")

        # No initial insert needed for multiple notes

        db.commit()
        logger.info("Database schema initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Error during database schema initialization for {db_name}: {e}", exc_info=True)
        raise # Re-raise the error


# --- CLI Command for DB Initialization ---

@click.command('init-db')
def init_db_command():
    """Clear existing data and create new tables."""
    try:
        init_db()
        click.echo('Initialized the database.')
    except Exception as e:
        click.echo(f'Error initializing database: {e}', err=True)

def init_app(app):
    """Register database functions with the Flask app."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

# --- Database Interaction Functions ---

# Chats
def create_new_chat_entry():
    """Creates a new chat entry with a default name based on current time."""
    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    # Format: Fri Apr 18, 03:27 PM (example)
    formatted_time = now.strftime("%a %b %d, %I:%M %p")
    default_chat_name = f"Chat on {formatted_time}"
    default_model = current_app.config.get('DEFAULT_MODEL', 'gemini-pro') # Use .get with default

    try:
        logger.info(f"Attempting to create new chat entry...")
        # Insert explicit name along with other defaults/values
        cursor.execute("INSERT INTO chats (name, created_at, last_updated_at, model_name) VALUES (?, ?, ?, ?)",
                       (default_chat_name, now, now, default_model))
        new_chat_id = cursor.lastrowid
        db.commit()
        logger.info(f"Successfully created new chat with ID: {new_chat_id}, Name: '{default_chat_name}', Model: {default_model}")
        return new_chat_id
    except sqlite3.Error as e:
        logger.error(f"Database error creating new chat entry: {e}", exc_info=True)
        # No commit needed on error, transaction is rolled back by default
        return None # Indicate failure


def get_chat_details_from_db(chat_id):
    """Retrieves details (including model_name) for a specific chat_id."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, name, created_at, last_updated_at, model_name FROM chats WHERE id = ?", (chat_id,))
        chat_details = cursor.fetchone()
        return dict(chat_details) if chat_details else None
    except sqlite3.Error as e:
        logger.error(f"Database error getting details for chat {chat_id}: {e}", exc_info=True)
        return None

def get_saved_chats_from_db():
    """Retrieves a list of all chats, ordered by last updated."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, name, last_updated_at FROM chats ORDER BY last_updated_at DESC")
        chats = cursor.fetchall()
        return [dict(row) for row in chats]
    except sqlite3.Error as e:
        logger.error(f"Database error getting saved chats: {e}", exc_info=True)
        return []

def save_chat_name_in_db(chat_id, name):
    """Updates the name of a specific chat."""
    try:
        db = get_db()
        cursor = db.cursor()
        # Ensure name is not empty, fallback if necessary (though UI might prevent empty)
        effective_name = name.strip() if name and name.strip() else f"Chat {chat_id}" # Fallback if empty
        logger.info(f"Attempting to save name for chat {chat_id} to '{effective_name}'...")
        cursor.execute("UPDATE chats SET name = ?, last_updated_at = ? WHERE id = ?", (effective_name, datetime.now(), chat_id))
        db.commit()
        logger.info(f"Successfully updated name for chat {chat_id} to '{effective_name}'")
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error saving chat name for {chat_id}: {e}", exc_info=True)
        return False

def update_chat_model(chat_id, model_name):
    """Updates the model name for a specific chat."""
    try:
        db = get_db()
        cursor = db.cursor()
        logger.info(f"Attempting to update model for chat {chat_id} to '{model_name}'...")
        cursor.execute("UPDATE chats SET model_name = ?, last_updated_at = ? WHERE id = ?",
                       (model_name, datetime.now(), chat_id))
        db.commit()
        logger.info(f"Successfully updated model for chat {chat_id} to '{model_name}'")
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error updating model for chat {chat_id}: {e}", exc_info=True)
        return False

def delete_chat_from_db(chat_id):
    """Deletes a chat and its associated messages."""
    try:
        db = get_db()
        cursor = db.cursor()
        logger.info(f"Attempting to delete chat with ID: {chat_id}...")
        cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        deleted_count = cursor.rowcount # Check how many rows were affected
        db.commit()
        if deleted_count > 0:
            logger.info(f"Successfully deleted chat with ID: {chat_id}")
            return True
        else:
            logger.warning(f"No chat record found with ID: {chat_id} to delete.")
            return False # Indicate chat not found
    except sqlite3.Error as e:
        logger.error(f"Database error deleting chat {chat_id}: {e}", exc_info=True)
        return False # Indicate failure

# Messages
def add_message_to_db(chat_id, role, content):
    """Adds a message to the messages table for a specific chat and updates chat timestamp."""
    logger.info(f"--> Entering add_message_to_db for chat {chat_id}, role '{role}'.") # Added log
    try:
        db = get_db()
        cursor = db.cursor()
        now = datetime.now()

        logger.info(f"Attempting to add '{role}' message to chat {chat_id} and update timestamp...")

        # Insert the message
        logger.info(f"Executing INSERT into messages for chat {chat_id}, role '{role}'.")
        cursor.execute("INSERT INTO messages (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                       (chat_id, role, content, now))
        logger.info(f"Message INSERT executed successfully for chat {chat_id}.")

        # Update the chat timestamp in the same transaction
        logger.info(f"Executing UPDATE chats timestamp for chat {chat_id}.")
        cursor.execute("UPDATE chats SET last_updated_at = ? WHERE id = ?", (now, chat_id))
        logger.info(f"Chat timestamp UPDATE executed successfully for chat {chat_id}.")

        # Commit both operations
        logger.info(f"Attempting to commit transaction for chat {chat_id}.")
        db.commit()
        logger.info(f"Successfully added '{role}' message to chat {chat_id} and updated timestamp.")
        return True
    except sqlite3.Error as e:
        # Rollback the transaction on error (automatic with default BEGIN DEFERRED)
        # db.rollback() # Explicit rollback is good practice even with default
        logger.error(f"Database error adding message to chat {chat_id}: {e}", exc_info=True)
        return False # Indicate failure

def get_chat_history_from_db(chat_id, limit=100):
    """Retrieves messages for a specific chat_id."""
    try:
        db = get_db()
        cursor = db.cursor()
        # Include 'assistant' role messages now, as they are part of the history
        cursor.execute("SELECT role, content, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp ASC LIMIT ?",
                       (chat_id, limit))
        history = cursor.fetchall()
        return [dict(row) for row in history]
    except sqlite3.Error as e:
        logger.error(f"Database error getting history for chat {chat_id}: {e}", exc_info=True)
        return []

# Files
def save_file_record_to_db(filename, content_blob, mimetype, filesize):
    """Saves file metadata and content blob to the database."""
    try:
        db = get_db()
        cursor = db.cursor()
        logger.info(f"Attempting to save file record for '{filename}'...")
        cursor.execute("INSERT INTO files (filename, content, mimetype, filesize, summary) VALUES (?, ?, ?, ?, NULL)",
                       (filename, content_blob, mimetype, filesize))
        file_id = cursor.lastrowid
        db.commit()
        logger.info(f"Successfully saved file record & BLOB: ID {file_id}, Name '{filename}', Type '{mimetype}', Size {filesize}")
        return file_id
    except sqlite3.Error as e:
        logger.error(f"Database error saving file record/BLOB for '{filename}': {e}", exc_info=True)
        return None # Indicate failure

def get_uploaded_files_from_db():
    """Retrieves metadata for all uploaded files (excluding BLOB)."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(" SELECT id, filename, mimetype, filesize, uploaded_at, (summary IS NOT NULL) as has_summary FROM files ORDER BY uploaded_at DESC ")
        files = cursor.fetchall()
        return [dict(row) for row in files]
    except sqlite3.Error as e:
        logger.error(f"Database error getting file list: {e}", exc_info=True)
        return []

def get_file_details_from_db(file_id, include_content=False):
    """Retrieves details for a specific file ID, optionally including the content BLOB."""
    try:
        db = get_db()
        cursor = db.cursor()
        columns = "id, filename, mimetype, filesize, summary, (summary IS NOT NULL) as has_summary"
        if include_content:
            columns += ", content"
        cursor.execute(f"SELECT {columns} FROM files WHERE id = ?", (file_id,))
        file_data = cursor.fetchone()
        return dict(file_data) if file_data else None
    except sqlite3.Error as e:
        logger.error(f"Database error getting details for file {file_id}: {e}", exc_info=True)
        return None

def get_summary_from_db(file_id):
    """Retrieves only the summary for a specific file, if it exists."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT summary FROM files WHERE id = ?", (file_id,))
        result = cursor.fetchone()
        return result['summary'] if result and result['summary'] else None
    except sqlite3.Error as e:
        logger.error(f"Database error getting summary for file {file_id}: {e}", exc_info=True)
        return None

def save_summary_in_db(file_id, summary):
    """Saves or updates the summary for a specific file."""
    try:
        db = get_db()
        cursor = db.cursor()
        logger.info(f"Attempting to save summary for file ID: {file_id}...")
        cursor.execute("UPDATE files SET summary = ? WHERE id = ?", (summary, file_id))
        db.commit()
        logger.info(f"Successfully saved summary for file ID: {file_id}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error saving summary for file {file_id}: {e}", exc_info=True)
        return False # Indicate failure

def delete_file_record_from_db(file_id):
    """Deletes a file record (and its BLOB) from the database."""
    try:
        db = get_db()
        cursor = db.cursor()
        logger.info(f"Attempting to delete file record with ID: {file_id}...")
        cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
        deleted_count = cursor.rowcount # Check how many rows were affected
        db.commit()
        if deleted_count > 0:
            logger.info(f"Successfully deleted file record with ID: {file_id}")
            return True
        else:
            logger.warning(f"No file record found with ID: {file_id} to delete.")
            return False # Indicate file not found
    except sqlite3.Error as e:
        logger.error(f"Database error deleting file record {file_id}: {e}", exc_info=True)
        return False # Indicate failure

# Notes (Modified for multiple notes)
def create_new_note_entry():
    """Creates a new note entry with a default name based on current time."""
    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    # Format: Fri Apr 18, 03:27 PM (example)
    formatted_time = now.strftime("%a %b %d, %I:%M %p")
    default_note_name = f"Note on {formatted_time}"

    try:
        logger.info(f"Attempting to create new note entry...")
        cursor.execute("INSERT INTO notes (name, content, created_at, last_saved_at) VALUES (?, ?, ?, ?)",
                       (default_note_name, '', now, now))
        new_note_id = cursor.lastrowid
        db.commit()
        logger.info(f"Successfully created new note with ID: {new_note_id}, Name: '{default_note_name}'")
        return new_note_id
    except sqlite3.Error as e:
        logger.error(f"Database error creating new note entry: {e}", exc_info=True)
        return None # Indicate failure

def get_saved_notes_from_db():
    """Retrieves a list of all notes, ordered by last saved."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, name, last_saved_at FROM notes ORDER BY last_saved_at DESC")
        notes = cursor.fetchall()
        return [dict(row) for row in notes]
    except sqlite3.Error as e:
        logger.error(f"Database error getting saved notes: {e}", exc_info=True)
        return []

def get_note_from_db(note_id):
    """Retrieves the content and details of a specific note by ID."""
    try:
        db = get_db()
        cursor = db.cursor()
        logger.info(f"Attempting to retrieve note content for ID: {note_id}...")
        cursor.execute("SELECT id, name, content, last_saved_at FROM notes WHERE id = ?", (note_id,))
        result = cursor.fetchone()
        content = dict(result) if result else None
        logger.info(f"Successfully retrieved note content for ID: {note_id}.")
        return content
    except sqlite3.Error as e:
        logger.error(f"Database error getting note {note_id}: {e}", exc_info=True)
        return None # Indicate failure

def save_note_to_db(note_id, name, content):
    """Saves or updates a specific note entry by ID."""
    try:
        db = get_db()
        cursor = db.cursor()
        now = datetime.now()
        # Ensure name is not empty, fallback if necessary
        effective_name = name.strip() if name and name.strip() else f"Note {note_id}" # Fallback if empty
        logger.info(f"Attempting to save note content for ID: {note_id} (name: '{effective_name}')...")
        cursor.execute("UPDATE notes SET name = ?, content = ?, last_saved_at = ? WHERE id = ?",
                       (effective_name, content, now, note_id))
        db.commit()
        logger.info(f"Successfully saved note content for ID: {note_id}.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error saving note {note_id}: {e}", exc_info=True)
        return False # Indicate failure

def delete_note_from_db(note_id):
    """Deletes a note entry by ID."""
    try:
        db = get_db()
        cursor = db.cursor()
        logger.info(f"Attempting to delete note with ID: {note_id}...")
        cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        deleted_count = cursor.rowcount # Check how many rows were affected
        db.commit()
        if deleted_count > 0:
            logger.info(f"Successfully deleted note with ID: {note_id}")
            return True
        else:
            logger.warning(f"No note record found with ID: {note_id} to delete.")
            return False # Indicate note not found
    except sqlite3.Error as e:
        logger.error(f"Database error deleting note {note_id}: {e}", exc_info=True)
        return False # Indicate failure
