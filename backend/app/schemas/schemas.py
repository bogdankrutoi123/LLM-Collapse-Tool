from pydantic import BaseModel, EmailStr, Field, ConfigDict, AliasChoices
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.database import UserRole, ModelStatus, NotificationStatus, EvaluationJobStatus


class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    role: UserRole = UserRole.OPERATOR


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=72)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[int] = None
    username: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class AuthBootstrapStatus(BaseModel):
    has_admin: bool
    public_registration_enabled: bool
    bootstrap_admin_available: bool


class BootstrapAdminRequest(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    password: str = Field(..., min_length=8, max_length=72)
    bootstrap_token: str = Field(..., min_length=12)


class ModelBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    source: Optional[str] = None


class ModelCreate(ModelBase):
    status: ModelStatus = ModelStatus.TESTING


class ModelUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    status: Optional[ModelStatus] = None


class ModelResponse(ModelBase):
    id: int
    status: ModelStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class ModelVersionBase(BaseModel):
    version: str = Field(..., max_length=100)
    description: Optional[str] = None
    model_metadata: Optional[dict] = Field(
        None,
        validation_alias=AliasChoices("model_metadata", "metadata"),
        serialization_alias="metadata",
    )
    weights_path: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class ModelVersionCreate(ModelVersionBase):
    model_id: int
    previous_version_id: Optional[int] = None


class ModelVersionUpdate(BaseModel):
    version: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    previous_version_id: Optional[int] = None
    model_metadata: Optional[dict] = Field(
        None,
        validation_alias=AliasChoices("model_metadata", "metadata"),
        serialization_alias="metadata",
    )
    weights_path: Optional[str] = None
    is_current: Optional[bool] = None

    model_config = ConfigDict(populate_by_name=True)


class ModelVersionResponse(ModelVersionBase):
    id: int
    model_id: int
    deployment_date: datetime
    previous_version_id: Optional[int] = None
    is_current: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PromptBase(BaseModel):
    input_text: str
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_k: Optional[int] = Field(None, ge=1)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_new_tokens: Optional[int] = Field(None, ge=1)


class PromptCreate(PromptBase):
    model_version_id: int


class PromptResponse(PromptBase):
    id: int
    model_version_id: int
    output_text: Optional[str] = None
    tokens: Optional[List] = None
    token_probabilities: Optional[dict] = None
    generation_trace: Optional[dict] = None
    embeddings: Optional[List] = None
    input_length: Optional[int] = None
    output_length: Optional[int] = None
    generation_time_ms: Optional[float] = None
    cpu_time_ms: Optional[float] = None
    gpu_time_ms: Optional[float] = None
    submitted_at: datetime
    processed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class PromptResponseUpdate(BaseModel):
    output_text: Optional[str] = None
    tokens: Optional[List] = None
    token_probabilities: Optional[dict] = None
    logits: Optional[dict] = None
    generation_time_ms: Optional[float] = None
    cpu_time_ms: Optional[float] = None
    gpu_time_ms: Optional[float] = None
    generation_trace: Optional[dict] = None
    embeddings: Optional[List] = None


class BatchPromptCreate(BaseModel):
    prompts: List[PromptCreate] = Field(..., max_length=100)


class PromptSetResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    source_filename: Optional[str] = None
    created_by_id: Optional[int] = None
    created_at: datetime
    item_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class PromptSetUploadResponse(BaseModel):
    prompt_set: PromptSetResponse
    accepted_items: int
    skipped_items: int


class EvaluationJobCreate(BaseModel):
    prompt_set_id: int
    model_version_id: int
    reference_version_id: Optional[int] = None
    max_new_tokens: int = Field(64, ge=1, le=512)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    num_beams: int = Field(1, ge=1, le=8)
    do_sample: bool = True
    store_full_token_probs: bool = False
    top_k_token_probs: int = Field(10, ge=1, le=100)


class EvaluationJobResponse(BaseModel):
    id: int
    prompt_set_id: int
    model_version_id: int
    reference_version_id: Optional[int] = None
    status: EvaluationJobStatus
    error_message: Optional[str] = None
    generation_params: Optional[Dict[str, Any]] = None
    store_full_token_probs: bool
    top_k_token_probs: int
    total_prompts: int
    processed_prompts: int
    successful_prompts: int
    failed_prompts: int
    created_by_id: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class EvaluationItemResponse(BaseModel):
    id: int
    job_id: int
    prompt_set_item_id: Optional[int] = None
    prompt_id: Optional[int] = None
    model_version_id: int
    input_text: str
    output_text: Optional[str] = None
    generation_time_ms: Optional[float] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class EvaluationCompareRequest(BaseModel):
    job_id_1: int
    job_id_2: int


class EvaluationCompareResponse(BaseModel):
    job_id_1: int
    job_id_2: int
    metrics_job_1: Dict[str, Optional[float]]
    metrics_job_2: Dict[str, Optional[float]]
    deltas: Dict[str, Optional[float]]


class PromptMetricResponse(BaseModel):
    id: int
    prompt_id: int
    entropy: Optional[float] = None
    kl_divergence: Optional[float] = None
    js_divergence: Optional[float] = None
    wasserstein_distance: Optional[float] = None
    ngram_drift: Optional[float] = None
    embedding_drift: Optional[float] = None
    token_frequency: Optional[dict] = None
    token_distribution_by_position: Optional[list] = None
    rare_token_percentage: Optional[float] = None
    new_token_percentage: Optional[float] = None
    median_length: Optional[float] = None
    length_variance: Optional[float] = None
    baseline_metadata: Optional[dict] = None
    is_anomaly: bool = False
    anomaly_reasons: Optional[List[str]] = None
    calculated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class AggregatedMetricResponse(BaseModel):
    id: int
    model_version_id: int
    period_start: datetime
    period_end: datetime
    total_prompts: int
    avg_entropy: Optional[float] = None
    avg_kl_divergence: Optional[float] = None
    avg_generation_time: Optional[float] = None
    avg_output_length: Optional[float] = None
    anomaly_count: int
    anomaly_percentage: Optional[float] = None
    metrics_data: Optional[dict] = None
    calculated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class WikiTextTokenStat(BaseModel):
    token: str
    count: int
    frequency: float


class WikiTextMetricsResponse(BaseModel):
    dataset: str
    dataset_id: Optional[str] = None
    tokenization: str
    tokenizer_model_id: Optional[str] = None
    token_count: int
    vocab_size: int
    entropy: float
    perplexity: float
    rare_token_percentage: float
    top_tokens: List[WikiTextTokenStat]


class WikiTextBenchmarkResponse(WikiTextMetricsResponse):
    model_id: Optional[str] = None
    sample_count: int
    prompts_used: int
    num_beams: Optional[int] = None
    avg_sequence_perplexity: Optional[float] = None
    std_sequence_perplexity: Optional[float] = None
    reference_entropy: Optional[float] = None
    reference_perplexity: Optional[float] = None
    js_divergence: Optional[float] = None


class AlertThresholdBase(BaseModel):
    name: str = Field(..., max_length=255)
    metric_name: str = Field(..., max_length=100)
    threshold_value: float
    comparison_operator: str = Field(..., pattern="^(>|<|>=|<=|==)$")
    persistence_count: int = Field(1, ge=1)
    persistence_window_minutes: int = Field(0, ge=0)
    group_key: Optional[str] = Field(None, max_length=100)
    require_all_in_group: bool = False
    description: Optional[str] = None


class AlertThresholdCreate(AlertThresholdBase):
    is_active: bool = True


class AlertThresholdUpdate(BaseModel):
    threshold_value: Optional[float] = None
    comparison_operator: Optional[str] = None
    is_active: Optional[bool] = None
    persistence_count: Optional[int] = None
    persistence_window_minutes: Optional[int] = None
    group_key: Optional[str] = None
    require_all_in_group: Optional[bool] = None
    description: Optional[str] = None


class AlertThresholdResponse(AlertThresholdBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class AlertRuleItemBase(BaseModel):
    metric_name: str = Field(..., max_length=100)
    threshold_value: float
    comparison_operator: str = Field(..., pattern="^(>|<|>=|<=|==)$")
    persistence_count: int = Field(1, ge=1)
    persistence_window_minutes: int = Field(0, ge=0)


class AlertRuleItemCreate(AlertRuleItemBase):
    pass


class AlertRuleItemResponse(AlertRuleItemBase):
    id: int
    rule_id: int

    model_config = ConfigDict(from_attributes=True)


class AlertRuleBase(BaseModel):
    name: str = Field(..., max_length=255)
    operator: str = Field("any", pattern="^(any|all)$")
    description: Optional[str] = None
    is_active: bool = True


class AlertRuleCreate(AlertRuleBase):
    items: List[AlertRuleItemCreate] = Field(default_factory=list)


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    operator: Optional[str] = Field(None, pattern="^(any|all)$")
    description: Optional[str] = None
    is_active: Optional[bool] = None


class AlertRuleResponse(AlertRuleBase):
    id: int
    items: List[AlertRuleItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class NotificationCreate(BaseModel):
    model_version_id: Optional[int] = None
    prompt_id: Optional[int] = None
    alert_threshold_id: Optional[int] = None
    title: str = Field(..., max_length=255)
    message: str
    severity: str = "warning"
    recipients: Optional[List[EmailStr]] = None


class NotificationUpdate(BaseModel):
    status: Optional[NotificationStatus] = None
    response_comment: Optional[str] = None


class NotificationResponse(BaseModel):
    id: int
    model_version_id: Optional[int] = None
    prompt_id: Optional[int] = None
    alert_threshold_id: Optional[int] = None
    title: str
    message: str
    severity: str
    status: NotificationStatus
    email_sent: bool
    email_sent_at: Optional[datetime] = None
    recipients: Optional[List[str]] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[int] = None
    response_comment: Optional[str] = None
    created_at: datetime
    created_by_id: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    old_value: Optional[dict] = None
    new_value: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: datetime
    
    model_config = ConfigDict(from_attributes=True)


class CollapseEventResponse(BaseModel):
    id: int
    model_version_id: Optional[int] = None
    prompt_id: Optional[int] = None
    triggered_metrics: Optional[list] = None
    baseline_metadata: Optional[dict] = None
    persistence_metadata: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExportRequest(BaseModel):
    entity_type: str = Field(..., pattern="^(models|versions|prompts|metrics)$")
    model_id: Optional[int] = None
    version_id: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    format: str = Field("csv", pattern="^(csv|json)$")


class ModelImport(BaseModel):
    id: Optional[int] = None
    name: str
    description: Optional[str] = None
    source: Optional[str] = None
    status: Optional[ModelStatus] = None


class ModelVersionImport(BaseModel):
    id: Optional[int] = None
    model_id: int
    version: str
    description: Optional[str] = None
    previous_version_id: Optional[int] = None
    model_metadata: Optional[dict] = Field(
        None,
        validation_alias=AliasChoices("model_metadata", "metadata"),
        serialization_alias="metadata",
    )
    weights_path: Optional[str] = None
    is_current: Optional[bool] = None

    model_config = ConfigDict(populate_by_name=True)


class PromptImport(BaseModel):
    id: Optional[int] = None
    model_version_id: int
    input_text: str
    output_text: Optional[str] = None
    tokens: Optional[List] = None
    token_probabilities: Optional[dict] = None
    logits: Optional[dict] = None
    generation_trace: Optional[dict] = None
    embeddings: Optional[List] = None
    input_length: Optional[int] = None
    output_length: Optional[int] = None
    generation_time_ms: Optional[float] = None
    cpu_time_ms: Optional[float] = None
    gpu_time_ms: Optional[float] = None
    temperature: Optional[float] = None
    top_k: Optional[int] = None
    top_p: Optional[float] = None
    max_new_tokens: Optional[int] = None
    submitted_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None


class PromptMetricImport(BaseModel):
    id: Optional[int] = None
    prompt_id: int
    entropy: Optional[float] = None
    kl_divergence: Optional[float] = None
    js_divergence: Optional[float] = None
    wasserstein_distance: Optional[float] = None
    ngram_drift: Optional[float] = None
    embedding_drift: Optional[float] = None
    token_frequency: Optional[dict] = None
    token_distribution_by_position: Optional[list] = None
    rare_token_percentage: Optional[float] = None
    new_token_percentage: Optional[float] = None
    median_length: Optional[float] = None
    length_variance: Optional[float] = None
    baseline_metadata: Optional[dict] = None
    is_anomaly: Optional[bool] = None
    anomaly_reasons: Optional[List[str]] = None
    calculated_at: Optional[datetime] = None


class BackupRestoreRequest(BaseModel):
    filename: str
    replace: bool = False


class ReportExportRequest(BaseModel):
    version_id_1: int
    version_id_2: int
    format: str = Field("json", pattern="^(csv|json)$")


class VersionComparisonRequest(BaseModel):
    version_id_1: int
    version_id_2: int
    metrics: Optional[List[str]] = None


class VersionComparisonResponse(BaseModel):
    version_1: ModelVersionResponse
    version_2: ModelVersionResponse
    metrics_comparison: dict
    changes: List[dict]
