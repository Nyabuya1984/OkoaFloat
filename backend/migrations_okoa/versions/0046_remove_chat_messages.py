"""Remove employee chat messages."""

from alembic import op
import sqlalchemy as sa


revision = "0046_remove_chat_messages"
down_revision = "0045_dev_plaintext_only"
branch_labels = None
depends_on = None


def upgrade():
    if "chat_messages" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("chat_messages")


def downgrade():
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
    )