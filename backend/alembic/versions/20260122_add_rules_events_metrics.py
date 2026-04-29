"""add rules events metrics fields

Revision ID: 20260122_rules_events
Revises: 
Create Date: 2026-01-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.db.session import Base
from app.models import database

revision = "20260122_rules_events"
down_revision = None
default_branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("prompts"):
        Base.metadata.create_all(bind)
        return

    def column_exists(table_name: str, column_name: str) -> bool:
        return column_name in {col["name"] for col in inspector.get_columns(table_name)}

    if not column_exists("prompts", "generation_trace"):
        op.add_column("prompts", sa.Column("generation_trace", sa.JSON(), nullable=True))
    if not column_exists("prompts", "embeddings"):
        op.add_column("prompts", sa.Column("embeddings", sa.JSON(), nullable=True))
    if not column_exists("prompts", "cpu_time_ms"):
        op.add_column("prompts", sa.Column("cpu_time_ms", sa.Float(), nullable=True))
    if not column_exists("prompts", "gpu_time_ms"):
        op.add_column("prompts", sa.Column("gpu_time_ms", sa.Float(), nullable=True))

    if not column_exists("prompt_metrics", "js_divergence"):
        op.add_column("prompt_metrics", sa.Column("js_divergence", sa.Float(), nullable=True))
    if not column_exists("prompt_metrics", "wasserstein_distance"):
        op.add_column("prompt_metrics", sa.Column("wasserstein_distance", sa.Float(), nullable=True))
    if not column_exists("prompt_metrics", "ngram_drift"):
        op.add_column("prompt_metrics", sa.Column("ngram_drift", sa.Float(), nullable=True))
    if not column_exists("prompt_metrics", "embedding_drift"):
        op.add_column("prompt_metrics", sa.Column("embedding_drift", sa.Float(), nullable=True))
    if not column_exists("prompt_metrics", "token_distribution_by_position"):
        op.add_column("prompt_metrics", sa.Column("token_distribution_by_position", sa.JSON(), nullable=True))
    if not column_exists("prompt_metrics", "baseline_metadata"):
        op.add_column("prompt_metrics", sa.Column("baseline_metadata", sa.JSON(), nullable=True))

    if not column_exists("alert_thresholds", "persistence_count"):
        op.add_column("alert_thresholds", sa.Column("persistence_count", sa.Integer(), nullable=True, server_default="1"))
    if not column_exists("alert_thresholds", "persistence_window_minutes"):
        op.add_column("alert_thresholds", sa.Column("persistence_window_minutes", sa.Integer(), nullable=True, server_default="0"))
    if not column_exists("alert_thresholds", "group_key"):
        op.add_column("alert_thresholds", sa.Column("group_key", sa.String(length=100), nullable=True))
    if not column_exists("alert_thresholds", "require_all_in_group"):
        op.add_column("alert_thresholds", sa.Column("require_all_in_group", sa.Boolean(), nullable=True, server_default=sa.text("false")))

    if not inspector.has_table("alert_rules"):
        op.create_table(
            "alert_rules",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("name", sa.String(length=255), nullable=False, unique=True),
            sa.Column("operator", sa.String(length=10), nullable=False, server_default="any"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
        )

    if not inspector.has_table("alert_rule_items"):
        op.create_table(
            "alert_rule_items",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("rule_id", sa.Integer(), sa.ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False),
            sa.Column("metric_name", sa.String(length=100), nullable=False),
            sa.Column("threshold_value", sa.Float(), nullable=False),
            sa.Column("comparison_operator", sa.String(length=10), nullable=False),
            sa.Column("persistence_count", sa.Integer(), nullable=True, server_default="1"),
            sa.Column("persistence_window_minutes", sa.Integer(), nullable=True, server_default="0")
        )

    if not inspector.has_table("collapse_events"):
        op.create_table(
            "collapse_events",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("prompt_id", sa.Integer(), sa.ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("triggered_metrics", sa.JSON(), nullable=True),
            sa.Column("baseline_metadata", sa.JSON(), nullable=True),
            sa.Column("persistence_metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False)
        )


def downgrade() -> None:
    op.drop_table("collapse_events")
    op.drop_table("alert_rule_items")
    op.drop_table("alert_rules")

    op.drop_column("alert_thresholds", "require_all_in_group")
    op.drop_column("alert_thresholds", "group_key")
    op.drop_column("alert_thresholds", "persistence_window_minutes")
    op.drop_column("alert_thresholds", "persistence_count")

    op.drop_column("prompt_metrics", "baseline_metadata")
    op.drop_column("prompt_metrics", "token_distribution_by_position")
    op.drop_column("prompt_metrics", "embedding_drift")
    op.drop_column("prompt_metrics", "ngram_drift")
    op.drop_column("prompt_metrics", "wasserstein_distance")
    op.drop_column("prompt_metrics", "js_divergence")

    op.drop_column("prompts", "gpu_time_ms")
    op.drop_column("prompts", "cpu_time_ms")
    op.drop_column("prompts", "embeddings")
    op.drop_column("prompts", "generation_trace")
