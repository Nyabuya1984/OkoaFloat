"""Pure aggregations for the additive Sales Reports V2 API.

The functions accept ``SalesDailyReport`` instances or their ``to_dict``
representations. They do not query, mutate, or depend on Flask application
state, which keeps the first V2 slice safe to test independently.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta


DOCUMENT_REQUIREMENTS = {
    "agent": {"certificate_of_incorporation", "company_kra_pin", "six_months_commission", "owners_directors_national_ids", "cr12_directors"},
    "sub_agent": {"business_permit", "individual_kra_pin", "six_months_commission", "subagent_agent_contract", "owner_national_id", "sign_contract"},
}
DOCUMENT_ALIASES = {
    "individual_kra_pin": "kra_pin",
    "six_months_commission": "commission_statement",
    "subagent_agent_contract": "contract",
    "owner_national_id": "national_id",
    "certificate_of_incorporation": "incorporation_certificate",
    "owners_directors_national_ids": "national_id",
    "cr12_directors": "cr12",
}
OUTCOME_KEYS = ("interested", "not_interested", "ready_to_register", "appointment", "registered", "undecided")


def _value(report, name, default=None):
    if isinstance(report, dict):
        return report.get(name, default)
    return getattr(report, name, default)


def _payload(report):
    data = _value(report, "report_data", {}) or {}
    return data if isinstance(data, dict) else {}


def _field(report, name, default=None):
    value = _value(report, name, None)
    return default if value is None else value


def _report_value(report, name, default=None):
    value = _value(report, name, None)
    if value is not None:
        return value
    return _payload(report).get(name, default)


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None
    return None


def _as_int(value, default=0):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _name(report):
    return _field(report, "employee_name") or _field(report, "agent_name") or "Unknown"


def _outcome(report):
    value = str(_field(report, "outcome", "") or "").strip().lower().replace(" ", "_")
    aliases = {"not interested": "not_interested", "ready": "ready_to_register"}
    return aliases.get(value, value)


def _is_registration(report):
    status = str(_report_value(report, "registration_status", "") or "").lower()
    return _outcome(report) == "registered" or status in {"complete", "partial"}


def _in_range(report, from_date=None, to_date=None):
    visited = _as_date(_field(report, "date_visited") or _field(report, "visit_date"))
    start = _as_date(from_date)
    end = _as_date(to_date)
    return visited is not None and (start is None or visited >= start) and (end is None or visited <= end)


def _rows(reports, from_date=None, to_date=None):
    return [report for report in reports or [] if _in_range(report, from_date, to_date)]


def _row(report):
    return {
        "id": _field(report, "id"),
        "employee_id": _field(report, "employee_id") or _field(report, "visited_by"),
        "employee_name": _name(report),
        "agent_name": _field(report, "agent_name"),
        "department": _field(report, "department"),
        "business_location": _field(report, "business_location"),
        "customer_type": _field(report, "customer_type") or _field(report, "category"),
        "outcome": _field(report, "outcome"),
        "date_visited": (_as_date(_field(report, "date_visited") or _field(report, "visit_date")) or date.today()).isoformat(),
        "registration_status": _report_value(report, "registration_status"),
        "appointment_date": _report_value(report, "appointment_date"),
        "referral_name": _report_value(report, "referral_name"),
    }


def _result(rows, summary_data=None, page=1, per_page=25):
    start = max(0, (page - 1) * per_page)
    selected = rows[start:start + per_page]
    return {
        "summary": summary_data or {"total": len(rows)},
        "rows": [row if isinstance(row, dict) else _row(row) for row in selected],
        "page": page,
        "per_page": per_page,
        "total_rows": len(rows),
    }


def summary(reports, today=None, expected_today=0, from_date=None, to_date=None):
    """Return headline totals and common dimensions for a report collection."""
    rows = _rows(reports, from_date, to_date)
    today_value = _as_date(today) or date.today()
    filed_today = sum(1 for report in rows if _as_date(_field(report, "date_visited")) == today_value)
    agents = defaultdict(lambda: {"visits": 0, "registrations": 0, "name": "Unknown"})
    categories = Counter()
    outcomes = Counter()
    for report in rows:
        agent_id = _field(report, "employee_id") or _field(report, "visited_by")
        bucket = agents[agent_id]
        bucket["name"] = _name(report)
        bucket["visits"] += 1
        bucket["registrations"] += int(_is_registration(report))
        categories[str(_field(report, "customer_type") or _field(report, "category") or "unknown").lower()] += 1
        outcomes[_outcome(report) or "unknown"] += 1
    return {
        "summary": {"total": len(rows), "filed_today": filed_today, "expected_today": expected_today},
        "by_agent": [{"agent_id": agent_id, **values} for agent_id, values in agents.items()],
        "by_category": dict(categories),
        "by_outcome": {key: outcomes.get(key, 0) for key in OUTCOME_KEYS},
    }


def daily_submissions(reports, days=30, end_date=None, page=1, per_page=25):
    """Group submissions by visit date, including zero-submission days."""
    end = _as_date(end_date) or date.today()
    start = end - timedelta(days=max(0, _as_int(days, 30) - 1))
    counts = Counter(_as_date(_field(report, "date_visited")) for report in reports or [])
    rows = [{"date": (start + timedelta(days=index)).isoformat(), "submissions": counts.get(start + timedelta(days=index), 0)} for index in range((end - start).days + 1)]
    return _result(rows, {"total": sum(item["submissions"] for item in rows), "days": len(rows)}, page, per_page)


def funnel(reports, from_date=None, to_date=None, page=1, per_page=25):
    """Count each supported outcome and expose the underlying visit rows."""
    rows = _rows(reports, from_date, to_date)
    counts = Counter(_outcome(report) for report in rows)
    return _result(rows, {"total": len(rows), "by_outcome": {key: counts.get(key, 0) for key in OUTCOME_KEYS}}, page, per_page)


def compliance(reports, from_date=None, to_date=None, expected_per_day=0, page=1, per_page=25):
    """Summarize filing compliance by agent without assuming a client target."""
    rows = _rows(reports, from_date, to_date)
    by_agent = defaultdict(lambda: {"name": "Unknown", "submitted": 0})
    for report in rows:
        agent_id = _field(report, "employee_id") or _field(report, "visited_by")
        by_agent[agent_id]["name"] = _name(report)
        by_agent[agent_id]["submitted"] += 1
    expected = len(by_agent) * max(0, _as_int(expected_per_day))
    return _result([{"agent_id": key, **value} for key, value in by_agent.items()], {"total": len(rows), "expected": expected, "filed": len(rows), "rate": round(len(rows) / expected * 100, 2) if expected else None}, page, per_page)


def registrations(reports, from_date=None, to_date=None, page=1, per_page=25):
    """Group registrations by completion status and retain visit detail."""
    rows = _rows(reports, from_date, to_date)
    statuses = Counter(
        "complete" if str(_report_value(report, "registration_status", "none") or "none").lower() == "complete"
        else "partial" if str(_report_value(report, "registration_status", "none") or "none").lower() in {"partial", "incomplete"}
        else "none"
        for report in rows
    )
    return _result(rows, {"total": len(rows), "complete": statuses.get("complete", 0), "partial": statuses.get("partial", 0), "none": statuses.get("none", 0)}, page, per_page)


def locations(reports, from_date=None, to_date=None, limit=10, page=1, per_page=25):
    """Rank visit locations by visits and registrations."""
    buckets = defaultdict(lambda: {"visits": 0, "registrations": 0})
    for report in _rows(reports, from_date, to_date):
        location = _field(report, "business_location") or "Unknown"
        buckets[location]["visits"] += 1
        buckets[location]["registrations"] += int(_is_registration(report))
    ranked = [{"location": name, **values} for name, values in buckets.items()]
    ranked.sort(key=lambda item: (-item["visits"], item["location"]))
    return _result(ranked[:max(0, _as_int(limit, 10))], {"total": len(ranked), "top_locations": ranked[:max(0, _as_int(limit, 10))]}, page, per_page)


def top_performers(reports, from_date=None, to_date=None, limit=10, page=1, per_page=25):
    """Rank agents by visits, then registrations, then name."""
    buckets = defaultdict(lambda: {"name": "Unknown", "visits": 0, "registrations": 0})
    for report in _rows(reports, from_date, to_date):
        agent_id = _field(report, "employee_id") or _field(report, "visited_by")
        buckets[agent_id]["name"] = _name(report)
        buckets[agent_id]["visits"] += 1
        buckets[agent_id]["registrations"] += int(_is_registration(report))
    ranked = [{"agent_id": key, **values} for key, values in buckets.items()]
    ranked.sort(key=lambda item: (-item["registrations"], -item["visits"], item["name"]))
    ranked = ranked[:max(0, _as_int(limit, 10))]
    return _result(ranked, {"total": len(buckets), "top_performers": ranked}, page, per_page)


def document_gaps(reports, from_date=None, to_date=None, document_type=None, page=1, per_page=25):
    """Return reports missing required documents for their customer type."""
    gaps = []
    for report in _rows(reports, from_date, to_date):
        customer_type = str(_field(report, "customer_type") or "").lower()
        documents = _value(report, "documents", {}) or {}
        documents.update(_payload(report).get("documents", {}) or {})
        required = DOCUMENT_REQUIREMENTS.get(customer_type, set())
        missing = [name for name in sorted(required) if not documents.get(name) and not documents.get(DOCUMENT_ALIASES.get(name, ""))]
        if document_type:
            missing = [name for name in missing if name == document_type]
        if missing:
            gaps.append({**_row(report), "missing_documents": missing})
    return _result(gaps, {"total": len(gaps), "missing": sum(len(row["missing_documents"]) for row in gaps)}, page, per_page)


def regions(reports, from_date=None, to_date=None, page=1, per_page=25):
    """Aggregate visits by the existing business location field."""
    return locations(reports, from_date, to_date, limit=10_000, page=page, per_page=per_page)


def integrity(reports):
    """Detect duplicate visit keys and malformed records without changing data."""
    rows = list(reports or [])
    keys = Counter((_field(report, "employee_id") or _field(report, "visited_by"), _field(report, "agent_name"), _field(report, "date_visited")) for report in rows)
    duplicates = [{"key": list(key), "count": count} for key, count in keys.items() if count > 1]
    missing_required = [
        _field(report, "id")
        for report in rows
        if not _field(report, "agent_name") or not (_field(report, "date_visited") or _field(report, "visit_date"))
    ]
    return {"summary": {"total": len(rows), "duplicate_groups": len(duplicates), "missing_required": len(missing_required)}, "duplicates": duplicates, "missing_required": missing_required}