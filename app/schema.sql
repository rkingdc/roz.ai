-- Drop tables if they exist to allow re-initialization
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS chats;
DROP TABLE IF EXISTS files;

-- Create the chats table
CREATE TABLE chats (
    id TEXT PRIMARY KEY UNIQUE NOT NULL, -- Using TEXT for UUIDs
    name TEXT NOT NULL DEFAULT 'New Chat',
    model_name TEXT NOT NULL DEFAULT 'gemini-1.5-flash-latest', -- Default model name
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    last_updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now'))
);

-- Create the messages table
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    role TEXT NOT NULL, -- 'user' or 'assistant'
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
);

-- Create the files table
CREATE TABLE files (
    id TEXT PRIMARY KEY UNIQUE NOT NULL, -- Using TEXT for UUIDs
    filename TEXT NOT NULL,
    content BLOB NOT NULL, -- Store file content as BLOB
    mimetype TEXT NOT NULL,
    filesize INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    summary TEXT -- Optional summary field
);
