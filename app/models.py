from datetime import datetime, timezone  # Use timezone-aware UTC
from app import db  # Import the db instance from app/__init__.py
from sqlalchemy import Table, DDL, event  # New imports for FTS


# Helper function for default timestamps
def default_utcnow():
    return datetime.now(timezone.utc)


class Chat(db.Model):
    __tablename__ = "chats"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, default="New Chat")  # Added length
    # Default model should be handled by application logic/config when creating a chat
    model_name = db.Column(
        db.String(100), nullable=False
    )  # Added length, removed default
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=default_utcnow
    )  # Ensure timezone=True
    last_updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=default_utcnow,
        onupdate=default_utcnow,
    )  # Ensure timezone=True
    messages = db.relationship(
        "Message", back_populates="chat", lazy=True, cascade="all, delete-orphan"
    )  # Use back_populates


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(
        db.Integer,
        db.ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )  # Added index=True
    role = db.Column(
        db.String(20), nullable=False
    )  # 'user' or 'assistant', added length
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(
        db.DateTime(timezone=True), nullable=False, default=default_utcnow, index=True
    )  # Added index=True, timezone=True
    attached_data = db.Column(
        db.JSON, nullable=True
    )  # New field for attached file metadata

    # Define relationship back to Chat
    chat = db.relationship("Chat", back_populates="messages")  # Use back_populates


class File(db.Model):
    __tablename__ = "files"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(
        db.String(255), nullable=False, index=True
    )  # Added length, index=True
    content = db.Column(db.LargeBinary, nullable=False)  # Use LargeBinary for BLOB
    mimetype = db.Column(db.String(100), nullable=False)  # Added length
    filesize = db.Column(db.Integer, nullable=False)
    summary = db.Column(db.Text, nullable=True)
    uploaded_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=default_utcnow, index=True
    )  # Added index=True, timezone=True


class Note(db.Model):
    __tablename__ = "notes"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, default="New Note")  # Added length
    content = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=default_utcnow
    )  # Ensure timezone=True
    last_saved_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=default_utcnow,
        onupdate=default_utcnow,
        index=True,
    )  # Added index=True, timezone=True

    # Add relationship to NoteHistory
    history = db.relationship(
        "NoteHistory",
        back_populates="note",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="NoteHistory.saved_at",
    )


class NoteHistory(db.Model):
    __tablename__ = "note_history"
    id = db.Column(db.Integer, primary_key=True)
    note_id = db.Column(
        db.Integer,
        db.ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(
        db.String(150), nullable=True
    )  # Store the name at this point in history
    content = db.Column(
        db.Text, nullable=True
    )  # Store the content at this point in history
    # note_diff_raw column removed
    note_diff = db.Column(
        db.Text, nullable=True
    )  # Store the AI-generated summary of the diff
    saved_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=default_utcnow, index=True
    )

    # Define relationship back to Note
    note = db.relationship("Note", back_populates="history")


# FTS5 Virtual Table Definitions

# For Message content
message_fts_table = Table(
    "message_fts",
    db.metadata,
    db.Column("rowid", db.Integer, primary_key=True),
    db.Column("content", db.Text),
)

