"""
SQLAlchemy models mapping to db/schema.sql. Only KB-relevant tables are modeled here
per the current build scope — RFP-agent tables exist in the schema for the production
design but aren't used by this module yet.
"""

import uuid
from sqlalchemy import (
    Column, String, Integer, Boolean, ForeignKey, Text, TIMESTAMP, BigInteger,
    UniqueConstraint, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from app.core.db import Base


def gen_uuid():
    return str(uuid.uuid4())


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    role = relationship("Role")


class Folder(Base):
    __tablename__ = "folders"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    folder_type = Column(String, nullable=False)  # 'kb_persona' or 'rfp'
    owner_role_id = Column(Integer, ForeignKey("roles.id"))
    archived = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class TagTaxonomy(Base):
    __tablename__ = "tag_taxonomy"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    folder_id = Column(UUID(as_uuid=False), ForeignKey("folders.id", ondelete="CASCADE"))
    tag_key = Column(String, nullable=False)
    allowed_values = Column(ARRAY(String), nullable=True)
    required = Column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("folder_id", "tag_key"),)


class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    folder_id = Column(UUID(as_uuid=False), ForeignKey("folders.id", ondelete="CASCADE"))
    display_name = Column(String, nullable=False)
    doctype = Column(String)
    current_version_id = Column(UUID(as_uuid=False), ForeignKey("document_versions.id", use_alter=True))
    status = Column(String, default="active")  # active | deleted
    created_by = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"))
    version_number = Column(Integer, nullable=False)
    storage_key = Column(String, nullable=False)
    file_type = Column(String)
    file_size_bytes = Column(BigInteger)
    content_sha256 = Column(String, nullable=False)
    content_simhash = Column(BigInteger)
    uploaded_by = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    change_note = Column(Text)
    uploaded_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("document_id", "version_number"),)


class DocumentTag(Base):
    __tablename__ = "document_tags"
    document_version_id = Column(UUID(as_uuid=False), ForeignKey("document_versions.id", ondelete="CASCADE"), primary_key=True)
    tag_key = Column(String, primary_key=True)
    tag_value = Column(String, nullable=False)


class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_version_id = Column(UUID(as_uuid=False), ForeignKey("document_versions.id", ondelete="CASCADE"))
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(Vector(1024))
    doc_metadata = Column("metadata", JSONB)


class DocumentCentroid(Base):
    __tablename__ = "document_centroids"
    document_version_id = Column(UUID(as_uuid=False), ForeignKey("document_versions.id", ondelete="CASCADE"), primary_key=True)
    centroid = Column(Vector(1024))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String)
    ip_address = Column(String)
    details = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class ChangeHistory(Base):
    __tablename__ = "change_history"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    field_name = Column(String, nullable=False)
    old_value = Column(Text)
    new_value = Column(Text)
    changed_by = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    changed_by_type = Column(String, nullable=False)  # user | ai | system
    changed_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
