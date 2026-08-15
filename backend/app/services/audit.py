"""
KB-22/KB-23: action-level audit logging + universal field-level change history.
Every mutating action in kb.py and admin.py should call these — see the
'update_entity_with_history' pattern from SKILLS.md.
"""

from sqlalchemy.orm import Session
from app.models.models import AuditLog, ChangeHistory


def log_action(db: Session, user_id: str, action: str, resource_type: str, resource_id: str, details: dict = None):
    db.add(AuditLog(user_id=user_id, action=action, resource_type=resource_type,
                     resource_id=resource_id, details=details or {}))
    db.commit()


def log_change(db: Session, entity_type: str, entity_id: str, field_name: str,
                old_value, new_value, changed_by: str = None, changed_by_type: str = "user"):
    db.add(ChangeHistory(entity_type=entity_type, entity_id=str(entity_id), field_name=field_name,
                          old_value=str(old_value) if old_value is not None else None,
                          new_value=str(new_value) if new_value is not None else None,
                          changed_by=changed_by, changed_by_type=changed_by_type))
    db.commit()
