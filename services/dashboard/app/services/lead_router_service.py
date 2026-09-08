import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from services.dashboard.app.models.crm import Contact, TeamMember, LeadTask, LeadReminder, Organization
from microsip_direct_caller import run_microsip_session

logger = logging.getLogger('lead_router')

def get_or_create_default_org(db: Session) -> Organization:
    org = db.query(Organization).first()
    if not org:
        org = Organization(id='default-org', name='Default Org', slug='default')
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


def assign_lead_round_robin(db: Session, org_id: str) -> Optional[TeamMember]:
    active_members = db.query(TeamMember).filter(
        TeamMember.organization_id == org_id,
        TeamMember.is_active == True
    ).order_by(TeamMember.assigned_leads_count.asc(), TeamMember.created_at.asc()).all()

    if not active_members:
        default_members = [
            TeamMember(organization_id=org_id, name='Agent Alex', email='alex@superfone.ai', role='Sales Agent', assigned_leads_count=0),
            TeamMember(organization_id=org_id, name='Agent Priya', email='priya@superfone.ai', role='Sales Agent', assigned_leads_count=0),
            TeamMember(organization_id=org_id, name='Agent Rahul', email='rahul@superfone.ai', role='Sales Agent', assigned_leads_count=0)
        ]
        for tm in default_members:
            db.add(tm)
        db.commit()
        active_members = default_members

    assigned_agent = active_members[0]
    assigned_agent.assigned_leads_count += 1
    db.commit()
    db.refresh(assigned_agent)
    return assigned_agent


def process_incoming_lead_webhook(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    org = get_or_create_default_org(db)
    
    phone = payload.get('phone') or payload.get('phone_number') or payload.get('mobile') or '9999999999'
    name = payload.get('name') or payload.get('full_name') or 'Valued Lead'
    email = payload.get('email') or payload.get('lead_email')
    lead_source = payload.get('source') or payload.get('lead_source') or payload.get('platform') or 'Google Ads'
    
    custom_inquiry = {
        'property_type': payload.get('property_type') or payload.get('requirement') or '2 BHK Apartment',
        'location': payload.get('location') or payload.get('city') or 'Bangalore',
        'budget': payload.get('budget') or '75 Lakhs',
        'raw_payload': payload
    }
    
    contact = db.query(Contact).filter(Contact.phone_number == phone).first()
    if not contact:
        contact = Contact(
            organization_id=org.id,
            phone_number=phone,
            name=name,
            email=email,
            status='lead',
            lead_source=lead_source,
            custom_fields=custom_inquiry
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)
    else:
        contact.name = name or contact.name
        contact.lead_source = lead_source or contact.lead_source
        contact.custom_fields.update(custom_inquiry)
        db.commit()

    agent = assign_lead_round_robin(db, org.id)
    if agent:
        contact.lead_owner_id = agent.id
        db.commit()

    task = LeadTask(
        organization_id=org.id,
        contact_id=contact.id,
        assigned_to_id=agent.id if agent else None,
        title=f'Inbound Lead Follow-up ({lead_source})',
        description=f'New lead captured from {lead_source}. Requirement: {custom_inquiry.get("property_type")}, City: {custom_inquiry.get("location")}.',
        status='pending',
        due_at=datetime.utcnow() + timedelta(hours=1),
        custom_inquiry_data=custom_inquiry
    )
    db.add(task)

    reminder = LeadReminder(
        organization_id=org.id,
        contact_id=contact.id,
        task_id=task.id,
        note=f'Feelow up with {contact.name} ({lead_source})',
        remind_at=datetime.utcnow() + timedelta(minutes=15)
    )
    db.add(reminder)
    db.commit()
    db.refresh(task)

    auto_call_triggered = False
    try:
        call_task = asyncio.create_task(
            run_microsip_session(
                campaign_id='lead-webhook-instant',
                script_content='',
                voice_model='cartesia_hi_sonic',
                call_mode='INTERACTIVE_AI',
                system_prompt='You are a polite AI assistant for Superfone. Qualify the lead concisely.'
            )
        )
        auto_call_triggered = True
    except Exception as ex:
        logger.warning(f'Auto call trigger deferred: {ex}')

    return {
        'status': 'success',
        'contact_id': contact.id,
        'contact_name': contact.name,
        'lead_source': contact.lead_source,
        'assigned_agent': agent.name if agent else 'Unassigned',
        'task_id': task.id,
        'auto_call_triggered': auto_call_triggered
    }
