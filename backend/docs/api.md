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

## OTP authentication and recovery

OTP codes are dispatched via SMS to the user's mobile phone using Onfon Media's Bulk SMS API.
In development and testing, codes are also saved in the `OTP.plaintext_code` column and logged
to the backend console for rapid local development. In other configurations, only the OTP hash is
stored. Codes expire after 10 minutes and are single-use.

SMS delivery is configured using:
- `SMS_ENABLED`: set to `true` to enable SMS dispatch (default `true` in prod/dev, `false` in testing).
- `ONFON_SMS_URL`: endpoint URL (default `https://api.onfonmedia.com/v1/sms/SendBulkSMS`).
- `ONFON_ACCESS_KEY`: HTTP header `Accesskey`.
- `ONFON_API_KEY`: payload `ApiKey`.
- `ONFON_CLIENT_ID`: payload `ClientId`.
- `ONFON_SENDER_ID`: payload `SenderId` (optional sender ID / alphanumeric header).

Login remains phone-and-password based. Verify with
`POST /api/auth/verify-otp` using `phone_number` and `otp`. Registration
verification uses `POST /api/auth/verify-registration` with `phone_number`,
the registered `email`, and `otp`. Password recovery uses
`POST /api/auth/request-password-reset` with `phone_number`; finish with
`POST /api/auth/reset-password` using `phone_number`, `otp`, and
`new_password`. Forgotten phone recovery uses
`POST /api/auth/request-phone-recovery` with a registered email, followed by
`POST /api/auth/recover-phone` with `email` and `otp`. Retrieve development
codes from the backend console or the `OTP.plaintext_code` column. Never enable
plaintext OTP storage outside development/testing.

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
| POST | `/api/auth/login` | Validate phone/password and request a login OTP. |
| POST | `/api/auth/phone-login` | Alias for phone/password login and OTP request. |
| POST | `/api/auth/verify-otp` | Verify the login OTP and issue an access/refresh session. |
| POST | `/api/auth/register` | Create a pending employee account and request a registration OTP. |
| POST | `/api/auth/verify-registration` | Verify the registration OTP; the account remains pending approval. |
| POST | `/api/auth/request-password-reset` | Request a password-reset OTP. |
| POST | `/api/auth/reset-password` | Verify the OTP and set a new password. |
| POST | `/api/auth/refresh` | Exchange a valid refresh token for a new access token. |
| POST | `/api/auth/logout` | Revoke the refresh token. |
| GET | `/api/auth/me` | Read the authenticated user profile. |
| PATCH | `/api/auth/me` | Update the authenticated user profile. |
| POST | `/api/auth/me/photo` | Upload a profile photo. |
| DELETE | `/api/auth/me/photo` | Remove the profile photo. |

## Administration

These endpoints require an approved HR administrator or super-admin unless the
route is explicitly used by a manager for their permitted scope.

New user forms use one `official_email` field (the older `email` key remains
accepted for compatibility). `personal_email` is retained only as a legacy
database/API alias and is set to the official address for new and updated
users. Managed-user creation also requires an `organizational_role`; field
agents, team leaders, and department managers must receive the operational
department role that matches their department and a reporting manager at the
immediately higher hierarchy level. Self-registration is always recorded as a
field-agent assignment until an authorized manager changes it.

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

## Debt Collection

The `debt_collection` operational role grants module access. Collectors see
only accounts allocated to them; team leaders can review their team accounts,
allocate unassigned accounts to direct-report agents, reassign their team's
accounts, and import/create/edit/soft-delete unassigned or team-owned records.
Departmental managers manage and distribute the department portfolio. General
Managers can perform department-manager operations. See `RBAC.md` for the role
and duty requirements.

