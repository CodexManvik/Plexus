from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MetadataFields(BaseModel):
    organization: str
    business_unit: str
    location: Optional[str] = None
    department: Optional[str] = None
    customer_partner_name: Optional[str] = None
    financial_year: Optional[str] = None
    contract_type: str
    agreement_type: str
    additional_info: Optional[str] = None

    contract_number: Optional[str] = None
    version_amendment_number: Optional[str] = None
    execution_type: Optional[str] = None
    governing_entity: Optional[str] = None
    jurisdiction: Optional[str] = None
    governing_law: Optional[str] = None
    legal_names_of_parties: Optional[str] = None
    registered_addresses: Optional[str] = None
    cin_registration_numbers: Optional[str] = None
    authorized_signatories: Optional[str] = None
    contact_persons: Optional[str] = None
    party_roles: Optional[str] = None
    affiliates_subsidiaries_involved: Optional[str] = None
    effective_date: Optional[date] = None


class ParameterResponse(BaseSchema):
    parameter_id: int
    contract_id: str
    header_name: str
    param_name: str
    original_extract: Optional[str] = None
    user_override: Optional[str] = None
    match_score: Optional[float] = None
    citation_text: Optional[str] = None
    citation_start: Optional[int] = None
    citation_end: Optional[int] = None
    spatial_json: Optional[Any] = None
    source_query: Optional[str] = None
    is_user_added: bool = False
    is_verified: bool = False
    verification_note: Optional[str] = None
    validation_state: str = "needs_review"
    validation_message: Optional[str] = None
    embed_model_name: Optional[str] = None
    embed_dimension: Optional[int] = None
    embed_quant_type: Optional[str] = None
    parser_version: Optional[str] = None
    chunking_version: Optional[str] = None
    embed_created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None


class ParameterUpdateRequest(BaseModel):
    user_override: str
    modified_by: str


class ParameterVerifyRequest(BaseModel):
    is_verified: bool
    modified_by: str
    note: Optional[str] = None


class DynamicSearchAddRequest(BaseModel):
    query: str = Field(min_length=1, max_length=250)
    parameter_head: str = Field(min_length=1, max_length=150)
    parameter_name: str = Field(min_length=1, max_length=150)
    modified_by: str = Field(min_length=1, max_length=100)


class ContractResponse(BaseSchema, MetadataFields):
    contract_id: str
    uploaded_filename: Optional[str] = None
    uploaded_content_type: Optional[str] = None
    workflow_state: str
    checked_out_by: Optional[str] = None
    checkout_expiry: Optional[datetime] = None
    document_version: int
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None
    risk_rationale: Optional[str] = None
    draft_checkpoint: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    document_text: Optional[str] = None
    parameters: List[ParameterResponse] = Field(default_factory=list)


class ContractListResponse(BaseModel):
    data: List[ContractResponse]
    total: int


class ContractSearchResponse(BaseModel):
    data: List[ContractResponse]
    total: int


class AssistantSourceSnippet(BaseModel):
    contract_id: str
    contract_type: Optional[str] = None
    agreement_type: Optional[str] = None
    source_type: str
    title: Optional[str] = None
    snippet: str
    score: float
    parameter_head: Optional[str] = None
    parameter_name: Optional[str] = None
    spatial_json: Optional[Any] = None


class AssistantQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    contract_ids: List[str] = Field(default_factory=list)
    top_k: int = Field(default=3, ge=1, le=5)
    draft_mode: bool = Field(
        default=False,
        description=(
            "When False (default), the assistant queries published (approved) data only. "
            "When True, queries draft tables instead \u2014 intended for development and debugging. "
            "Using draft_mode=True in production will emit a warning."
        ),
    )


class AssistantQueryResponse(BaseModel):
    answer: str
    contract_ids: List[str]
    sources: List[AssistantSourceSnippet] = Field(default_factory=list)
    used_llm: bool = False


class ContractUpdateMetadataRequest(BaseModel):
    metadata: MetadataFields
    modified_by: str


class WorkflowActionRequest(BaseModel):
    modified_by: str
    comment: Optional[str] = None


class LockAcquireRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)


class LockResponse(BaseModel):
    contract_id: str
    checked_out_by: Optional[str] = None
    checkout_expiry: Optional[datetime] = None
    lock_acquired: bool


