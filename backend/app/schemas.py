from typing import Any

from pydantic import BaseModel


class ContractCreateRequest(BaseModel):
    contract_id: str | None = None
    contract_type: str | None = None
    metadata: dict[str, Any] | None = None
    workflow_state: str = "STAGED_DRAFT"


class ContractVersionResponse(BaseModel):
    contract_id: str
    version_number: int
    workflow_state: str
    is_current: bool
    etag: str


class ExtractionRequest(BaseModel):
    contract_text: str
    parameters: list[str] | None = None


class ParameterResponse(BaseModel):
    parameter_id: int
    parameter_key: str
    original_extract: str | None = None
    user_override: str | None = None
    combined_score: float | None = None


class ContractParameterResponse(ParameterResponse):
    param_group_id: str | None = None
    param_structure_type: str | None = None
    spatial_json: dict[str, Any] | None = None


class UpdateParameterRequest(BaseModel):
    user_override: str | None = None


class SearchRequest(BaseModel):
    query: str
    k: int = 5


class SearchResult(BaseModel):
    parameter_id: int
    parameter_key: str
    original_extract: str | None
    score: float