| Method | Endpoint | Function |
|---|---|---|
| GET | `/api/debt-collection/summary` | Scoped portfolio totals and access capabilities. |
| GET | `/api/debt-collection/loans` | Scoped searchable loan portfolio. |
| POST | `/api/debt-collection/debtors` | Create debtor data; team leader or manager. |
| PATCH/DELETE | `/api/debt-collection/debtors/<debtor_id>` | Update or soft-delete a debtor; managers can manage the full portfolio, team leaders are limited to unassigned or team-owned accounts. |
| DELETE | `/api/debt-collection/debtors/<debtor_id>/permanent` | Permanently delete a client and its debt-collection records; super admins and general managers only. |
| POST | `/api/debt-collection/loans` | Create loans; team leader or manager. |
| PATCH/DELETE | `/api/debt-collection/loans/<loan_id>` | Update or soft-delete a loan; team leaders are limited to unassigned or team-owned accounts. |
| DELETE | `/api/debt-collection/loans/<loan_id>/permanent` | Permanently delete a loan; super admins and general managers may delete any loan, while team leaders may delete only flagged duplicates in their team. |
| POST | `/api/debt-collection/loans/<loan_id>/assignments` | Allocate or reassign an account; team leaders are limited to direct reports. |
| POST | `/api/debt-collection/loans/<loan_id>/calls` | Record an interaction on an allocated account. |
| POST | `/api/debt-collection/loans/<loan_id>/payments` | Record a payment on an allocated account. |
| GET | `/api/debt-collection/analytics` | Portfolio, collector, recovery, and interaction analysis. |
| POST | `/api/debt-collection/import` | Import CSV or `.xlsx` portfolio rows; team leaders can import for their allocation list. |
| GET | `/api/debt-collection/export.csv` | Export permitted portfolio rows as CSV. |
| GET | `/api/debt-collection/export.xlsx` | Export permitted portfolio rows as Excel. |
| POST | `/api/debt-collection/loans/<loan_id>/write-off` | Approve and audit a loan write-off; manager only. |
| GET | `/api/collector/my-portfolio` | Collector's allocated accounts (team scope for team leaders). |

Active loan entries are flagged as duplicates when their client's agent number,
agent phone number (compared as digits), and business name (case- and
whitespace-normalized) all match another active entry. Team leaders can
permanently delete only flagged duplicates within their team. Super admins and
general managers can permanently delete any loan or client. Permanently
deleting a loan removes linked payment, assignment, and status-history records
while retaining call history; permanently deleting a client also removes that
client's call and follow-up history. A non-PII audit event is retained.

Loan filters include `q`, `business_name`, `location`, `agent_name`,
`agent_number`, `store_number`, `collector_id`, `collector_name`, and
`collector_number`, plus status and balance filters. Team leaders can set
`include_unassigned=true` to include unassigned accounts in their team
allocation view. CSV exports use this exact header order:
`first_name, other_names, agent_msisdn, owner_msisdn, operator_msisdn,
agent_no, store_number, business_name, location, loan_amount, amount_paid,
loan_balance, loan_date, last_interest_calc_date, no_of_days, days_outstanding,
status, collector_name, created_at, record_created_at`.
Imports accept columns in the supplied portfolio format:
`first_name, other_names, agent_msisdn, owner_msisdn, operator_msisdn, agent_no,
store_number, business_name, location, loan_amount, loan_balance, amount_paid,
status, created_at, last_interest_calc_date, no_of_days`.
Header capitalization and spacing are normalized. The legacy `wner_msisdn`
owner header and `mount_paid` (or `a mount_paid`) are accepted as aliases for
`owner_msisdn` and `amount_paid`. Common visually truncated variants such as
`operator_msid`, `amount_p`, and `last_interest_calc_da` are also recognized.
CSV imports detect comma, semicolon, tab, and pipe delimiters and can skip
introductory rows before the header. Excel imports search workbook sheets for
the portfolio header row.
Imports preserve the supplied `loan_balance` as the current outstanding
balance, including balances that contain interest and therefore differ from
`loan_amount - amount_paid`. Numeric legacy `status` values are treated as
active accounts. Excel date cells and comma-formatted monetary values are
accepted. If `loan_date` is omitted, import derives it from `created_at` or
uses today's date. The dashboard provides a downloadable CSV template with
the required portfolio headers. Call outcomes include
phone off/unreachable, no answer, negotiation, wrong number, promise to pay,
callback, full payment, and partial payment. Promises/callbacks require a
scheduled date and time; partial payments return the revised outstanding
balance and schedule the next agreed payment.

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

`POST /api/sales/reports` accepts the workflow form as multipart data. Send
`new_client=true` with `outcome=interested`, `not_interested`, `appointment`,
or `ready_to_register`; existing clients use `new_client=false` and
`outcome=existing`. Every workflow submission requires the business owner's
name (`business_owner_name`), ID number (`id_number`), and phone (`contact_phone`).
`appointment` requires `appointment_date` and
`appointment_time`. Existing-client submissions include `referral_agreed`
(`yes` or `no`) and, when yes, `referral_contact_number`. Ready-to-register
submissions include the category in `customer_type` (`agent` or `sub_agent`),
`registration_date`, witness details, and the checklist fields for that
category. `registration_status` is derived by the API from all applicable
checklist fields rather than trusted from the client; incomplete registrations
are still saved as `INCOMPLETE`.
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

## Organization transfers and location tracking

Apply migrations `0034_org_tracking`, `0035_simulated_locations`,
`0036_location_sharing`, and `0037_scheduled_agent_tracking` in order. An active employee has
one current department assignment and one matching department-role permission.
Transfers close the previous history row and replace the role in the same
transaction. Only General Management, HR, or a manager authorized for the
employee's current department can transfer an employee. Reporting lines follow
General Manager → HR/Department Manager → Team Leader → Field Agent.