class AuditResponse(BaseSchema):
    audit_id: int
    contract_id: str
    action_type: str
    field_changed: Optional[str] = None
    old_value_clob: Optional[str] = None
    new_value_clob: Optional[str] = None
    modified_by: str
    logged_timestamp: datetime


class AuditTrailResponse(BaseModel):
    contract_id: str
    audit_trail: List[AuditResponse]


class KPIItem(BaseModel):
    value: int
    label: str
    change: Optional[str] = None
    percentage: Optional[int] = None
    urgent: Optional[bool] = None


class KPIDashboardResponse(BaseModel):
    executed: KPIItem
    pending: KPIItem
    closingSoon: KPIItem


class BacklogDepartmentItem(BaseModel):
    department: str
    count: int


class ExpiryContractItem(BaseModel):
    contract_id: str
    title: str
    partner: Optional[str] = None
    daysLeft: int
    date: Optional[str] = None
    urgent: bool


class ActivityLogItem(BaseModel):
    title: str
    department: Optional[str] = None
    status: str
    owner: Optional[str] = None
    updated: Optional[str] = None


class DashboardAnalyticsResponse(BaseModel):
    kpis: KPIDashboardResponse
    backlog: List[BacklogDepartmentItem]
    expiries: List[ExpiryContractItem]
    activity: List[ActivityLogItem]
    pending_rule_count: int = 0


class ExtractionStatusResponse(BaseModel):
    contract_id: str
    status: str
    total: int
    extracted: int
    verified: int
    percentage: int


class ReExtractionResponse(BaseModel):
    contract_id: str
    rules_applied: int
    parameters_written: int
    parameters_filled: int


class MasterRuleBase(BaseModel):
    contract_type: str
    agreement_type: str
    parameter_head: str
    parameter_name: str
    parameter_logic: Optional[str] = None
    is_active: bool = True


class MasterRuleCreate(MasterRuleBase):
    created_by: Optional[str] = None


class MasterRuleUpdate(BaseModel):
    contract_type: Optional[str] = None
    agreement_type: Optional[str] = None
    parameter_head: Optional[str] = None
    parameter_name: Optional[str] = None
    parameter_logic: Optional[str] = None
    is_active: Optional[bool] = None


class MasterRuleResponse(BaseSchema, MasterRuleBase):
    rule_id: int
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MetadataOptionCreate(BaseModel):
    category: str
    value: str


class MetadataOptionResponse(BaseSchema):
    option_id: int
    category: str
    value: str
    is_active: bool
    created_at: datetime


class MetadataBundleResponse(BaseModel):
    organizations: List[str]
    business_units: List[str]
    locations: List[str]
    departments: List[str]
    customer_partner_names: List[str]
    financial_years: List[str]
    contract_types: List[str]
    agreement_types: List[str]
    execution_types: List[str]


class SemanticSearchResult(BaseModel):
    contract_id: str
    contract_type: Optional[str] = None
    agreement_type: Optional[str] = None
    organization: Optional[str] = None
    uploaded_filename: Optional[str] = None
    similarity_score: float


class SemanticSearchResponse(BaseModel):
    data: List[SemanticSearchResult]
    total: int
    query: str


class TagSuggestionEntry(BaseModel):
    value: str
    confidence: float
    rationale: str


class ContractTagSuggestionResponse(BaseModel):
    suggestion_id: int
    contract_id: str
    contract_type: TagSuggestionEntry
    business_unit: TagSuggestionEntry
    risk_level: TagSuggestionEntry
    jurisdiction: TagSuggestionEntry
    workflow_route: TagSuggestionEntry
    extraction_template: TagSuggestionEntry
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TagSuggestionsAcceptRequest(BaseModel):
    modified_by: str


class TagSuggestionsEditRequest(BaseModel):
    modified_by: str
    contract_type: Optional[str] = None
    business_unit: Optional[str] = None
    risk_level: Optional[str] = None
    jurisdiction: Optional[str] = None
    workflow_route: Optional[str] = None
    extraction_template: Optional[str] = None


class DraftPauseRequest(BaseModel):
    modified_by: str
    checkpoint_json: str


class DraftPauseResponse(BaseModel):
    contract_id: str
    workflow_state: str
    draft_checkpoint: Optional[str] = None


