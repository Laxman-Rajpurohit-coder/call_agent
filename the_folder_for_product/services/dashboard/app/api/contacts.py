import io
import csv
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from services.dashboard.app.database import get_db
from services.dashboard.app.models import (
    Contact, Organization, TeamMember, ContactPhone, ContactEmail, ContactNote,
    LeadReminder, CallSession as CallSessionModel
)
from services.dashboard.app.schemas import (
    ContactCreate, ContactResponse, ContactNoteCreate, ContactNoteResponse
)
from services.dashboard.app.dependencies import get_optional_user, get_authorized_lead
from services.dashboard.app.services.contact_identity.normalizer import normalize_phone
from services.dashboard.app.services.contact_identity.duplicate_detector import check_duplicate
from services.dashboard.app.services.contact_identity.merger import merge_contacts
from services.dashboard.app.services.contact_identity.timeline_service import get_contact_timeline

router = APIRouter(prefix="/contacts", tags=["Contacts"])

class TagUpdatePayload(BaseModel):
    action: str  # "add" or "remove"
    tag: str

class ReassignPayload(BaseModel):
    lead_owner_id: Optional[str] = None

class MergePayload(BaseModel):
    victim_id: str

class CheckDuplicatePayload(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    exclude_contact_id: Optional[str] = None

@router.get("", response_model=List[ContactResponse])
async def list_contacts(
    status: Optional[str] = None,
    lead_owner_id: Optional[str] = None,
    unassigned: Optional[bool] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    is_archived: bool = False,
    limit: int = Query(200, le=500),
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    """
    Action-oriented Contact list query supporting multi-tenant isolation,
    filtering by status, tag, owner, unassigned, search, and archiving.
    """
    query = db.query(Contact)

    if user:
        query = query.filter(Contact.organization_id == user.organization_id)
        role_upper = (user.role or "AGENT").upper()
        if role_upper not in ["OWNER", "ADMIN", "MANAGER"]:
            # Standard agents can see contacts assigned to them or unassigned
            query = query.filter(
                or_(Contact.lead_owner_id == user.id, Contact.lead_owner_id.is_(None))
            )

    if not is_archived:
        query = query.filter(Contact.is_archived.is_(False))
    else:
        query = query.filter(Contact.is_archived.is_(True))

    if status and status.lower() != 'all':
        query = query.filter(Contact.status.ilike(f"%{status}%"))

    if unassigned is True:
        query = query.filter(Contact.lead_owner_id.is_(None))
    elif lead_owner_id:
        query = query.filter(Contact.lead_owner_id == lead_owner_id)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Contact.name.ilike(term),
                Contact.phone_number.ilike(term),
                Contact.email.ilike(term),
                Contact.company.ilike(term)
            )
        )

    contacts = query.order_by(Contact.updated_at.desc(), Contact.created_at.desc()).limit(limit).all()

    # In-memory filter for JSON tags if tag requested
    if tag and tag.strip():
        clean_tag = tag.strip().upper()
        contacts = [
            c for c in contacts
            if c.tags and any(clean_tag == str(t).upper() for t in c.tags)
        ]

    return contacts

