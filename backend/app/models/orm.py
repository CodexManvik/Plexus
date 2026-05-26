from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class ContractMaster(Base):
    __tablename__ = "contracts_master"

    contract_id = Column(String(50), primary_key=True, index=True)
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
    document_text = Column(Text, nullable=True)

    workflow_state = Column(
        String(30), default="STAGED_DRAFT", server_default="STAGED_DRAFT", nullable=False
    )
    checked_out_by = Column(String(100), nullable=True)
    checkout_expiry = Column(DateTime(timezone=True), nullable=True)
    document_version = Column(Integer, default=1, server_default="1", nullable=False)
    created_by = Column(String(100), nullable=True)
    approved_by = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=func.now(), server_default=func.now())
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now()
    )
    last_updated = Column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now()
    )

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


class ContractParameterExtracted(Base):
    __tablename__ = "contract_parameters_extracted"

    parameter_id = Column(Integer, primary_key=True, autoincrement=True)
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
    spatial_json = Column(JSON, nullable=True)
    vector_embed = Column(Text, nullable=True)
    source_query = Column(String(250), nullable=True)
    is_user_added = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_note = Column(Text, nullable=True)
    last_modified = Column(DateTime, default=func.now(), onupdate=func.now())

    contract = relationship("ContractMaster", back_populates="parameters")


class ContractAuditTrail(Base):
    __tablename__ = "contract_audit_trail"

    audit_id = Column(Integer, primary_key=True, autoincrement=True)
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

    rule_id = Column(Integer, primary_key=True, autoincrement=True)
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

    option_id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(80), nullable=False, index=True)
    value = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), server_default=func.now())
