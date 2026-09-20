from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime

from services.dashboard.app.database import get_db
from services.dashboard.app.models.crm import LeadReminder, Contact, Organization
from services.dashboard.app.schemas.task_schemas import ReminderCreate

router = APIRouter()

@router.post("")
def create_reminder(rem_in: ReminderCreate, db: Session = Depends(get_db)):
    org = db.query(Organization).first()
    org_id = org.id if org else 'default-org'
    
    rem = LeadReminder(
        organization_id=org_id,
        contact_id=rem_in.contact_id,
        task_id=rem_in.task_id,
        note=rem_in.note,
        remind_at=rem_in.remind_at
    )
    db.add(rem)
    db.commit()
    db.refresh(rem)
    return {'id': rem.id, 'note': rem.note, 'remind_at': rem.remind_at}

@router.get("/active")
def list_active_reminders(db: Session = Depends(get_db)):
    rems = db.query(LeadReminder).filter(LeadReminder.is_triggered == False).order_by(LeadReminder.remind_at.asc()).all()
    results = []
    for r in rems:
        contact = db.query(Contact).filter(Contact.id == r.contact_id).first() if r.contact_id else None
        results.append({
            'id': r.id,
            'note': r.note,
            'remind_at': r.remind_at,
            'contact_name': contact.name if contact else 'Lead',
            'contact_phone': contact.phone_number if contact else ''
        })
    return results

@router.post("/{reminder_id}/dismiss")
def dismiss_reminder(reminder_id: str, db: Session = Depends(get_db)):
    r = db.query(LeadReminder).filter(LeadReminder.id == reminder_id).first()
    if r:
        r.is_triggered = True
        db.commit()
    return {'status': 'dismissed'}
