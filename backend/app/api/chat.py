from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models import ChatMessage, User
from app.utils.rbac import is_super_admin


chat_bp = Blueprint("chat", __name__)


def _user():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None
    user = db.session.get(User, user_id)
    if not user or not user.is_currently_active() or user.account_status != "approved":
        return None
    return user


def _can_access_peer(user, peer):
    if not peer or peer.id == user.id:
        return False
    if not peer.is_currently_active() or peer.account_status != "approved":
        return False
    return not is_super_admin(peer) or is_super_admin(user)


def _message_dict(message):
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "sender_name": message.sender.full_name,
        "recipient_id": message.recipient_id,
        "body": message.body,
        "created_at": message.created_at.isoformat(),
    }


@chat_bp.get("/users")
@jwt_required()
def users():
    user = _user()
    if not user:
        return jsonify({"error": "User not found or inactive"}), 404
    peers = User.query.filter(
        User.id != user.id,
        User.is_active.is_(True),
        User.is_archived.is_(False),
        User.is_deleted.is_(False),
        User.account_status == "approved",
    )
    if not is_super_admin(user):
        peers = peers.filter(User.is_superuser.is_(False), User.role != "SUPER_ADMIN")
    peers = peers.order_by(User.full_name.asc()).all()
    return jsonify({
        "data": [
            {
                "id": peer.id,
                "name": peer.full_name,
                "role": peer.role,
                "department": peer.department,
                "department_name": (
                    peer.department_record.name
                    if peer.department_record
                    else peer.department
                ),
                "department_id": peer.department_id,
            }
            for peer in peers
        ]
    })


@chat_bp.get("/messages/<int:peer_id>")
@jwt_required()
def messages(peer_id):
    user = _user()
    peer = db.session.get(User, peer_id)
    if not user or not _can_access_peer(user, peer):
        return jsonify({"error": "User not found"}), 404
    rows = ChatMessage.query.filter(
        ((ChatMessage.sender_id == user.id) & (ChatMessage.recipient_id == peer.id))
        | ((ChatMessage.sender_id == peer.id) & (ChatMessage.recipient_id == user.id))
    ).order_by(ChatMessage.created_at.asc()).limit(200).all()
    return jsonify({"data": [_message_dict(row) for row in rows]})


@chat_bp.get("/unread-count")
@jwt_required()
def unread_count():
    user = _user()
    if not user:
        return jsonify({"error": "User not found or inactive"}), 404
    count = ChatMessage.query.filter_by(recipient_id=user.id, read_at=None).count()
    return jsonify({"data": {"count": count}})


@chat_bp.post("/messages/<int:peer_id>/read")
@jwt_required()
def mark_messages_read(peer_id):
    user = _user()
    peer = db.session.get(User, peer_id)
    if not user or not _can_access_peer(user, peer):
        return jsonify({"error": "User not found"}), 404
    ChatMessage.query.filter_by(sender_id=peer.id, recipient_id=user.id, read_at=None).update(
        {"read_at": datetime.utcnow()}, synchronize_session=False
    )
    db.session.commit()
    return jsonify({"data": {"count": 0}})


@chat_bp.post("/messages")
@jwt_required()
def send_message():
    user = _user()
    payload = request.get_json(silent=True) or {}
    peer = db.session.get(User, payload.get("recipient_id"))
    body = (payload.get("body") or "").strip()
    if not user or not _can_access_peer(user, peer):
        return jsonify({"error": "Recipient not found"}), 404
    if not body or len(body) > 2000:
        return jsonify({"error": "Message must contain 1 to 2000 characters"}), 400
    message = ChatMessage(sender_id=user.id, recipient_id=peer.id, body=body)
    db.session.add(message)
    db.session.commit()
    return jsonify({"data": _message_dict(message)}), 201