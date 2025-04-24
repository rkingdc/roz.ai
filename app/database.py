# app/database.py - Refactored for Flask-SQLAlchemy ORM

import logging
# Removed difflib import
from datetime import datetime, timezone
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

# Import AI services for summary generation
from app import ai_services

# Import db instance and models
from app import db
from .models import Chat, Message, File, Note, NoteHistory, default_utcnow # Import NoteHistory

logger = logging.getLogger(__name__)

# --- Helper Functions (Optional) ---

def _commit_session():
    """Commits the current session and handles potential errors."""
    try:
        db.session.commit()
        return True
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Database commit/rollback error: {e}", exc_info=True)
        return False

# --- Database Interaction Functions (ORM based) ---

# Chats
def create_new_chat_entry():
    """Creates a new chat entry using the Chat model."""
    now = default_utcnow()
    formatted_time = now.strftime("%a %b %d, %I:%M %p")
    default_chat_name = f"Chat on {formatted_time}"
    # Get default model from config
    default_model_name = current_app.config.get('DEFAULT_MODEL', 'gemini-1.5-flash') # Fallback if not in config

    new_chat = Chat(
        name=default_chat_name,
        model_name=default_model_name
        # created_at and last_updated_at have defaults in the model
    )
    try:
        db.session.add(new_chat)
        if _commit_session():
            logger.info(f"Successfully created new chat with ID: {new_chat.id}, Name: '{new_chat.name}', Model: {new_chat.model_name}")
            return new_chat.id
        else:
            return None # Commit failed
    except SQLAlchemyError as e:
        logger.error(f"Database error creating new chat entry: {e}", exc_info=True)
        db.session.rollback() # Ensure rollback on add error too
        return None

def get_chat_details_from_db(chat_id):
    """Retrieves details for a specific chat_id using the Chat model."""
    try:
        chat = db.session.get(Chat, chat_id)
        if chat:
            # Return as a dictionary matching previous structure
            return {
                'id': chat.id,
                'name': chat.name,
                'created_at': chat.created_at,
                'last_updated_at': chat.last_updated_at,
                'model_name': chat.model_name
            }
        else:
            return None
    except SQLAlchemyError as e:
        logger.error(f"Database error getting details for chat {chat_id}: {e}", exc_info=True)
        return None

def get_saved_chats_from_db():
    """Retrieves a list of all chats, ordered by last updated, using Chat model."""
    try:
        chats = Chat.query.order_by(Chat.last_updated_at.desc()).all()
        # Return list of dictionaries matching previous structure
        return [
            {'id': chat.id, 'name': chat.name, 'last_updated_at': chat.last_updated_at}
            for chat in chats
        ]
    except SQLAlchemyError as e:
        logger.error(f"Database error getting saved chats: {e}", exc_info=True)
        return []

def save_chat_name_in_db(chat_id, name):
    """Updates the name of a specific chat using the Chat model."""
    try:
        chat = db.session.get(Chat, chat_id)
        if not chat:
            logger.warning(f"Chat not found with ID: {chat_id} for name update.")
            return False

        effective_name = name.strip() if name and name.strip() else f"Chat {chat_id}"
        chat.name = effective_name
        # last_updated_at is handled by onupdate in the model
        # chat.last_updated_at = default_utcnow() # Or manually set if needed

        logger.info(f"Attempting to save name for chat {chat_id} to '{effective_name}'...")
        if _commit_session():
            logger.info(f"Successfully updated name for chat {chat_id} to '{effective_name}'")
            return True
        else:
            return False # Commit failed
    except SQLAlchemyError as e:
        logger.error(f"Database error saving chat name for {chat_id}: {e}", exc_info=True)
        db.session.rollback()
        return False

def update_chat_model(chat_id, model_name):
    """Updates the model name for a specific chat using the Chat model."""
    try:
        chat = db.session.get(Chat, chat_id)
        if not chat:
            logger.warning(f"Chat not found with ID: {chat_id} for model update.")
            return False

        chat.model_name = model_name
        # last_updated_at is handled by onupdate in the model
        # chat.last_updated_at = default_utcnow() # Or manually set if needed

        logger.info(f"Attempting to update model for chat {chat_id} to '{model_name}'...")
        if _commit_session():
            logger.info(f"Successfully updated model for chat {chat_id} to '{model_name}'")
            return True
        else:
            return False # Commit failed
    except SQLAlchemyError as e:
        logger.error(f"Database error updating model for chat {chat_id}: {e}", exc_info=True)
        db.session.rollback()
        return False

