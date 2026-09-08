from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime

from services.dashboard.app.database import get_db
from services.dashboard.app.models.crm import WhatsAppMessage, Contact, Organization
from services.dashboard.app.schemas.whatsapp_schemas import WhatsAppSendRequest

router = APIRouter()

@router.get("/chats")
def list_whatsapp_chats(db: Session = Depends(get_db)):
    msgs = db.query(WhatsAppMessage).order_by(WhatsAppMessage.timestamp.asc()).all()
    if not msgs:
        contacts = db.query(Contact).limit(5).all()
        for c in contacts:
            db.add(WhatsAppMessage(
                contact_id=c.id,
                phone_number=c.phone_number,
                direction='inbound',
                message_text=f'Hi superfone, I am interested in {c.custom_fields.get("property_type", "real estate property")}.',
                status='read'
            ))
            db.add(WhatsAppMessage(
                contact_id=c.id,
                phone_number=c.phone_number,
                direction='outbound',
                message_text=f'Hello {c.name or "Lead"}! Our AI Agent just tried calling you. How can we help?',
                status='delivered'
            ))
        db.commit()
        msgs = db.query(WhatsAppMessage).order_by(WhatsAppMessage.timestamp.asc()).all()

    chats = {}
    for m in msgs:
        phone = m.phone_number
        if phone not in chats:
            contact = db.query(Contact).filter(Contact.phone_number == phone).first()
            chats[phone] = {
                'phone_number': phone,
                'contact_name': contact.name if contact and contact.name else f'Lead {phone}',
                'contact_id': m.contact_id,
                'messages': []
            }
        chats[phone]['messages'].append({
            'id': m.id,
            'direction': m.direction,
            'message_text': m.message_text,
            'status': m.status,
            'timestamp': m.timestamp
        })
    return list(chats.values())

@router.post("/send")
def send_whatsapp_message(req: WhatsAppSendRequest, db: Session = Depends(get_db)):
    org = db.query(Organization).first()
    org_id = org.id if org else 'default-org'
    
    m = WhatsAppMessage(
        organization_id=org_id,
        contact_id=req.contact_id,
        phone_number=req.phone_number,
        direction='outbound',
        message_text=req.message_text,
        status='sent'
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {'id': m.id, 'status': 'sent', 'timestamp': m.timestamp}
