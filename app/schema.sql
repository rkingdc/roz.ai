-- Drop tables if they exist to allow re-initialization
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS chats;
DROP TABLE IF EXISTS files;
-- Add drop for the new notes table
DROP TABLE IF EXISTS notes;

-- Create the chats table
CREATE TABLE chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- Changed to INTEGER PRIMARY KEY AUTOINCREMENT
    name TEXT NOT NULL DEFAULT 'New Chat',
    model_name TEXT NOT NULL DEFAULT 'gemini-1.5-flash-latest', -- Default model name
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Changed to DATETIME
    last_updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP -- Changed to DATETIME
);

-- Create the messages table
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL, -- Changed to INTEGER
    role TEXT NOT NULL, -- 'user' or 'assistant'
    content TEXT NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Changed to DATETIME
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
);

-- Create the files table
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- Changed to INTEGER PRIMARY KEY AUTOINCREMENT
    filename TEXT NOT NULL,
    content BLOB NOT NULL, -- Store file content as BLOB
    mimetype TEXT NOT NULL,
    filesize INTEGER NOT NULL,
    summary TEXT,
    uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP -- Changed to DATETIME
);

-- Create the notes table
-- We'll use a single row with a fixed ID (e.g., 1) for a single global note
CREATE TABLE notes (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), -- Enforce single row with ID 1
    content TEXT NOT NULL DEFAULT '',
    last_saved_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Insert the initial single row for notes if it doesn't exist
INSERT OR IGNORE INTO notes (id, content, last_saved_at) VALUES (1, '', CURRENT_TIMESTAMP);
