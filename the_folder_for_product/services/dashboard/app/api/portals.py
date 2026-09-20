import os
import uuid
import re
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from services.dashboard.app.database import get_db
from services.dashboard.app.dependencies import (
    get_current_user, require_role, hash_password, get_optional_user
)
from services.dashboard.app.models.crm import (
    Organization, PortalConfig, AgentConfig, Service, PhoneNumber,
    BusinessHours, TeamMember, Contact, CallSession, AuditLog
)
from services.dashboard.app.models.campaign import Campaign

router = APIRouter(prefix="/portals", tags=["Portals"])

# --- Schemas ---

class ServiceInput(BaseModel):
    name: str
    description: Optional[str] = ""
    price: Optional[float] = 0.0
    duration_mins: Optional[int] = 30
    category: Optional[str] = "General"

class PhoneNumberInput(BaseModel):
    phone_number: str
    provider: Optional[str] = "Exotel"
    purpose: Optional[str] = "reception"
    is_primary: Optional[bool] = True

class InitialUserInput(BaseModel):
    name: str
    email: str
    password: str
    role: Optional[str] = "ADMIN"

class PortalCreateRequest(BaseModel):
    # 1. Organization Profile
    name: str
    slug: str
    industry: Optional[str] = "Healthcare / Dental"
    country: Optional[str] = "India"
    timezone: Optional[str] = "Asia/Kolkata"

    # 2. Portal Branding
    portal_name: Optional[str] = None
    subtitle: Optional[str] = "AI Receptionist & Lead Management"
    theme_primary: Optional[str] = "#6366f1"
    theme_bg: Optional[str] = "#0f172a"
    logo_icon: Optional[str] = "⚡"
    logo_url: Optional[str] = None

    # 3. AI Agent Configuration
    agent_name: Optional[str] = "Riya"
    voice_model: Optional[str] = "cartesia_hi_sonic"
    language: Optional[str] = "hi"
    system_instructions: Optional[str] = None
    max_call_duration_s: Optional[int] = 300

    # 4. Catalog & Contact Details
    services: Optional[List[ServiceInput]] = []
    phone_numbers: Optional[List[PhoneNumberInput]] = []

    # 5. Initial User
    initial_user: Optional[InitialUserInput] = None

class PortalUpdateRequest(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    portal_name: Optional[str] = None
    subtitle: Optional[str] = None
    theme_primary: Optional[str] = None
    theme_bg: Optional[str] = None
    logo_icon: Optional[str] = None
    agent_name: Optional[str] = None
    voice_model: Optional[str] = None
    language: Optional[str] = None
    system_instructions: Optional[str] = None
    max_call_duration_s: Optional[int] = None
    is_active: Optional[bool] = None

def _sync_prisma_account_and_user(org: Organization, user: Optional[TeamMember], plain_password: Optional[str]):
    """Sync newly provisioned tenant to Prisma SQLite for backward-compatible Express login."""
    prisma_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../prisma/dev.db"))
    if not os.path.exists(prisma_db_path):
        return

    try:
        conn = sqlite3.connect(prisma_db_path)
        cur = conn.cursor()
        now_iso = datetime.utcnow().isoformat()

        # Check / insert Account
        cur.execute("SELECT id FROM Account WHERE id = ?", (org.id,))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO Account (id, name, phone, workingHours, agentName, voiceName, createdAt, updatedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (org.id, org.name, "+919876543210", "09:00 - 20:00", "Riya", "en-IN-Wavenet-A", now_iso, now_iso))

        # Check / insert User
        if user and plain_password:
            cur.execute("SELECT id FROM User WHERE email = ?", (user.email,))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO User (id, accountId, email, password, name, role, createdAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user.id, org.id, user.email, plain_password, user.name, user.role, now_iso))

        conn.commit()
        conn.close()
    except Exception as ex:
        print(f"[Prisma Sync Warning] Could not sync tenant to prisma/dev.db: {ex}")

# --- Endpoints ---

