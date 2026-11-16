from types import SimpleNamespace

import pytest

from seed_system_test_data import delete_records, seed_records


@pytest.mark.parametrize("action", [seed_records, delete_records])
def test_system_test_data_actions_reject_non_development_apps(action):
    app = SimpleNamespace(
        debug=False,
        config={"SQLALCHEMY_DATABASE_URI": "mysql+pymysql://user:pass@localhost/Okoa_Float_DB"},
    )

    with pytest.raises(RuntimeError, match="local development database"):
        action(app)
