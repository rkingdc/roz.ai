"""add_fts_and_triggers

Revision ID: 8a3d29562348
Revises: f9f87a845197
Create Date: 2025-05-08 09:52:51.875710

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a3d29562348'
down_revision = 'f9f87a845197'
branch_labels = None
depends_on = None


def upgrade():
    # ### Create FTS5 Virtual Tables ###

    # Message FTS table
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
            content,
            tokenize=porter,
            content='messages',
            content_rowid='id'
        )
    """)

    # Note FTS table
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5(
            content,
            tokenize=porter,
            content='notes',
            content_rowid='id'
        )
    """)

    # File FTS table (for summaries)
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS file_fts USING fts5(
            summary,
            tokenize=porter,
            content='files',
            content_rowid='id'
        )
    """)

    # ### Triggers to keep FTS tables synchronized ###

    # --- Message FTS Triggers ---
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS messages_ai_trigger
        AFTER INSERT ON messages
        BEGIN
            INSERT INTO message_fts (rowid, content)
            VALUES (new.id, new.content);
        END;
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS messages_ad_trigger
        AFTER DELETE ON messages
        BEGIN
            INSERT INTO message_fts (message_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
        END;
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS messages_au_trigger
        AFTER UPDATE ON messages
        WHEN new.content IS NOT old.content
        BEGIN
            INSERT INTO message_fts (message_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
            INSERT INTO message_fts (rowid, content)
            VALUES (new.id, new.content);
        END;
    """)

    # --- Note FTS Triggers ---
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS notes_ai_trigger
        AFTER INSERT ON notes
        BEGIN
            INSERT INTO note_fts (rowid, content)
            VALUES (new.id, new.content);
        END;
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS notes_ad_trigger
        AFTER DELETE ON notes
        BEGIN
            INSERT INTO note_fts (note_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
        END;
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS notes_au_trigger
        AFTER UPDATE ON notes
        WHEN new.content IS NOT old.content
        BEGIN
            INSERT INTO note_fts (note_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
            INSERT INTO note_fts (rowid, content)
            VALUES (new.id, new.content);
        END;
    """)

    # --- File FTS Triggers (for summary) ---
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS files_ai_trigger
        AFTER INSERT ON files
        WHEN new.summary IS NOT NULL
        BEGIN
            INSERT INTO file_fts (rowid, summary)
            VALUES (new.id, new.summary);
        END;
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS files_ad_trigger
        AFTER DELETE ON files
        WHEN old.summary IS NOT NULL
        BEGIN
            INSERT INTO file_fts (file_fts, rowid, summary)
            VALUES ('delete', old.id, old.summary);
        END;
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS files_au_trigger
        AFTER UPDATE ON files
        WHEN new.summary IS NOT old.summary -- Handles changes to/from NULL
        BEGIN
            -- Delete old entry if old.summary was not NULL
            -- Note: FTS5 handles 'delete' for non-existent rowids gracefully.
            -- However, to be precise, we only attempt delete if old.summary was relevant.
            -- This also handles the case where old.summary was NULL and new.summary is not.
            -- And the case where old.summary was not NULL and new.summary is NULL.
            -- And the case where both old and new summaries are different and not NULL.
            INSERT INTO file_fts (file_fts, rowid, summary)
            VALUES ('delete', old.id, old.summary);
            
            -- Insert new entry if new.summary is not NULL
            -- This condition is important to avoid inserting NULLs or empty strings if not desired.
            -- The trigger condition `WHEN new.summary IS NOT old.summary` already implies
            -- that either new.summary is not NULL, or old.summary was not NULL, or both.
            -- If new.summary is NULL, this insert will effectively do nothing for the new value,
            -- which is correct as we only want non-NULL summaries in FTS.
            INSERT INTO file_fts (rowid, summary)
            VALUES (new.id, new.summary);
        END;
    """)

    # ### Populate FTS tables with existing data ###
    op.execute("""
        INSERT INTO message_fts (rowid, content)
        SELECT id, content FROM messages;
    """)
    op.execute("""
        INSERT INTO note_fts (rowid, content)
        SELECT id, content FROM notes;
    """)
    op.execute("""
        INSERT INTO file_fts (rowid, summary)
        SELECT id, summary FROM files WHERE summary IS NOT NULL;
    """)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###

    # --- Drop File FTS Triggers ---
    op.execute("DROP TRIGGER IF EXISTS files_au_trigger")
    op.execute("DROP TRIGGER IF EXISTS files_ad_trigger")
    op.execute("DROP TRIGGER IF EXISTS files_ai_trigger")

    # --- Drop Note FTS Triggers ---
    op.execute("DROP TRIGGER IF EXISTS notes_au_trigger")
    op.execute("DROP TRIGGER IF EXISTS notes_ad_trigger")
    op.execute("DROP TRIGGER IF EXISTS notes_ai_trigger")

    # --- Drop Message FTS Triggers ---
    op.execute("DROP TRIGGER IF EXISTS messages_au_trigger")
    op.execute("DROP TRIGGER IF EXISTS messages_ad_trigger")
    op.execute("DROP TRIGGER IF EXISTS messages_ai_trigger")

    # --- Drop FTS Tables ---
    op.execute("DROP TABLE IF EXISTS file_fts")
    op.execute("DROP TABLE IF EXISTS note_fts")
    op.execute("DROP TABLE IF EXISTS message_fts")
    # ### end Alembic commands ###
