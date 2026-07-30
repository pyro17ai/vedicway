"""Codex HTML gate, blog, difficulty and public comments.

Revision ID: 20260728_01
Revises: 20260719_01
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260728_01"
down_revision: str | None = "20260719_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQLITE_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade() -> None:
    with op.batch_alter_table(
        "articles",
        naming_convention=SQLITE_NAMING_CONVENTION,
    ) as batch:
        batch.add_column(
            sa.Column(
                "section",
                sa.String(20),
                nullable=False,
                server_default="guide",
            )
        )
        batch.add_column(
            sa.Column(
                "difficulty",
                sa.String(20),
                nullable=False,
                server_default="beginner",
            )
        )
        batch.add_column(
            sa.Column(
                "content_format",
                sa.String(30),
                nullable=False,
                server_default="html.v1",
            )
        )
        batch.add_column(sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(
            sa.Column(
                "schema_extra",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            )
        )
        batch.create_check_constraint(
            "ck_articles_section",
            "section IN ('guide', 'blog')",
        )
        batch.create_check_constraint(
            "ck_articles_difficulty",
            "difficulty IN ('beginner', 'expert')",
        )
        batch.create_index("ix_articles_section", ["section"])
        batch.create_index("ix_articles_difficulty", ["difficulty"])
        batch.drop_index("ix_articles_slug")
        batch.drop_constraint("uq_articles_slug", type_="unique")
        batch.create_index("ix_articles_slug", ["slug"])
        batch.create_unique_constraint(
            "uq_articles_section_slug",
            ["section", "slug"],
        )
        batch.drop_column("author_id")

    with op.batch_alter_table(
        "media_assets",
        naming_convention=SQLITE_NAMING_CONVENTION,
    ) as batch:
        batch.drop_column("uploaded_by")

    op.create_table(
        "article_comments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "article_id",
            sa.String(36),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("body", sa.String(3000), nullable=False),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("user_agent_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_article_comments_article_id",
        "article_comments",
        ["article_id"],
    )
    op.create_index(
        "ix_article_comments_created_at",
        "article_comments",
        ["created_at"],
    )

    op.drop_table("admin_sessions")
    op.drop_table("users")


def downgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'user')", name="ck_users_role"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent_hash", sa.String(64)),
        sa.Column("ip_hash", sa.String(64)),
        sa.UniqueConstraint(
            "session_token_hash",
            name="uq_admin_sessions_token_hash",
        ),
    )
    op.create_index(
        "ix_admin_sessions_token",
        "admin_sessions",
        ["session_token_hash"],
        unique=True,
    )
    op.create_index("ix_admin_sessions_user", "admin_sessions", ["user_id"])
    op.create_index("ix_admin_sessions_expiry", "admin_sessions", ["expires_at"])

    with op.batch_alter_table(
        "articles",
        naming_convention=SQLITE_NAMING_CONVENTION,
    ) as batch:
        batch.add_column(sa.Column("author_id", sa.String(36)))
        batch.create_foreign_key(
            "articles_author_id_fkey",
            "users",
            ["author_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.drop_constraint("uq_articles_section_slug", type_="unique")
        batch.drop_index("ix_articles_slug")
        batch.create_index("ix_articles_slug", ["slug"], unique=True)
        batch.create_unique_constraint("uq_articles_slug", ["slug"])
        batch.drop_index("ix_articles_difficulty")
        batch.drop_index("ix_articles_section")
        batch.drop_constraint("ck_articles_difficulty", type_="check")
        batch.drop_constraint("ck_articles_section", type_="check")
        batch.drop_column("schema_extra")
        batch.drop_column("tags")
        batch.drop_column("content_format")
        batch.drop_column("difficulty")
        batch.drop_column("section")

    with op.batch_alter_table(
        "media_assets",
        naming_convention=SQLITE_NAMING_CONVENTION,
    ) as batch:
        batch.add_column(sa.Column("uploaded_by", sa.String(36)))
        batch.create_foreign_key(
            "media_assets_uploaded_by_fkey",
            "users",
            ["uploaded_by"],
            ["id"],
            ondelete="SET NULL",
        )

    op.drop_table("article_comments")
