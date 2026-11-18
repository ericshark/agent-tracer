"""Add browser sessions and give legacy share links a bounded expiry."""

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision = "9c6d0139c8ef"
down_revision = "87e42d38c899"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "browser_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_browser_sessions_user_id", "browser_sessions", ["user_id"])
    op.create_index("ix_browser_sessions_expires_at", "browser_sessions", ["expires_at"])
    shares = sa.table("share_links", sa.column("expires_at", sa.DateTime(timezone=True)))
    cap = datetime.now(UTC) + timedelta(days=7)
    op.execute(
        shares.update()
        .where(shares.c.expires_at.is_(None) | (shares.c.expires_at > cap))
        .values(expires_at=cap)
    )


def downgrade() -> None:
    # Previously capped links retain their expiration.
    op.drop_table("browser_sessions")
