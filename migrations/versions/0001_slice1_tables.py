"""Slice-1 tables

Revision ID: 0001
Revises:
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True)


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "company",
        sa.Column("cik", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("ticker", sa.Text),
        sa.Column("sic", sa.Text),
        sa.Column("sector", sa.Text),
        _created_at(),
    )

    op.create_table(
        "filing",
        _id(),
        sa.Column("cik", sa.BigInteger, sa.ForeignKey("company.cik"), nullable=False),
        sa.Column("accession", sa.Text, nullable=False),
        sa.Column("form", sa.Text, nullable=False),
        sa.Column("period_of_report", sa.Date),
        sa.Column("fiscal_year", sa.Integer),
        sa.Column("filed_date", sa.Date, nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("primary_document", sa.Text, nullable=False),
        sa.Column("raw_sha256", sa.Text),
        sa.Column("raw_bytes", sa.Integer),
        sa.Column("fetch_status", sa.Text, server_default="pending", nullable=False),
        sa.Column("fetch_error", sa.Text),
        sa.Column("parse_status", sa.Text),
        sa.Column("parse_notes", pg.JSONB),
        sa.Column("parser_version", sa.Text),
        _created_at(),
        sa.UniqueConstraint("accession"),
        sa.CheckConstraint(
            "fetch_status IN ('pending', 'ok', 'failed', 'skipped')",
            name="ck_filing_fetch_status",
        ),
        sa.CheckConstraint(
            "parse_status IN ('ok', 'partial', 'failed')", name="ck_filing_parse_status"
        ),
    )
    op.create_index("ix_filing_cik_fiscal_year", "filing", ["cik", "fiscal_year"])

    op.create_table(
        "paragraph",
        _id(),
        sa.Column(
            "filing_id",
            sa.BigInteger,
            sa.ForeignKey("filing.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item", sa.Text, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("heading_path", pg.ARRAY(sa.Text), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("is_table", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("n_tokens", sa.Integer, nullable=False),
        sa.Column("exact_hash", sa.CHAR(40), nullable=False),
        sa.Column("masked_hash", sa.CHAR(40), nullable=False),
        _created_at(),
        sa.UniqueConstraint("filing_id", "seq", name="uq_paragraph_filing_id_seq"),
    )
    op.create_index("ix_paragraph_filing_id_item_seq", "paragraph", ["filing_id", "item", "seq"])
    op.create_index("ix_paragraph_masked_hash", "paragraph", ["masked_hash"])

    op.create_table(
        "alignment_pair",
        _id(),
        sa.Column("cik", sa.BigInteger, sa.ForeignKey("company.cik"), nullable=False),
        sa.Column(
            "old_filing_id",
            sa.BigInteger,
            sa.ForeignKey("filing.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "new_filing_id",
            sa.BigInteger,
            sa.ForeignKey("filing.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item", sa.Text),
        sa.Column("eligible", sa.Boolean, nullable=False),
        sa.Column("exclusion_reason", sa.Text),
        sa.Column("idf_version", sa.Text),
        sa.Column("aligner_version", sa.Text, nullable=False),
        sa.Column("sim_cosine", sa.Double),
        sa.Column("sim_jaccard", sa.Double),
        sa.Column("change_intensity_raw", sa.Double),
        sa.Column("change_intensity", sa.Double),
        _created_at(),
        sa.UniqueConstraint(
            "old_filing_id",
            "new_filing_id",
            "item",
            name="uq_alignment_pair_old_filing_id_new_filing_id_item",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_alignment_pair_new_filing_id", "alignment_pair", ["new_filing_id"])

    op.create_table(
        "alignment_edge",
        _id(),
        sa.Column(
            "pair_id",
            sa.BigInteger,
            sa.ForeignKey("alignment_pair.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column(
            "old_paragraph_ids",
            pg.ARRAY(sa.BigInteger),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "new_paragraph_ids",
            pg.ARRAY(sa.BigInteger),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("sim", sa.Double),
        sa.Column("n_ins", sa.Integer, server_default="0", nullable=False),
        sa.Column("n_del", sa.Integer, server_default="0", nullable=False),
        sa.Column("changed_ratio", sa.Double, server_default="0", nullable=False),
        sa.Column("cross_item", sa.Boolean, server_default=sa.false(), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "label IN ('unchanged', 'rollforward', 'modified', 'moved', 'split', 'merged', "
            "'added', 'deleted')",
            name="ck_alignment_edge_label",
        ),
    )
    op.create_index("ix_alignment_edge_pair_id", "alignment_edge", ["pair_id"])

    op.create_table(
        "change_label",
        _id(),
        sa.Column(
            "edge_id",
            sa.BigInteger,
            sa.ForeignKey("alignment_edge.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("annotation_label", sa.Text, nullable=False),
        sa.Column("labelled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pass", sa.SmallInteger, nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "annotation_label IN ('formatting_reorder', 'boilerplate_refresh', "
            "'numeric_rollforward', 'new_topic', 'removed_topic', 'substantive_reword')",
            name="ck_change_label_annotation_label",
        ),
        sa.CheckConstraint("pass IN (1, 2)", name="ck_change_label_pass"),
        sa.UniqueConstraint("edge_id", "pass", name="uq_change_label_edge_id_pass"),
    )

    op.create_table(
        "change_pred",
        _id(),
        sa.Column(
            "edge_id",
            sa.BigInteger,
            sa.ForeignKey("alignment_edge.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("p_cosmetic", sa.Double, nullable=False),
        sa.Column("p_rollforward", sa.Double, nullable=False),
        sa.Column("p_substantive", sa.Double, nullable=False),
        sa.Column("boilerplate", sa.Double),
        sa.Column("alert_score", sa.Double),
        _created_at(),
        sa.UniqueConstraint("edge_id", "model_version", name="uq_change_pred_edge_id_model_version"),
    )

    op.create_table(
        "numeric_alert",
        _id(),
        sa.Column(
            "edge_id",
            sa.BigInteger,
            sa.ForeignKey("alignment_edge.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("old_value", sa.Double, nullable=False),
        sa.Column("new_value", sa.Double, nullable=False),
        sa.Column("unit", sa.Text, nullable=False),
        sa.Column("rel_change", sa.Double),
        sa.Column("context", sa.Text),
        _created_at(),
    )

    op.create_table(
        "alert",
        _id(),
        sa.Column(
            "filing_id",
            sa.BigInteger,
            sa.ForeignKey("filing.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "edge_id",
            sa.BigInteger,
            sa.ForeignKey("alignment_edge.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "numeric_alert_id",
            sa.BigInteger,
            sa.ForeignKey("numeric_alert.id", ondelete="CASCADE"),
        ),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("alert_score", sa.Double),
        sa.Column("summary", sa.Text),
        sa.Column("summary_model", sa.Text),
        _created_at(),
        sa.CheckConstraint("kind IN ('text', 'numeric')", name="ck_alert_kind"),
    )
    op.create_index("ix_alert_filing_id_kind_rank", "alert", ["filing_id", "kind", "rank"])


def downgrade() -> None:
    op.drop_table("alert")
    op.drop_table("numeric_alert")
    op.drop_table("change_pred")
    op.drop_table("change_label")
    op.drop_table("alignment_edge")
    op.drop_table("alignment_pair")
    op.drop_table("paragraph")
    op.drop_table("filing")
    op.drop_table("company")
