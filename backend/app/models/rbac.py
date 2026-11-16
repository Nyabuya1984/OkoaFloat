from app.extensions import db


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, unique=True)
    level = db.Column(db.Integer, nullable=False, default=4)


class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)


class RolePermission(db.Model):
    __tablename__ = "role_permissions"
    __table_args__ = (
        db.UniqueConstraint(
            "role_id",
            "permission_id",
            "effect",
            name="uq_role_permission_effect",
        ),
        db.CheckConstraint("effect IN ('allow', 'deny')", name="ck_role_permission_effect"),
        db.Index("ix_role_permissions_role_effect", "role_id", "effect"),
    )

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(
        db.Integer,
        db.ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    permission_id = db.Column(
        db.Integer,
        db.ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    effect = db.Column(db.String(8), nullable=False)

    role = db.relationship("Role")
    permission = db.relationship("Permission")


class UserRole(db.Model):
    __tablename__ = "user_roles"
    __table_args__ = (
        db.UniqueConstraint("user_id", name="uq_user_single_role"),
        db.Index("ix_user_roles_role_id", "role_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id = db.Column(
        db.Integer,
        db.ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
    )

    user = db.relationship("User")
    role = db.relationship("Role")
