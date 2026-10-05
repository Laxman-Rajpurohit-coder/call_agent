from typing import Optional
from sqlalchemy.orm import Session
from services.dashboard.app.models.crm import (
    Contact, ContactPhone, ContactEmail, ContactNote,
    CallSession, LeadTask, LeadReminder
)

def merge_contacts(db: Session, survivor_id: str, victim_id: str) -> Contact:
    """
    Merges victim contact into survivor contact.
    
    1. Re-points calls, notes, reminders, tasks, phones, emails.
    2. Unions tags and merges custom fields.
    3. Fills in missing profile fields on survivor.
    4. Sets victim.merged_into_id = survivor_id and is_archived = True.
    5. Returns survivor contact with updated records.
    """
    if survivor_id == victim_id:
        raise ValueError("Cannot merge a contact into itself.")

    survivor = db.query(Contact).filter(Contact.id == survivor_id).first()
    victim = db.query(Contact).filter(Contact.id == victim_id).first()

    if not survivor or not victim:
        raise ValueError("Both survivor and victim contacts must exist.")

    if survivor.organization_id != victim.organization_id:
        raise ValueError("Cannot merge contacts across different organizations.")

    # 1. Re-point CallSessions
    db.query(CallSession).filter(CallSession.contact_id == victim.id).update(
        {"contact_id": survivor.id}, synchronize_session="fetch"
    )

    # 2. Re-point ContactNotes
    db.query(ContactNote).filter(ContactNote.contact_id == victim.id).update(
        {"contact_id": survivor.id}, synchronize_session="fetch"
    )

    # 3. Re-point LeadTasks & LeadReminders
    db.query(LeadTask).filter(LeadTask.contact_id == victim.id).update(
        {"contact_id": survivor.id}, synchronize_session="fetch"
    )
    db.query(LeadReminder).filter(LeadReminder.contact_id == victim.id).update(
        {"contact_id": survivor.id}, synchronize_session="fetch"
    )

    # 4. Migrate ContactPhones
    victim_phones = db.query(ContactPhone).filter(ContactPhone.contact_id == victim.id).all()
    survivor_phone_numbers = {p.phone_e164 for p in survivor.phones}
    for vp in victim_phones:
        if vp.phone_e164 not in survivor_phone_numbers:
            vp.contact_id = survivor.id
            vp.is_primary = False  # Keep survivor's primary
        else:
            db.delete(vp)  # Duplicate phone record removed

    # 5. Migrate ContactEmails
    victim_emails = db.query(ContactEmail).filter(ContactEmail.contact_id == victim.id).all()
    survivor_email_addresses = {e.email.lower() for e in survivor.emails}
    for ve in victim_emails:
        if ve.email.lower() not in survivor_email_addresses:
            ve.contact_id = survivor.id
            ve.is_primary = False
        else:
            db.delete(ve)

    # 6. Merge Tags (Set Union)
    survivor_tags = set(survivor.tags or [])
    victim_tags = set(victim.tags or [])
    survivor.tags = list(survivor_tags | victim_tags)

    # 7. Merge Custom Fields
    survivor_cf = dict(survivor.custom_fields or {})
    victim_cf = dict(victim.custom_fields or {})
    merged_cf = {**victim_cf, **survivor_cf}  # Survivor overrides victim
    survivor.custom_fields = merged_cf

    # 8. Adopt missing basic info
    if not survivor.name and victim.name:
        survivor.name = victim.name
    if not survivor.company and victim.company:
        survivor.company = victim.company
    if not survivor.email and victim.email:
        survivor.email = victim.email

    # 9. Mark victim as merged and archived
    victim.merged_into_id = survivor.id
    victim.is_archived = True

    # 10. Record merge note in ContactNotes
    merge_note = ContactNote(
        contact_id=survivor.id,
        organization_id=survivor.organization_id,
        agent_name="System",
        note=f"Merged duplicate contact '{victim.name or victim.phone_number}' (ID: {victim.id[:8]}...) into this contact.",
        disposition="System Action"
    )
    db.add(merge_note)

    db.commit()
    db.refresh(survivor)
    return survivor
