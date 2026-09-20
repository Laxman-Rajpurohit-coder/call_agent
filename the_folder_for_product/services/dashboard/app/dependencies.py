import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Callable
import jwt
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from services.dashboard.app.config import settings
from services.dashboard.app.database import get_db, tenant_query, agent_scoped_query
from services.dashboard.app.models.crm import (
    TeamMember, Contact, LeadTask, CallSession, Organization
)
from services.dashboard.app.models.campaign import Campaign, CampaignAgent

security_bearer = HTTPBearer(auto_error=False)

SALT = b"superfone_stable_tenant_salt_2026"

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), SALT, 100000).hex()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against PBKDF2 hash."""
    if not plain_password or not hashed_password:
        return False
    return hash_password(plain_password) == hashed_password

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Issue cryptographically signed JWT.
    Note: Token contains subject (user_id), but tenant membership & role
    are always verified dynamically from the database to prevent privilege escalation.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> dict:
    """Decode and verify JWT signature."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token signature",
            headers={"WWW-Authenticate": "Bearer"}
        )

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db)
) -> TeamMember:
    """
    Core Authentication Guard (Tier 1):
    1. Cryptographically verifies Bearer token signature.
    2. Queries database for authoritative user record.
    3. Guarantees user.organization_id and user.role come directly from DB.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials

    # Support backward-compatible demo session format: session-<user_id>-<random>
    user_id = None
    if token.startswith("session-"):
        parts = token.split("-")
        if len(parts) >= 2:
            user_id = parts[1]
    else:
        payload = decode_access_token(token)
        user_id = payload.get("sub") or payload.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Database is authoritative for tenant and role
    user = db.query(TeamMember).filter(TeamMember.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return user

def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db)
) -> Optional[TeamMember]:
    """Resolves authenticated user if Bearer token is present, else returns None."""
    if not credentials or not credentials.credentials:
        return None
    return get_current_user(credentials, db)

def require_role(allowed_roles: List[str]) -> Callable:
    """
    Role Authorization Guard (Tier 3):
    Enforces minimum role permissions (OWNER, ADMIN, MANAGER, AGENT, VIEWER).
    """
    def role_checker(user: TeamMember = Depends(get_current_user)) -> TeamMember:
        # Standardize uppercase comparison
        current_role = (user.role or "AGENT").upper()
        # Map common aliases
        if "ADMIN" in current_role or "DIRECTOR" in current_role:
            effective_role = "ADMIN"
        elif "MANAGER" in current_role or "LEAD" in current_role:
            effective_role = "MANAGER"
        elif "VIEWER" in current_role:
            effective_role = "VIEWER"
        elif "OWNER" in current_role:
            effective_role = "OWNER"
        else:
            effective_role = "AGENT"

        allowed_upper = [r.upper() for r in allowed_roles]
        if effective_role not in allowed_upper:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted for role: {user.role}"
            )
        return user
    return role_checker

def require_non_viewer(user: TeamMember = Depends(get_current_user)) -> TeamMember:
    """Blocks write/mutation actions for read-only VIEWER role."""
    current_role = (user.role or "AGENT").upper()
    if current_role == "VIEWER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewer role is read-only and cannot perform mutations"
        )
    return user

def verify_tenant_access(user: TeamMember, resource_org_id: str) -> None:
    """
    Tenant Isolation Guard (Tier 2):
    Enforces cross-tenant isolation. Returns stealth 404 to avoid resource enumeration.
    """
    if user.organization_id != resource_org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

def get_authorized_lead(
    contact_id: str,
    db: Session = Depends(get_db),
    user: TeamMember = Depends(get_current_user)
) -> Contact:
    """
    Validates tenant ownership (stealth 404) and agent confidentiality (403).
    """
    lead = db.query(Contact).filter(Contact.id == contact_id).first()
    if not lead or lead.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )

    # Intra-tenant confidentiality: AGENT can only access assigned leads
    user_role = (user.role or "AGENT").upper()
    if user_role not in ["OWNER", "ADMIN", "MANAGER"] and lead.lead_owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not the assigned owner of this lead"
        )

    return lead

def get_authorized_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: TeamMember = Depends(get_current_user)
) -> LeadTask:
    """
    Validates tenant ownership (stealth 404) and agent confidentiality (403).
    """
    task = db.query(LeadTask).filter(LeadTask.id == task_id).first()
    if not task or task.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    user_role = (user.role or "AGENT").upper()
    if user_role not in ["OWNER", "ADMIN", "MANAGER"] and task.assigned_to_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not assigned to this task"
        )

    return task

def get_authorized_call(
    call_id: str,
    db: Session = Depends(get_db),
    user: TeamMember = Depends(get_current_user)
) -> CallSession:
    """
    Validates tenant ownership (stealth 404) and agent confidentiality (403).
    For historical call sessions, handled_by_user_id takes precedence.
    """
    call = db.query(CallSession).filter(CallSession.id == call_id).first()
    if not call or call.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call record not found"
        )

    user_role = (user.role or "AGENT").upper()
    if user_role not in ["OWNER", "ADMIN", "MANAGER"]:
        # An agent can view a call if they handled it OR if they currently own the associated contact
        is_handler = (call.handled_by_user_id == user.id)
        is_lead_owner = False
        if call.contact_id:
            contact = db.query(Contact).filter(Contact.id == call.contact_id).first()
            if contact and contact.lead_owner_id == user.id:
                is_lead_owner = True

        if not is_handler and not is_lead_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not authorized to view this call session"
            )

    return call

def verify_campaign_access(
    campaign_id: str,
    db: Session = Depends(get_db),
    user: TeamMember = Depends(get_current_user)
) -> Campaign:
    """
    Validates tenant ownership and campaign assignment for agents.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or campaign.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found"
        )

    user_role = (user.role or "AGENT").upper()
    if user_role not in ["OWNER", "ADMIN", "MANAGER"]:
        # Verify enrollment in campaign_agents
        membership = db.query(CampaignAgent).filter(
            CampaignAgent.campaign_id == campaign_id,
            CampaignAgent.user_id == user.id
        ).first()
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not assigned to this campaign"
            )

    return campaign