@router.post("", status_code=status.HTTP_201_CREATED)
def create_portal(
    req: PortalCreateRequest,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    """
    Atomic 6-Entity Portal Provisioning:
    Creates Organization, PortalConfig, AgentConfig, Services, PhoneNumber,
    Initial User, and AuditLog in a single atomic database transaction.
    """
    # 1. Validate slug
    slug_clean = re.sub(r"[^a-z0-9-]", "", req.slug.lower().strip().replace(" ", "-"))
    if not slug_clean or len(slug_clean) < 3:
        raise HTTPException(status_code=400, detail="Portal slug must be at least 3 alphanumeric characters")

    existing_slug = db.query(Organization).filter(Organization.slug == slug_clean).first()
    if existing_slug:
        raise HTTPException(status_code=400, detail=f"Portal with slug '{slug_clean}' already exists")

    try:
        # Entity 1: Organization
        org_id = str(uuid.uuid4())
        org = Organization(
            id=org_id,
            name=req.name.strip(),
            slug=slug_clean,
            industry=req.industry or "Healthcare / Dental",
            country=req.country or "India",
            timezone=req.timezone or "Asia/Kolkata",
            is_active=True
        )
        db.add(org)

        # Entity 2: PortalConfig
        portal_config = PortalConfig(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            portal_name=req.portal_name or f"{req.name} Portal",
            subtitle=req.subtitle or "AI Receptionist & Lead Management",
            theme_primary=req.theme_primary or "#6366f1",
            theme_bg=req.theme_bg or "#0f172a",
            logo_icon=req.logo_icon or "⚡",
            logo_url=req.logo_url
        )
        db.add(portal_config)

        # Entity 3: AgentConfig
        agent_config = AgentConfig(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            agent_name=req.agent_name or "Riya",
            voice_model=req.voice_model or "cartesia_hi_sonic",
            language=req.language or "hi",
            system_instructions=req.system_instructions or f"You are {req.agent_name or 'Riya'}, AI assistant for {req.name}. Greet patients warmly and assist with bookings.",
            max_call_duration_s=req.max_call_duration_s or 300
        )
        db.add(agent_config)

        # Entity 4: Services
        default_services = req.services or [
            ServiceInput(name="Consultation", description="General consultation", price=500.0, duration_mins=20, category="General")
        ]
        for s in default_services:
            db.add(Service(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                name=s.name,
                description=s.description or "",
                price=float(s.price or 0.0),
                duration_mins=int(s.duration_mins or 30),
                category=s.category or "General",
                is_active=True
            ))

        # Entity 5: Phone Numbers
        default_phones = req.phone_numbers or [
            PhoneNumberInput(phone_number="+919876543210", provider="Exotel", purpose="reception", is_primary=True)
        ]
        for p in default_phones:
            db.add(PhoneNumber(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                phone_number=p.phone_number,
                provider=p.provider or "Exotel",
                purpose=p.purpose or "reception",
                is_primary=bool(p.is_primary),
                status="active"
            ))

        # Business Hours (Mon - Sat default)
        for day in range(6):
            db.add(BusinessHours(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                day_of_week=day,
                is_open=True,
                open_time="09:00",
                close_time="20:00"
            ))

        # Entity 6: Initial User
        initial_user_record = None
        plain_password = None
        if req.initial_user and req.initial_user.email:
            plain_password = req.initial_user.password or "admin123"
            initial_user_record = TeamMember(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                name=req.initial_user.name or "Portal Admin",
                email=req.initial_user.email.strip().lower(),
                role=(req.initial_user.role or "ADMIN").upper(),
                password_hash=hash_password(plain_password),
                pin_code="1234",
                is_active=True
            )
            db.add(initial_user_record)

        # Entity 7: Audit Log
        db.add(AuditLog(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            user_id=user.id if user else None,
            action="PORTAL_PROVISIONED",
            resource_type="portal",
            resource_id=org_id,
            meta_info={
                "portal_name": portal_config.portal_name,
                "slug": slug_clean,
                "created_by": user.email if user else "system"
            }
        ))

        db.commit()
        db.refresh(org)

        # Sync to Prisma dev.db for seamless Express /agent-legacy compatibility
        _sync_prisma_account_and_user(org, initial_user_record, plain_password)

        return {
            "success": True,
            "message": f"Portal '{org.name}' successfully provisioned",
            "portal": {
                "id": org.id,
                "name": org.name,
                "slug": org.slug,
                "portal_url": f"/portal/{org.slug}",
                "legacy_portal_url": f"/agent-legacy/?portal={org.slug}",
                "theme_primary": portal_config.theme_primary,
                "agent_name": agent_config.agent_name,
                "initial_admin_email": req.initial_user.email if req.initial_user else None
            }
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as ex:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to provision portal: {str(ex)}"
        )

@router.get("/{slug}/public")
def get_public_portal_config(slug: str, db: Session = Depends(get_db)):
    """
    Public Portal Configuration Endpoint:
    Strict whitelist returning ONLY branding, agent metadata, and public service catalog.
    Zero internal credentials, passwords, SIP secrets, or audit logs exposed.
    """
    org = db.query(Organization).filter(Organization.slug == slug).first()
    if not org or not org.is_active:
        raise HTTPException(status_code=404, detail="Portal not found or inactive")

    p_conf = org.portal_config or PortalConfig()
    a_conf = org.agent_config or AgentConfig()

    active_services = db.query(Service).filter(
        Service.organization_id == org.id,
        Service.is_active == True
    ).all()

    hours = db.query(BusinessHours).filter(
        BusinessHours.organization_id == org.id
    ).order_by(BusinessHours.day_of_week.asc()).all()

    return {
        "success": True,
        "organization": {
            "name": org.name,
            "slug": org.slug,
            "industry": org.industry,
            "country": org.country,
            "timezone": org.timezone
        },
        "branding": {
            "portal_name": p_conf.portal_name or org.name,
            "subtitle": p_conf.subtitle or "AI Receptionist & Lead Management",
            "theme_primary": p_conf.theme_primary or "#6366f1",
            "theme_bg": p_conf.theme_bg or "#0f172a",
            "logo_icon": p_conf.logo_icon or "⚡",
            "logo_url": p_conf.logo_url
        },
        "ai_receptionist": {
            "agent_name": a_conf.agent_name or "Riya",
            "voice_model": a_conf.voice_model or "cartesia_hi_sonic",
            "language": a_conf.language or "hi",
            "max_call_duration_s": a_conf.max_call_duration_s or 300
        },
        "services": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "price": s.price,
                "duration_mins": s.duration_mins,
                "category": s.category
            }
            for s in active_services
        ],
        "business_hours": [
            {
                "day_of_week": h.day_of_week,
                "is_open": h.is_open,
                "open_time": h.open_time,
                "close_time": h.close_time
            }
            for h in hours
        ]
    }

