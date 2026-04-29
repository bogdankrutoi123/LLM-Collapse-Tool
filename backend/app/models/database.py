from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base
from app.core.crypto import EncryptedText
import enum


class UserRole(str, enum.Enum):
    """User role enumeration."""
    ADMIN = "admin"
    MODEL_ENGINEER = "model_engineer"
    OPERATOR = "operator"


class ModelStatus(str, enum.Enum):
    """Model status enumeration."""
    ACTIVE = "active"
    ARCHIVED = "archived"
    ROLLBACK = "rollback"
    TESTING = "testing"


class NotificationStatus(str, enum.Enum):
    """Notification status enumeration."""
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class EvaluationJobStatus(str, enum.Enum):
    """Evaluation job lifecycle status."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class User(Base):
    """User model."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(SQLEnum(UserRole), default=UserRole.OPERATOR, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    audit_logs = relationship("AuditLog", back_populates="user")
    notifications_created = relationship("Notification", foreign_keys="Notification.created_by_id", back_populates="created_by")


class Model(Base):
    """Language model model."""
    __tablename__ = "models"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    description = Column(Text)
    source = Column(String(500))
    status = Column(SQLEnum(ModelStatus), default=ModelStatus.TESTING, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    versions = relationship("ModelVersion", back_populates="model", cascade="all, delete-orphan")


class ModelVersion(Base):
    """Model version tracking."""
    __tablename__ = "model_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("models.id", ondelete="CASCADE"), nullable=False)
    version = Column(String(100), nullable=False)
    description = Column(Text)
    deployment_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    previous_version_id = Column(Integer, ForeignKey("model_versions.id", ondelete="SET NULL"))
    model_metadata = Column("metadata", JSON)
    weights_path = Column(String(500))
    is_current = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    model = relationship("Model", back_populates="versions")
    previous_version = relationship("ModelVersion", remote_side=[id], foreign_keys=[previous_version_id])
    prompts = relationship("Prompt", back_populates="model_version")
    metrics = relationship("AggregatedMetric", back_populates="model_version")


class Prompt(Base):
    """Prompt and response storage."""
    __tablename__ = "prompts"
    
    id = Column(Integer, primary_key=True, index=True)
    model_version_id = Column(Integer, ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False)
    input_text = Column(EncryptedText, nullable=False)
    output_text = Column(EncryptedText)
    tokens = Column(JSON)
    token_probabilities = Column(JSON)
    logits = Column(JSON)
    generation_trace = Column(JSON)
    embeddings = Column(JSON)
    
    input_length = Column(Integer)
    output_length = Column(Integer)
    generation_time_ms = Column(Float)
    cpu_time_ms = Column(Float)
    gpu_time_ms = Column(Float)
    
    temperature = Column(Float)
    top_k = Column(Integer)
    top_p = Column(Float)
    max_new_tokens = Column(Integer)
    
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True))
    
    model_version = relationship("ModelVersion", back_populates="prompts")
    metrics = relationship("PromptMetric", back_populates="prompt", cascade="all, delete-orphan")


class PromptMetric(Base):
    """Metrics calculated for each prompt."""
    __tablename__ = "prompt_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    prompt_id = Column(Integer, ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False)
    
    entropy = Column(Float)
    kl_divergence = Column(Float)
    js_divergence = Column(Float)
    wasserstein_distance = Column(Float)
    ngram_drift = Column(Float)
    embedding_drift = Column(Float)
    token_frequency = Column(JSON)
    token_distribution_by_position = Column(JSON)
    rare_token_percentage = Column(Float)
    new_token_percentage = Column(Float)
    median_length = Column(Float)
    length_variance = Column(Float)
    baseline_metadata = Column(JSON)
    
    is_anomaly = Column(Boolean, default=False)
    anomaly_reasons = Column(JSON)
    
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    prompt = relationship("Prompt", back_populates="metrics")


class PromptSet(Base):
    """Uploaded prompt set used for batch evaluation."""
    __tablename__ = "prompt_sets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    source_filename = Column(String(255))
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    items = relationship("PromptSetItem", back_populates="prompt_set", cascade="all, delete-orphan")
    jobs = relationship("EvaluationJob", back_populates="prompt_set", cascade="all, delete-orphan")


