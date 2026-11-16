from app.models import Department, DepartmentPageConfiguration


def test_super_admin_can_read_defaults_and_configure_department_pages(
    client, admin_token, session
):
    department = Department(name="People & Culture")
    session.add(department)
    session.commit()
    headers = {"Authorization": f"Bearer {admin_token}"}

    defaults = client.get("/api/admin/department-pages", headers=headers)
    assert defaults.status_code == 200
    department_data = next(
        row for row in defaults.get_json()["data"] if row["id"] == department.id
    )
    assert department_data["pages"] == ["hr-module", "hr-verification"]

    updated = client.put(
        f"/api/admin/departments/{department.id}/pages",
        headers=headers,
        json={"pages": ["hr-module", "sales-reports"]},
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["pages"] == ["hr-module", "sales-reports"]

    persisted = session.get(DepartmentPageConfiguration, department.id)
    assert persisted.pages == ["hr-module", "sales-reports"]
    reread = client.get("/api/admin/department-pages", headers=headers)
    department_data = next(
        row for row in reread.get_json()["data"] if row["id"] == department.id
    )
    assert department_data["pages"] == ["hr-module", "sales-reports"]


def test_department_page_configuration_is_super_admin_only(
    client, rbac_tokens, session
):
    department = Department(name="Engineering")
    session.add(department)
    session.commit()
    headers = {"Authorization": f"Bearer {rbac_tokens['sales']}"}

    assert client.get("/api/admin/department-pages", headers=headers).status_code == 403
    assert client.put(
        f"/api/admin/departments/{department.id}/pages",
        headers=headers,
        json={"pages": ["sales-reports"]},
    ).status_code == 403


def test_department_page_configuration_rejects_unsupported_page_ids(
    client, admin_token, session
):
    department = Department(name="Engineering")
    session.add(department)
    session.commit()

    response = client.put(
        f"/api/admin/departments/{department.id}/pages",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"pages": ["not-a-department-page"]},
    )
    assert response.status_code == 422


def test_empty_department_page_selection_uses_known_department_defaults(
    client, admin_token, session
):
    department = Department(name="Debt Collection")
    session.add(department)
    session.flush()
    session.add(DepartmentPageConfiguration(
        department_id=department.id,
        pages=[],
    ))
    session.commit()
    headers = {"Authorization": f"Bearer {admin_token}"}

    configured = client.get("/api/admin/department-pages", headers=headers)
    department_data = next(
        row for row in configured.get_json()["data"] if row["id"] == department.id
    )
    assert department_data["pages"] == ["debt-collection"]

    reset = client.put(
        f"/api/admin/departments/{department.id}/pages",
        headers=headers,
        json={"pages": []},
    )
    assert reset.status_code == 200
    assert reset.get_json()["data"]["pages"] == ["debt-collection"]
    assert session.get(DepartmentPageConfiguration, department.id) is None