| Method | Endpoint | Function |
|---|---|---|
| GET | `/api/organization/assignment/me` | Return the caller's active department and role for frontend route guards. |
| GET | `/api/organization/departments` | List departments. |
| GET | `/api/organization/transfer-candidates` | List employees in the caller's transfer scope and reporting levels. |
| POST | `/api/organization/users/<user_id>/transfer` | Transfer department, operational role, hierarchy role, and reporting manager atomically. |
| POST | `/api/organization/clients` | Register a Sales and Marketing client with required GPS coordinates. |
| POST | `/api/organization/locations/ping` | Store a field agent's scheduled GPS update; clients should send one every 60 seconds. |
| GET | `/api/organization/agent/location-sharing` | Return whether the authenticated field agent is currently inside the schedule and manager controls. |
| GET/PUT | `/api/organization/location-tracking/schedule` | System-admin-only read/update of global schedule (`enabled`, `timezone`, weekday codes in `days`, `start_time`, and `end_time`). |
| GET/PUT | `/api/organization/location-tracking/control` | Team-leader, department-manager, or general-manager status and scoped temporary override (`{"enabled": true}` or `{"enabled": false}`). |
| GET | `/api/organization/locations/live` | Return manager-authorized agent tracking status, latest positions, and the last 24 hours of travel points. |
| GET | `/api/organization/locations/stream` | Stream manager-authorized live location snapshots over SSE. |
| GET | `/api/organization/reports/history` | Read the caller's own previous-department sales reports; responses are read-only. |
| POST | `/api/employees/transfer` | Compatibility route for department transfers; include `user_id` in the JSON body. |
| POST | `/api/agent/location` | Compatibility route for a field-agent GPS ping during scheduled tracking hours. |
| POST | `/api/clients/register` | Compatibility route for GPS-bound Sales and Marketing client registration. |
| GET | `/api/manager/agents/live-locations` | Compatibility route for manager-scoped live locations and trails. |
| GET | `/api/reports/<department_id>` | Read reports for a department the caller manages or is assigned to currently or historically. |

`/users/<user_id>/transfer` accepts `department_id`, `department_role`
(`sales`, `debt_collection`, `customer_care`, or `null` for non-operational
management roles), `organizational_role` (`general_manager`, `hr_manager`,
`department_manager`, `team_leader`, or `field_agent`), and `manager_id` when
the reporting line requires one. Field agents must have a matching department
role and team-leader manager.

Department report responses include `read_only` and `can_edit`; employees
reading reports from a former department receive only their own reports with
editing disabled. General Management and HR can view company-wide department
reports, while department managers and team leaders are limited to their
authorized team scope.

The default schedule is disabled until a system administrator configures it
from Dashboard settings. The administrator selects recurring weekdays and a
daily start/end time in `Africa/Nairobi`; overnight windows are supported.
During scheduled hours, active field agents are tracked automatically without
an employee-dashboard toggle. Browser GPS permission is still required, and
the signed-in web client collects only while the app is open and visible; this
repository has no native background-tracking client. The tracking notice tells
employees whether collection is scheduled or blocked by a browser permission.
Team leaders can control their own teams, department managers their department,
and general managers the organization. Manager pause/resume overrides last
until the next schedule boundary; a system-admin schedule change clears them.
The ping endpoint rejects updates outside the effective schedule/control
window, associates each location with the authenticated field agent, and
validates coordinate bounds, accuracy, current assignment, and the 60-second
server-side interval; a body `user_id` is never used as identity. Managers
may view active agent locations within their authorized scope. Location
records are removed after 30 days. The tracking and manager APIs
opportunistically expire old records; production deployments should also run
`flask cleanup-agent-locations` daily. The dashboard receives authenticated
server-sent snapshots every 15 seconds and falls back to
15-second REST refreshes if the stream disconnects. It displays agent markers
and trails on OpenStreetMap tiles. Historical playback accepts a selected start/end time
within the 30-day retention window and includes a scrubber, interpolated
position, play/pause, one-minute rewind/forward, and 1x/2x/5x/10x speed
controls. OpenStreetMap tile requests disclose the viewed map area to the tile
provider. Rows marked `is_simulated` or “Demo data” are seed/demo coordinates,
never live GPS.

## API conventions

- Dates use `YYYY-MM-DD`.
- Phone numbers are normalized server-side to Kenyan E.164 format.
- Do not print access tokens, refresh tokens, or passwords in logs.
- Use `GET /health` for a lightweight dependency check.
