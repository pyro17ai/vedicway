from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    defer,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.orm.exc import StaleDataError

from .legal_config import INTERPRETATION_PROCESSOR_ENV, interpretation_processor_config

CONTENT_SCHEMA_REVISION = "20260728_01"
CONTENT_SCHEMA_TABLES = {
    "articles",
    "article_comments",
    "media_assets",
    "consent_records",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


def fingerprint_hash(value: str, purpose: str) -> str:
    """Hash low-entropy personal data with a server secret and domain separation."""
    configured = os.environ.get("VEDICWAY_PRIVACY_PEPPER") or os.environ.get("VEDICWAY_SIGNING_KEY")
    production = os.environ.get("VEDICWAY_ENV", "development").casefold() == "production"
    if not configured:
        if production:
            raise RuntimeError(
                "VEDICWAY_SIGNING_KEY or VEDICWAY_PRIVACY_PEPPER is required for fingerprints"
            )
        configured = "vedicway-development-only-fingerprint-pepper"
    if production and len(configured.encode()) < 32:
        raise RuntimeError("Fingerprint secret must contain at least 32 bytes in production")
    message = f"{purpose}\0{value}".encode()
    return hmac.new(configured.encode(), message, hashlib.sha256).hexdigest()


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("section", "slug", name="uq_articles_section_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(240), default="")
    slug: Mapped[str] = mapped_column(String(120), index=True)
    section: Mapped[str] = mapped_column(String(20), default="guide", index=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner", index=True)
    category: Mapped[str] = mapped_column(String(120), default="Основы астрологии")
    excerpt: Mapped[str] = mapped_column(String(500), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    content_format: Mapped[str] = mapped_column(String(30), default="html.v1")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    schema_extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cover_media_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    body_media_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_image_alt: Mapped[str] = mapped_column(String(300), default="")
    seo_title: Mapped[str] = mapped_column(String(180), default="")
    meta_description: Mapped[str] = mapped_column(String(320), default="")
    focus_keyphrase: Mapped[str] = mapped_column(String(180), default="")
    canonical_url: Mapped[str] = mapped_column(String(500), default="")
    author_name: Mapped[str] = mapped_column(String(160), default="Редакция VedicWay")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": revision}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    comments: Mapped[list[ArticleComment]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class ArticleComment(Base):
    __tablename__ = "article_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    article_id: Mapped[str] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(String(3000))
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

    article: Mapped[Article] = relationship(back_populates="comments")


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    public_url: Mapped[str] = mapped_column(String(500))
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    purpose: Mapped[str] = mapped_column(String(20))
    mime_type: Mapped[str] = mapped_column(String(100))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    alt_text: Mapped[str] = mapped_column(String(300), default="")
    title: Mapped[str] = mapped_column(String(240), default="")
    caption: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    __table_args__ = (
        UniqueConstraint(
            "subject_reference_hash",
            "chart_id",
            "consent_type",
            "document_version",
            name="uq_consent_record_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    subject_reference_hash: Mapped[str] = mapped_column(String(64), index=True)
    chart_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    consent_type: Mapped[str] = mapped_column(String(60), index=True)
    document_version: Mapped[str] = mapped_column(String(40))
    granted: Mapped[bool] = mapped_column(Boolean)
    data_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(40), default="web")
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class ArticleRevisionConflict(RuntimeError):
    pass


class ContentDatabase:
    def __init__(self, database_url: str | None = None) -> None:
        configured_url = (
            database_url
            or os.environ.get("VEDICWAY_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
        )
        if not configured_url:
            raise RuntimeError("VEDICWAY_DATABASE_URL is required")
        if not configured_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("VEDICWAY_DATABASE_URL must use PostgreSQL")
        self.url = configured_url.replace("postgresql://", "postgresql+psycopg://", 1)
        self.engine: Engine = create_engine(self.url, pool_pre_ping=True)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        if os.environ.get("VEDICWAY_ENV", "development").casefold() != "production":
            Base.metadata.create_all(self.engine)

    def ping(self, *, require_migrations: bool = False) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            if not require_migrations:
                return
            tables = set(inspect(connection).get_table_names())
            missing = CONTENT_SCHEMA_TABLES - tables
            if missing or "alembic_version" not in tables:
                raise RuntimeError(f"Content schema is incomplete: {', '.join(sorted(missing))}")
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != CONTENT_SCHEMA_REVISION:
                raise RuntimeError(
                    f"Content schema revision {revision!r} does not match {CONTENT_SCHEMA_REVISION}"
                )

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._sessions() as database:
            try:
                yield database
                database.commit()
            except Exception:
                database.rollback()
                raise

    def list_articles(
        self,
        include_drafts: bool,
        *,
        section: str | None = None,
        include_content: bool = False,
    ) -> list[Article]:
        with self.session() as database:
            query = select(Article)
            if not include_content:
                query = query.options(defer(Article.content))
            if not include_drafts:
                query = query.where(Article.status == "published")
            if section:
                query = query.where(Article.section == section)
            query = query.order_by(Article.published_at.desc(), Article.updated_at.desc())
            return list(database.scalars(query))

    def get_article(self, article_id: str) -> Article | None:
        with self.session() as database:
            return database.get(Article, article_id)

    def get_article_by_slug(self, slug: str) -> Article | None:
        with self.session() as database:
            return database.scalar(select(Article).where(Article.slug == slug))

    def get_published_article_by_slug(self, slug: str) -> Article | None:
        with self.session() as database:
            return database.scalar(
                select(Article).where(Article.slug == slug, Article.status == "published")
            )

    def get_article_by_path(
        self,
        section: str,
        slug: str,
        *,
        published_only: bool = False,
    ) -> Article | None:
        with self.session() as database:
            query = select(Article).where(
                Article.section == section,
                Article.slug == slug,
            )
            if published_only:
                query = query.where(Article.status == "published")
            return database.scalar(query)

    def slug_exists(
        self,
        slug: str,
        except_id: str | None = None,
        *,
        section: str | None = None,
    ) -> bool:
        with self.session() as database:
            query = select(Article.id).where(Article.slug == slug)
            if section:
                query = query.where(Article.section == section)
            if except_id:
                query = query.where(Article.id != except_id)
            return database.scalar(query) is not None

    def save_article(
        self,
        values: dict[str, Any],
        article_id: str | None = None,
        expected_revision: int | None = None,
    ) -> Article:
        with self.session() as database:
            article = database.get(Article, article_id) if article_id else None
            if article is None:
                article = Article(
                    id=article_id or new_id(),
                    slug=values["slug"],
                    section=values.get("section", "guide"),
                )
                database.add(article)
            elif expected_revision is None or article.revision != expected_revision:
                raise ArticleRevisionConflict
            for field in (
                "title",
                "slug",
                "section",
                "difficulty",
                "category",
                "excerpt",
                "content",
                "content_format",
                "tags",
                "schema_extra",
                "cover_media_id",
                "body_media_ids",
                "cover_image_url",
                "cover_image_alt",
                "seo_title",
                "meta_description",
                "focus_keyphrase",
                "canonical_url",
                "author_name",
                "status",
            ):
                if field in values:
                    setattr(article, field, values[field])
            article.updated_at = utc_now()
            if article.status == "published" and article.published_at is None:
                article.published_at = utc_now()
            try:
                database.flush()
            except StaleDataError as exc:
                raise ArticleRevisionConflict from exc
            database.refresh(article)
            return article

    def list_comments(self, article_id: str) -> list[ArticleComment]:
        with self.session() as database:
            query = (
                select(ArticleComment)
                .where(ArticleComment.article_id == article_id)
                .order_by(ArticleComment.created_at.asc(), ArticleComment.id.asc())
            )
            return list(database.scalars(query))

    def add_comment(
        self,
        *,
        article_id: str,
        display_name: str,
        body: str,
        ip: str | None,
        user_agent: str | None,
    ) -> ArticleComment:
        with self.session() as database:
            comment = ArticleComment(
                article_id=article_id,
                display_name=display_name,
                body=body,
                ip_hash=fingerprint_hash(ip, "article-comment-ip") if ip else None,
                user_agent_hash=(
                    fingerprint_hash(user_agent, "article-comment-user-agent")
                    if user_agent
                    else None
                ),
            )
            database.add(comment)
            database.flush()
            database.refresh(comment)
            return comment

    def delete_article(self, article_id: str) -> bool:
        with self.session() as database:
            article = database.get(Article, article_id)
            if not article:
                return False
            database.delete(article)
            return True

    def add_media(self, values: dict[str, Any]) -> MediaAsset:
        with self.session() as database:
            asset = MediaAsset(**values)
            database.add(asset)
            database.flush()
            database.refresh(asset)
            return asset

    def get_media(self, asset_id: str) -> MediaAsset | None:
        with self.session() as database:
            return database.get(MediaAsset, asset_id)

    def list_media(self, asset_ids: list[str]) -> list[MediaAsset]:
        if not asset_ids:
            return []
        with self.session() as database:
            assets = list(database.scalars(select(MediaAsset).where(MediaAsset.id.in_(asset_ids))))
        by_id = {asset.id: asset for asset in assets}
        return [by_id[asset_id] for asset_id in asset_ids if asset_id in by_id]

    def media_in_use(self, asset_id: str) -> bool:
        with self.session() as database:
            asset = database.get(MediaAsset, asset_id)
            if not asset:
                return False
            articles = database.execute(
                select(
                    Article.cover_media_id,
                    Article.body_media_ids,
                    Article.cover_image_url,
                )
            ).all()
            return any(
                article.cover_media_id == asset_id
                or asset_id in (article.body_media_ids or [])
                or article.cover_image_url == asset.public_url
                for article in articles
            )

    def media_is_public(self, asset_id: str, filename: str) -> bool:
        with self.session() as database:
            asset = database.get(MediaAsset, asset_id)
            if not asset:
                return False
            urls = [asset.public_url, *(source.get("url", "") for source in asset.sources or [])]
            allowed_filenames = {
                PurePosixPath(urlsplit(url).path).name
                for url in urls
                if isinstance(url, str) and url
            }
            if filename not in allowed_filenames:
                return False
            articles = database.execute(
                select(
                    Article.cover_media_id,
                    Article.body_media_ids,
                    Article.cover_image_url,
                ).where(Article.status == "published")
            ).all()
            return any(
                article.cover_media_id == asset_id
                or asset_id in (article.body_media_ids or [])
                or article.cover_image_url == asset.public_url
                for article in articles
            )

    def delete_media(self, asset_id: str) -> bool:
        with self.session() as database:
            asset = database.get(MediaAsset, asset_id)
            if not asset:
                return False
            database.delete(asset)
            return True

    def record_consent(
        self,
        subject_reference: str,
        consent_type: str,
        document_version: str,
        granted: bool,
        data_categories: list[str],
        chart_id: str | None,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        subject_hash = fingerprint_hash(subject_reference, "consent-subject")
        with self.session() as database:
            self._add_consent_record(
                database,
                subject_hash=subject_hash,
                consent_type=consent_type,
                document_version=document_version,
                granted=granted,
                data_categories=data_categories,
                chart_id=chart_id,
                ip=ip,
                user_agent=user_agent,
            )

    def record_chart_acceptances(
        self,
        *,
        subject_reference: str,
        chart_id: str,
        personal_data_version: str,
        terms_version: str,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        """Commit the two mandatory chart acceptances in one database transaction."""
        subject_hash = fingerprint_hash(subject_reference, "consent-subject")
        with self.session() as database:
            self._add_consent_record(
                database,
                subject_hash=subject_hash,
                consent_type="personal_data",
                document_version=personal_data_version,
                granted=True,
                data_categories=[
                    "birth_date",
                    "birth_time",
                    "birth_place",
                    "time_accuracy",
                    "technical_session",
                ],
                chart_id=chart_id,
                ip=ip,
                user_agent=user_agent,
            )
            self._add_consent_record(
                database,
                subject_hash=subject_hash,
                consent_type="terms",
                document_version=terms_version,
                granted=True,
                data_categories=[],
                chart_id=chart_id,
                ip=ip,
                user_agent=user_agent,
            )

    @staticmethod
    def _add_consent_record(
        database: Session,
        *,
        subject_hash: str,
        consent_type: str,
        document_version: str,
        granted: bool,
        data_categories: list[str],
        chart_id: str | None,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        existing = database.scalar(
            select(ConsentRecord.id).where(
                ConsentRecord.subject_reference_hash == subject_hash,
                ConsentRecord.chart_id == chart_id,
                ConsentRecord.consent_type == consent_type,
                ConsentRecord.document_version == document_version,
            )
        )
        if existing:
            return
        database.add(
            ConsentRecord(
                subject_reference_hash=subject_hash,
                chart_id=chart_id,
                consent_type=consent_type,
                document_version=document_version,
                granted=granted,
                data_categories=data_categories,
                ip_hash=fingerprint_hash(ip, "consent-ip") if ip else None,
                user_agent_hash=(
                    fingerprint_hash(user_agent, "consent-user-agent") if user_agent else None
                ),
            )
        )


def production_configuration_errors(database: ContentDatabase) -> list[str]:
    if os.environ.get("VEDICWAY_ENV", "development").casefold() != "production":
        return []
    missing = [
        name
        for name in (
            "VEDICWAY_LEGAL_OPERATOR_NAME",
            "VEDICWAY_LEGAL_OPERATOR_ADDRESS",
            "VEDICWAY_LEGAL_OPERATOR_INN",
            "VEDICWAY_LEGAL_OPERATOR_OGRN",
            "VEDICWAY_PRIVACY_EMAIL",
            "VEDICWAY_PUBLIC_ORIGIN",
            "VEDICWAY_DATA_DIR",
            "VEDICWAY_MEDIA_DIR",
            "VEDICWAY_SIGNING_KEY",
            "VEDICWAY_SEO_AGENT_TOKEN",
        )
        if not os.environ.get(name, "").strip()
    ]
    errors = [f"missing:{name}" for name in missing]
    if os.environ.get("VEDICWAY_INTERPRETATION_PROVIDER", "").strip().casefold() == "codex":
        processor = interpretation_processor_config()
        for name in INTERPRETATION_PROCESSOR_ENV:
            if not os.environ.get(name, "").strip():
                errors.append(f"missing:{name}")
        if not bool(processor["configured"]):
            errors.append("legal:interpretation_processor_configuration_required")
        if os.environ.get("VEDICWAY_INTERPRETATION_PROCESSOR_CROSS_BORDER", "").strip() not in {
            "0",
            "1",
        }:
            errors.append("invalid:VEDICWAY_INTERPRETATION_PROCESSOR_CROSS_BORDER")
    fingerprint_secret = os.environ.get("VEDICWAY_PRIVACY_PEPPER") or os.environ.get(
        "VEDICWAY_SIGNING_KEY", ""
    )
    if fingerprint_secret and len(fingerprint_secret.encode()) < 32:
        errors.append("security:fingerprint_secret_too_short")
    if not database.url.startswith(("postgresql://", "postgresql+psycopg://")):
        errors.append("database:postgresql_required")
    return errors
