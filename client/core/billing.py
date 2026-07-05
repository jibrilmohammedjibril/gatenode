from __future__ import annotations

import calendar
from datetime import datetime


RENT_BILL_TYPE = "rent"
SERVICE_CHARGE_BILL_TYPE = "service_charge"
BILL_BILL_TYPE = "bill"
MANUAL_GENERATION_SOURCE = "manual"
RECURRING_GENERATION_SOURCE = "recurring"
ANNUAL_APP_CHARGE_KOBO = 1_200_000

SUPPORTED_BILL_TYPES = {
    BILL_BILL_TYPE,
    RENT_BILL_TYPE,
    SERVICE_CHARGE_BILL_TYPE,
}

SUPPORTED_GENERATION_SOURCES = {
    MANUAL_GENERATION_SOURCE,
    RECURRING_GENERATION_SOURCE,
}

TITLE_PREFIXES = {
    BILL_BILL_TYPE: "[BILL]",
    RENT_BILL_TYPE: "[RENT]",
    SERVICE_CHARGE_BILL_TYPE: "[SERVICE_CHARGE]",
}

DEFAULT_TITLES = {
    BILL_BILL_TYPE: "Bill",
    RENT_BILL_TYPE: "Rent",
    SERVICE_CHARGE_BILL_TYPE: "Service Charge",
}

LEGACY_KEYWORDS = {
    BILL_BILL_TYPE: ("estate bill", "property bill"),
    RENT_BILL_TYPE: ("rent",),
    SERVICE_CHARGE_BILL_TYPE: ("service charge",),
}

DURATION_MONTHS = {
    "monthly": 1,
    "bi_monthly": 2,
    "quarterly": 3,
    "half_yearly": 6,
    "yearly": 12,
}

SUPPORTED_RECURRING_DURATIONS = set(DURATION_MONTHS)


def normalize_bill_type(value: str | None) -> str:
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in SUPPORTED_BILL_TYPES:
        raise ValueError("Unsupported bill type")
    return normalized


def normalize_generation_source(value: str | None) -> str:
    if hasattr(value, "value"):
        value = value.value
    normalized = (value or "").strip().lower()
    if normalized not in SUPPORTED_GENERATION_SOURCES:
        raise ValueError("Unsupported generation source")
    return normalized


def normalize_duration(value: str | None) -> str:
    if hasattr(value, "value"):
        value = value.value
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in SUPPORTED_RECURRING_DURATIONS:
        raise ValueError("Unsupported duration")
    return normalized


def duration_months(value: str | None) -> int:
    return DURATION_MONTHS[normalize_duration(value)]


def cycle_app_charge_kobo(duration: str | None) -> int:
    return (ANNUAL_APP_CHARGE_KOBO // 12) * duration_months(duration)


def add_months(value: datetime, months: int) -> datetime:
    total_month = (value.month - 1) + months
    year = value.year + (total_month // 12)
    month = (total_month % 12) + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def advance_cycle_date(value: datetime, duration: str | None) -> datetime:
    return add_months(value, duration_months(duration))


def _month_abbrev(month: int) -> str:
    return calendar.month_abbr[month]


def recurring_cycle_label(due_date: datetime, duration: str | None) -> str:
    normalized = normalize_duration(duration)
    if normalized == "monthly":
        return due_date.strftime("%b %Y")
    if normalized == "bi_monthly":
        end_date = add_months(due_date, 1)
        if due_date.year == end_date.year:
            return f"{_month_abbrev(due_date.month)}-{_month_abbrev(end_date.month)} {due_date.year}"
        return f"{_month_abbrev(due_date.month)} {due_date.year}-{_month_abbrev(end_date.month)} {end_date.year}"
    if normalized == "quarterly":
        quarter = ((due_date.month - 1) // 3) + 1
        return f"Q{quarter} {due_date.year}"
    if normalized == "half_yearly":
        half = 1 if due_date.month <= 6 else 2
        return f"H{half} {due_date.year}"
    return due_date.strftime("%Y")


def bill_title_prefix(bill_type: str) -> str:
    return TITLE_PREFIXES[normalize_bill_type(bill_type)]


def default_bill_title(bill_type: str) -> str:
    return DEFAULT_TITLES[normalize_bill_type(bill_type)]


def build_bill_title(bill_type: str, title: str | None = None) -> str:
    normalized = normalize_bill_type(bill_type)
    label = (title or DEFAULT_TITLES[normalized]).strip()
    prefix = TITLE_PREFIXES[normalized]

    if label.upper().startswith(prefix):
        trimmed = label[len(prefix):].strip()
        return f"{prefix} {trimmed or DEFAULT_TITLES[normalized]}"

    return f"{prefix} {label}"


def build_recurring_bill_title(
    bill_type: str,
    due_date: datetime,
    *,
    title: str | None = None,
    duration: str | None = None,
) -> str:
    label = title or default_bill_title(bill_type)
    cycle_label = recurring_cycle_label(due_date, duration or "monthly")
    return build_bill_title(bill_type, f"{label} - {cycle_label}")


def infer_bill_type(title: str | None) -> str | None:
    normalized_title = (title or "").strip()
    if not normalized_title:
        return None

    upper_title = normalized_title.upper()
    for bill_type, prefix in TITLE_PREFIXES.items():
        if upper_title.startswith(prefix):
            return bill_type

    lowered_title = normalized_title.lower()
    for bill_type, keywords in LEGACY_KEYWORDS.items():
        if any(keyword in lowered_title for keyword in keywords):
            return bill_type

    return None


def display_bill_title(title: str | None) -> str:
    normalized_title = (title or "").strip()
    if not normalized_title:
        return ""

    upper_title = normalized_title.upper()
    for bill_type, prefix in TITLE_PREFIXES.items():
        if upper_title.startswith(prefix):
            trimmed = normalized_title[len(prefix):].strip()
            return trimmed or DEFAULT_TITLES[bill_type]

    return normalized_title


def display_bill_transaction_text(text: str | None) -> str:
    normalized_text = (text or "").strip()
    if not normalized_text:
        return ""

    paid_bill_prefix = "Paid Bill:"
    if normalized_text.lower().startswith(paid_bill_prefix.lower()):
        raw_title = normalized_text[len(paid_bill_prefix):].strip()
        bill_type = infer_bill_type(raw_title)
        title = display_bill_title(raw_title)
        if title.lower() == "multi-assignment payment":
            title = f"{default_bill_title(bill_type) if bill_type else 'Bill'} payment"
        return f"{paid_bill_prefix} {title or 'Bill'}"

    return display_bill_title(normalized_text)


def assignment_total_amount_kobo(assignment) -> int:
    assignment_total = getattr(assignment, "total_amount", None)
    if assignment_total is not None:
        return int(assignment_total or 0)
    bill = getattr(assignment, "bill", None)
    return int(getattr(bill, "total_amount", 0) or 0)


def assignment_base_amount_kobo(assignment) -> int:
    assignment_base = getattr(assignment, "base_amount", None)
    if assignment_base is not None:
        return int(assignment_base or 0)
    return assignment_total_amount_kobo(assignment)


def assignment_app_charge_amount_kobo(assignment) -> int:
    assignment_app_charge = getattr(assignment, "app_charge_amount", None)
    if assignment_app_charge is not None:
        return int(assignment_app_charge or 0)
    return 0
