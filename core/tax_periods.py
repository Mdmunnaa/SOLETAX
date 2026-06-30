"""
HMRC MTD for Income Tax — UK tax-year & quarterly period helpers.

HMRC's "standard" quarterly update periods for MTD ITSA are fixed to the
UK tax year (6 April -> 5 April), regardless of when a business started
trading. A trader can elect "calendar quarters" instead (aligned to
calendar months) but standard periods are the default and what most
sole traders will use.

This module is intentionally dependency-free (no Django imports) so it
can be unit tested in isolation and reused by the future API submission
code without dragging in the whole app.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date


# Standard quarterly periods within a UK tax year (HMRC default).
# Each tuple is (start_month, start_day, end_month, end_day).
STANDARD_QUARTERS = [
    (4, 6, 7, 5),    # Q1: 6 Apr - 5 Jul
    (7, 6, 10, 5),   # Q2: 6 Jul - 5 Oct
    (10, 6, 1, 5),   # Q3: 6 Oct - 5 Jan (crosses calendar year)
    (1, 6, 4, 5),    # Q4: 6 Jan - 5 Apr
]

# Calendar quarter alternative (taxpayer can elect this with HMRC).
CALENDAR_QUARTERS = [
    (4, 1, 6, 30),
    (7, 1, 9, 30),
    (10, 1, 12, 31),
    (1, 1, 3, 31),
]

# Quarterly update filing deadlines (day after period end + 1 month + 2 days,
# HMRC's actual published deadlines for standard periods).
STANDARD_DEADLINES = ['08-07', '11-07', '02-07', '05-07']  # MM-DD, year-relative


def tax_year_start(for_date: date) -> int:
    """
    Return the starting year of the UK tax year containing `for_date`.
    E.g. 2026-04-06 .. 2027-04-05 is tax year "2026" (commonly written 2026/27).
    """
    if (for_date.month, for_date.day) >= (4, 6):
        return for_date.year
    return for_date.year - 1


def tax_year_label(start_year: int) -> str:
    """e.g. 2026 -> '2026-27'"""
    return f"{start_year}-{str(start_year + 1)[-2:]}"


@dataclass(frozen=True)
class Quarter:
    tax_year_start_year: int
    index: int          # 1-4
    period_start: date
    period_end: date
    deadline: date

    @property
    def label(self) -> str:
        return f"Q{self.index} {tax_year_label(self.tax_year_start_year)}"

    @property
    def period_key(self) -> str:
        """Stable machine key, e.g. '2026-27-Q1'. Used as a DB index value."""
        return f"{tax_year_label(self.tax_year_start_year)}-Q{self.index}"


def quarters_for_tax_year(start_year: int, calendar: bool = False) -> list[Quarter]:
    """Build all 4 Quarter objects for a given UK tax year start year."""
    defs = CALENDAR_QUARTERS if calendar else STANDARD_QUARTERS
    quarters = []
    for i, (sm, sd, em, ed) in enumerate(defs, start=1):
        # Period start is always within start_year unless it's before 4 Apr
        period_start_year = start_year if sm >= 4 else start_year + 1
        period_end_year = start_year if em >= sm and sm >= 4 else (
            start_year + 1 if em < sm else start_year
        )
        # Special-case Q3 standard period which crosses into next calendar year
        if not calendar and i == 3:
            period_start_year = start_year
            period_end_year = start_year + 1
        elif not calendar and i == 4:
            period_start_year = start_year + 1
            period_end_year = start_year + 1
        elif not calendar:
            period_start_year = start_year
            period_end_year = start_year

        period_start = date(period_start_year, sm, sd)
        period_end = date(period_end_year, em, ed)

        # Deadline: 1 calendar month + a few days after period end (HMRC standard)
        if not calendar:
            deadline_str = STANDARD_DEADLINES[i - 1]
            dl_month, dl_day = map(int, deadline_str.split('-'))
            deadline_year = period_end_year if dl_month >= em else period_end_year + 1
            # Quarters ending in Jan/Apr need deadline pushed to next year correctly
            if i in (3, 4):
                deadline_year = period_end_year + (1 if dl_month < em else 0)
                if i == 3:
                    deadline_year = period_end_year  # Q3 ends Jan, deadline Feb same year
                if i == 4:
                    deadline_year = period_end_year  # Q4 ends Apr, deadline May same year
            else:
                deadline_year = period_end_year
            deadline = date(deadline_year, dl_month, dl_day)
        else:
            # Calendar quarters: deadline is last day of month after quarter end
            deadline = date(period_end.year + (1 if em == 12 else 0),
                             (em % 12) + 1, 7)

        quarters.append(Quarter(
            tax_year_start_year=start_year,
            index=i,
            period_start=period_start,
            period_end=period_end,
            deadline=deadline,
        ))
    return quarters


def quarter_for_date(d: date, calendar: bool = False) -> Quarter:
    """Find which quarterly period a given date falls into."""
    ty_start = tax_year_start(d)
    for q in quarters_for_tax_year(ty_start, calendar=calendar):
        if q.period_start <= d <= q.period_end:
            return q
    # Fallback — shouldn't happen if quarters are built correctly
    raise ValueError(f"Could not resolve quarter for date {d}")


def current_quarter(today: date | None = None, calendar: bool = False) -> Quarter:
    return quarter_for_date(today or date.today(), calendar=calendar)


def all_quarters_to_date(start_year: int, today: date | None = None,
                          calendar: bool = False) -> list[Quarter]:
    """All quarters in a tax year whose period_end has already passed (or today)."""
    today = today or date.today()
    return [q for q in quarters_for_tax_year(start_year, calendar=calendar)
            if q.period_start <= today]
