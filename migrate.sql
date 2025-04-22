-- Migration script to convert from the user-provided schema
-- to the schema defined in the 'sqlite_schema_sql' artifact.

-- It's highly recommended to back up your database before running this script.

BEGIN TRANSACTION;

-- Disable foreign keys temporarily to allow table restructuring.
PRAGMA foreign_keys=off;

-- ==================================================================
-- Migrate 'uploaded_files' table to 'files' table
-- ==================================================================

-- 1. Rename the existing 'uploaded_files' table to avoid conflicts.
ALTER TABLE uploaded_files RENAME TO files_old;

-- 2. Create the new 'files' table according to the target schema.
--    (Using the definition from 'sqlite_schema_sql')
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    mimetype TEXT NOT NULL,
    filesize INTEGER NOT NULL,
    content BLOB NOT NULL,
    uploaded_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')), -- Column name from target schema
    summary TEXT
);

-- 3. Copy data from the old table ('files_old') to the new 'files' table.
--    Ensure column names match between SELECT and INSERT INTO.
INSERT INTO files (id, filename, mimetype, filesize, content, uploaded_at, summary)
SELECT id, filename, mimetype, filesize, content, uploaded_at, summary
FROM files_old;

-- 4. Drop the old temporary table.
DROP TABLE files_old;

-- 5. Recreate the index on the new 'files' table.
--    Drop the old index first (it pointed to 'uploaded_files').
DROP INDEX IF EXISTS idx_files_filename;
CREATE INDEX IF NOT EXISTS idx_files_filename ON files (filename);


-- ==================================================================
-- Migrate 'messages' table to add CHECK constraint and ON DELETE CASCADE
-- ==================================================================

-- 1. Rename the existing 'messages' table.
ALTER TABLE messages RENAME TO messages_old;

-- 2. Drop the old index (it references the old table).
DROP INDEX IF EXISTS idx_messages_chat_id;

-- 3. Create the new 'messages' table according to the target schema.
--    (Including CHECK constraint and ON DELETE CASCADE)
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')), -- Added CHECK constraint
    content TEXT NOT NULL,
    timestamp TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE -- Added ON DELETE CASCADE
);

-- 4. Copy data from the old 'messages_old' table to the new 'messages' table.
INSERT INTO messages (id, chat_id, role, content, timestamp)
SELECT id, chat_id, role, content, timestamp
FROM messages_old;

-- 5. Drop the old temporary table.
DROP TABLE messages_old;

-- 6. Recreate the index on the new 'messages' table.
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id);


-- ==================================================================
-- Create the 'update_chat_timestamp' trigger (if it doesn't exist)
-- ==================================================================
-- This trigger ensures the 'last_updated_at' field in 'chats' is updated
-- when a new message is inserted.
CREATE TRIGGER IF NOT EXISTS update_chat_timestamp AFTER INSERT ON messages
BEGIN
    UPDATE chats
    SET last_updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now') -- Use the correct column name and format
    WHERE id = NEW.chat_id;
END;


-- Re-enable foreign key constraints.
PRAGMA foreign_keys=on;

-- Commit the transaction.
COMMIT;