class PromptSetItem(Base):
    """Individual prompt row in an uploaded prompt set."""
    __tablename__ = "prompt_set_items"

    id = Column(Integer, primary_key=True, index=True)
    prompt_set_id = Column(Integer, ForeignKey("prompt_sets.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, nullable=False)
    input_text = Column(Text, nullable=False)
    item_metadata = Column("metadata", JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    prompt_set = relationship("PromptSet", back_populates="items")
    evaluation_items = relationship("EvaluationItem", back_populates="prompt_set_item")


class EvaluationJob(Base):
    """Asynchronous batch evaluation job for one model version."""
    __tablename__ = "evaluation_jobs"

    id = Column(Integer, primary_key=True, index=True)
    prompt_set_id = Column(Integer, ForeignKey("prompt_sets.id", ondelete="CASCADE"), nullable=False)
    model_version_id = Column(Integer, ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False)
    reference_version_id = Column(Integer, ForeignKey("model_versions.id", ondelete="SET NULL"))
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    status = Column(SQLEnum(EvaluationJobStatus), default=EvaluationJobStatus.QUEUED, nullable=False)
    error_message = Column(Text)

    generation_params = Column(JSON)
    store_full_token_probs = Column(Boolean, default=False, nullable=False)
    top_k_token_probs = Column(Integer, default=10, nullable=False)

    total_prompts = Column(Integer, default=0, nullable=False)
    processed_prompts = Column(Integer, default=0, nullable=False)
    successful_prompts = Column(Integer, default=0, nullable=False)
    failed_prompts = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    prompt_set = relationship("PromptSet", back_populates="jobs")
    items = relationship("EvaluationItem", back_populates="job", cascade="all, delete-orphan")


class EvaluationItem(Base):
    """Per-prompt inference result inside an evaluation job."""
    __tablename__ = "evaluation_items"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("evaluation_jobs.id", ondelete="CASCADE"), nullable=False)
    prompt_set_item_id = Column(Integer, ForeignKey("prompt_set_items.id", ondelete="SET NULL"))
    prompt_id = Column(Integer, ForeignKey("prompts.id", ondelete="SET NULL"))
    model_version_id = Column(Integer, ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False)

    input_text = Column(Text, nullable=False)
    output_text = Column(Text)
    tokens = Column(JSON)
    token_probabilities = Column(JSON)
    generation_time_ms = Column(Float)

    status = Column(String(20), default="pending", nullable=False)
    error_message = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True))

    job = relationship("EvaluationJob", back_populates="items")
    prompt_set_item = relationship("PromptSetItem", back_populates="evaluation_items")


class AggregatedMetric(Base):
    """Aggregated metrics for model versions."""
    __tablename__ = "aggregated_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    model_version_id = Column(Integer, ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False)
    
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    
    total_prompts = Column(Integer, default=0)
    avg_entropy = Column(Float)
    avg_kl_divergence = Column(Float)
    avg_generation_time = Column(Float)
    avg_output_length = Column(Float)
    anomaly_count = Column(Integer, default=0)
    anomaly_percentage = Column(Float)
    
    metrics_data = Column(JSON)
    
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    model_version = relationship("ModelVersion", back_populates="metrics")


class AlertThreshold(Base):
    """Configurable alert thresholds."""
    __tablename__ = "alert_thresholds"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    metric_name = Column(String(100), nullable=False)
    threshold_value = Column(Float, nullable=False)
    comparison_operator = Column(String(10), nullable=False)
    is_active = Column(Boolean, default=True)
    persistence_count = Column(Integer, default=1)
    persistence_window_minutes = Column(Integer, default=0)
    group_key = Column(String(100))
    require_all_in_group = Column(Boolean, default=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AlertRule(Base):
    """Multi-signal alert rule (AND/OR across items)."""
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    operator = Column(String(10), default="any", nullable=False)
    is_active = Column(Boolean, default=True)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    items = relationship("AlertRuleItem", back_populates="rule", cascade="all, delete-orphan")


class AlertRuleItem(Base):
    """Rule item defining a metric threshold with persistence."""
    __tablename__ = "alert_rule_items"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False)
    metric_name = Column(String(100), nullable=False)
    threshold_value = Column(Float, nullable=False)
    comparison_operator = Column(String(10), nullable=False)
    persistence_count = Column(Integer, default=1)
    persistence_window_minutes = Column(Integer, default=0)

    rule = relationship("AlertRule", back_populates="items")


class Notification(Base):
    """Notification/alert storage."""
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    model_version_id = Column(Integer, ForeignKey("model_versions.id", ondelete="SET NULL"))
    prompt_id = Column(Integer, ForeignKey("prompts.id", ondelete="SET NULL"))
    alert_threshold_id = Column(Integer, ForeignKey("alert_thresholds.id", ondelete="SET NULL"))
    
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String(50), default="warning")
    status = Column(SQLEnum(NotificationStatus), default=NotificationStatus.PENDING, nullable=False)
    
    email_sent = Column(Boolean, default=False)
    email_sent_at = Column(DateTime(timezone=True))
    recipients = Column(JSON)
    
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledged_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    response_comment = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    
    created_by = relationship("User", foreign_keys=[created_by_id], back_populates="notifications_created")


class CollapseEvent(Base):
    """Collapse event record triggered by persistent threshold conditions."""
    __tablename__ = "collapse_events"

    id = Column(Integer, primary_key=True, index=True)
    model_version_id = Column(Integer, ForeignKey("model_versions.id", ondelete="SET NULL"))
    prompt_id = Column(Integer, ForeignKey("prompts.id", ondelete="SET NULL"))
    triggered_metrics = Column(JSON)
    baseline_metadata = Column(JSON)
    persistence_metadata = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditLog(Base):
    """Audit log for tracking all system actions."""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(Integer)
    old_value = Column(JSON)
    new_value = Column(JSON)
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    user = relationship("User", back_populates="audit_logs")


class SystemSetting(Base):
    """System-wide configuration settings."""
    __tablename__ = "system_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), unique=True, nullable=False)
    value = Column(JSON, nullable=False)
    description = Column(Text)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