@router.get("")
def list_portals(db: Session = Depends(get_db)):
    """
    List all provisioned agent portals with aggregated operational metrics.
    """
    orgs = db.query(Organization).order_by(Organization.created_at.desc()).all()
    results = []
    for org in orgs:
        p_conf = org.portal_config or PortalConfig()
        a_conf = org.agent_config or AgentConfig()

        agent_count = db.query(TeamMember).filter(TeamMember.organization_id == org.id).count()
        lead_count = db.query(Contact).filter(Contact.organization_id == org.id).count()
        call_count = db.query(CallSession).filter(CallSession.organization_id == org.id).count()
        campaign_count = db.query(Campaign).filter(Campaign.organization_id == org.id).count()

        results.append({
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "industry": org.industry,
            "country": org.country,
            "is_active": org.is_active,
            "created_at": org.created_at.isoformat() if org.created_at else None,
            "branding": {
                "portal_name": p_conf.portal_name or org.name,
                "theme_primary": p_conf.theme_primary or "#6366f1",
                "logo_icon": p_conf.logo_icon or "⚡"
            },
            "agent_config": {
                "agent_name": a_conf.agent_name or "Riya",
                "voice_model": a_conf.voice_model or "cartesia_hi_sonic",
                "language": a_conf.language or "hi"
            },
            "metrics": {
                "agent_count": agent_count,
                "lead_count": lead_count,
                "call_count": call_count,
                "campaign_count": campaign_count
            },
            "urls": {
                "portal_url": f"/portal/{org.slug}",
                "legacy_portal_url": f"/agent-legacy/?portal={org.slug}"
            }
        })
    return results

