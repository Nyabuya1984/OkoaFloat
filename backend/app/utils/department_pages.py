from app.extensions import db
from app.models import DepartmentPageConfiguration


def default_department_pages(name):
    normalized = str(name or "").casefold()
    if "sales" in normalized or "marketing" in normalized:
        return ["sales-reports", "organization-live"]
    if "debt" in normalized or "collection" in normalized:
        return ["debt-collection"]
    if "customer" in normalized or "care" in normalized:
        return [
            "customer-care-logs",
            "customer-care-new",
            "customer-care-customers",
            "customer-care-follow-ups",
            "okia-overview",
            "okia-escalations",
            "okia-shifts",
            "okia-shift-coverage",
            "okia-concerns",
            "okia-gm-resolution",
            "okia-gm-attention",
            "okia-agent-shift-matrix",
            "okia-concern-report",
            "okia-escalation-report",
        ]
    if "human resources" in normalized or normalized == "hr" or "people" in normalized:
        return ["hr-module", "hr-verification"]
    return []


def department_pages_for(department_id, department_name):
    configuration = (
        db.session.get(DepartmentPageConfiguration, department_id)
        if department_id is not None
        else None
    )
    if configuration and configuration.pages:
        return configuration.pages
    return default_department_pages(department_name)