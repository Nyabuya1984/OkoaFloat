# Sales & Marketing lead and telesales workflows

## Lead upload and allocation

Sales & Marketing managers can upload CSV or Excel `.xlsx` prospect lists to
`POST /api/sales/leads/import`. Files contain 1–500 rows. Column headings are
case-insensitive; the template uses `Business Name`, `Head Office Location`,
`Director's Name`, `Phone Number`, `M-Pesa Agent Name`, `M-Pesa Agent Number`,
and `M-Pesa Store Number`. A
director/contact name or company name and a phone number are required. Invalid
rows reject the entire upload. The frontend provides a matching CSV template.

Managers can select leads and assign them to one representative using
`POST /api/sales/leads/assignments/bulk`, or split selected leads evenly across
their permitted Sales representatives using `POST /api/sales/leads/distribute`.
Both actions preserve allocation audit events and require a reason when
reassigning allocated leads. Managers can also distribute all unassigned leads
or distribute new rows during upload. Manager scope is enforced on list,
upload, distribution, allocation, analytics, and exports; representatives only
see their assigned calling queue.

Managers can view each lead's details and call history, edit business/contact
fields with `PATCH /api/sales/leads/<id>/details`, and remove leads from the
active queue with `DELETE /api/sales/leads/<id>`. Delete archives the lead;
call history and audit records are retained. The lead table supports
column-level filters for business/director, phone, business/head-office
location, representative, call response, and registration state.

`GET /api/sales/leads` returns the scoped lead sheet, including call history,
registration status, and open follow-up counts. An employee sees their assigned
leads plus leads they contacted previously, so reassignment does not erase their
client context. Managers can export the current filtered lead sheet as CSV,
Excel, or PDF from `/api/sales/leads/export.csv`, `/export.xlsx`, or
`/export.pdf`. Employees can export their own audit-stamped call history, and
managers can export their permitted scope, from
`/api/sales/leads/call-history/export.csv?format=csv|xlsx|pdf`. Lead exports
begin with the seven template columns and include current allocation, call, and
registration status.

## Representative call sheet

Representatives use the daily call queue and tap-to-call links. The workspace
separates the active queue from contacted clients: once a call outcome reaches
the client, the lead moves to the Contacted Clients view, where its response is
color-coded and the full cross-agent call timeline remains available. Unreached
attempts stay in the active queue for retry. Each outcome is submitted as a
separate immutable call attempt to
`POST /api/sales/leads/<id>/calls`. The accepted outcomes are `New`,
`Interested`, `Not Interested`, `Ready to Register`, `Appointment`,
`Registered`, `Unreachable`, and `Wrong Number` (API values are lowercase
snake-case). A decline reason is mandatory for Not Interested. Appointment
date/time is mandatory and must be in the future.

The backend stamps contact date, weekday, 24-hour `HH:MM:SS` contact time, and
authenticated representative identity. Unreachable attempts create a next-day retry task;
appointments create a due task; Wrong Number archives the lead from the active
queue while retaining its call history for manager exports.

Each call can update the lead's current response, but prior call attempts remain
available in its call history and exports. A manager can view the full call
timeline for leads in their permitted hierarchy; an employee can view timelines
for currently assigned and previously contacted leads. The legacy lead PATCH
endpoint is retained and translates previous status values to a structured call
log.

Employees can escalate a lead to a Group Leader, Department Manager, or General
Manager from its call-history row. The reason is required. The API routes the
task to the active manager assignment for the lead's department (or the active
General Manager), records an audit event, and creates in-app notifications.
Managers see the open item in their scoped follow-up list with the lead and its
call history; completing the follow-up closes the escalation task.

## Registration quality and reminders

A Registered call requires the representative to mark Director ID copy,
business permit, tax certificate, and Till/Store number verification.
Registration status is computed on the server:

- `COMPLETE` when every required item is verified.
- `INCOMPLETE` when an item is missing; a reason is mandatory.

Incomplete registrations automatically create a follow-up task assigned to the
representative. Representatives see due tasks in their calling workspace and
can complete them after follow-up.

## Analytics

`GET /api/sales/leads/analytics` reports call attempts, reached calls,
reachability rate, assigned/attempted/reached/interested/registered funnel
counts, complete/incomplete registrations, bottlenecks, and a representative
performance matrix. Employees see their own period totals; managers see their
permitted team/org totals. Optional `from`, `to`, and (manager-only)
`employee_id` filters are supported; dates use ISO `YYYY-MM-DD`. The workspace
supports daily, weekly, monthly, and custom reporting ranges.

## Sample data

For local/testing environments with an active Sales & Marketing manager and
at least one approved representative, run:

```sh
cd backend
python seed_sales_demo.py
```

The seed inserts ten clearly marked `DEMO TELESALES SAMPLE` prospects, call
outcomes, an appointment, a retry, complete and incomplete registrations, and
follow-up tasks. It is idempotent and will not create duplicate sample leads.
Do not run it in production reporting environments unless the demo data is
intended to appear in reports.

## Field visit reports

Daily Sales reports retain the existing `field_visit` workflow and registration
analytics. Managers and permitted representatives can download CSV or Excel
templates and import/export report records from the Sales reports page. CSV and
`.xlsx` imports are limited to 500 records, validated as one batch, and rejected
without saving any rows if one row is invalid. The Excel template uses the same
column names as the CSV template. Managers must fill `employee_id` for each
field-agent row; individual Sales employees may leave it blank to assign rows to
themselves. The imported owner must be an active Sales employee inside the
importer's permitted hierarchy. Do not treat template/example rows as production
activity; only import verified employee figures.

`GET /api/sales/analytics/field-agents` returns statistics for the authenticated
employee's permitted scope; `/team` is restricted to Sales & Marketing managers,
and `/org` to organization-level administrators/HR and general managers. The
response includes visits, registration starts, complete/incomplete counts,
agent/dealer and sub-agent splits, conversion/completion rates, and recovery
feedback. `/analytics/field-agents/export.csv` and `/export.xlsx` provide the
same scoped, date-filtered per-agent/category metrics. Optional `from` and `to`
filters use ISO `YYYY-MM-DD` dates. Incomplete visit registrations
create a seven-day recovery item in report data. The Sales page exposes the
missing requirement list and lets an authorized employee or manager submit
verified document checklist and witness details. The item stays open until the
server-side registration rules are satisfied; manager updates notify the report
owner and are audit logged. This recovery workflow does not change telesales
follow-up tasks.

Field-visit location sharing is an explicit, optional action in the field-agent
visit form. The browser requests GPS permission only after the agent selects
“Start field visit and opt in to location”; it sends updates only while the
page is visible and the active session is running. The agent can end sharing
manually, successful report submission ends the session, and page/session exit
attempts a keepalive stop. If that final request cannot reach the server, the
server expires the session after eight hours. `/api/agent/location` rejects
`tracking_mode=active_visit` updates without an authenticated agent's current
active-sharing session. The existing supervisor live-location endpoint and map
remain scoped by current team/department/org permissions and label active
opt-in visits. Location coordinates are not part of report exports or analytics.

The legacy scheduled tracking policy and ping API remain available for other
explicitly configured use cases, but the automatic agent tracker is no longer
mounted globally in the employee app. This prevents background/scheduled
collection from bypassing the field-visit opt-in flow. The active-visit session
uses the existing sharing row and has no report-ID association; it is started
from the visit form, not linked to a persisted registration record.
