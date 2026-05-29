import json
from decimal import Decimal

from sqlalchemy import (
    Identity,
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.oracle.base import ischema_names
from sqlalchemy.types import TypeDecorator, UserDefinedType

# Native vector type abstraction provided by newer oracledb dialects
from sqlalchemy.dialects.oracle import VECTOR
from sqlalchemy.dialects.oracle.vector import VectorStorageFormat

from app.config import settings
from app.database import Base


# ─── Oracle native JSON type ───────────────────────────────────────────────────

class OracleJSONDDL(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw):
        return "JSON"


class OracleNativeJSON(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "oracle":
            return dialect.type_descriptor(OracleJSONDDL())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name != "oracle":
            return value

        def decimal_default(obj):
            if isinstance(obj, Decimal):
                if obj % 1 == 0:
                    return int(obj)
                return float(obj)
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

        return json.dumps(value, default=decimal_default, ensure_ascii=False, separators=(",", ":"))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if hasattr(value, "read"):
            value = value.read()
        if isinstance(value, (bytes, bytearray, memoryview)):
            value = bytes(value).decode()
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value


ischema_names["JSON"] = OracleJSONDDL


# ─── Models ───────────────────────────────────────────────────────────────────

class ContractMaster(Base):
    __tablename__ = "contracts_master"

    contract_id = Column(String(50), primary_key=True)
    organization = Column(String(100), nullable=False)
    business_unit = Column(String(100), nullable=False)
    location = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)
    customer_partner_name = Column(String(200), nullable=True)
    financial_year = Column(String(20), nullable=True)
    contract_type = Column(String(100), nullable=False)
    agreement_type = Column(String(100), nullable=False)
    additional_info = Column(Text, nullable=True)

    contract_number = Column(String(120), nullable=True)
    version_amendment_number = Column(String(120), nullable=True)
    execution_type = Column(String(50), nullable=True)
    governing_entity = Column(String(120), nullable=True)
    jurisdiction = Column(String(120), nullable=True)
    governing_law = Column(String(120), nullable=True)
    legal_names_of_parties = Column(Text, nullable=True)
    registered_addresses = Column(Text, nullable=True)
    cin_registration_numbers = Column(Text, nullable=True)
    authorized_signatories = Column(Text, nullable=True)
    contact_persons = Column(Text, nullable=True)
    party_roles = Column(Text, nullable=True)
    affiliates_subsidiaries_involved = Column(Text, nullable=True)
    effective_date = Column(Date, nullable=True)

    uploaded_filename = Column(String(255), nullable=True)
    uploaded_content_type = Column(String(120), nullable=True)

    document_blob = Column(LargeBinary, nullable=True)
    document_text = Column(Text, nullable=True)

    # Updated: Native VECTOR definition for direct 26ai serialization tracking
    document_vector = Column(VECTOR(settings.embedding_vector_dim, storage_format=VectorStorageFormat.INT8), nullable=True)

    workflow_state = Column(
        String(30), default="STAGED_DRAFT", server_default="STAGED_DRAFT", nullable=False
    )
    checked_out_by = Column(String(100), nullable=True)
    checkout_expiry = Column(DateTime(timezone=True), nullable=True)
    document_version = Column(Integer, default=1, server_default="1", nullable=False)
    created_by = Column(String(100), nullable=True)
    approved_by = Column(String(100), nullable=True)

    risk_score = Column(Numeric(precision=5, scale=2), nullable=True)
    risk_level = Column(String(30), nullable=True)
    risk_rationale = Column(Text, nullable=True)
    draft_checkpoint = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now(), server_default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), server_default=func.now())
    last_updated = Column(DateTime, default=func.now(), onupdate=func.now(), server_default=func.now())

    parameters = relationship(
        "ContractParameterExtracted",
        back_populates="contract",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    audits = relationship(
        "ContractAuditTrail",
        back_populates="contract",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    chunks = relationship(
        "ContractDocumentChunk",
        back_populates="contract",
        cascade="all, delete-orphan",
        lazy="noload",  # Never eager-load; queried directly by vector search.
    )
    tag_suggestions = relationship(
        "ContractTagSuggestion",
        back_populates="contract",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ContractParameterExtracted(Base):
    __tablename__ = "contract_parameters_extracted"

    parameter_id = Column(Integer, Identity(start=1), primary_key=True)
    contract_id = Column(
        String(50), ForeignKey("contracts_master.contract_id", ondelete="CASCADE"), nullable=False
    )
    header_name = Column(String(150), nullable=False)
    param_name = Column(String(150), nullable=False)
    original_extract = Column(Text, nullable=True)
    user_override = Column(Text, nullable=True)

    match_score = Column(Numeric(precision=4, scale=3), nullable=True)

    citation_text = Column(Text, nullable=True)
    citation_start = Column(Integer, nullable=True)
    citation_end = Column(Integer, nullable=True)

    spatial_json = Column(OracleNativeJSON(), nullable=True)

    # Updated: Native VECTOR definition for direct 26ai serialization tracking
    vector_embed = Column(VECTOR(settings.embedding_vector_dim, storage_format=VectorStorageFormat.INT8), nullable=True)

    source_query = Column(String(250), nullable=True)
    is_user_added = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_note = Column(Text, nullable=True)
    validation_state = Column(String(30), default="needs_review", server_default="needs_review", nullable=False)
    validation_message = Column(Text, nullable=True)

    # Embedding versioning metadata
    embed_model_name = Column(String(100), nullable=True)
    embed_dimension = Column(Integer, nullable=True)
    embed_quant_type = Column(String(30), nullable=True)
    parser_version = Column(String(50), nullable=True)
    chunking_version = Column(String(50), nullable=True)
    embed_created_at = Column(DateTime, default=func.now(), server_default=func.now())

    last_modified = Column(DateTime, default=func.now(), onupdate=func.now())

    contract = relationship("ContractMaster", back_populates="parameters")


class ContractDocumentChunk(Base):
    """
    Stores paragraph-level text chunks produced by the Layout-Aware Semantic
    Accumulation parser.  Each chunk carries:
      - its global character offsets into ContractMaster.document_text,
      - a spatial_json array of per-line bounding boxes for frontend highlighting,
      - a VECTOR embedding for Oracle 26ai cosine similarity search.
    """
    __tablename__ = "contract_document_chunks"
    __table_args__ = (
        UniqueConstraint("contract_id", "chunk_index", name="uq_chunk_contract_idx"),
    )

    chunk_id    = Column(Integer, Identity(start=1), primary_key=True)
    contract_id = Column(
        String(50), ForeignKey("contracts_master.contract_id", ondelete="CASCADE"), nullable=False
    )
    chunk_index  = Column(Integer, nullable=False)   # 0-based sequential position
    chunk_text   = Column(Text, nullable=False)
    char_start   = Column(Integer, nullable=False)   # global offset in document_text
    char_end     = Column(Integer, nullable=False)

    # List of per-line coordinate arrays: [[page, x0, y0, x1, y1, pw, ph], ...]
    spatial_json = Column(OracleNativeJSON(), nullable=True)

    # Paragraph-level vector for granular RAG retrieval.
    chunk_vector = Column(VECTOR(settings.embedding_vector_dim, storage_format=VectorStorageFormat.INT8), nullable=True)

    # Embedding versioning metadata
    embed_model_name = Column(String(100), nullable=True)
    embed_dimension = Column(Integer, nullable=True)
    embed_quant_type = Column(String(30), nullable=True)
    parser_version = Column(String(50), nullable=True)
    chunking_version = Column(String(50), nullable=True)
    embed_created_at = Column(DateTime, default=func.now(), server_default=func.now())

    contract = relationship("ContractMaster", back_populates="chunks")


class ContractAuditTrail(Base):
    __tablename__ = "contract_audit_trail"

    audit_id = Column(Integer, Identity(start=1), primary_key=True)
    contract_id = Column(
        String(50), ForeignKey("contracts_master.contract_id", ondelete="CASCADE"), nullable=False
    )
    action_type = Column(String(50), nullable=False)
    field_changed = Column(String(150), nullable=True)
    old_value_clob = Column(Text, nullable=True)
    new_value_clob = Column(Text, nullable=True)
    modified_by = Column(String(100), nullable=False)
    logged_timestamp = Column(DateTime, default=func.now(), server_default=func.now())

    contract = relationship("ContractMaster", back_populates="audits")


class MasterExtractionRule(Base):
    __tablename__ = "master_extraction_rules"
    __table_args__ = (
        UniqueConstraint(
            "contract_type",
            "agreement_type",
            "parameter_head",
            "parameter_name",
            name="uq_master_rule_signature",
        ),
    )

    rule_id = Column(Integer, Identity(start=1), primary_key=True)
    contract_type = Column(String(100), nullable=False)
    agreement_type = Column(String(100), nullable=False)
    parameter_head = Column(String(150), nullable=False)
    parameter_name = Column(String(150), nullable=False)
    parameter_logic = Column(String(250), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=func.now(), server_default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class MetadataOption(Base):
    __tablename__ = "metadata_options"
    __table_args__ = (
        UniqueConstraint("category", "value", name="uq_metadata_category_value"),
    )

    option_id = Column(Integer, Identity(start=1), primary_key=True)
    category = Column(String(80), nullable=False, index=True)
    value = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), server_default=func.now())


# ───────────────── Published Tables (approved / trusted corpus) ───────────────────────────────────────────────────────────────────
#
# The published tables are a separate trust zone from the draft tables.
# Presence in these tables IS the publication signal — no workflow_state column.
# There is deliberately no CASCADE DELETE from contracts_master: published records
# must survive any future archival or re-classification of the source draft.


class PublishedContract(Base):
    """
    One row per approved contract publication event.
    Promotes key metadata from ContractMaster at approval time.
    """
    __tablename__ = "published_contracts"

    published_id = Column(Integer, Identity(start=1), primary_key=True)
    # Reference back to the source draft — NOT a CASCADE FK by design.
    contract_id = Column(String(50), nullable=False, index=True)
    contract_type = Column(String(100), nullable=False)
    agreement_type = Column(String(100), nullable=False)
    organization = Column(String(100), nullable=False)
    business_unit = Column(String(100), nullable=False)
    customer_partner_name = Column(String(200), nullable=True)
    effective_date = Column(Date, nullable=True)
    approved_by = Column(String(100), nullable=False)
    approved_at = Column(DateTime, nullable=True)

    risk_score = Column(Numeric(precision=5, scale=2), nullable=True)
    risk_level = Column(String(30), nullable=True)
    risk_rationale = Column(Text, nullable=True)

    published_at = Column(DateTime, default=func.now(), server_default=func.now())

    parameters = relationship(
        "PublishedParameter",
        back_populates="published_contract",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    chunks = relationship(
        "PublishedChunk",
        back_populates="published_contract",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class PublishedParameter(Base):
    """
    Approved parameter values promoted from ContractParameterExtracted.
    effective_value = user_override if present, else original_extract.
    Embedding is copied as-is from the draft row.
    """
    __tablename__ = "published_parameters"

    published_param_id = Column(Integer, Identity(start=1), primary_key=True)
    published_id = Column(
        Integer,
        ForeignKey("published_contracts.published_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalized for direct query without joins.
    contract_id = Column(String(50), nullable=False, index=True)
    header_name = Column(String(150), nullable=False)
    param_name = Column(String(150), nullable=False)
    # Resolved at promotion time: user_override if set, else original_extract.
    effective_value = Column(Text, nullable=True)
    citation_text = Column(Text, nullable=True)
    citation_start = Column(Integer, nullable=True)
    citation_end = Column(Integer, nullable=True)
    spatial_json = Column(OracleNativeJSON(), nullable=True)
    vector_embed = Column(
        VECTOR(settings.embedding_vector_dim, storage_format=VectorStorageFormat.INT8),
        nullable=True,
    )
    source_query = Column(String(250), nullable=True)
    validation_state = Column(String(30), default="needs_review", server_default="needs_review", nullable=False)
    validation_message = Column(Text, nullable=True)

    # Embedding versioning metadata
    embed_model_name = Column(String(100), nullable=True)
    embed_dimension = Column(Integer, nullable=True)
    embed_quant_type = Column(String(30), nullable=True)
    parser_version = Column(String(50), nullable=True)
    chunking_version = Column(String(50), nullable=True)
    embed_created_at = Column(DateTime, default=func.now(), server_default=func.now())

    published_contract = relationship("PublishedContract", back_populates="parameters")


class PublishedChunk(Base):
    """
    Approved document chunks promoted from ContractDocumentChunk.
    Spatial coordinates and vector embeddings are copied as-is.
    """
    __tablename__ = "published_chunks"

    published_chunk_id = Column(Integer, Identity(start=1), primary_key=True)
    published_id = Column(
        Integer,
        ForeignKey("published_contracts.published_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id = Column(String(50), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    char_start = Column(Integer, nullable=False)
    char_end = Column(Integer, nullable=False)
    spatial_json = Column(OracleNativeJSON(), nullable=True)
    chunk_vector = Column(
        VECTOR(settings.embedding_vector_dim, storage_format=VectorStorageFormat.INT8),
        nullable=True,
    )

    # Embedding versioning metadata
    embed_model_name = Column(String(100), nullable=True)
    embed_dimension = Column(Integer, nullable=True)
    embed_quant_type = Column(String(30), nullable=True)
    parser_version = Column(String(50), nullable=True)
    chunking_version = Column(String(50), nullable=True)
    embed_created_at = Column(DateTime, default=func.now(), server_default=func.now())

    published_contract = relationship("PublishedContract", back_populates="chunks")


class ContractTagSuggestion(Base):
    """
    ContractTagSuggestion — Stores suggested metadata, confidence scores, and rationales
    predicted at upload time.
    """
    __tablename__ = "contract_tag_suggestions"

    suggestion_id = Column(Integer, Identity(start=1), primary_key=True)
    contract_id = Column(
        String(50),
        ForeignKey("contracts_master.contract_id", ondelete="CASCADE"),
        nullable=False,
    )
    contract_type = Column(String(100), nullable=True)
    contract_type_confidence = Column(Numeric(precision=4, scale=3), nullable=True)
    contract_type_rationale = Column(Text, nullable=True)

    business_unit = Column(String(100), nullable=True)
    business_unit_confidence = Column(Numeric(precision=4, scale=3), nullable=True)
    business_unit_rationale = Column(Text, nullable=True)

    risk_level = Column(String(30), nullable=True)
    risk_level_confidence = Column(Numeric(precision=4, scale=3), nullable=True)
    risk_level_rationale = Column(Text, nullable=True)

    jurisdiction = Column(String(100), nullable=True)
    jurisdiction_confidence = Column(Numeric(precision=4, scale=3), nullable=True)
    jurisdiction_rationale = Column(Text, nullable=True)

    workflow_route = Column(String(150), nullable=True)
    workflow_route_confidence = Column(Numeric(precision=4, scale=3), nullable=True)
    workflow_route_rationale = Column(Text, nullable=True)

    extraction_template = Column(String(150), nullable=True)
    extraction_template_confidence = Column(Numeric(precision=4, scale=3), nullable=True)
    extraction_template_rationale = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now(), server_default=func.now())

    contract = relationship("ContractMaster", back_populates="tag_suggestions")