@router.get("/agent/{agent_id}")
async def list_contacts_for_agent(agent_id: str, db: Session = Depends(get_db)):
    """
    Returns contacts assigned to this agent (lead_owner_id == agent_id).
    Each contact includes full custom_fields: intent_score, bot_summary,
    last_disposition, callback_scheduled_for, agent_notes.
    """
    contacts = db.query(Contact).filter(
        Contact.lead_owner_id == agent_id,
        Contact.is_archived.is_(False)
    ).order_by(Contact.updated_at.desc()).all()

    result = []
    for c in contacts:
        cf = c.custom_fields or {}
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
            "company": c.company,
            "status": c.status,
            "tags": c.tags or [],
            "preferred_language": c.preferred_language,
            "lead_source": c.lead_source,
            "lead_owner_id": c.lead_owner_id,
            "last_called_at": c.last_called_at.isoformat() if c.last_called_at else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "total_calls": call_count,
            "intent_score": cf.get("intent_score"),
            "bot_summary": cf.get("bot_summary"),
            "last_intent": cf.get("last_intent") or cf.get("bot_intent"),
            "last_disposition": cf.get("last_disposition_by"),
            "callback_scheduled_for": cf.get("callback_scheduled_for"),
            "agent_notes": cf.get("agent_notes", []),
            "custom_fields": cf,
            "ai_profile": c.ai_profile or {}
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

    phone_clean = normalize_phone(contact_in.phone_number) or contact_in.phone_number.strip()

    # Check duplicate
    dup = check_duplicate(db, org_id, phone=phone_clean, email=contact_in.email)
    if dup:
        existing = db.query(Contact).filter(Contact.id == dup["contact_id"]).first()
        if existing:
            return existing

    new_c = Contact(
        organization_id=org_id,
        phone_number=phone_clean,
        name=contact_in.name,
        email=contact_in.email.strip().lower() if contact_in.email else None,
        company=contact_in.company,
        status=contact_in.status or "lead",
        tags=contact_in.tags or [],
        preferred_language=contact_in.preferred_language or "hi",
        lead_owner_id=contact_in.lead_owner_id or (user.id if user else None),
        custom_fields=contact_in.custom_fields or {}
    )
    db.add(new_c)
    db.flush()

    # Add primary ContactPhone record
    phone_rec = ContactPhone(
        contact_id=new_c.id,
        organization_id=org_id,
        phone_e164=phone_clean,
        phone_type="mobile",
        is_primary=True
    )
    db.add(phone_rec)

    if contact_in.email:
        email_rec = ContactEmail(
            contact_id=new_c.id,
            organization_id=org_id,
            email=contact_in.email.strip().lower(),
            email_type="work",
            is_primary=True
        )
        db.add(email_rec)

    db.commit()
    db.refresh(new_c)
    return new_c

