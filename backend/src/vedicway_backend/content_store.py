from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pwdlib import PasswordHash
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
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.orm.exc import StaleDataError

PASSWORD_HASH = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = PASSWORD_HASH.hash(secrets.token_urlsafe(32))
ADMIN_SESSION_TTL = timedelta(hours=8)
CONTENT_SCHEMA_REVISION = "20260719_01"
CONTENT_SCHEMA_TABLES = {
    "users",
    "admin_sessions",
    "articles",
    "media_assets",
    "consent_records",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160), default="Редактор")
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    sessions: Mapped[list[AdminSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(240), default="")
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(120), default="Основы астрологии")
    excerpt: Mapped[str] = mapped_column(String(500), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    cover_media_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    body_media_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_image_alt: Mapped[str] = mapped_column(String(300), default="")
    seo_title: Mapped[str] = mapped_column(String(180), default="")
    meta_description: Mapped[str] = mapped_column(String(320), default="")
    focus_keyphrase: Mapped[str] = mapped_column(String(180), default="")
    canonical_url: Mapped[str] = mapped_column(String(500), default="")
    author_name: Mapped[str] = mapped_column(String(160), default="Редакция VedicWay")
    author_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
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
    uploaded_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
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
        self.url = database_url or os.environ.get("VEDICWAY_DATABASE_URL") or self._default_url()
        engine_options: dict[str, Any] = {"pool_pre_ping": True}
        if self.url.startswith("sqlite"):
            engine_options["connect_args"] = {"check_same_thread": False}
        self.engine: Engine = create_engine(self.url, **engine_options)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    @staticmethod
    def _default_url() -> str:
        data_dir = Path(os.environ.get("VEDICWAY_DATA_DIR", Path.cwd() / ".data"))
        data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(data_dir / 'content.sqlite3').as_posix()}"

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

    def bootstrap_admin_from_environment(self) -> bool:
        email = os.environ.get("VEDICWAY_BOOTSTRAP_ADMIN_EMAIL", "").strip().casefold()
        password = os.environ.get("VEDICWAY_BOOTSTRAP_ADMIN_PASSWORD", "")
        if not email and not password:
            return False
        if not email or not password:
            raise RuntimeError(
                "Both VEDICWAY_BOOTSTRAP_ADMIN_EMAIL and VEDICWAY_BOOTSTRAP_ADMIN_PASSWORD are required"
            )
        minimum = 16 if os.environ.get("VEDICWAY_ENV") == "production" else 12
        if len(password) < minimum:
            raise RuntimeError(
                f"Bootstrap admin password must contain at least {minimum} characters"
            )
        with self.session() as database:
            existing = database.scalar(select(User).where(User.email == email))
            if existing:
                if existing.role != "admin" or not existing.is_active:
                    raise RuntimeError("Bootstrap email belongs to a non-admin or disabled account")
                return False
            database.add(
                User(
                    email=email,
                    display_name=os.environ.get(
                        "VEDICWAY_BOOTSTRAP_ADMIN_NAME", "Администратор"
                    ).strip()
                    or "Администратор",
                    password_hash=PASSWORD_HASH.hash(password),
                    role="admin",
                )
            )
        return True

    def authenticate(self, email: str, password: str) -> User | None:
        with self.session() as database:
            user = database.scalar(select(User).where(User.email == email.strip().casefold()))
            verified, updated_hash = PASSWORD_HASH.verify_and_update(
                password,
                user.password_hash if user else DUMMY_PASSWORD_HASH,
            )
            if not user or not user.is_active or not verified:
                return None
            if updated_hash:
                user.password_hash = updated_hash
            return user

    def create_admin_session(
        self, user: User, user_agent: str | None, ip: str | None
    ) -> tuple[str, str]:
        session_token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(36)
        with self.session() as database:
            database.add(
                AdminSession(
                    user_id=user.id,
                    session_token_hash=token_hash(session_token),
                    csrf_token_hash=token_hash(csrf_token),
                    expires_at=utc_now() + ADMIN_SESSION_TTL,
                    user_agent_hash=token_hash(user_agent) if user_agent else None,
                    ip_hash=token_hash(ip) if ip else None,
                )
            )
        return session_token, csrf_token

    def resolve_admin_session(self, session_token: str | None) -> tuple[AdminSession, User] | None:
        if not session_token:
            return None
        with self.session() as database:
            session = database.scalar(
                select(AdminSession).where(
                    AdminSession.session_token_hash == token_hash(session_token)
                )
            )
            if not session or self._aware(session.expires_at) <= utc_now():
                if session:
                    database.delete(session)
                return None
            user = database.get(User, session.user_id)
            if not user or not user.is_active:
                return None
            session.last_seen_at = utc_now()
            return session, user

    def revoke_admin_session(self, session_token: str | None) -> None:
        if not session_token:
            return
        with self.session() as database:
            session = database.scalar(
                select(AdminSession).where(
                    AdminSession.session_token_hash == token_hash(session_token)
                )
            )
            if session:
                database.delete(session)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    def list_articles(self, include_drafts: bool) -> list[Article]:
        with self.session() as database:
            query = select(Article)
            if not include_drafts:
                query = query.where(Article.status == "published")
            query = query.order_by(Article.published_at.desc(), Article.updated_at.desc())
            return list(database.scalars(query))

    def get_article(self, article_id: str) -> Article | None:
        with self.session() as database:
            return database.get(Article, article_id)

    def get_published_article_by_slug(self, slug: str) -> Article | None:
        with self.session() as database:
            return database.scalar(
                select(Article).where(Article.slug == slug, Article.status == "published")
            )

    def slug_exists(self, slug: str, except_id: str | None = None) -> bool:
        with self.session() as database:
            query = select(Article.id).where(Article.slug == slug)
            if except_id:
                query = query.where(Article.id != except_id)
            return database.scalar(query) is not None

    def save_article(
        self,
        values: dict[str, Any],
        author_id: str,
        article_id: str | None = None,
        expected_revision: int | None = None,
    ) -> Article:
        with self.session() as database:
            article = database.get(Article, article_id) if article_id else None
            if article is None:
                article = Article(
                    id=article_id or new_id(), slug=values["slug"], author_id=author_id
                )
                database.add(article)
            elif expected_revision is None or article.revision != expected_revision:
                raise ArticleRevisionConflict
            for field in (
                "title",
                "slug",
                "category",
                "excerpt",
                "content",
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
                setattr(article, field, values.get(field))
            article.author_id = author_id
            article.updated_at = utc_now()
            if article.status == "published" and article.published_at is None:
                article.published_at = utc_now()
            try:
                database.flush()
            except StaleDataError as exc:
                raise ArticleRevisionConflict from exc
            database.refresh(article)
            return article

    def delete_article(self, article_id: str) -> bool:
        with self.session() as database:
            article = database.get(Article, article_id)
            if not article:
                return False
            database.delete(article)
            return True

    def add_media(self, values: dict[str, Any], user_id: str) -> MediaAsset:
        with self.session() as database:
            asset = MediaAsset(**values, uploaded_by=user_id)
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
        marker = f"{{{{media:{asset_id}}}}}"
        with self.session() as database:
            asset = database.get(MediaAsset, asset_id)
            if not asset:
                return False
            articles = database.scalars(select(Article)).all()
            return any(
                article.cover_media_id == asset_id
                or asset_id in (article.body_media_ids or [])
                or marker in article.content
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
        subject_hash = token_hash(subject_reference)
        with self.session() as database:
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
                    ip_hash=token_hash(ip) if ip else None,
                    user_agent_hash=token_hash(user_agent) if user_agent else None,
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
        )
        if not os.environ.get(name, "").strip()
    ]
    errors = [f"missing:{name}" for name in missing]
    if not database.url.startswith(("postgresql://", "postgresql+psycopg://")):
        errors.append("database:postgresql_required")
    if os.environ.get("VEDICWAY_RUNTIME_PROFILE") != "single-node-sqlite":
        errors.append("runtime:single_node_profile_required")
    if os.environ.get("VEDICWAY_BOOTSTRAP_ADMIN_PASSWORD"):
        errors.append("security:bootstrap_admin_secret_must_be_removed")
    return errors
