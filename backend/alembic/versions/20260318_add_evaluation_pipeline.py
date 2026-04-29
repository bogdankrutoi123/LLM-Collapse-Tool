"""add evaluation pipeline tables

Revision ID: 20260318_eval_pipeline
Revises: 20260122_rules_events
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260318_eval_pipeline"
down_revision = "20260122_rules_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("prompt_sets"):
        op.create_table(
            "prompt_sets",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("name", sa.String(length=255), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source_filename", sa.String(length=255), nullable=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )

    if not inspector.has_table("prompt_set_items"):
        op.create_table(
            "prompt_set_items",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("prompt_set_id", sa.Integer(), sa.ForeignKey("prompt_sets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("input_text", sa.Text(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )

    if not inspector.has_table("evaluation_jobs"):
        op.create_table(
            "evaluation_jobs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("prompt_set_id", sa.Integer(), sa.ForeignKey("prompt_sets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("reference_version_id", sa.Integer(), sa.ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column(
                "status",
                sa.Enum("QUEUED", "RUNNING", "COMPLETED", "FAILED", "PARTIAL", name="evaluationjobstatus"),
                nullable=False,
                server_default="QUEUED",
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("generation_params", sa.JSON(), nullable=True),
            sa.Column("store_full_token_probs", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("top_k_token_probs", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("total_prompts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("processed_prompts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("successful_prompts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_prompts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not inspector.has_table("evaluation_items"):
        op.create_table(
            "evaluation_items",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("evaluation_jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("prompt_set_item_id", sa.Integer(), sa.ForeignKey("prompt_set_items.id", ondelete="SET NULL"), nullable=True),
            sa.Column("prompt_id", sa.Integer(), sa.ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("input_text", sa.Text(), nullable=False),
            sa.Column("output_text", sa.Text(), nullable=True),
            sa.Column("tokens", sa.JSON(), nullable=True),
            sa.Column("token_probabilities", sa.JSON(), nullable=True),
            sa.Column("generation_time_ms", sa.Float(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("evaluation_items")
    op.drop_table("evaluation_jobs")
    op.drop_table("prompt_set_items")
    op.drop_table("prompt_sets")

    op.execute("DROP TYPE IF EXISTS evaluationjobstatus")
