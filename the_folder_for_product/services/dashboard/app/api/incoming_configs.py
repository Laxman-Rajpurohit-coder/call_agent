from services.dashboard.app.dependencies import get_optional_user
from typing import Optional
import uuid
from typing import List, Optional, Any, Dict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.dashboard.app.database import get_db
from services.dashboard.app.models.crm import (
    TeamMember, Organization, IncomingCallConfig, IncomingCallConfigAudit, PhoneNumber
)
from services.dashboard.app.dependencies import get_current_user, require_role, verify_tenant_access

router = APIRouter(prefix="/incoming-configs", tags=["Incoming Call Configs"])

# --- Pydantic Models ---

class IncomingCallConfigBase(BaseModel):
    phone_number_id: Optional[str] = None
    name: str
    is_active: bool = True
    priority: int = 0

    ai_model: str = "gpt-4o"
    voice_provider: str = "cartesia"
    voice_id: str = "cartesia_hi_sonic"
    speaking_style: str = "Friendly"
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)

    ai_name: str = "Ananya"
    role_description: Optional[str] = None
    primary_objective: Optional[str] = None
    behavior_rules: List[str] = []
    system_instructions: Optional[str] = None

    primary_language: str = "en"
    supported_languages: List[str] = []
    auto_detect_language: bool = True
    allow_language_switching: bool = True
    language_priority: List[str] = []

    auto_answer: bool = True
    ring_timeout_s: int = Field(default=15, gt=0)
    max_call_duration_s: Optional[int] = Field(default=None, gt=0)
    max_ai_duration_s: Optional[int] = Field(default=None, gt=0)

    business_name: Optional[str] = None
    business_description: Optional[str] = None
    services_offered: List[str] = []
    faq_knowledge_base: Optional[str] = None

    auto_create_contact: bool = True
    generate_ai_summary: bool = True
    extract_intent: bool = True
    auto_tags: List[str] = []

    recording_enabled: bool = True
    transcription_enabled: bool = True
    transcript_language: str = "en"

    greeting_message: Optional[str] = None
    auto_generate_greeting: bool = False

    outside_hours_action: str = "continue_ai"

    transfer_enabled: bool = True
    transfer_triggers: List[str] = []
    transfer_confidence_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    transfer_timeout_s: int = Field(default=15, gt=0)
    transfer_team_id: Optional[str] = None
    ring_strategy: str = "first_available"
    no_answer_action: str = "voicemail"

class IncomingCallConfigCreate(IncomingCallConfigBase):
    pass

class IncomingCallConfigUpdate(BaseModel):
    # Required for optimistic locking
    expected_config_version: int

    phone_number_id: Optional[str] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    ai_model: Optional[str] = None
    voice_provider: Optional[str] = None
    voice_id: Optional[str] = None
    speaking_style: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    ai_name: Optional[str] = None
    role_description: Optional[str] = None
    primary_objective: Optional[str] = None
    behavior_rules: Optional[List[str]] = None
    system_instructions: Optional[str] = None
    primary_language: Optional[str] = None
    supported_languages: Optional[List[str]] = None
    auto_detect_language: Optional[bool] = None
    allow_language_switching: Optional[bool] = None
    language_priority: Optional[List[str]] = None
    auto_answer: Optional[bool] = None
    ring_timeout_s: Optional[int] = Field(default=None, gt=0)
    max_call_duration_s: Optional[int] = Field(default=None, gt=0)
    max_ai_duration_s: Optional[int] = Field(default=None, gt=0)
    business_name: Optional[str] = None
    business_description: Optional[str] = None
    services_offered: Optional[List[str]] = None
    faq_knowledge_base: Optional[str] = None
    auto_create_contact: Optional[bool] = None
    generate_ai_summary: Optional[bool] = None
    extract_intent: Optional[bool] = None
    auto_tags: Optional[List[str]] = None
    recording_enabled: Optional[bool] = None
    transcription_enabled: Optional[bool] = None
    transcript_language: Optional[str] = None
    greeting_message: Optional[str] = None
    auto_generate_greeting: Optional[bool] = None
    outside_hours_action: Optional[str] = None
    transfer_enabled: Optional[bool] = None
    transfer_triggers: Optional[List[str]] = None
    transfer_confidence_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    transfer_timeout_s: Optional[int] = Field(default=None, gt=0)
    transfer_team_id: Optional[str] = None
    ring_strategy: Optional[str] = None
    no_answer_action: Optional[str] = None

