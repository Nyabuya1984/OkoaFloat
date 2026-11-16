import pytest
from flask import Flask

from app.api.sales import _filter_sales_leads


class QueryStub:
    def __init__(self):
        self.conditions = []

    def filter(self, condition):
        self.conditions.append(condition)
        return self


def test_lead_filters_validate_dates_and_employee_scope():
    app = Flask(__name__)
    query = QueryStub()
    with app.test_request_context(
        "/?from=2026-04-01&to=2026-04-30&employee_id=12&status=callback_requested"
    ):
        assert _filter_sales_leads(query) is query
    assert len(query.conditions) == 4


@pytest.mark.parametrize(
    "query_string",
    [
        "from=not-a-date",
        "to=not-a-date",
        "from=2026-05-01&to=2026-04-01",
        "employee_id=0",
        "status=unsupported",
    ],
)
def test_lead_filters_reject_invalid_values(query_string):
    app = Flask(__name__)
    with app.test_request_context(f"/?{query_string}"):
        with pytest.raises(ValueError):
            _filter_sales_leads(QueryStub())
