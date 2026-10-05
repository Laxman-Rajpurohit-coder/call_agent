from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from services.dashboard.app.models.crm import Contact, ContactPhone, ContactEmail
from services.dashboard.app.services.contact_identity.normalizer import normalize_phone

def check_duplicate(
    db: Session,
    organization_id: str,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    exclude_contact_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Checks if a phone number or email is already registered under this tenant.
    Returns details of existing contact if duplicate found, or None.
    """
    if phone:
        phone_e164 = normalize_phone(phone)
        if phone_e164:
            # 1. Check dedicated contact_phones table
            phone_record = db.query(ContactPhone).filter(
                ContactPhone.organization_id == organization_id,
                ContactPhone.phone_e164 == phone_e164
            ).first()

            if phone_record and phone_record.contact_id != exclude_contact_id:
                contact = db.query(Contact).filter(Contact.id == phone_record.contact_id).first()
                if contact and not contact.is_archived:
                    return {
                        "is_duplicate": True,
                        "match_field": "phone",
                        "matched_value": phone_e164,
                        "contact_id": contact.id,
                        "name": contact.name or "Unnamed Lead",
                        "phone_number": contact.phone_number,
                        "status": contact.status,
                        "company": contact.company
                    }

            # 2. Check legacy phone_number column on Contact
            direct_contact = db.query(Contact).filter(
                Contact.organization_id == organization_id,
                Contact.phone_number == phone_e164,
                Contact.id != exclude_contact_id,
                Contact.is_archived.is_(False)
            ).first()

            if direct_contact:
                return {
                    "is_duplicate": True,
                    "match_field": "phone",
                    "matched_value": phone_e164,
                    "contact_id": direct_contact.id,
                    "name": direct_contact.name or "Unnamed Lead",
                    "phone_number": direct_contact.phone_number,
                    "status": direct_contact.status,
                    "company": direct_contact.company
                }

    if email and email.strip():
        clean_email = email.strip().lower()
        email_record = db.query(ContactEmail).filter(
            ContactEmail.organization_id == organization_id,
            ContactEmail.email == clean_email
        ).first()

        if email_record and email_record.contact_id != exclude_contact_id:
            contact = db.query(Contact).filter(Contact.id == email_record.contact_id).first()
            if contact and not contact.is_archived:
                return {
                    "is_duplicate": True,
                    "match_field": "email",
                    "matched_value": clean_email,
                    "contact_id": contact.id,
                    "name": contact.name or "Unnamed Lead",
                    "phone_number": contact.phone_number,
                    "status": contact.status,
                    "company": contact.company
                }

        direct_email_contact = db.query(Contact).filter(
            Contact.organization_id == organization_id,
            Contact.email == clean_email,
            Contact.id != exclude_contact_id,
            Contact.is_archived.is_(False)
        ).first()

        if direct_email_contact:
            return {
                "is_duplicate": True,
                "match_field": "email",
                "matched_value": clean_email,
                "contact_id": direct_email_contact.id,
                "name": direct_email_contact.name or "Unnamed Lead",
                "phone_number": direct_email_contact.phone_number,
                "status": direct_email_contact.status,
                "company": direct_email_contact.company
            }

    return None
