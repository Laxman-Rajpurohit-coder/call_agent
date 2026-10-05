from typing import Optional
from sqlalchemy.orm import Session
from services.dashboard.app.models.crm import Contact, ContactPhone
from services.dashboard.app.services.contact_identity.normalizer import normalize_phone

def resolve_contact(
    db: Session,
    organization_id: str,
    phone: str,
    name: Optional[str] = None,
    company: Optional[str] = None,
    auto_create: bool = True
) -> Optional[Contact]:
    """
    Resolves the single customer identity for a given phone number under a tenant.
    
    1. Normalizes phone to E.164.
    2. Looks up in contact_phones under tenant.
    3. If found, resolves surviving contact if merged.
    4. If not found in contact_phones, checks legacy Contact.phone_number.
    5. If found, backfills contact_phones record.
    6. If not found and auto_create is True, creates new Contact + primary ContactPhone.
    """
    if not phone:
        return None

    phone_e164 = normalize_phone(phone)
    if not phone_e164:
        return None

    # Step 1: Check contact_phones table
    phone_entry = db.query(ContactPhone).filter(
        ContactPhone.organization_id == organization_id,
        ContactPhone.phone_e164 == phone_e164
    ).first()

    contact = None
    if phone_entry:
        contact = db.query(Contact).filter(Contact.id == phone_entry.contact_id).first()

    # Step 2: Fallback to Contact.phone_number
    if not contact:
        contact = db.query(Contact).filter(
            Contact.organization_id == organization_id,
            (Contact.phone_number == phone_e164) | (Contact.phone_number == phone)
        ).first()

        # If found in Contact table, backfill ContactPhone
        if contact:
            existing_phone = db.query(ContactPhone).filter(
                ContactPhone.organization_id == organization_id,
                ContactPhone.phone_e164 == phone_e164
            ).first()
            if not existing_phone:
                new_phone = ContactPhone(
                    contact_id=contact.id,
                    organization_id=organization_id,
                    phone_e164=phone_e164,
                    phone_type="mobile",
                    is_primary=True
                )
                db.add(new_phone)
                db.commit()

    # Step 3: If contact is merged, follow pointer to surviving identity
    if contact and contact.merged_into_id:
        visited = {contact.id}
        current = contact
        while current and current.merged_into_id and current.merged_into_id not in visited:
            visited.add(current.merged_into_id)
            current = db.query(Contact).filter(Contact.id == current.merged_into_id).first()
        if current:
            contact = current

    # Step 4: Auto-create if not found
    if not contact and auto_create:
        contact = Contact(
            organization_id=organization_id,
            phone_number=phone_e164,
            name=name or f"Caller {phone_e164[-4:]}",
            company=company,
            status="lead",
            preferred_language="hi",
            lead_source="Incoming Call"
        )
        db.add(contact)
        db.flush()

        # Create primary contact_phones entry
        primary_phone = ContactPhone(
            contact_id=contact.id,
            organization_id=organization_id,
            phone_e164=phone_e164,
            phone_type="mobile",
            is_primary=True
        )
        db.add(primary_phone)
        db.commit()
        db.refresh(contact)

    return contact