@router.post("/check-duplicate")
async def api_check_duplicate(
    payload: CheckDuplicatePayload,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    org_id = user.organization_id if user else None
    if not org_id:
        org = db.query(Organization).first()
        org_id = org.id if org else "default-org"

    dup = check_duplicate(
        db,
        org_id,
        phone=payload.phone,
        email=payload.email,
        exclude_contact_id=payload.exclude_contact_id
    )
    return {"duplicate": dup}

@router.get("/{contact_id}/timeline")
async def api_get_contact_timeline(
    contact_id: str,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    """
    Returns single customer identity timeline: calls with audio recordings & transcripts,
    agent notes, reminders, transfers, and AI customer summary card.
    """
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        contact = db.query(Contact).filter(Contact.phone_number == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if user and contact.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Contact not found")

    return get_contact_timeline(db, contact.id)

@router.post("/{contact_id}/notes", response_model=ContactNoteResponse)
async def add_contact_note(
    contact_id: str,
    payload: ContactNoteCreate,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    """
    Adds a structured note to the Contact Diary with agent attribution,
    updates lead disposition/status, and optionally schedules a follow-up reminder.
    """
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        contact = db.query(Contact).filter(Contact.phone_number == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if user:
        if contact.organization_id != user.organization_id:
            raise HTTPException(status_code=404, detail="Contact not found")
        if (user.role or "AGENT").upper() == "VIEWER":
            raise HTTPException(status_code=403, detail="Viewer role is read-only")

    agent_id = user.id if user else None
    agent_name = payload.agent_name or (user.name if user else "Agent")

    note_rec = ContactNote(
        contact_id=contact.id,
        organization_id=contact.organization_id,
        agent_id=agent_id,
        agent_name=agent_name,
        note=payload.note.strip(),
        disposition=payload.disposition,
        sentiment=payload.sentiment or "neutral"
    )
    db.add(note_rec)

    # If disposition given, update contact status & custom_fields
    if payload.disposition:
        contact.status = payload.disposition
        cf = dict(contact.custom_fields or {})
        cf["last_disposition_by"] = payload.disposition
        contact.custom_fields = cf

    # If reminder requested, schedule LeadReminder
    if payload.remind_in_minutes and payload.remind_in_minutes > 0:
        remind_time = datetime.utcnow() + timedelta(minutes=payload.remind_in_minutes)
        reminder = LeadReminder(
            contact_id=contact.id,
            organization_id=contact.organization_id,
            note=f"Follow-up: {payload.disposition or 'Call'} - {payload.note[:100]}",
            remind_at=remind_time,
            is_triggered=False
        )
        db.add(reminder)

    contact.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note_rec)
    return note_rec

@router.post("/{contact_id}/tags")
async def update_contact_tags(
    contact_id: str,
    payload: TagUpdatePayload,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    """Add or remove controlled tags on a contact."""
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    current_tags = list(contact.tags or [])
    tag_clean = payload.tag.strip().upper()

    if payload.action == "add":
        if tag_clean not in current_tags:
            current_tags.append(tag_clean)
    elif payload.action == "remove":
        current_tags = [t for t in current_tags if t != tag_clean]

    contact.tags = current_tags
    contact.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(contact)
    return {"status": "success", "tags": contact.tags}

@router.post("/{contact_id}/reassign")
async def reassign_contact(
    contact_id: str,
    payload: ReassignPayload,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    """Reassign lead ownership to another team member."""
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    target_agent_name = "Unassigned"
    if payload.lead_owner_id:
        target_agent = db.query(TeamMember).filter(TeamMember.id == payload.lead_owner_id).first()
        if target_agent:
            target_agent_name = target_agent.name

    contact.lead_owner_id = payload.lead_owner_id
    contact.updated_at = datetime.utcnow()

    # Append audit note
    audit_note = ContactNote(
        contact_id=contact.id,
        organization_id=contact.organization_id,
        agent_name="System",
        note=f"Lead reassigned to {target_agent_name}.",
        disposition="Reassignment"
    )
    db.add(audit_note)
    db.commit()
    return {"status": "success", "lead_owner_id": contact.lead_owner_id}

@router.post("/{contact_id}/merge")
async def api_merge_contact(
    contact_id: str,
    payload: MergePayload,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    """Merge duplicate victim contact into survivor contact (contact_id)."""
    try:
        survivor = merge_contacts(db, survivor_id=contact_id, victim_id=payload.victim_id)
        return {"status": "success", "survivor_id": survivor.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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

        phone_clean = normalize_phone(phone) or phone.strip()
        name = row.get("name")
        email = row.get("email")
        company = row.get("company")

        dup = check_duplicate(db, org.id, phone=phone_clean, email=email)
        if not dup:
            c = Contact(
                organization_id=org.id,
                phone_number=phone_clean,
                name=name,
                email=email.strip().lower() if email else None,
                company=company
            )
            db.add(c)
            db.flush()

            # Add primary ContactPhone
            phone_rec = ContactPhone(
                contact_id=c.id,
                organization_id=org.id,
                phone_e164=phone_clean,
                phone_type="mobile",
                is_primary=True
            )
            db.add(phone_rec)
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

    calls = db.query(CallSessionModel).filter(
        (CallSessionModel.contact_id == contact.id) |
        (CallSessionModel.from_number == contact.phone_number) |
        (CallSessionModel.to_number == contact.phone_number)
    ).order_by(CallSessionModel.created_at.desc()).all()

    return {
        "contact": {
            "id": contact.id,
            "name": contact.name or "Unnamed Lead",
            "phone_number": contact.phone_number,
            "email": contact.email,
            "company": contact.company,
            "status": contact.status,
            "tags": contact.tags or [],
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

    if "name" in payload:
        contact.name = payload["name"]
    if "company" in payload:
        contact.company = payload["company"]
    if "email" in payload:
        contact.email = payload["email"]
    if "status" in payload:
        contact.status = payload["status"]
    if "lead_owner_id" in payload:
        contact.lead_owner_id = payload["lead_owner_id"]
    if "tags" in payload:
        contact.tags = payload["tags"]
    if "custom_fields" in payload:
        cf = dict(contact.custom_fields or {})
        cf.update(payload["custom_fields"])
        contact.custom_fields = cf
    if "notes" in payload and payload["notes"]:
        note_rec = ContactNote(
            contact_id=contact.id,
            organization_id=contact.organization_id,
            agent_id=user.id if user else None,
            agent_name=user.name if user else "Agent",
            note=payload["notes"],
            disposition=payload.get("status")
        )
        db.add(note_rec)

    contact.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(contact)
    return {"status": "success", "contact": contact}