def delete_chat_from_db(chat_id):
    """Deletes a chat and its associated messages using the Chat model and cascade."""
    try:
        chat = db.session.get(Chat, chat_id)
        if not chat:
            logger.warning(f"No chat record found with ID: {chat_id} to delete.")
            return False # Indicate chat not found

        logger.info(f"Attempting to delete chat with ID: {chat_id}...")
        db.session.delete(chat)
        if _commit_session():
            logger.info(f"Successfully deleted chat with ID: {chat_id}")
            return True
        else:
            return False # Commit failed
    except SQLAlchemyError as e:
        logger.error(f"Database error deleting chat {chat_id}: {e}", exc_info=True)
        db.session.rollback()
        return False

# Messages
def add_message_to_db(chat_id, role, content):
    """Adds a message using the Message model and updates chat timestamp."""
    logger.info(f"--> Entering add_message_to_db for chat {chat_id}, role '{role}'.")
    try:
        # Check if chat exists first
        chat = db.session.get(Chat, chat_id)
        if not chat:
            logger.error(f"Cannot add message: Chat with ID {chat_id} not found.")
            return False

        new_message = Message(
            chat_id=chat_id,
            role=role,
            content=content
            # timestamp has default in model
        )
        db.session.add(new_message)

        # Manually update chat timestamp (onupdate might not trigger reliably on relationship changes)
        chat.last_updated_at = default_utcnow()
        db.session.add(chat) # Add chat to session again to ensure update is tracked

        logger.info(f"Attempting to add '{role}' message to chat {chat_id} and update timestamp...")
        if _commit_session():
            logger.info(f"Successfully added '{role}' message to chat {chat_id} and updated timestamp.")
            return True
        else:
            return False # Commit failed
    except SQLAlchemyError as e:
        logger.error(f"Database error adding message to chat {chat_id}: {e}", exc_info=True)
        db.session.rollback()
        return False

def get_chat_history_from_db(chat_id, limit=100):
    """Retrieves messages for a specific chat_id using the Message model."""
    try:
        messages = Message.query.filter_by(chat_id=chat_id)\
                                .order_by(Message.timestamp.asc())\
                                .limit(limit)\
                                .all()
        # Return list of dictionaries matching previous structure
        return [
            {'role': msg.role, 'content': msg.content, 'timestamp': msg.timestamp}
            for msg in messages
        ]
    except SQLAlchemyError as e:
        logger.error(f"Database error getting history for chat {chat_id}: {e}", exc_info=True)
        return []

# Files
# Added optional commit parameter
def save_file_record_to_db(filename, content_blob, mimetype, filesize, commit=True):
    """Saves file metadata and content blob using the File model."""
    logger.debug(f"save_file_record_to_db called for '{filename}' with commit={commit}.")
    new_file = File(
        filename=filename,
        content=content_blob,
        mimetype=mimetype,
        filesize=filesize
        # uploaded_at has default, summary is nullable
    )
    try:
        db.session.add(new_file)
        logger.debug(f"Added file record for '{filename}' to session.")
        if commit:
            logger.info(f"Attempting to commit file record for '{filename}'...")
            if _commit_session():
                logger.info(f"Successfully saved file record & BLOB: ID {new_file.id}, Name '{filename}', Type '{mimetype}', Size {filesize}")
                return new_file.id
            else:
                # _commit_session handles rollback and logging
                return None # Commit failed
        else:
            # Return the object itself so the caller can collect it
            logger.debug(f"File record for '{filename}' added to session, commit deferred. Returning object.")
            return new_file # Return the SQLAlchemy object
    except SQLAlchemyError as e:
        logger.error(f"Database error adding file record/BLOB for '{filename}' to session: {e}", exc_info=True)
        db.session.rollback() # Rollback the add operation if it failed
        return None

