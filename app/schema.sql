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
-- Modified to allow multiple notes
CREATE TABLE notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- Allow multiple notes with auto-incrementing ID
    name TEXT NOT NULL DEFAULT 'New Note', -- Add a name field for notes
    content TEXT NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Add creation timestamp
    last_saved_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- No initial insert needed for multiple notes, they will be created via the UI
