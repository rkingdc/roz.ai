from datetime import datetime, timezone # Use timezone-aware UTC
from app import db # Import the db instance from app/__init__.py
import os

# DEFAULT_MODEL = os.environ.get('DEFAULT_MODEL', 'gemini-1.5-flash') # Remove redundant definition

# Helper function for default timestamps
def default_utcnow():
    return datetime.now(timezone.utc)

class Chat(db.Model):
    __tablename__ = 'chats'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, default='New Chat') # Added length
    # Default model should be handled by application logic/config when creating a chat
    model_name = db.Column(db.String(100), nullable=False) # Added length, removed default
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=default_utcnow) # Ensure timezone=True
    last_updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=default_utcnow, onupdate=default_utcnow) # Ensure timezone=True
    messages = db.relationship('Message', back_populates='chat', lazy=True, cascade="all, delete-orphan") # Use back_populates

    # Remove explicit index, Alembic handles based on model definition + naming convention
    # __table_args__ = (db.Index('idx_chats_last_updated', last_updated_at.desc()),)


class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chats.id', ondelete='CASCADE'), nullable=False, index=True) # Added index=True
    role = db.Column(db.String(20), nullable=False) # 'user' or 'assistant', added length
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=default_utcnow, index=True) # Added index=True, timezone=True

    # Define relationship back to Chat
    chat = db.relationship('Chat', back_populates='messages') # Use back_populates

    # Remove explicit __table_args__ for indexes, use index=True on columns


class File(db.Model):
    __tablename__ = 'files'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False, index=True) # Added length, index=True
    content = db.Column(db.LargeBinary, nullable=False) # Use LargeBinary for BLOB
    mimetype = db.Column(db.String(100), nullable=False) # Added length
    filesize = db.Column(db.Integer, nullable=False)
    summary = db.Column(db.Text, nullable=True)
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=default_utcnow, index=True) # Added index=True, timezone=True

    # Remove explicit __table_args__ for indexes, use index=True on columns


class Note(db.Model):
    __tablename__ = 'notes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, default='New Note') # Added length
    content = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=default_utcnow) # Ensure timezone=True
    last_saved_at = db.Column(db.DateTime(timezone=True), nullable=False, default=default_utcnow, onupdate=default_utcnow, index=True) # Added index=True, timezone=True

    # Remove explicit __table_args__ for index, use index=True on column