def get_uploaded_files_from_db():
    """Retrieves metadata for all uploaded files using the File model."""
    try:
        files = File.query.order_by(File.uploaded_at.desc()).all()
        # Return list of dictionaries matching previous structure
        return [
            {
                'id': f.id,
                'filename': f.filename,
                'mimetype': f.mimetype,
                'filesize': f.filesize,
                'uploaded_at': f.uploaded_at,
                'has_summary': f.summary is not None # Check summary in Python
            } for f in files
        ]
    except SQLAlchemyError as e:
        logger.error(f"Database error getting file list: {e}", exc_info=True)
        return []

def get_file_details_from_db(file_id, include_content=False):
    """Retrieves details for a specific file ID using the File model."""
    try:
        query = File.query.filter_by(id=file_id)
        if include_content:
            # Load content explicitly if needed
            # For large blobs, consider deferred loading if not always needed
            file_data = query.first()
        else:
            # Select specific columns excluding content
            file_data = query.options(db.defer(File.content)).first()

        if file_data:
            details = {
                'id': file_data.id,
                'filename': file_data.filename,
                'mimetype': file_data.mimetype,
                'filesize': file_data.filesize,
                'summary': file_data.summary,
                'has_summary': file_data.summary is not None
            }
            if include_content:
                details['content'] = file_data.content
            return details
        else:
            return None
    except SQLAlchemyError as e:
        logger.error(f"Database error getting details for file {file_id}: {e}", exc_info=True)
        return None

def get_summary_from_db(file_id):
    """Retrieves only the summary for a specific file using the File model."""
    try:
        # Query only the summary column for efficiency
        result = db.session.query(File.summary).filter_by(id=file_id).first()
        return result.summary if result else None
    except SQLAlchemyError as e:
        logger.error(f"Database error getting summary for file {file_id}: {e}", exc_info=True)
        return None

def save_summary_in_db(file_id, summary):
    """Saves or updates the summary for a specific file using the File model."""
    try:
        file_rec = db.session.get(File, file_id)
        if not file_rec:
            logger.warning(f"File not found with ID: {file_id} for summary update.")
            return False

        file_rec.summary = summary
        logger.info(f"Attempting to save summary for file ID: {file_id}...")
        if _commit_session():
            logger.info(f"Successfully saved summary for file ID: {file_id}")
            return True
        else:
            return False # Commit failed
    except SQLAlchemyError as e:
        logger.error(f"Database error saving summary for file {file_id}: {e}", exc_info=True)
        db.session.rollback()
        return False

def delete_file_record_from_db(file_id):
    """Deletes a file record using the File model."""
    try:
        file_rec = db.session.get(File, file_id)
        if not file_rec:
            logger.warning(f"No file record found with ID: {file_id} to delete.")
            return False # Indicate file not found

        logger.info(f"Attempting to delete file record with ID: {file_id}...")
        db.session.delete(file_rec)
        if _commit_session():
            logger.info(f"Successfully deleted file record with ID: {file_id}")
            return True
        else:
            return False # Commit failed
    except SQLAlchemyError as e:
        logger.error(f"Database error deleting file record {file_id}: {e}", exc_info=True)
        db.session.rollback()
        return False

# Notes
def create_new_note_entry():
    """Creates a new note entry using the Note model."""
    now = default_utcnow()
    formatted_time = now.strftime("%a %b %d, %I:%M %p")
    default_note_name = f"Note on {formatted_time}"

    new_note = Note(
        name=default_note_name,
        content=''
        # created_at and last_saved_at have defaults
    )
    try:
        db.session.add(new_note)
        logger.info(f"Attempting to create new note entry...")
        if _commit_session():
            logger.info(f"Successfully created new note with ID: {new_note.id}, Name: '{new_note.name}'")
            return new_note.id
        else:
            return None # Commit failed
    except SQLAlchemyError as e:
        logger.error(f"Database error creating new note entry: {e}", exc_info=True)
        db.session.rollback()
        return None

def get_saved_notes_from_db():
    """Retrieves a list of all notes, ordered by last saved, using Note model."""
    try:
        notes = Note.query.order_by(Note.last_saved_at.desc()).all()
        # Return list of dictionaries matching previous structure
        return [
            {'id': note.id, 'name': note.name, 'last_saved_at': note.last_saved_at}
            for note in notes
        ]
    except SQLAlchemyError as e:
        logger.error(f"Database error getting saved notes: {e}", exc_info=True)
        return []