event.listen(
    message_fts_table,
    "after_create",
    DDL(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {message_fts_table.name} USING fts5("
        f"  content, "
        "tokenize=porter, "
        f"  content_table='{Message.__tablename__}', "
        f"  content_rowid='id' "
        f")"
    ),
)

# For Note content
note_fts_table = Table(
    "note_fts",
    db.metadata,
    db.Column("rowid", db.Integer, primary_key=True),
    db.Column("content", db.Text),
)

event.listen(
    note_fts_table,
    "after_create",
    DDL(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {note_fts_table.name} USING fts5("
        f"  content, "
        "tokenize=porter, "
        f"  content_table='{Note.__tablename__}', "
        f"  content_rowid='id' "
        f")"
    ),
)

# For File summaries
file_fts_table = Table(
    "file_fts",
    db.metadata,
    db.Column("rowid", db.Integer, primary_key=True),
    db.Column("summary", db.Text),
)

event.listen(
    file_fts_table,
    "after_create",
    DDL(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {file_fts_table.name} USING fts5("
        f"  summary, "
        "tokenize=porter, "
        f"  content_table='{File.__tablename__}', "
        f"  content_rowid='id' "
        f")"
    ),
)

# Triggers to keep FTS tables synchronized

# --- Message FTS Triggers ---
event.listen(
    Message.__table__,
    "after_create",
    DDL(
        f"""
        CREATE TRIGGER IF NOT EXISTS messages_ai_trigger
        AFTER INSERT ON {Message.__tablename__}
        BEGIN
            INSERT INTO {message_fts_table.name} (rowid, content)
            VALUES (new.id, new.content);
        END;
    """
    ),
)

event.listen(
    Message.__table__,
    "after_create",
    DDL(
        f"""
        CREATE TRIGGER IF NOT EXISTS messages_ad_trigger
        AFTER DELETE ON {Message.__tablename__}
        BEGIN
            INSERT INTO {message_fts_table.name} ({message_fts_table.name}, rowid, content)
            VALUES ('delete', old.id, old.content);
        END;
    """
    ),
)

event.listen(
    Message.__table__,
    "after_create",
    DDL(
        f"""
        CREATE TRIGGER IF NOT EXISTS messages_au_trigger
        AFTER UPDATE ON {Message.__tablename__}
        WHEN new.content IS NOT old.content
        BEGIN
            INSERT INTO {message_fts_table.name} ({message_fts_table.name}, rowid, content)
            VALUES ('delete', old.id, old.content);
            INSERT INTO {message_fts_table.name} (rowid, content)
            VALUES (new.id, new.content);
        END;
    """
    ),
)

# --- Note FTS Triggers ---
event.listen(
    Note.__table__,
    "after_create",
    DDL(
        f"""
        CREATE TRIGGER IF NOT EXISTS notes_ai_trigger
        AFTER INSERT ON {Note.__tablename__}
        BEGIN
            INSERT INTO {note_fts_table.name} (rowid, content)
            VALUES (new.id, new.content);
        END;
    """
    ),
)

event.listen(
    Note.__table__,
    "after_create",
    DDL(
        f"""
        CREATE TRIGGER IF NOT EXISTS notes_ad_trigger
        AFTER DELETE ON {Note.__tablename__}
        BEGIN
            INSERT INTO {note_fts_table.name} ({note_fts_table.name}, rowid, content)
            VALUES ('delete', old.id, old.content);
        END;
    """
    ),
)

event.listen(
    Note.__table__,
    "after_create",
    DDL(
        f"""
        CREATE TRIGGER IF NOT EXISTS notes_au_trigger
        AFTER UPDATE ON {Note.__tablename__}
        WHEN new.content IS NOT old.content
        BEGIN
            INSERT INTO {note_fts_table.name} ({note_fts_table.name}, rowid, content)
            VALUES ('delete', old.id, old.content);
            INSERT INTO {note_fts_table.name} (rowid, content)
            VALUES (new.id, new.content);
        END;
    """
    ),
)

# --- File FTS Triggers (for summary) ---
event.listen(
    File.__table__,
    "after_create",
    DDL(
        f"""
        CREATE TRIGGER IF NOT EXISTS files_ai_trigger
        AFTER INSERT ON {File.__tablename__}
        WHEN new.summary IS NOT NULL
        BEGIN
            INSERT INTO {file_fts_table.name} (rowid, summary)
            VALUES (new.id, new.summary);
        END;
    """
    ),
)

event.listen(
    File.__table__,
    "after_create",
    DDL(
        f"""
        CREATE TRIGGER IF NOT EXISTS files_ad_trigger
        AFTER DELETE ON {File.__tablename__}
        WHEN old.summary IS NOT NULL
        BEGIN
            INSERT INTO {file_fts_table.name} ({file_fts_table.name}, rowid, summary)
            VALUES ('delete', old.id, old.summary);
        END;
    """
    ),
)

event.listen(
    File.__table__,
    "after_create",
    DDL(
        f"""
        CREATE TRIGGER IF NOT EXISTS files_au_trigger
        AFTER UPDATE ON {File.__tablename__}
        WHEN new.summary IS NOT old.summary -- This condition handles changes to/from NULL correctly
        BEGIN
            -- Delete old entry (FTS handles old.summary being NULL as a no-op for deletion)
            INSERT INTO {file_fts_table.name} ({file_fts_table.name}, rowid, summary)
            VALUES ('delete', old.id, old.summary);
            -- Insert new entry (FTS handles new.summary being NULL as a no-op for insertion)
            INSERT INTO {file_fts_table.name} (rowid, summary)
            VALUES (new.id, new.summary);
        END;
    """
    ),
)
