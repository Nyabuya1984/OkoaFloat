# API Notes

## Phone numbers

All phone inputs are normalized server-side to Kenyan E.164 format:
`+2547XXXXXXXX` or `+2541XXXXXXXX`. Clients may continue sending local formats such as `0712345678`.

## Administrative users

User listing and summary require an approved HR administrator or superuser.
Managers are limited to themselves and their direct reports.

```bash
curl "http://localhost:5000/api/admin/users?status=active&page=1&per_page=25&q=Amina&role=employee&department_id=2" \
  -H "Authorization: ******"

curl "http://localhost:5000/api/admin/users/summary" \
  -H "Authorization: ******"

# Deleted users require a superuser.
curl "http://localhost:5000/api/admin/users?status=all&include_deleted=true" \
  -H "Authorization: ******"
```

Responses use the standard envelope:
`{"data": ..., "error": null}` or `{"data": null, "error": {"code": "...", "message": "..."}}`.

## Profile

All profile endpoints require `Authorization: Bearer <access-token>`.

```bash
curl http://localhost:5000/api/auth/me \
  -H "Authorization: Bearer <access-token>"

curl -X PATCH http://localhost:5000/api/auth/me \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"employee_name":"Amina Otieno","city":"Nairobi"}'

curl -X POST http://localhost:5000/api/auth/me/photo \
  -H "Authorization: Bearer <access-token>" \
  -F "photo=@/path/to/photo.jpg"

curl -X DELETE http://localhost:5000/api/auth/me/photo \
  -H "Authorization: Bearer <access-token>"
```

## Leave request contact

Leave submissions require a reachable contact phone and email plus address,
city, and country. Postal code and address line 2 are optional.

```bash
curl -X POST http://localhost:5000/api/leave/requests \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "leave_type_id": 1,
    "start_date": "2026-10-12",
    "end_date": "2026-10-14",
    "reason": "Personal leave",
    "contact_phone": "+254712345678",
    "contact_email": "amina@example.com",
    "address_line1": "12 Kenyatta Avenue",
    "city": "Nairobi",
    "country": "Kenya",
    "postal_code": "00100"
  }'
```

## Super admin bootstrap

The system treats `hr_admin` users as the super-user role when `is_superuser` is `true`.
Use the helper below to ensure the default super admin exists.

```bash
cd /home/wycliffe/Desktop/OKOA_FLOAT_LEAVE/backend
python create_super_admin.py
```

Default credentials:

# Okoa Float API Reference

Base URL: `http://localhost:5000`

Unless marked **public**, send `Authorization: Bearer <access-token>`. JSON
endpoints use `Content-Type: application/json`; file endpoints use multipart
form data. Responses normally use `{"data": ..., "error": null}` or an error
object containing `code` and `message`.

## Public and Health

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Service metadata and links. |
| GET | `/health` | Database connectivity and service health. |
| GET | `/api/auth/photos/<filename>` | Serve an uploaded profile photo. |

## Authentication and Profile

| Method | Endpoint | Function |
|---|---|---|
| POST | `/api/auth/login` | Email/password login and token issuance. |
| POST | `/api/auth/phone-login` | Start phone OTP login. Development mode returns the OTP in the server log, never the challenge identifier. |
| POST | `/api/auth/verify-otp` | Verify a login OTP and issue an access/refresh session. |
| POST | `/api/auth/register` | Create a pending employee account and registration OTP. |
| POST | `/api/auth/verify-registration` | Verify registration OTP and activate the registration flow. |
| POST | `/api/auth/request-password-reset` | Start password reset OTP. |
| POST | `/api/auth/reset-password` | Verify reset OTP and set a new password. |
| POST | `/api/auth/refresh` | Exchange a valid refresh token for a new access token. |
| POST | `/api/auth/logout` | Revoke the refresh token. |
| GET | `/api/auth/me` | Read the authenticated user profile. |
| PATCH | `/api/auth/me` | Update the authenticated user profile. |
| POST | `/api/auth/me/photo` | Upload a profile photo. |
| DELETE | `/api/auth/me/photo` | Remove the profile photo. |