class ConfigPreviewRequest(IncomingCallConfigBase):
    pass

# --- Endpoints ---

@router.get("")
def list_configs(
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    from services.dashboard.app.models.crm import Organization
    org_id = org_id if user else db.query(Organization).first().id
    configs = db.query(IncomingCallConfig).filter(
        IncomingCallConfig.organization_id == org_id
    ).order_by(IncomingCallConfig.priority.desc()).all()
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone_number_id": c.phone_number_id,
            "is_active": c.is_active,
            "priority": c.priority,
            "config_version": c.config_version,
            "ai_name": c.ai_name,
            "ai_model": c.ai_model
        }
        for c in configs
    ]

@router.post("")
def create_config(
    req: IncomingCallConfigCreate,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    from services.dashboard.app.models.crm import Organization
    org_id = org_id if user else db.query(Organization).first().id
    # Validate enum strings
    if req.outside_hours_action not in ["continue_ai", "voicemail", "schedule_callback"]:
        raise HTTPException(status_code=400, detail="Invalid outside_hours_action")
    if req.ring_strategy not in ["round_robin", "first_available", "team_parallel"]:
        raise HTTPException(status_code=400, detail="Invalid ring_strategy")
    if req.no_answer_action not in ["voicemail", "continue_ai", "schedule_callback", "end_call"]:
        raise HTTPException(status_code=400, detail="Invalid no_answer_action")

    # Enforce one org-default config
    if req.phone_number_id is None:
        existing_default = db.query(IncomingCallConfig).filter(
            IncomingCallConfig.organization_id == org_id,
            IncomingCallConfig.phone_number_id == None
        ).first()
        if existing_default:
            raise HTTPException(status_code=400, detail="Organization already has an active default configuration")

    new_config = IncomingCallConfig(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        config_version=1,
        **req.dict()
    )
    db.add(new_config)
    db.commit()
    db.refresh(new_config)
    
    # Optional: write initial audit log
    audit = IncomingCallConfigAudit(
        id=str(uuid.uuid4()),
        config_id=new_config.id,
        organization_id=org_id,
        changed_by_user_id=(user.id if user else "system"),
        changes={"_init": "created"},
        config_version=1
    )
    db.add(audit)
    db.commit()

    return {"success": True, "id": new_config.id, "config_version": new_config.config_version}

@router.get("/{config_id}")
def get_config(
    config_id: str,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    from services.dashboard.app.models.crm import Organization
    org_id = org_id if user else db.query(Organization).first().id
    config = db.query(IncomingCallConfig).filter(
        IncomingCallConfig.id == config_id,
        IncomingCallConfig.organization_id == org_id
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
        
    return {c.name: getattr(config, c.name) for c in config.__table__.columns}

@router.patch("/{config_id}")
def update_config(
    config_id: str,
    req: IncomingCallConfigUpdate,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    from services.dashboard.app.models.crm import Organization
    org_id = org_id if user else db.query(Organization).first().id
    # Fetch config to ensure it exists and belongs to org
    config = db.query(IncomingCallConfig).filter(
        IncomingCallConfig.id == config_id,
        IncomingCallConfig.organization_id == org_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    update_data = req.dict(exclude_unset=True, exclude={"expected_config_version"})
    if not update_data:
        return {"success": True, "message": "No changes provided"}
        
    # Enforce enums if updated
    if "outside_hours_action" in update_data and update_data["outside_hours_action"] not in ["continue_ai", "voicemail", "schedule_callback"]:
        raise HTTPException(status_code=400, detail="Invalid outside_hours_action")
    if "ring_strategy" in update_data and update_data["ring_strategy"] not in ["round_robin", "first_available", "team_parallel"]:
        raise HTTPException(status_code=400, detail="Invalid ring_strategy")
    if "no_answer_action" in update_data and update_data["no_answer_action"] not in ["voicemail", "continue_ai", "schedule_callback", "end_call"]:
        raise HTTPException(status_code=400, detail="Invalid no_answer_action")

    # Enforce one org-default config if phone_number_id is updated to None
    if "phone_number_id" in update_data and update_data["phone_number_id"] is None:
        existing_default = db.query(IncomingCallConfig).filter(
            IncomingCallConfig.organization_id == org_id,
            IncomingCallConfig.phone_number_id == None,
            IncomingCallConfig.id != config_id
        ).first()
        if existing_default:
            raise HTTPException(status_code=400, detail="Organization already has an active default configuration")

    # Optimistic locking update
    # Increment config_version atomically
    update_data["config_version"] = req.expected_config_version + 1
    update_data["updated_at"] = datetime.utcnow()

    updated_rows = db.query(IncomingCallConfig).filter(
        IncomingCallConfig.id == config_id,
        IncomingCallConfig.config_version == req.expected_config_version
    ).update(update_data, synchronize_session=False)

    if updated_rows == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Configuration was modified by another user.")

    # Make a copy for JSON serialization (convert datetime to string)
    audit_changes = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in update_data.items()}

    # Write audit log
    audit = IncomingCallConfigAudit(
        id=str(uuid.uuid4()),
        config_id=config_id,
        organization_id=org_id,
        changed_by_user_id=(user.id if user else "system"),
        changes=audit_changes,
        config_version=req.expected_config_version + 1
    )
    db.add(audit)
    db.commit()

    return {"success": True, "config_version": req.expected_config_version + 1}

@router.get("/{config_id}/audit")
def list_config_audits(
    config_id: str,
    db: Session = Depends(get_db),
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    from services.dashboard.app.models.crm import Organization
    org_id = org_id if user else db.query(Organization).first().id
    audits = db.query(IncomingCallConfigAudit).filter(
        IncomingCallConfigAudit.config_id == config_id,
        IncomingCallConfigAudit.organization_id == org_id
    ).order_by(IncomingCallConfigAudit.changed_at.desc()).all()
    
    return [
        {
            "id": a.id,
            "changed_at": a.changed_at.isoformat(),
            "changed_by_user_id": a.changed_by_user_id,
            "changes": a.changes,
            "config_version": a.config_version
        }
        for a in audits
    ]

@router.post("/preview")
def preview_configuration(
    req: ConfigPreviewRequest,
    user: Optional[TeamMember] = Depends(get_optional_user)
):
    """
    Test configuration. Validates the configuration and compiles the prompt
    without mutating the database.
    """
    # Simply compile the components visually for the frontend
    compiled_prompt = f"SYSTEM INSTRUCTIONS\\n\\n"
    compiled_prompt += f"IDENTITY: You are {req.ai_name}, acting as a {req.role_description or 'receptionist'}.\\n"
    if req.business_name:
        compiled_prompt += f"BUSINESS: {req.business_name}\\n{req.business_description or ''}\\n"
    if req.primary_objective:
        compiled_prompt += f"OBJECTIVE: {req.primary_objective}\\n"
    if req.behavior_rules:
        compiled_prompt += "RULES:\\n- " + "\\n- ".join(req.behavior_rules) + "\\n"
    if req.faq_knowledge_base:
        compiled_prompt += f"KNOWLEDGE BASE:\\n{req.faq_knowledge_base}\\n"
    if req.system_instructions:
        compiled_prompt += f"ADVANCED INSTRUCTIONS:\\n{req.system_instructions}\\n"

    return {
        "success": True,
        "preview": {
            "ai_name": req.ai_name,
            "model": req.ai_model,
            "languages": [req.primary_language] + req.supported_languages,
            "compiled_prompt": compiled_prompt,
            "transfer_strategy": req.ring_strategy,
            "greeting": req.greeting_message or "Auto-generated greeting based on context"
        }
    }
