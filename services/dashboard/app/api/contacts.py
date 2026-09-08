import io
import csv
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from services.dashboard.app.database import get_db
from services.dashboard.app.models import Contact, Organization
from services.dashboard.app.schemas import ContactCreate, ContactResponse

router = APIRouter(prefix="/contacts", tags=["Contacts"])

@router.get("", response_model=List[ContactResponse])
async def list_contacts(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Contact).order_by(Contact.created_at.desc()).limit(limit).all()

@router.post("", response_model=ContactResponse)
async def create_contact(contact_in: ContactCreate, db: Session = Depends(get_db)):
    org = db.query(Organization).first()
    if not org:
        org = Organization(name="Default Org", slug="default-org")
        db.add(org)
        db.commit()
        db.refresh(org)

    existing = db.query(Contact).filter(Contact.organization_id == org.id, Contact.phone_number == contact_in.phone_number).first()
    if existing:
        return existing

    new_c = Contact(
        organization_id=org.id,
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
async def get_contact_history(contact_id: str, db: Session = Depends(get_db)):
    from services.dashboard.app.models import CallSession
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        contact = db.query(Contact).filter(Contact.phone_number == contact_id).first()

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

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
