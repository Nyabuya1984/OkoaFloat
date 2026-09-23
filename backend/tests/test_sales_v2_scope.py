from datetime import date

from app.services.sales_reports_v2 import funnel, summary


def test_summary_and_funnel_aggregate_serialized_sales_rows():
    rows = [
        {"id": 1, "employee_id": 7, "employee_name": "Jane Doe", "agent_name": "Shop A", "date_visited": date.today().isoformat(), "customer_type": "agent", "outcome": "registered", "report_data": {"registration_status": "Complete"}},
        {"id": 2, "employee_id": 7, "employee_name": "Jane Doe", "agent_name": "Shop B", "date_visited": date.today().isoformat(), "customer_type": "sub_agent", "outcome": "appointment", "report_data": {}},
    ]

    result = summary(rows, today=date.today())
    funnel_result = funnel(rows)

    assert result["summary"] == {"total": 2, "filed_today": 2, "expected_today": 0}
    assert result["by_category"] == {"agent": 1, "sub_agent": 1}
    assert result["by_outcome"]["registered"] == 1
    assert funnel_result["summary"]["by_outcome"]["appointment"] == 1
