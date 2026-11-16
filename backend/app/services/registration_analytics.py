"""Pure calculations for M-Pesa registration analytics."""

from collections import defaultdict
from datetime import date, datetime


DOCUMENT_REQUIREMENTS = {
    "sub_agent": (
        "business_permit",
        "individual_kra_pin",
        "six_months_commission",
        "subagent_agent_contract",
        "owner_national_id",
        "sign_contract",
    ),
    "agent": (
        "certificate_of_incorporation",
        "company_kra_pin",
        "six_months_commission",
        "owners_directors_national_ids",
        "cr12_directors",
    ),
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
DOCUMENT_LABELS = {
    "business_permit": "Business permit",
    "individual_kra_pin": "Individual KRA PIN",
    "six_months_commission": "Six months commission statement",
    "subagent_agent_contract": "Sub-agent agent contract",
    "owner_national_id": "Owner national ID",
    "sign_contract": "Signed contract",
    "certificate_of_incorporation": "Certificate of incorporation",
    "company_kra_pin": "Company KRA PIN",
    "owners_directors_national_ids": "Owners/directors national IDs",
    "cr12_directors": "CR12 directors",
}
WITNESS_REQUIREMENTS = ("witness_name", "witness_id_number", "witness_phone")
WITNESS_LABELS = {
    "witness_name": "Witness name",
    "witness_id_number": "Witness ID number",
    "witness_phone": "Witness phone",
}
TRUE_VALUES = {"1", "true", "yes", "y"}
FALSE_VALUES = {"0", "false", "no", "n", ""}


def as_bool(value):
    """Parse JSON booleans and common form encodings; unknowns are false."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    normalized = str(value).strip().lower()
    return normalized in TRUE_VALUES if normalized in TRUE_VALUES | FALSE_VALUES else False


def _explicit_false(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value == 0
    return str(value).strip().lower() in {"0", "false", "no", "n"}


def _value(report, key, default=None):
    if isinstance(report, dict):
        return report.get(key, default)
    return getattr(report, key, default)


def report_data(report):
    value = _value(report, "report_data", {})
    return value if isinstance(value, dict) else {}


def date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except (TypeError, ValueError):
        return None


def category_of(report):
    category = str(_value(report, "customer_type", "") or "").strip().lower()
    return category if category in DOCUMENT_REQUIREMENTS else "unknown"


def applicable_documents(category):
    return DOCUMENT_REQUIREMENTS.get(category, ())


def document_submitted(report, key):
    documents = _value(report, "documents", {})
    if not isinstance(documents, dict):
        documents = {}
    alias = DOCUMENT_ALIASES.get(key)
    # A canonical or known alias is evidence only when explicitly truthy.
    return as_bool(documents.get(key)) or (bool(alias) and as_bool(documents.get(alias)))


def is_existing(report):
    data = report_data(report)
    client_type = str(data.get("client_type") or "").strip().lower()
    return (
        str(_value(report, "outcome", "") or "").strip().lower() == "existing"
        or ("new_client" in data and _explicit_false(data.get("new_client")))
        or as_bool(data.get("already_uses_okoa"))
        or client_type in {"existing", "existing_client", "existing-client"}
    )


def registration_started(report):
    data = report_data(report)
    return (
        str(_value(report, "outcome", "") or "").strip().lower()
        in {"ready_to_register", "registered"}
        or bool(str(data.get("registration_status") or "").strip())
        or date_value(_value(report, "registration_date")) is not None
    )


def missing_requirements(report):
    category = category_of(report)
    missing = ["customer_type"] if category not in DOCUMENT_REQUIREMENTS else []
    missing.extend(
        key for key in applicable_documents(category)
        if not document_submitted(report, key)
    )
    for key in WITNESS_REQUIREMENTS:
        if not str(_value(report, key, "") or "").strip():
            missing.append(key)
    return missing


def registration_status(report):
    if not registration_started(report):
        return "not_started"
    return "complete" if not missing_requirements(report) else "incomplete"


def is_eligible(report):
    return not is_existing(report)


def is_outstanding_followup(report):
    data = report_data(report)
    return (
        str(_value(report, "outcome", "") or "").strip().lower() == "appointment"
        or bool(str(data.get("appointment_date") or "").strip())
        or bool(str(data.get("follow_up_details") or "").strip())
    )


def _metrics(reports):
    eligible = [report for report in reports if is_eligible(report)]
    statuses = [registration_status(report) for report in eligible]
    visited = len(eligible)
    started = sum(status != "not_started" for status in statuses)
    complete = statuses.count("complete")
    incomplete = statuses.count("incomplete")
    not_started = statuses.count("not_started")
    outstanding = sum(is_outstanding_followup(report) for report in eligible)

    def rate(numerator, denominator):
        return round(numerator * 100 / denominator, 2) if denominator else 0

    return {
        "visited": visited,
        "started": started,
        "complete": complete,
        "incomplete": incomplete,
        "total_registrations": complete + incomplete,
        "unconverted": visited - started,
        "outstanding_followups": outstanding,
        "not_started": not_started,
        "conversion_rate": rate(started, visited),
        "completion_rate": rate(complete, started),
        "visit_to_complete_rate": rate(complete, visited),
        "incomplete_rate": rate(incomplete, started),
    }


def _aggregation_rows(reports, key_for_report, include_category=False):
    groups = defaultdict(list)
    for report in reports:
        if not is_eligible(report):
            continue
        key = key_for_report(report)
        if key is not None:
            groups[key].append(report)

    rows = []
    for key in sorted(groups):
        group = groups[key]
        metrics = _metrics(group)
        if include_category:
            visit_date, category = key
            dt = date_value(visit_date)
            rows.append({
                "date": visit_date,
                "weekday": dt.strftime("%A") if dt else None,
                "month_label": dt.strftime("%B %Y") if dt else None,
                "category": category,
                **metrics,
            })
        else:
            rows.append({"period": key, **metrics})
    return rows


def _visit_period(report, period):
    visited = date_value(_value(report, "date_visited"))
    if not visited:
        return None
    if period == "daily":
        return visited.isoformat(), category_of(report)
    if period == "monthly":
        return visited.strftime("%Y-%m")
    return visited.strftime("%Y")


def calculate_employee_performance(employees, reports, from_date=None, to_date=None, category=None):
    """Rank sales employees by complete registrations completed in the selected period."""
    roster = {
        int(_value(employee, "id")): {
            "employee_id": int(_value(employee, "id")),
            "employee_name": _value(employee, "full_name") or "Unnamed employee",
            "complete": 0,
            "agent_complete": 0,
            "sub_agent_complete": 0,
        }
        for employee in employees
    }
    for report in reports:
        employee_id = _value(report, "employee_id")
        if employee_id is not None:
            employee_id = int(employee_id)
        if employee_id not in roster or registration_status(report) != "complete":
            continue
        completed_on = date_value(_value(report, "completion_date"))
        if not completed_on or (from_date and completed_on < from_date) or (to_date and completed_on > to_date):
            continue
        report_category = category_of(report)
        if category and report_category != category:
            continue
        row = roster[employee_id]
        row["complete"] += 1
        if report_category == "sub_agent":
            row["sub_agent_complete"] += 1
        elif report_category == "agent":
            row["agent_complete"] += 1

    rows = list(roster.values())
    counts = [row["complete"] for row in rows]
    team_average = sum(counts) / len(counts) if counts else 0
    rank_by_count = {
        count: rank
        for rank, count in enumerate(sorted(set(counts), reverse=True), start=1)
    }
    for row in rows:
        row["rank"] = rank_by_count[row["complete"]]
        if row["complete"] > team_average:
            row["performance"] = "above_average"
        elif row["complete"] < team_average:
            row["performance"] = "needs_support"
        else:
            row["performance"] = "at_average"
    rows.sort(key=lambda row: (-row["complete"], row["employee_name"].casefold(), row["employee_id"]))

    return {
        "total_complete": sum(counts),
        "agent_complete": sum(row["agent_complete"] for row in rows),
        "sub_agent_complete": sum(row["sub_agent_complete"] for row in rows),
        "team_average": round(team_average, 2),
        "employee_count": len(rows),
        "rows": rows,
    }


def _document_rows(reports):
    started = [report for report in reports if is_eligible(report) and registration_started(report)]
    rows = []
    for category, requirements in DOCUMENT_REQUIREMENTS.items():
        applicable_rows = [report for report in started if category_of(report) == category]
        for key in requirements:
            applicable = len(applicable_rows)
            submitted = sum(document_submitted(report, key) for report in applicable_rows)
            rows.append({
                "key": key,
                "label": DOCUMENT_LABELS.get(key, key.replace("_", " ").title()),
                "category": category,
                "category_label": "Sub-agent" if category == "sub_agent" else category.replace("_", " ").title(),
                "applicable": applicable,
                "submitted": submitted,
                "pending": applicable - submitted,
                "rate": round(submitted * 100 / applicable, 2) if applicable else 0,
                "submission_rate": round(submitted * 100 / applicable, 2) if applicable else 0,
                "priority": "required",
            })
    for key in WITNESS_REQUIREMENTS:
        applicable = len(started)
        submitted = sum(bool(str(_value(report, key, "") or "").strip()) for report in started)
        rows.append({
            "key": key,
            "label": WITNESS_LABELS[key],
            "category": "all",
            "category_label": "All categories",
            "applicable": applicable,
            "submitted": submitted,
            "pending": applicable - submitted,
            "rate": round(submitted * 100 / applicable, 2) if applicable else 0,
            "submission_rate": round(submitted * 100 / applicable, 2) if applicable else 0,
            "priority": "required",
        })
    return rows


def calculate_registration_analytics(reports):
    """Build analytics from already-filtered SalesDailyReport rows."""
    eligible = [report for report in reports if is_eligible(report)]
    daily = _aggregation_rows(
        eligible,
        lambda report: _visit_period(report, "daily"),
        include_category=True,
    )
    categories = []
    for category in sorted({category_of(report) for report in eligible}):
        categories.append({
            "category": category,
            "label": "Sub-agent" if category == "sub_agent" else category.replace("_", " ").title(),
            **_metrics([row for row in eligible if category_of(row) == category]),
        })

    monthly = _aggregation_rows(
        eligible,
        lambda report: _visit_period(report, "monthly"),
    )
    yearly = _aggregation_rows(
        eligible,
        lambda report: _visit_period(report, "yearly"),
    )
    for row in monthly:
        row["month"] = row.pop("period")
        try:
            row["month_label"] = datetime.strptime(row["month"], "%Y-%m").strftime("%B %Y")
        except ValueError:
            row["month_label"] = row["month"]
    for row in yearly:
        row["year"] = row.pop("period")
    totals = _metrics(eligible)
    statuses_count = {
        "complete": totals["complete"],
        "incomplete": totals["incomplete"],
        "not_started": totals["not_started"],
    }
    denominator = totals["visited"]
    status_rows = []
    for status, count in statuses_count.items():
        if status == "complete":
            missing, action = [], "Registration is complete."
        elif status == "incomplete":
            missing_counts = defaultdict(int)
            for report in eligible:
                if registration_status(report) == "incomplete":
                    for requirement in missing_requirements(report):
                        missing_counts[requirement] += 1
            missing = [
                {"key": key, "count": count}
                for key, count in sorted(missing_counts.items(), key=lambda item: (-item[1], item[0]))
            ]
            action = "Collect all missing required documents and witness details."
        else:
            missing, action = ["registration start"], "Begin registration or record a follow-up."
        status_rows.append({
            "status": status,
            "count": count,
            "percent": round(count * 100 / denominator, 2) if denominator else 0,
            "missing_requirements": missing,
            "recommended_action": action,
        })
    return {
        "daily": {"rows": daily, "totals": totals},
        "categories": {"rows": categories, "totals": totals},
        "monthly": {"rows": monthly, "totals": totals},
        "yearly": {"rows": yearly, "totals": totals},
        "documents": _document_rows(eligible),
        "statuses": {"rows": status_rows, "totals": totals},
        "funnel": {
            "visited": totals["visited"],
            "started": totals["started"],
            "complete": totals["complete"],
            "incomplete": totals["incomplete"],
            "not_started": totals["not_started"],
            "unconverted": totals["unconverted"],
        },
    }