def get_note_from_db(note_id):
    """Retrieves the content and details of a specific note by ID using Note model."""
    try:
        note = db.session.get(Note, note_id)
        if note:
            logger.info(f"Successfully retrieved note content for ID: {note_id}.")
            # Return dictionary matching previous structure
            return {
                'id': note.id,
                'name': note.name,
                'content': note.content,
                'last_saved_at': note.last_saved_at
            }
        else:
            logger.warning(f"Note not found with ID: {note_id}.")
            return None
    except SQLAlchemyError as e:
        logger.error(f"Database error getting note {note_id}: {e}", exc_info=True)
        return None

def save_note_to_db(note_id, name, content):
    """Saves or updates a specific note entry by ID using the Note model, creating history."""
    try:
        note = db.session.get(Note, note_id)
        if not note:
            logger.warning(f"Note not found with ID: {note_id} for saving.")
            return False

        effective_name = name.strip() if name and name.strip() else f"Note {note_id}"

        # Store the current state *before* updating the note object
        old_name = note.name
        old_content = note.content

        # Update the note with new values
        note.name = effective_name
        note.content = content
        # last_saved_at is handled by onupdate in the model

        # Check if content or name has changed *after* updating the note object
        # This check compares the *old* state to the *new* state now stored in the note object
        content_changed = old_content != note.content
        name_changed = old_name != note.name

        # Create a history entry *after* updating the note object,
        # capturing the state *as it is about to be saved*
        history_entry = None # Initialize history_entry
        last_history_id = None # To store the ID of the previous history entry

        # Only create history if something actually changed
        if content_changed or name_changed:
            # Get the previous history entry *before* creating the new one
            last_history = NoteHistory.query.filter_by(note_id=note.id)\
                                            .order_by(NoteHistory.saved_at.desc())\
                                            .first()
            last_history_id = last_history.id if last_history else None

            # Create the history entry *without* the summary first
            history_entry = NoteHistory(
                note_id=note.id,
                name=note.name,      # Save the name *after* the update
                content=note.content, # Save the content *after* the update
                note_diff=None # Summary will be generated after adding
                # saved_at defaults to now()
            )
            db.session.add(history_entry)
            # We need to flush to get the ID of the new history_entry if needed,
            # but we won't commit yet. The AI generation happens before the final commit.
            db.session.flush() # Assigns ID to history_entry
            logger.info(f"Created history entry (ID: {history_entry.id}) for note ID {note_id} capturing the new state. Summary generation pending.")
        else:
            logger.info(f"No changes detected for note ID {note_id}, skipping history entry creation.")

        # --- Attempt to commit the main note save and the history entry (without summary yet) ---
        logger.info(f"Attempting initial commit for note ID: {note_id} (name: '{effective_name}')...")
        if not _commit_session():
            logger.error(f"Initial commit failed for note {note_id}. Aborting summary generation.")
            return False # Main save failed

        # --- If initial commit succeeded AND a history entry was created, generate summary ---
        if history_entry:
            logger.info(f"Note {note_id} saved. Proceeding with summary generation for history entry {history_entry.id}.")
            summary_to_save = None
            try:
                # Get previous content (use the last_history object fetched earlier)
                previous_content_str = last_history.content if last_history else ""
                # Ensure current content is string
                current_content_str = note.content if note.content is not None else ""

                if not last_history:
                    # This is the first version saved
                    summary_to_save = "[Initial version]"
                    logger.info(f"Marking history entry {history_entry.id} as initial version.")
                elif not content_changed:
                    # Only name changed, no content diff to summarize
                    summary_to_save = "[Metadata change only]"
                    logger.info(f"Marking history entry {history_entry.id} as metadata change only.")
                else:
                    # Generate AI summary
                    logger.info(f"Calling AI service to generate diff summary between history {last_history_id} and {history_entry.id}.")
                    generated_summary = ai_services.generate_note_diff_summary(previous_content_str, current_content_str)

                    # Check for AI errors, but save a marker instead of failing the whole process
                    if generated_summary.startswith(("[Error", "[AI Error", "[System Note")):
                        logger.error(f"AI service failed to generate diff summary for history {history_entry.id}: {generated_summary}")
                        summary_to_save = "[AI summary generation failed]" # Save error marker
                    else:
                        summary_to_save = generated_summary
                        logger.info(f"AI summary generated successfully for history entry {history_entry.id}.")

                # --- Save the summary (or marker) to the existing history entry ---
                # Fetch the entry again within this session context to update it
                hist_entry_to_update = db.session.get(NoteHistory, history_entry.id)
                if hist_entry_to_update:
                    hist_entry_to_update.note_diff = summary_to_save
                    logger.info(f"Attempting to commit summary '{summary_to_save[:30]}...' for history ID: {history_entry.id}...")
                    if _commit_session():
                        logger.info(f"Successfully saved summary for history ID: {history_entry.id}")
                    else:
                        # Log error, but don't return False, as the main note save succeeded
                        logger.error(f"Failed to commit summary update for history ID: {history_entry.id}. Note content was saved.")
                else:
                     logger.error(f"Could not find history entry {history_entry.id} in session to save summary. Note content was saved.")

            except Exception as ai_err:
                # Catch any unexpected error during AI call or summary saving logic
                logger.error(f"Unexpected error during AI summary generation/saving for history {history_entry.id}: {ai_err}", exc_info=True)
                # Attempt to save a generic error marker
                try:
                    hist_entry_to_update = db.session.get(NoteHistory, history_entry.id)
                    if hist_entry_to_update and hist_entry_to_update.note_diff is None: # Avoid overwriting previous marker
                        hist_entry_to_update.note_diff = "[Summary generation error]"
                        _commit_session() # Attempt commit, ignore failure here
                except Exception as marker_err:
                    logger.error(f"Failed to save error marker for history {history_entry.id}: {marker_err}")
                # Do not return False, main save succeeded.

        # If we reached here, the main note save was successful
        logger.info(f"save_note_to_db completed for note ID: {note_id}.")
        return True

    except SQLAlchemyError as e:
        logger.error(f"Database error during save_note_to_db for note {note_id}: {e}", exc_info=True)
    except SQLAlchemyError as e:
        logger.error(f"Database error saving note {note_id}: {e}", exc_info=True)
        db.session.rollback()
        return False

