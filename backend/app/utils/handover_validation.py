import json
import re


SENSITIVE_PATTERN = re.compile(
    r"(?i)(?:password|pin|secret|api[_\s-]?key|apikey|access[_\s-]?token|private[_\s-]?key)"
)


def _is_planned_leave(leave_request):
    code = (getattr(getattr(leave_request, "leave_type", None), "code", "") or "").upper()
    return code not in {"SICK", "UNPAID"}


def validate_handover_submission(leave_request, payload):
    errors = {}
    if not isinstance(payload, dict):
        payload = {}

    if float(getattr(leave_request, "days_requested", 0) or 0) > 2:
        if not leave_request.handover_user_id:
            errors["_"] = "Delegate is required for absences longer than two working days"
        elif leave_request.handover_user_id == leave_request.user_id:
            errors["_"] = "Delegate must not be the requester"
        else:
            delegate = leave_request.handover_user
            if delegate is None or not getattr(delegate, "is_active", False):
                errors["_"] = "Delegate must be an active user"

    if float(getattr(leave_request, "days_requested", 0) or 0) > 3 and _is_planned_leave(leave_request):
        if not (payload.get("summary") or "").strip():
            errors["_"] = "A handover report is required for absences longer than three planned working days"

    summary = (payload.get("summary") or "").strip()
    if summary:
        if len(summary) < 50 or len(summary) > 500:
            errors["summary"] = "Summary must be between 50 and 500 characters"
    elif float(getattr(leave_request, "days_requested", 0) or 0) > 3 and _is_planned_leave(leave_request):
        pass

    raw_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if SENSITIVE_PATTERN.search(raw_text):
        errors["_"] = "Passwords, PINs, secrets, and API keys are not allowed in the handover report"

    tasks = payload.get("tasks") or []
    if not isinstance(tasks, list):
        errors["tasks"] = "At least one task is required"
    elif not tasks:
        errors["tasks"] = "At least one task is required"
    else:
        for index, task in enumerate(tasks):
            if not isinstance(task, dict):
                errors[f"tasks.{index}"] = "Task record is invalid"
                continue
            if not (task.get("next_action") or "").strip():
                errors[f"tasks.{index}.next_action"] = "Next action is required"
            if not task.get("deadline"):
                errors[f"tasks.{index}.deadline"] = "Deadline is required"

    escalations = payload.get("escalations") or []
    if not isinstance(escalations, list):
        escalations = []
    for index, escalation in enumerate(escalations):
        if not isinstance(escalation, dict):
            errors[f"escalations.{index}"] = "Escalation record is invalid"
            continue
        phone = (escalation.get("contact_phone") or "").strip()
        email = (escalation.get("contact_email") or "").strip()
        if not phone and not email:
            errors[f"escalations.{index}"] = "Each escalation needs a phone number or email address"

    attachments = payload.get("attachments") or []
    if not isinstance(attachments, list):
        attachments = []
    for index, attachment in enumerate(attachments):
        if not isinstance(attachment, dict):
            errors[f"attachments.{index}"] = "Attachment record is invalid"
            continue
        mime_type = (attachment.get("mime_type") or "").lower()
        size_bytes = attachment.get("size_bytes")
        if mime_type not in {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
            errors[f"attachments.{index}.mime_type"] = "Attachment must be PDF or DOCX"
        if size_bytes is not None:
            try:
                if int(size_bytes) > 10 * 1024 * 1024:
                    errors[f"attachments.{index}.size_bytes"] = "Attachment must be 10 MB or less"
            except (TypeError, ValueError):
                errors[f"attachments.{index}.size_bytes"] = "Attachment size is invalid"

    if not summary and float(getattr(leave_request, "days_requested", 0) or 0) <= 3:
        return errors

    if float(getattr(leave_request, "days_requested", 0) or 0) > 3 and _is_planned_leave(leave_request):
        if not summary or len(summary) < 50 or len(summary) > 500:
            errors["summary"] = "Summary must be between 50 and 500 characters"

    return errors
