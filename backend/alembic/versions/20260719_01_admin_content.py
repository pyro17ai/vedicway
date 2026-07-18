"""Admin authentication, articles, media and consent audit.

Revision ID: 20260719_01
Revises:
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260719_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("session_token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent_hash", sa.String(64)),
        sa.Column("ip_hash", sa.String(64)),
        sa.UniqueConstraint("session_token_hash", name="uq_admin_sessions_token_hash"),
    )
    op.create_index(
        "ix_admin_sessions_token", "admin_sessions", ["session_token_hash"], unique=True
    )
    op.create_index("ix_admin_sessions_user", "admin_sessions", ["user_id"])
    op.create_index("ix_admin_sessions_expiry", "admin_sessions", ["expires_at"])

    op.create_table(
        "articles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("excerpt", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("cover_media_id", sa.String(36)),
        sa.Column("body_media_ids", sa.JSON(), nullable=False),
        sa.Column("cover_image_url", sa.String(500)),
        sa.Column("cover_image_alt", sa.String(300), nullable=False),
        sa.Column("seo_title", sa.String(180), nullable=False),
        sa.Column("meta_description", sa.String(320), nullable=False),
        sa.Column("focus_keyphrase", sa.String(180), nullable=False),
        sa.Column("canonical_url", sa.String(500), nullable=False),
        sa.Column("author_name", sa.String(160), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_articles_status"),
        sa.UniqueConstraint("slug", name="uq_articles_slug"),
    )
    op.create_index("ix_articles_slug", "articles", ["slug"], unique=True)
    op.create_index("ix_articles_status", "articles", ["status"])
    op.create_index("ix_articles_published", "articles", ["published_at"])
    op.create_index("ix_articles_cover_media", "articles", ["cover_media_id"])

    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("public_url", sa.String(500), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("alt_text", sa.String(300), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("caption", sa.String(500), nullable=False),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("storage_key", name="uq_media_storage_key"),
    )
    op.create_index("ix_media_storage_key", "media_assets", ["storage_key"], unique=True)

    op.create_table(
        "consent_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject_reference_hash", sa.String(64), nullable=False),
        sa.Column("chart_id", sa.String(80)),
        sa.Column("consent_type", sa.String(60), nullable=False),
        sa.Column("document_version", sa.String(40), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("data_categories", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("user_agent_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "subject_reference_hash",
            "chart_id",
            "consent_type",
            "document_version",
            name="uq_consent_record_version",
        ),
    )
    op.create_index("ix_consent_subject", "consent_records", ["subject_reference_hash"])
    op.create_index("ix_consent_chart", "consent_records", ["chart_id"])
    op.create_index("ix_consent_type", "consent_records", ["consent_type"])
    op.create_index("ix_consent_created", "consent_records", ["created_at"])


def downgrade() -> None:
    op.drop_table("consent_records")
    op.drop_table("media_assets")
    op.drop_table("articles")
    op.drop_table("admin_sessions")
    op.drop_table("users")
