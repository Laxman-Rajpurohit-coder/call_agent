import io
import csv
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from services.dashboard.app.database import get_db
from services.dashboard.app.models import Contact, Organization, TeamMember
from services.dashboard.app.schemas import ContactCreate, ContactResponse
from services.dashboard.app.dependencies import get_optional_user, get_authorized_lead

router = APIRouter(prefix="/contacts", tags=["Contacts"])

@router.get("", response_model=List[ContactResponse])
async def list_contacts(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Contact).order_by(Contact.created_at.desc()).limit(limit).all()

@router.get("/agent/{agent_id}")
async def list_contacts_for_agent(agent_id: str, db: Session = Depends(get_db)):
    """
    Returns contacts assigned to this agent (lead_owner_id == agent_id).
    Each contact includes full custom_fields: intent_score, bot_summary,
    last_disposition, callback_scheduled_for, agent_notes.
    """
    from services.dashboard.app.models import CallSession as CallSessionModel
    contacts = db.query(Contact).filter(
        Contact.lead_owner_id == agent_id
    ).order_by(Contact.updated_at.desc()).all()

    result = []
    for c in contacts:
        cf = c.custom_fields or {}
        # Count calls for this contact
        call_count = db.query(CallSessionModel).filter(
            (CallSessionModel.contact_id == c.id) |
            (CallSessionModel.from_number == c.phone_number) |
            (CallSessionModel.to_number == c.phone_number)
        ).count()

        result.append({
            "id": c.id,
            "name": c.name or "Unnamed Lead",
            "phone_number": c.phone_number,
            "email": c.email,
            "status": c.status,
            "preferred_language": c.preferred_language,
            "lead_source": c.lead_source,
            "lead_owner_id": c.lead_owner_id,
            "last_called_at": c.last_called_at.isoformat() if c.last_called_at else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "total_calls": call_count,
            # Interest / intent fields from AI bot
            "intent_score": cf.get("intent_score"),
            "bot_summary": cf.get("bot_summary"),
            "last_intent": cf.get("last_intent") or cf.get("bot_intent"),
            "last_disposition": cf.get("last_disposition_by"),
            "callback_scheduled_for": cf.get("callback_scheduled_for"),
            "agent_notes": cf.get("agent_notes", []),
            "custom_fields": cf,
        })

    return result

@router.post("", response_model=ContactResponse)
async def create_contact(
    contact_in: ContactCreate,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    if user:
        if (user.role or "AGENT").upper() == "VIEWER":
            raise HTTPException(status_code=403, detail="Viewer role is read-only")
        org_id = user.organization_id
    else:
        org = db.query(Organization).first()
        org_id = org.id if org else "default-org"

    existing = db.query(Contact).filter(Contact.organization_id == org_id, Contact.phone_number == contact_in.phone_number).first()
    if existing:
        return existing

    new_c = Contact(
        organization_id=org_id,
        phone_number=contact_in.phone_number,
        name=contact_in.name,
        email=contact_in.email,
        status=contact_in.status or "lead",
        preferred_language=contact_in.preferred_language or "hi"
    )
    db.add(new_c)
    db.commit()
    db.refresh(new_c)
    return new_c

@router.get("/{contact_id}")
async def get_contact_detail(
    contact_id: str,
    lead: Contact = Depends(get_authorized_lead)
):
    """Returns single lead detail with strict tenant isolation and agent confidentiality."""
    return lead

@router.post("/import-csv")
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    org = db.query(Organization).first()
    if not org:
        org = Organization(name="Default Org", slug="default-org")
        db.add(org)
        db.commit()
        db.refresh(org)

    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    skipped = 0

    for row in reader:
        phone = row.get("phone") or row.get("phone_number") or row.get("mobile")
        if not phone:
            skipped += 1
            continue

        name = row.get("name")
        email = row.get("email")
        existing = db.query(Contact).filter(Contact.organization_id == org.id, Contact.phone_number == phone).first()
        if not existing:
            c = Contact(organization_id=org.id, phone_number=phone, name=name, email=email)
            db.add(c)
            imported += 1
        else:
            skipped += 1

    db.commit()
    return {"status": "success", "imported": imported, "skipped": skipped}

@router.get("/{contact_id}/history")
async def get_contact_history(
    contact_id: str,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    from services.dashboard.app.models import CallSession
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        contact = db.query(Contact).filter(Contact.phone_number == contact_id).first()

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if user:
        if contact.organization_id != user.organization_id:
            raise HTTPException(status_code=404, detail="Contact not found")
        role_upper = (user.role or "AGENT").upper()
        if role_upper not in ["OWNER", "ADMIN", "MANAGER"] and contact.lead_owner_id != user.id:
            raise HTTPException(status_code=403, detail="Access denied: You do not own this lead")

    calls = db.query(CallSession).filter(
        (CallSession.contact_id == contact.id) |
        (CallSession.from_number == contact.phone_number) |
        (CallSession.to_number == contact.phone_number)
    ).order_by(CallSession.created_at.desc()).all()

    return {
        "contact": {
            "id": contact.id,
            "name": contact.name or "Unnamed Lead",
            "phone_number": contact.phone_number,
            "email": contact.email,
            "status": contact.status,
            "preferred_language": contact.preferred_language,
            "last_called_at": contact.last_called_at,
            "created_at": contact.created_at
        },
        "total_calls": len(calls),
        "total_duration_s": sum(c.duration_s or 0 for c in calls),
        "calls": calls
    }

@router.patch("/{contact_id}")
async def update_contact_disposition(
    contact_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        contact = db.query(Contact).filter(Contact.phone_number == contact_id).first()

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if user:
        if contact.organization_id != user.organization_id:
            raise HTTPException(status_code=404, detail="Contact not found")
        role_upper = (user.role or "AGENT").upper()
        if role_upper == "VIEWER":
            raise HTTPException(status_code=403, detail="Viewer role is read-only")
        if role_upper not in ["OWNER", "ADMIN", "MANAGER"] and contact.lead_owner_id != user.id:
            raise HTTPException(status_code=403, detail="Access denied: You do not own this lead")

    if "status" in payload:
        contact.status = payload["status"]
    if "lead_owner_id" in payload:
        contact.lead_owner_id = payload["lead_owner_id"]
    if "custom_fields" in payload:
        cf = dict(contact.custom_fields or {})
        cf.update(payload["custom_fields"])
        contact.custom_fields = cf
    if "notes" in payload:
        from datetime import datetime
        cf = dict(contact.custom_fields or {})
        notes_list = list(cf.get("agent_notes") or [])
        notes_list.append({
            "text": payload["notes"],
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": payload.get("agent_id", "agent-1"),
            "disposition": payload.get("status")
        })
        cf["agent_notes"] = notes_list
        contact.custom_fields = cf

    db.commit()
    db.refresh(contact)
    return {"status": "success", "contact": contact}
