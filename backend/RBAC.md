# Backend RBAC

The RBAC schema is in the Flask-SQLAlchemy models and is created by migration
`0033_rbac`. `user_roles.user_id` is unique, so an account can have at most one
RBAC role. Users without an assigned role are denied, including legacy
administrator and superuser accounts.

From `backend/`, apply the migration and load the policy file into the runtime
policy tables:

```sh
PYTHONPATH=. FLASK_APP=run.py flask db upgrade
PYTHONPATH=. FLASK_APP=run.py flask seed-rbac
```

The exact role rules are defined in `app/policies/rbac.json`. The
`app.utils.rbac.can(user, permission)` service reads role assignments and
permission rules from the database on each decision. Update the JSON policy
and rerun `flask seed-rbac` to load policy changes; no authorization logic
needs to change.

Existing users are not assigned a department role automatically. After the
migration and policy seed, a system administrator can open the Employee
Directory and explicitly assign each employee exactly one of `customer_care`,
`debt_collection`, or `sales`. Until assigned, department dashboard features
remain hidden and their protected APIs deny access. Role assignment is also
available through `PUT /api/admin/users/<user_id>/department-role` with
`{"role":"customer_care"}`, `{"role":"debt_collection"}`, or `{"role":"sales"}`.

Department API blueprints enforce the department wildcard permissions.
Sales-report read and write endpoints enforce `sales_reports.view` and
`sales_reports.write`; `POST /api/leave/requests` enforces `leave.apply`.
Other leave workflow and administrative endpoints are outside this policy
scope and retain their existing guards.

The RBAC permission tests create one test account per role and exercise the
full permission matrix and protected API routes:

```sh
python -m pytest tests/test_rbac_permissions.py
```

## Debt collection hierarchy

The `debt_collection` department role grants access to the module, but does not
by itself grant portfolio-wide access or management actions. Collectors can
view and work only loans currently allocated to them. A debt-collection
Department Manager (organizational role `department_manager` or the explicitly
assigned `departmental_manager` duty) can manage the department portfolio and
allocate/reassign accounts. A Group Leader/Team Leader (organizational role
`team_leader`, or the `group_leader`/`team_leader` duty) can read all active
debtor and loan entries through the portfolio list, including accounts assigned
to other teams and unassigned accounts. Their summaries, analytics, follow-ups,
and individual record access remain limited to their direct-report team. They
cannot create, import, allocate, edit, archive, or delete records. Department
Managers and General Managers can perform department-wide portfolio CRUD,
allocation, and the existing authorized bulk actions. HR administrators
retain read-only department reporting access; system-administrator write
access still requires the existing debt-collection permission. Active
department role assignments and account allocation remain the source of
scope; assigning the operational department role alone never exposes another
team's assigned accounts.

The super-admin employee duty editor accepts `departmental_manager`,
`department_manager`, `group_leader`, `team_leader`, and
`debt_collector_agent` duty identifiers.

## Department manager coverage and account lifecycle

The authenticated organization-assignment response includes
`effective_organizational_roles`. A Departmental Manager receives the
additional `team_leader` capability only when their own department has no
active, approved Group Leader; the stored organizational role and the
Departmental Manager's existing permissions are unchanged. The check is
department-specific. When a Group Leader is active, the Departmental Manager
does not receive this fallback.

Department employees retain their reporting links through Group Leader,
Departmental Manager, and General Manager. If the Group Leader is deactivated,
the Departmental Manager may cover the Group Leader approval stage for that
department, while the Department Manager and General Manager stages remain
intact. Reactivating an assigned user continues to validate their reporting
chain.

Super Admins can update account status from the existing User Directory for
employees, organizational leaders, and other accounts. Status changes apply
to the existing account; they do not assign organizational or department
permissions. Deactivated, archived, or deleted accounts cannot sign in, and
existing access/refresh tokens are rejected after account deactivation.
