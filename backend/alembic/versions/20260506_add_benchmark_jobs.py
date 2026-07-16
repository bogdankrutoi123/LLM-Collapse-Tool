"""add benchmark_jobs table for async benchmark pipeline

Revision ID: 20260506_benchmark_jobs
Revises: 20260318_eval_pipeline
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260506_benchmark_jobs"
down_revision = "20260318_eval_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("benchmark_jobs"):
        op.create_table(
            "benchmark_jobs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column(
                "model_version_id",
                sa.Integer(),
                sa.ForeignKey("model_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "created_by_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "status",
                sa.Enum("QUEUED", "RUNNING", "COMPLETED", "FAILED", name="benchmarkjobstatus"),
                nullable=False,
                server_default="QUEUED",
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("dataset_id", sa.String(length=255), nullable=False),
            sa.Column("sample_count", sa.Integer(), nullable=False),
            sa.Column("max_new_tokens", sa.Integer(), nullable=False),
            sa.Column("temperature", sa.Float(), nullable=False),
            sa.Column("num_beams", sa.Integer(), nullable=False),
            sa.Column("max_tokens", sa.Integer(), nullable=False),
            sa.Column("top_k", sa.Integer(), nullable=False),
            sa.Column("rare_percentile", sa.Float(), nullable=False),
            sa.Column("seed", sa.Integer(), nullable=True),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column(
                "aggregated_metric_id",
                sa.Integer(),
                sa.ForeignKey("aggregated_metrics.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_benchmark_jobs_model_version_id", "benchmark_jobs", ["model_version_id"])
        op.create_index("ix_benchmark_jobs_status", "benchmark_jobs", ["status"])
        op.create_index("ix_benchmark_jobs_created_at", "benchmark_jobs", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("benchmark_jobs"):
        op.drop_index("ix_benchmark_jobs_created_at", table_name="benchmark_jobs")
        op.drop_index("ix_benchmark_jobs_status", table_name="benchmark_jobs")
        op.drop_index("ix_benchmark_jobs_model_version_id", table_name="benchmark_jobs")
        op.drop_table("benchmark_jobs")

    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS benchmarkjobstatus")
