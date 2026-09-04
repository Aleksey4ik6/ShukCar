# ShukCar/audit.py
from sqlalchemy.orm import Session
from models import AuditLog

def log_action(db: Session, *, user_id: int | None, action: str, entity: str, entity_id: int | None = None, details: str | None = None):
    row = AuditLog(user_id=user_id, action=action, entity=entity, entity_id=entity_id, details=details)
    db.add(row)
    db.commit()