The `challenge_id` is an opaque client/API value used internally to match an
OTP verification request. It is not a secret explanation or user-facing key,
and it is intentionally excluded from backend console logging.

## Administration

These endpoints require an approved HR administrator or super-admin unless the
route is explicitly used by a manager for their permitted scope.

| Method | Endpoint | Function |
|---|---|---|
| GET | `/api/admin/users` | List users with status, role, department, and search filters. |
| GET | `/api/admin/users/summary` | Return total, active, and pending user counts. |
| GET/POST | `/api/auth/admin/users` | List or create managed users. |
| PATCH/DELETE | `/api/auth/admin/users/<user_id>` | Edit or remove a managed user. |
| PATCH | `/api/auth/admin/users/<user_id>/status` | Activate, deactivate, archive, or approve a user. |
| PATCH | `/api/auth/admin/users/<user_id>/role` | Change a role or super-admin privilege. |
| GET/POST | `/api/auth/admin/departments` | List or create departments. |
| PATCH/DELETE | `/api/auth/admin/departments/<department_id>` | Edit or delete a department. |
| GET/POST | `/api/auth/admin/leave-types` | List or create leave types. |
| PATCH/DELETE | `/api/auth/admin/leave-types/<leave_type_id>` | Edit or delete a leave type. |
| GET/PATCH | `/api/auth/admin/workflow-settings` | Read or update handover and approval rules. |
| GET | `/api/auth/admin/security-events` | Read security audit events. |
| GET | `/api/auth/admin/audit` | Read administrative audit entries. |
| GET | `/api/auth/admin/system-health` | Read database, uploads, and account health. |
| POST | `/api/auth/accounts/<user_id>/approve` | Approve a pending account. |
| POST | `/api/auth/accounts/<user_id>/deactivate` | Deactivate an account. |
| POST | `/api/auth/accounts/<user_id>/ban` | Ban an account. |

## Leave and Handover

| Method | Endpoint | Function |
|---|---|---|
| GET | `/api/leave/types` | List available leave types. |
| GET | `/api/leave/balances` | Read the current user's leave balances. |
| POST | `/api/leave/requests` | Submit a leave request. Applies notice, service, balance, contact, and handover rules. |
| GET | `/api/leave/requests` | List the current user's requests. |
| GET | `/api/leave/requests/history` | Read historical leave requests. |
| GET | `/api/leave/requests/delegations` | List handovers assigned to the current user. |
| GET | `/api/leave/requests/pending` | Manager/HR approval queue. |
| GET | `/api/leave/team-calendar` | Manager/HR/super-admin team leave calendar. |
| GET | `/api/leave/requests/<request_id>` | Read one leave request. |
| POST | `/api/leave/requests/<request_id>/cancel` | Cancel an eligible request. |
| POST | `/api/leave/requests/<request_id>/approve` | Approve a request. |
| POST | `/api/leave/requests/<request_id>/reject` | Reject a request. |
| POST | `/api/leave/requests/<request_id>/defer` | Defer a decision. |
| POST | `/api/leave/requests/<request_id>/verify-complete` | Complete HR verification. |
| GET/PATCH | `/api/leave/requests/<request_id>/handover` | Read or update a handover report. |
| POST | `/api/leave/requests/<request_id>/handover-ack` | Acknowledge a handover. |
| POST | `/api/leave/requests/<request_id>/handover/accept` | Accept a handover. |
| POST | `/api/leave/requests/<request_id>/handover/decline` | Decline a handover. |
| POST | `/api/leave/requests/<request_id>/handover/submit` | Submit a completed handover report. |
| POST | `/api/leave/requests/<request_id>/handover/request-changes` | Request corrections to a handover. |
| POST | `/api/leave/requests/<request_id>/handover/remind` | Remind a delegate. |
| GET | `/api/leave/requests/<request_id>/handover/pdf` | Download a handover PDF. |
| POST/GET/DELETE | `/api/leave/requests/<request_id>/handover/attachment` | Upload or manage handover attachments. |

## Chat

