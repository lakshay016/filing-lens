from __future__ import annotations

from datetime import UTC, date, datetime

from filinglens.compare.load import FilingRef, Gap, plan_pairs


def ref(year: int, period: date | None = None, *, cik: int = 1, form: str = "10-K") -> FilingRef:
    return FilingRef(
        filing_id=year,
        cik=cik,
        company="Acme",
        accession=f"0000000001-{year}-000001",
        fiscal_year=year,
        period_of_report=period or date(year, 12, 31),
        filed_date=date(year + 1, 2, 20),
        accepted_at=datetime(year + 1, 2, 20, tzinfo=UTC),
        url="https://www.sec.gov/x",
        form=form,
    )


def test_missing_year_is_a_gap_naming_the_year() -> None:
    plan = plan_pairs([ref(2021), ref(2023)])
    assert len(plan) == 1 and isinstance(plan[0], Gap)
    assert plan[0].reason == "period gap 730 days; FY2022 filing missing"


def test_consecutive_years_make_two_pairs() -> None:
    plan = plan_pairs([ref(2021), ref(2022), ref(2023)])
    assert len(plan) == 2 and all(isinstance(p, tuple) for p in plan)


def test_short_period_is_a_gap() -> None:
    plan = plan_pairs([ref(2021), ref(2022, date(2022, 7, 19))])
    assert len(plan) == 1 and isinstance(plan[0], Gap)
    assert "200 days" in plan[0].reason


def test_bounds_are_inclusive() -> None:
    assert isinstance(
        plan_pairs([ref(2021), ref(2022, date(2021, 12, 31).replace(year=2022))])[0], tuple
    )
    low = plan_pairs([ref(2021, date(2021, 1, 1)), ref(2021, date(2021, 9, 28))])[0]
    assert isinstance(low, tuple)  # 270 days
    high = plan_pairs([ref(2021, date(2021, 1, 1)), ref(2022, date(2022, 4, 6))])[0]
    assert isinstance(high, tuple)  # 460 days
    over = plan_pairs([ref(2021, date(2021, 1, 1)), ref(2022, date(2022, 4, 7))])[0]
    assert isinstance(over, Gap)


def test_amended_form_or_other_company_is_a_gap() -> None:
    assert isinstance(plan_pairs([ref(2021), ref(2022, form="10-K/A")])[0], Gap)
    assert isinstance(plan_pairs([ref(2021), ref(2022, cik=2)])[0], Gap)
    assert isinstance(plan_pairs([ref(2021, form="10-K405"), ref(2022)])[0], tuple)
