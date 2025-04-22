from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData
import os # Import os for default model name

# Define naming conventions for constraints to ensure Alembic generates
# consistent migration scripts, especially for SQLite.
# See: https://flask-sqlalchemy.palletsprojects.com/en/3.1.x/config/#using-custom-metadata-and-naming-conventions
metadata = MetaData(naming_convention={
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
})

# Initialize SQLAlchemy with the custom metadata
# We will initialize it properly with the app in __init__.py
# This db object will be imported by other modules.
db = SQLAlchemy(metadata=metadata)

# Get default model from environment or use a fallback
DEFAULT_MODEL = os.environ.get('DEFAULT_MODEL', 'gemini-1.5-flash')

class Chat(db.Model):
    __tablename__ = 'chats'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False, default='New Chat')
    # Use the DEFAULT_MODEL variable for the default value
    model_name = db.Column(db.String, nullable=False, default=DEFAULT_MODEL)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = db.relationship('Message', backref='chat', lazy=True, cascade="all, delete-orphan")

    # Add index matching schema.sql
    __table_args__ = (db.Index('idx_chats_last_updated', last_updated_at.desc()),)


class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chats.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(db.String, nullable=False) # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Add indexes matching schema.sql
    __table_args__ = (
        db.Index('idx_messages_chat_id', chat_id),
        db.Index('idx_messages_timestamp', timestamp.asc()),
    )


class File(db.Model):
    __tablename__ = 'files'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String, nullable=False)
    content = db.Column(db.LargeBinary, nullable=False) # Use LargeBinary for BLOB
    mimetype = db.Column(db.String, nullable=False)
    filesize = db.Column(db.Integer, nullable=False)
    summary = db.Column(db.Text, nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Add indexes matching schema.sql
    __table_args__ = (
        db.Index('idx_files_filename', filename),
        db.Index('idx_files_uploaded_at', uploaded_at.desc()),
    )


class Note(db.Model):
    __tablename__ = 'notes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False, default='New Note')
    content = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_saved_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Add index matching schema.sql
    __table_args__ = (db.Index('idx_notes_last_saved', last_saved_at.desc()),)
