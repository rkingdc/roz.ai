# app/database.py
import sqlite3
import click
from flask import current_app, g
from datetime import datetime

# --- Database Connection ---

def get_db():
    """Connects to the application's configured database. The connection
    is unique for each request and will be reused if this is called
    again.
    """
    if 'db' not in g:
        try:
            g.db = sqlite3.connect(
                current_app.config['DB_NAME'],
                detect_types=sqlite3.PARSE_DECLTYPES
            )
            g.db.row_factory = sqlite3.Row
            print(f"Database connection opened: {current_app.config['DB_NAME']}")
        except sqlite3.Error as e:
            print(f"Error connecting to database '{current_app.config['DB_NAME']}': {e}")
            raise # Re-raise the error after logging
    return g.db

def close_db(e=None):
    """Closes the database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()
        print("Database connection closed.")

# --- Database Initialization ---

def init_db():
    """Clears existing data and creates new tables."""
    db = get_db()
    cursor = db.cursor()

    print(f"Initializing database schema for {current_app.config['DB_NAME']}...")

    # Drop existing tables (simple approach for dev/example)
    # In production, use migrations (e.g., Flask-Migrate with Alembic)
    cursor.execute("DROP TABLE IF EXISTS messages")
    cursor.execute("DROP TABLE IF EXISTS uploaded_files")
    cursor.execute("DROP TABLE IF EXISTS chats")
    print("Dropped existing tables (if any).")

    # Create chats table
    cursor.execute(f'''
        CREATE TABLE chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT DEFAULT 'New Chat',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            model_name TEXT DEFAULT '{current_app.config["DEFAULT_MODEL"]}'
        )
    ''')
    print("Created 'chats' table.")

    # Create messages table
    cursor.execute('''
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX idx_messages_chat_id ON messages (chat_id)')
    print("Created 'messages' table and index.")

    # Create uploaded_files table (with BLOB)
    cursor.execute('''
        CREATE TABLE uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content BLOB NOT NULL,
            mimetype TEXT NOT NULL,
            filesize INTEGER NOT NULL,
            summary TEXT,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX idx_files_filename ON uploaded_files (filename)')
    print("Created 'uploaded_files' table and index.")

    db.commit()
    print("Database schema initialized successfully.")

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
    app.teardown_appcontext(close_db) # Call close_db when app context tears down
    app.cli.add_command(init_db_command) # Add `flask init-db` command

# --- Database Interaction Functions ---

# Chats
def create_new_chat_entry():
    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    default_model = current_app.config['DEFAULT_MODEL']
    cursor.execute("INSERT INTO chats (created_at, last_updated_at, model_name) VALUES (?, ?, ?)",
                   (now, now, default_model))
    db.commit()
    new_chat_id = cursor.lastrowid
    print(f"Created new chat with ID: {new_chat_id}, Model: {default_model}")
    return new_chat_id

def update_chat_timestamp(chat_id):
    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    cursor.execute("UPDATE chats SET last_updated_at = ? WHERE id = ?", (now, chat_id))
    db.commit()

def get_chat_details_from_db(chat_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, name, created_at, last_updated_at, model_name FROM chats WHERE id = ?", (chat_id,))
        chat_details = cursor.fetchone()
        return dict(chat_details) if chat_details else None
    except sqlite3.Error as e:
        print(f"Database error getting details for chat {chat_id}: {e}")
        return None

def get_saved_chats_from_db():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, name, last_updated_at FROM chats ORDER BY last_updated_at DESC")
        chats = cursor.fetchall()
        return [dict(row) for row in chats]
    except sqlite3.Error as e:
        print(f"Database error getting saved chats: {e}")
        return []

def save_chat_name_in_db(chat_id, name):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE chats SET name = ?, last_updated_at = ? WHERE id = ?", (name, datetime.now(), chat_id))
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
        cursor.execute("UPDATE chats SET model_name = ?, last_updated_at = ? WHERE id = ?",
                       (model_name, datetime.now(), chat_id))
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

# Messages
def add_message_to_db(chat_id, role, content):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                       (chat_id, role, content))
        db.commit()
        update_chat_timestamp(chat_id) # Also update chat timestamp
        return True
    except sqlite3.Error as e:
        print(f"Database error adding message: {e}")
        return False

def get_chat_history_from_db(chat_id, limit=100):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT role, content, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp ASC LIMIT ?",
                       (chat_id, limit))
        history = cursor.fetchall()
        return [dict(row) for row in history]
    except sqlite3.Error as e:
        print(f"Database error getting history for chat {chat_id}: {e}")
        return []

# Files
def save_file_record_to_db(filename, content_blob, mimetype, filesize):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO uploaded_files (filename, content, mimetype, filesize, summary) VALUES (?, ?, ?, ?, NULL)",
                       (filename, content_blob, mimetype, filesize))
        db.commit()
        file_id = cursor.lastrowid
        print(f"Saved file record & BLOB: ID {file_id}, Name '{filename}', Type '{mimetype}', Size {filesize}")
        return file_id
    except sqlite3.Error as e:
        print(f"Database error saving file record/BLOB for '{filename}': {e}")
        return None

def get_uploaded_files_from_db():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(" SELECT id, filename, mimetype, filesize, uploaded_at, (summary IS NOT NULL) as has_summary FROM uploaded_files ORDER BY uploaded_at DESC ")
        files = cursor.fetchall()
        return [dict(row) for row in files]
    except sqlite3.Error as e:
        print(f"Database error getting file list: {e}")
        return []

def get_file_details_from_db(file_id, include_content=False):
    try:
        db = get_db()
        cursor = db.cursor()
        columns = "id, filename, mimetype, filesize, summary, (summary IS NOT NULL) as has_summary"
        if include_content:
            columns += ", content"
        cursor.execute(f"SELECT {columns} FROM uploaded_files WHERE id = ?", (file_id,))
        file_data = cursor.fetchone()
        return dict(file_data) if file_data else None
    except sqlite3.Error as e:
        print(f"Database error getting details for file {file_id}: {e}")
        return None

def get_summary_from_db(file_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT summary FROM uploaded_files WHERE id = ?", (file_id,))
        result = cursor.fetchone()
        return result['summary'] if result and result['summary'] else None
    except sqlite3.Error as e:
        print(f"Database error getting summary for file {file_id}: {e}")
        return None

def save_summary_in_db(file_id, summary):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE uploaded_files SET summary = ? WHERE id = ?", (summary, file_id))
        db.commit()
        print(f"Saved summary for file ID: {file_id}")
        return True
    except sqlite3.Error as e:
        print(f"Database error saving summary for file {file_id}: {e}")
        return False

