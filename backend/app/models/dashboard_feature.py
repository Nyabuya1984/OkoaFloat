from app.extensions import db


class DashboardFeatureSetting(db.Model):
    __tablename__ = "dashboard_feature_settings"
    __table_args__ = (
        db.UniqueConstraint("role", "feature", name="uq_dashboard_feature_role"),
    )

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(32), nullable=False)
    feature = db.Column(db.String(80), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)