@router.get("/{id_or_slug}")
def get_portal_detail(id_or_slug: str, db: Session = Depends(get_db)):
    """Get full portal configuration by ID or slug."""
    org = db.query(Organization).filter(
        (Organization.id == id_or_slug) | (Organization.slug == id_or_slug)
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Portal not found")

    p_conf = org.portal_config or PortalConfig()
    a_conf = org.agent_config or AgentConfig()
    services = db.query(Service).filter(Service.organization_id == org.id).all()
    phones = db.query(PhoneNumber).filter(PhoneNumber.organization_id == org.id).all()
    members = db.query(TeamMember).filter(TeamMember.organization_id == org.id).all()

    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "industry": org.industry,
        "country": org.country,
        "timezone": org.timezone,
        "is_active": org.is_active,
        "portal_config": {
            "portal_name": p_conf.portal_name,
            "subtitle": p_conf.subtitle,
            "theme_primary": p_conf.theme_primary,
            "theme_bg": p_conf.theme_bg,
            "logo_icon": p_conf.logo_icon,
            "logo_url": p_conf.logo_url
        },
        "agent_config": {
            "agent_name": a_conf.agent_name,
            "voice_model": a_conf.voice_model,
            "language": a_conf.language,
            "system_instructions": a_conf.system_instructions,
            "max_call_duration_s": a_conf.max_call_duration_s
        },
        "services": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "price": s.price,
                "duration_mins": s.duration_mins,
                "category": s.category,
                "is_active": s.is_active
            }
            for s in services
        ],
        "phone_numbers": [
            {
                "id": p.id,
                "phone_number": p.phone_number,
                "provider": p.provider,
                "purpose": p.purpose,
                "is_primary": p.is_primary,
                "status": p.status
            }
            for p in phones
        ],
        "team_members": [
            {
                "id": m.id,
                "name": m.name,
                "email": m.email,
                "role": m.role,
                "is_active": m.is_active
            }
            for m in members
        ]
    }

@router.patch("/{portal_id}")
def update_portal(
    portal_id: str,
    req: PortalUpdateRequest,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    """Update portal branding and configuration."""
    org = db.query(Organization).filter(Organization.id == portal_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Portal not found")

    if user:
        if (user.role or "AGENT").upper() == "VIEWER":
            raise HTTPException(status_code=403, detail="Viewer role is read-only")
        if (user.role or "AGENT").upper() not in ["OWNER", "ADMIN"]:
            raise HTTPException(status_code=403, detail="Admin or Owner role required to update portal configuration")

    if req.name:
        org.name = req.name.strip()
    if req.industry:
        org.industry = req.industry
    if req.is_active is not None:
        org.is_active = req.is_active

    p_conf = org.portal_config
    if not p_conf:
        p_conf = PortalConfig(id=str(uuid.uuid4()), organization_id=org.id)
        db.add(p_conf)

    if req.portal_name: p_conf.portal_name = req.portal_name
    if req.subtitle: p_conf.subtitle = req.subtitle
    if req.theme_primary: p_conf.theme_primary = req.theme_primary
    if req.theme_bg: p_conf.theme_bg = req.theme_bg
    if req.logo_icon: p_conf.logo_icon = req.logo_icon

    a_conf = org.agent_config
    if not a_conf:
        a_conf = AgentConfig(id=str(uuid.uuid4()), organization_id=org.id)
        db.add(a_conf)

    if req.agent_name: a_conf.agent_name = req.agent_name
    if req.voice_model: a_conf.voice_model = req.voice_model
    if req.language: a_conf.language = req.language
    if req.system_instructions: a_conf.system_instructions = req.system_instructions
    if req.max_call_duration_s: a_conf.max_call_duration_s = req.max_call_duration_s

    db.commit()
    db.refresh(org)
    return {"success": True, "message": "Portal configuration updated successfully"}
