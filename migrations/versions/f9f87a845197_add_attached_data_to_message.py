"""add_attached_data_to_message

Revision ID: f9f87a845197
Revises: ea9779eb17cf
Create Date: 2025-05-07 19:40:51.295653

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9f87a845197'
down_revision = 'ea9779eb17cf'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('attached_data', sa.JSON(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('attached_data')

    # ### end Alembic commands ###
