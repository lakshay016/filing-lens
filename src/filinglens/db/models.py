"""Slice-1 tables (SPEC §12). Chain, version, fact and trace tables arrive in slice 2."""

from __future__ import annotations

import datetime as dt
from typing import Any

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Identity
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NOW = sa.text("now()")


def _in(column: str, values: tuple[str, ...] | tuple[int, ...]) -> str:
    listed = ", ".join(repr(v) for v in values)
    return f"{column} IN ({listed})"


def _created_at() -> Mapped[dt.datetime]:
    return mapped_column(sa.DateTime(timezone=True), server_default=NOW)


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "company"

    cik: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(sa.Text)
    ticker: Mapped[str | None] = mapped_column(sa.Text)
    sic: Mapped[str | None] = mapped_column(sa.Text)
    sector: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[dt.datetime] = _created_at()


class Filing(Base):
    __tablename__ = "filing"
    __table_args__ = (
        sa.CheckConstraint(
            _in("fetch_status", ("pending", "ok", "failed", "skipped")),
            name="ck_filing_fetch_status",
        ),
        sa.CheckConstraint(
            _in("parse_status", ("ok", "partial", "failed")), name="ck_filing_parse_status"
        ),
        sa.Index("ix_filing_cik_fiscal_year", "cik", "fiscal_year"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, Identity(always=True), primary_key=True)
    cik: Mapped[int] = mapped_column(sa.BigInteger, ForeignKey("company.cik"))
    accession: Mapped[str] = mapped_column(sa.Text, unique=True)
    form: Mapped[str] = mapped_column(sa.Text)
    period_of_report: Mapped[dt.date | None] = mapped_column(sa.Date)
    fiscal_year: Mapped[int | None] = mapped_column(sa.Integer)
    filed_date: Mapped[dt.date] = mapped_column(sa.Date)
    accepted_at: Mapped[dt.datetime | None] = mapped_column(sa.DateTime(timezone=True))
    primary_document: Mapped[str] = mapped_column(sa.Text)
    raw_sha256: Mapped[str | None] = mapped_column(sa.Text)
    raw_bytes: Mapped[int | None] = mapped_column(sa.Integer)
    fetch_status: Mapped[str] = mapped_column(sa.Text, server_default="pending")
    fetch_error: Mapped[str | None] = mapped_column(sa.Text)
    parse_status: Mapped[str | None] = mapped_column(sa.Text)
    parse_notes: Mapped[Any | None] = mapped_column(pg.JSONB)
    parser_version: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[dt.datetime] = _created_at()


class Paragraph(Base):
    __tablename__ = "paragraph"
    __table_args__ = (
        sa.UniqueConstraint("filing_id", "seq", name="uq_paragraph_filing_id_seq"),
        sa.Index("ix_paragraph_filing_id_item_seq", "filing_id", "item", "seq"),
        sa.Index("ix_paragraph_masked_hash", "masked_hash"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, Identity(always=True), primary_key=True)
    filing_id: Mapped[int] = mapped_column(
        sa.BigInteger, ForeignKey("filing.id", ondelete="CASCADE")
    )
    item: Mapped[str] = mapped_column(sa.Text)
    seq: Mapped[int] = mapped_column(sa.Integer)
    heading_path: Mapped[list[str]] = mapped_column(
        pg.ARRAY(sa.Text), server_default=sa.text("'{}'")
    )
    text: Mapped[str] = mapped_column(sa.Text)
    is_table: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    n_tokens: Mapped[int] = mapped_column(sa.Integer)
    exact_hash: Mapped[str] = mapped_column(sa.CHAR(40))
    masked_hash: Mapped[str] = mapped_column(sa.CHAR(40))
    created_at: Mapped[dt.datetime] = _created_at()


class AlignmentPair(Base):
    __tablename__ = "alignment_pair"
    __table_args__ = (
        sa.UniqueConstraint(
            "old_filing_id",
            "new_filing_id",
            "item",
            name="uq_alignment_pair_old_filing_id_new_filing_id_item",
            postgresql_nulls_not_distinct=True,
        ),
        sa.Index("ix_alignment_pair_new_filing_id", "new_filing_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, Identity(always=True), primary_key=True)
    cik: Mapped[int] = mapped_column(sa.BigInteger, ForeignKey("company.cik"))
    old_filing_id: Mapped[int] = mapped_column(
        sa.BigInteger, ForeignKey("filing.id", ondelete="CASCADE")
    )
    new_filing_id: Mapped[int] = mapped_column(
        sa.BigInteger, ForeignKey("filing.id", ondelete="CASCADE")
    )
    item: Mapped[str | None] = mapped_column(sa.Text)  # NULL = whole-document row
    eligible: Mapped[bool] = mapped_column(sa.Boolean)
    exclusion_reason: Mapped[str | None] = mapped_column(sa.Text)
    idf_version: Mapped[str | None] = mapped_column(sa.Text)
    aligner_version: Mapped[str] = mapped_column(sa.Text)
    sim_cosine: Mapped[float | None] = mapped_column(sa.Double)
    sim_jaccard: Mapped[float | None] = mapped_column(sa.Double)
    change_intensity_raw: Mapped[float | None] = mapped_column(sa.Double)
    change_intensity: Mapped[float | None] = mapped_column(sa.Double)
    created_at: Mapped[dt.datetime] = _created_at()


class AlignmentEdge(Base):
    __tablename__ = "alignment_edge"
    __table_args__ = (
        sa.CheckConstraint(
            _in(
                "label",
                (
                    "unchanged",
                    "rollforward",
                    "modified",
                    "moved",
                    "split",
                    "merged",
                    "added",
                    "deleted",
                ),
            ),
            name="ck_alignment_edge_label",
        ),
        sa.Index("ix_alignment_edge_pair_id", "pair_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, Identity(always=True), primary_key=True)
    pair_id: Mapped[int] = mapped_column(
        sa.BigInteger, ForeignKey("alignment_pair.id", ondelete="CASCADE")
    )
    label: Mapped[str] = mapped_column(sa.Text)
    old_paragraph_ids: Mapped[list[int]] = mapped_column(
        pg.ARRAY(sa.BigInteger), server_default=sa.text("'{}'")
    )
    new_paragraph_ids: Mapped[list[int]] = mapped_column(
        pg.ARRAY(sa.BigInteger), server_default=sa.text("'{}'")
    )
    sim: Mapped[float | None] = mapped_column(sa.Double)
    n_ins: Mapped[int] = mapped_column(sa.Integer, server_default="0")
    n_del: Mapped[int] = mapped_column(sa.Integer, server_default="0")
    changed_ratio: Mapped[float] = mapped_column(sa.Double, server_default="0")
    cross_item: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    created_at: Mapped[dt.datetime] = _created_at()


class ChangeLabel(Base):
    __tablename__ = "change_label"
    __table_args__ = (
        sa.CheckConstraint(
            _in(
                "annotation_label",
                (
                    "formatting_reorder",
                    "boilerplate_refresh",
                    "numeric_rollforward",
                    "new_topic",
                    "removed_topic",
                    "substantive_reword",
                ),
            ),
            name="ck_change_label_annotation_label",
        ),
        sa.CheckConstraint(_in("pass", (1, 2)), name="ck_change_label_pass"),
        sa.UniqueConstraint("edge_id", "pass", name="uq_change_label_edge_id_pass"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, Identity(always=True), primary_key=True)
    edge_id: Mapped[int] = mapped_column(
        sa.BigInteger, ForeignKey("alignment_edge.id", ondelete="CASCADE")
    )
    annotation_label: Mapped[str] = mapped_column(sa.Text)
    labelled_at: Mapped[dt.datetime] = mapped_column(sa.DateTime(timezone=True))
    pass_: Mapped[int] = mapped_column("pass", sa.SmallInteger)
    created_at: Mapped[dt.datetime] = _created_at()


class ChangePred(Base):
    __tablename__ = "change_pred"
    __table_args__ = (
        sa.UniqueConstraint(
            "edge_id", "model_version", name="uq_change_pred_edge_id_model_version"
        ),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, Identity(always=True), primary_key=True)
    edge_id: Mapped[int] = mapped_column(
        sa.BigInteger, ForeignKey("alignment_edge.id", ondelete="CASCADE")
    )
    model_version: Mapped[str] = mapped_column(sa.Text)
    p_cosmetic: Mapped[float] = mapped_column(sa.Double)
    p_rollforward: Mapped[float] = mapped_column(sa.Double)
    p_substantive: Mapped[float] = mapped_column(sa.Double)
    boilerplate: Mapped[float | None] = mapped_column(sa.Double)
    alert_score: Mapped[float | None] = mapped_column(sa.Double)
    created_at: Mapped[dt.datetime] = _created_at()


class NumericAlert(Base):
    __tablename__ = "numeric_alert"

    id: Mapped[int] = mapped_column(sa.BigInteger, Identity(always=True), primary_key=True)
    edge_id: Mapped[int] = mapped_column(
        sa.BigInteger, ForeignKey("alignment_edge.id", ondelete="CASCADE")
    )
    old_value: Mapped[float] = mapped_column(sa.Double)
    new_value: Mapped[float] = mapped_column(sa.Double)
    unit: Mapped[str] = mapped_column(sa.Text)  # percent | currency | plain
    rel_change: Mapped[float | None] = mapped_column(sa.Double)  # NULL when old_value = 0
    context: Mapped[str | None] = mapped_column(sa.Text)  # short snippet around the new number
    created_at: Mapped[dt.datetime] = _created_at()


class Alert(Base):
    __tablename__ = "alert"
    __table_args__ = (
        sa.CheckConstraint(_in("kind", ("text", "numeric")), name="ck_alert_kind"),
        sa.Index("ix_alert_filing_id_kind_rank", "filing_id", "kind", "rank"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, Identity(always=True), primary_key=True)
    filing_id: Mapped[int] = mapped_column(
        sa.BigInteger, ForeignKey("filing.id", ondelete="CASCADE")
    )
    edge_id: Mapped[int] = mapped_column(
        sa.BigInteger, ForeignKey("alignment_edge.id", ondelete="CASCADE")
    )
    numeric_alert_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, ForeignKey("numeric_alert.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(sa.Text)
    rank: Mapped[int] = mapped_column(sa.Integer)
    alert_score: Mapped[float | None] = mapped_column(sa.Double)
    summary: Mapped[str | None] = mapped_column(sa.Text)
    summary_model: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[dt.datetime] = _created_at()
