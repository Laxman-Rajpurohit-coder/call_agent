from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Dict, Any, List

from services.dashboard.app.database import get_db
from services.dashboard.app.models.crm import Contact, TeamMember
from services.dashboard.app.services.lead_router_service import process_incoming_lead_webhook

router = APIRouter()

@router.post("/webhook")
async def handle_lead_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        try:
            form_data = await request.form()
            payload = dict(form_data)
        except Exception:
            payload = {}
    
    result = process_incoming_lead_webhook(db, payload)
    return result

@router.get("")
def list_leads(db: Session = Depends(get_db)):
    contacts = db.query(Contact).filter(Contact.status == 'lead').order_by(Contact.created_at.desc()).all()
    results = []
    for c in contacts:
        owner = db.query(TeamMember).filter(TeamMember.id == c.lead_owner_id).first() if c.lead_owner_id else None
        results.append({
            'id': c.id,
            'name': c.name,
            'phone_number': c.phone_number,
            'email': c.email,
            'status': c.status,
            'lead_source': c.lead_source,
            'lead_owner_name': owner.name if owner else 'Unassigned',
            'custom_fields': c.custom_fields,
            'created_at': c.created_at
        })
    return results
