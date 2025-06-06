"""Create initial tables

Revision ID: b39695d5f072
Revises: 
Create Date: 2025-04-22 15:57:07.503766

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b39695d5f072'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('chats',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('model_name', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_chats'))
    )
    op.create_table('files',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content', sa.LargeBinary(), nullable=False),
    sa.Column('mimetype', sa.String(length=100), nullable=False),
    sa.Column('filesize', sa.Integer(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_files'))
    )
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_files_filename'), ['filename'], unique=False)
        batch_op.create_index(batch_op.f('ix_files_uploaded_at'), ['uploaded_at'], unique=False)

    op.create_table('notes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_saved_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notes'))
    )
    with op.batch_alter_table('notes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notes_last_saved_at'), ['last_saved_at'], unique=False)

    op.create_table('messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('chat_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], name=op.f('fk_messages_chat_id_chats'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_messages_chat_id'), ['chat_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_messages_timestamp'), ['timestamp'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_messages_timestamp'))
        batch_op.drop_index(batch_op.f('ix_messages_chat_id'))

    op.drop_table('messages')
    with op.batch_alter_table('notes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notes_last_saved_at'))

    op.drop_table('notes')
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_files_uploaded_at'))
        batch_op.drop_index(batch_op.f('ix_files_filename'))

    op.drop_table('files')
    op.drop_table('chats')
    # ### end Alembic commands ###