def delete_note_from_db(note_id):
    """Deletes a note entry by ID using the Note model."""
    try:
        note = db.session.get(Note, note_id)
        if not note:
            logger.warning(f"No note record found with ID: {note_id} to delete.")
            return False # Indicate note not found

        logger.info(f"Attempting to delete note with ID: {note_id}...")
        db.session.delete(note)
        if _commit_session():
            logger.info(f"Successfully deleted note with ID: {note_id}")
            return True
        else:
            return False # Commit failed
    except SQLAlchemyError as e:
        logger.error(f"Database error deleting note {note_id}: {e}", exc_info=True)
        db.session.rollback()
        return False

# Function to get a single note history entry
def get_note_history_entry_from_db(history_id):
    """Retrieves a single note history entry by its ID."""
    try:
        entry = db.session.get(NoteHistory, history_id)
        if entry:
            return {
                'id': entry.id,
                'note_id': entry.note_id,
                'name': entry.name,
                'content': entry.content,
                'note_diff': entry.note_diff,
                'saved_at': entry.saved_at
            }
        else:
            return None
    except SQLAlchemyError as e:
        logger.error(f"Database error getting history entry {history_id}: {e}", exc_info=True)
        return None

# Removed save_note_diff_summary_in_db function

# Function to get note history
def get_note_history_from_db(note_id, limit=None):
    """Retrieves history entries for a specific note_id, ordered by saved_at descending."""
    try:
        query = NoteHistory.query.filter_by(note_id=note_id).order_by(NoteHistory.saved_at.desc())
        if limit is not None:
            query = query.limit(limit)
        history_entries = query.all()

        return [
            {
                'id': entry.id,
                'note_id': entry.note_id,
                'name': entry.name,
                'content': entry.content,
                'note_diff': entry.note_diff, # Include the AI summary
                'saved_at': entry.saved_at
            } for entry in history_entries
        ]
    except SQLAlchemyError as e:
        logger.error(f"Database error getting history for note {note_id}: {e}", exc_info=True)
        return []