| Method | Endpoint | Function |
|---|---|---|
| GET | `/api/chat/users` | List chat peers. |
| GET | `/api/chat/messages/<peer_id>` | Read messages with a peer. |
| POST | `/api/chat/messages` | Send a message. |
| GET | `/api/chat/unread-count` | Read the unread message count. |
| POST | `/api/chat/messages/<peer_id>/read` | Mark a peer's messages as read. |

## Sales and Marketing Reports

Employees are scoped to their own reports. Managers, HR, and super-admins can
view team or organization reports according to their role. Only managers, HR,
and super-admins can correct an existing report.

| Method | Endpoint | Function |
|---|---|---|
| POST | `/api/sales/reports` | Create a daily client report. |
| GET | `/api/sales/reports` | List reports within the viewer's permitted scope. |
| PATCH | `/api/sales/reports/<report_id>` | Correct a report; manager/HR/super-admin only. |
| GET | `/api/sales/reports/template` | Download the CSV import template. |
| GET | `/api/sales/reports/export` | Export permitted legacy reports as CSV. |
| POST | `/api/sales/reports/import` | Import employee reports from CSV. |
| GET | `/api/sales/reports/<report_id>/documents/<filename>` | Download a report document. |
| GET | `/api/sales/v2/summary?scope=mine` | Employee summary and own visit rows. |
| GET | `/api/sales/v2/submissions/daily` | Daily submission totals. |
| GET | `/api/sales/v2/funnel` | Sales funnel and outcome insights. |
| GET | `/api/sales/v2/referrals` | Referral performance insights. |
| GET | `/api/sales/v2/appointments` | Appointment rows and upcoming/overdue totals. |
| GET | `/api/sales/v2/reports?scope=team` | Manager team reports. |
| GET | `/api/sales/v2/compliance/team` | Team filing compliance. |
| GET | `/api/sales/v2/performance/team` | Ranked salesperson performance. |
| GET | `/api/sales/v2/registrations/team` | Complete, partial, and unstarted team registrations. |
| GET | `/api/sales/v2/locations` | Team location rankings. |
| GET | `/api/sales/v2/compliance/org` | Organization compliance for HR/super-admin. |
| GET | `/api/sales/v2/registrations/org` | Organization registration totals. |
| GET | `/api/sales/v2/document-gaps` | Missing document analysis. |
| GET | `/api/sales/v2/regions` | Organization region rankings. |
| GET | `/api/sales/v2/top-performers` | Organization top performers. |
| GET | `/api/sales/v2/audit` | Super-admin sales audit information. |
| GET | `/api/sales/v2/integrity` | Super-admin data integrity checks. |
| GET | `/api/sales/v2/exports` | Super-admin export inventory or export metadata. |
| POST | `/api/sales/v2/imports` | Super-admin sales data import. |
| GET | `/api/sales/v2/export.csv` | Export V2 reports as CSV using the requested scope and filters. |
| GET | `/api/sales/v2/export.xlsx` | Export V2 reports as Excel using the requested scope and filters. |
| POST | `/api/sales/v2/actions/chase` | Chase a selected team report. |
| POST | `/api/sales/v2/actions/flag` | Flag a selected organization report. |
| POST | `/api/sales/v2/actions/verify` | Verify a selected organization report. |

### Common sales filters

Use `from=YYYY-MM-DD`, `to=YYYY-MM-DD`, `category`, `status`, `agent`,
`employee_id`, `page`, and `per_page` where supported. Managers should use
`scope=team`; employees should use `scope=mine`; HR and super-admin analytics
may use organization endpoints.

Example:

```bash
curl "http://localhost:5000/api/sales/v2/performance/team?scope=team&from=2026-09-01&to=2026-09-30" \
  -H "Authorization: Bearer <access-token>"
```

## API conventions

- Dates use `YYYY-MM-DD`.
- Phone numbers are normalized server-side to Kenyan E.164 format.
- Do not print access tokens, refresh tokens, OTP challenge identifiers, or passwords in logs.
- Use `GET /health` for a lightweight dependency check.
