from sqlalchemy import Column, String, Boolean, Integer, BigInteger, ForeignKey, Enum, DateTime, Text, JSON, Float, Date, UniqueConstraint
from sqlalchemy.orm import relationship as sa_relationship, backref
from sqlalchemy.sql import func
import enum
import uuid
from typing import Optional

from core.db import Base

import secrets
import string

def generate_uuid():
    return str(uuid.uuid4())


def generate_uuid7():
    generator = getattr(uuid, "uuid7", None)
    if generator is None:
        return str(uuid.uuid4())
    return str(generator())

def generate_access_code(length=6) -> str:
    """Generates a secure alphanumeric code (uppercase)."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def generate_digital_id_token() -> str:
    """Generates a secure 6-character alphanumeric token for Digital ID."""
    return generate_access_code(6)


def normalize_email(email: Optional[str]) -> Optional[str]:
    if email is None:
        return None

    normalized = email.strip().lower()
    return normalized or None


def split_person_name(full_name: Optional[str]) -> dict[str, Optional[str]]:
    parts = [part for part in (full_name or "").split() if part]
    if not parts:
        return {"first_name": None, "middle_name": None, "last_name": None}
    if len(parts) == 1:
        return {"first_name": parts[0], "middle_name": None, "last_name": parts[0]}
    if len(parts) == 2:
        return {"first_name": parts[0], "middle_name": None, "last_name": parts[1]}
    return {
        "first_name": parts[0],
        "middle_name": " ".join(parts[1:-1]),
        "last_name": parts[-1],
    }


def build_full_name(
    first_name: Optional[str],
    middle_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> str:
    parts = [part.strip() for part in (first_name, middle_name, last_name) if part and part.strip()]
    return " ".join(parts)

# Enums
class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin" # Platform owner
    ADMIN = "admin"             # Estate Manager
    SECURITY = "security"       # Gate Guard
    RESIDENT = "resident"       # Tenant/Owner

class UnitStatus(str, enum.Enum):
    VACANT = "vacant"
    OCCUPIED = "occupied"

class ComplaintStatus(str, enum.Enum):
    PENDING = "pending"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    CLOSED = "closed"

class ComplaintPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ComplaintCategory(str, enum.Enum):
    SECURITY = "security"
    MAINTENANCE = "maintenance"
    STAFF = "staff"
    NOISE = "noise"
    OTHER = "other"

class IncidentStatus(str, enum.Enum):
    PENDING = "pending"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    CLOSED = "closed"

class IncidentPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class IncidentCategory(str, enum.Enum):
    SECURITY = "security"

class VehicleStatus(str, enum.Enum):
    PENDING_DELIVERY = "pending_delivery"
    ACTIVE = "active"

# Models

# Models

class Estate(Base):
    __tablename__ = "estates"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    logo_url = Column(String, nullable=True)
    rent_collection_enabled = Column(Boolean, default=False)
    unit_type = Column(String, default="Unit") # Unit, House, Flat, Mixed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    home_config = Column(JSON, nullable=True) # Custom home screen config
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # Relationships
    blocks = sa_relationship("Block", back_populates="estate", cascade="all, delete-orphan")
    users = sa_relationship("User", back_populates="estate")
    posts = sa_relationship("Post", back_populates="estate", cascade="all, delete-orphan")

class Block(Base):
    __tablename__ = "blocks"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False) # e.g. "Block A"
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False)
    
    # Relationships
    estate = sa_relationship("Estate", back_populates="blocks")
    units = sa_relationship("Unit", back_populates="block", cascade="all, delete-orphan")

class Unit(Base):
    __tablename__ = "units"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    block_id = Column(String, ForeignKey("blocks.id"), nullable=False, default="default_block") # Default for migration safety or handle in script
    unit_number = Column(String, nullable=False) # e.g. "Flat 101"
    wallet_balance = Column(BigInteger, default=0) # Shared Wallet
    rent_amount = Column(Integer, default=0) # Default annual rent
    next_rent_due = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(UnitStatus), default=UnitStatus.VACANT)
    access_code = Column(String, unique=True, nullable=True) # For self-onboarding
    address_metadata = Column(JSON, nullable=True)
    
    # App Fee (15% Deduction Logic)
    app_fee_pending = Column(Integer, default=0) # Default to 0, was 18,000 Naira

    
    # Relationships
    block = sa_relationship("Block", back_populates="units")
    # One unit can have multiple residents (Family), but for now linked via UserUnit
    residents = sa_relationship("UserUnit", back_populates="unit")

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    first_name = Column(String, nullable=True)
    middle_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    access_code = Column(String, unique=True, index=True, nullable=True) # For signup/onboarding
    profile_image_url = Column(String, nullable=True) # Profile Picture
    role = Column(Enum(UserRole), default=UserRole.RESIDENT)
    is_active = Column(Boolean, default=True)
    settings_location_enabled = Column(Boolean, default=False)
    settings_push_enabled = Column(Boolean, default=True)
    kyc_level = Column(Integer, default=1)
    bvn_verified = Column(Boolean, default=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String, nullable=True)
    
    # Account deletion fields
    deletion_requested_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_deletion_date = Column(DateTime(timezone=True), nullable=True)
    is_deleted = Column(Boolean, default=False)
    
    # Personal Wallet
    wallet_balance = Column(BigInteger, default=0) # Shared Wallet moved to Personal

    
    # Session Tracking (Single Device Login)
    active_token_id = Column(String, nullable=True) # UUID of the currently valid token
    
    # Transactional PIN
    transaction_pin_hash = Column(String, nullable=True)

    # Digital ID (Opaque Token for Gate Access)
    digital_id_token = Column(String, unique=True, index=True, default=generate_digital_id_token)
    digital_id_refreshed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Context (Multi-tenancy)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=True) # If null, maybe Super Admin
    
    # Relationships
    estate = sa_relationship("Estate", back_populates="users")
    units = sa_relationship("UserUnit", back_populates="user")

class HouseholdRole(str, enum.Enum):
    ADMIN = "admin" # Head of household, can pay bills
    SUB_ADMIN = "sub_admin" # Can pay bills, invite members, strict delete rights
    SPOUSE = "spouse"
    CHILD = "child"
    PARENT = "parent"
    RELATIVE = "relative"
    STAFF = "staff" # Security, Maid, etc.
    OTHER = "other"

class UserUnit(Base):
    """Link table for Users <-> Units (Many-to-Many with payload)"""
    __tablename__ = "user_units"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    unit_id = Column(String, ForeignKey("units.id"), nullable=False)
    is_primary = Column(Boolean, default=True) # Which unit is selected by default
    
    # Force values_callable to ensure SQLAlchemy uses 'admin' (value) not 'ADMIN' (name)
    role = Column(Enum(HouseholdRole, values_callable=lambda x: [e.value for e in x]), default=HouseholdRole.OTHER)

    
    user = sa_relationship("User", back_populates="units")
    unit = sa_relationship("Unit", back_populates="residents")

class Complaint(Base):
    __tablename__ = "complaints"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    ticket_number = Column(String, unique=True, index=True, default=lambda: generate_access_code(8))
    category = Column(Enum(ComplaintCategory), nullable=False)
    priority = Column(Enum(ComplaintPriority), default=ComplaintPriority.LOW)
    description = Column(Text, nullable=False)
    status = Column(Enum(ComplaintStatus), default=ComplaintStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    attachments = Column(JSON, default=[]) # List of URLs
    
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    unit_id = Column(String, ForeignKey("units.id"), nullable=True) # Optional link to unit
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False) # Important for Admin filtering
    
    # Relationships
    user = sa_relationship("User", backref="complaints")
    estate = sa_relationship("Estate", backref="complaints")
    unit = sa_relationship("Unit")

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(String, primary_key=True, default=generate_uuid)
    ticket_number = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    location = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(
        Enum(
            IncidentCategory,
            values_callable=lambda x: [e.value for e in x],
            name="incident_category",
        ),
        nullable=False,
    )
    priority = Column(
        Enum(
            IncidentPriority,
            values_callable=lambda x: [e.value for e in x],
            name="incident_priority",
        ),
        default=IncidentPriority.HIGH,
        nullable=False,
    )
    status = Column(
        Enum(
            IncidentStatus,
            values_callable=lambda x: [e.value for e in x],
            name="incident_status",
        ),
        default=IncidentStatus.PENDING,
        nullable=False,
    )
    attachments = Column(JSON, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    unit_id = Column(String, ForeignKey("units.id"), nullable=True)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False)

    user = sa_relationship("User", backref="incidents")
    estate = sa_relationship("Estate", backref="incidents")
    unit = sa_relationship("Unit")

class Vehicle(Base):
    __tablename__ = "vehicles"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    make = Column(String, nullable=False)
    model = Column(String, nullable=False)
    plate_number = Column(String, nullable=False)
    color = Column(String, nullable=False)
    vehicle_type = Column(String, default="Car") # Car, Motorcycle, Truck
    status = Column(Enum(VehicleStatus), default=VehicleStatus.PENDING_DELIVERY)
    qr_code_data = Column(String, unique=True, default=lambda: generate_access_code(12))
    payment_reference = Column(String, nullable=True)
    
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    unit_id = Column(String, ForeignKey("units.id"), nullable=True)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False)
    
    user = sa_relationship("User", backref="vehicles")
    estate = sa_relationship("Estate", backref="vehicles")

class InviteStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    USED = "USED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    PENDING = "PENDING" # For Household Invites
    ACCEPTED = "ACCEPTED" # For Household Invites
    CHECKED_IN = "CHECKED_IN"
    DENIED = "DENIED"
    COMPLETED = "COMPLETED"


class InviteType(str, enum.Enum):
    SINGLE = "SINGLE"
    GROUP = "GROUP"
    GUEST = "GUEST"
    DELIVERY = "DELIVERY"
    CONTRACTOR = "CONTRACTOR"
    RECURRING = "RECURRING"

class VisitorInvite(Base):
    __tablename__ = "visitor_invites"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    visitor_name = Column(String, nullable=False)
    visitor_phone = Column(String, nullable=True) # Optional
    access_code = Column(String, unique=True, index=True, default=lambda: generate_access_code(6))
    valid_from = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True), nullable=False) # e.g., 24 hours
    status = Column(Enum(InviteStatus, values_callable=lambda x: [e.value for e in x]), default=InviteStatus.ACTIVE)
    invite_type = Column(Enum(InviteType, values_callable=lambda x: [e.value for e in x]), default=InviteType.SINGLE)
    
    # Enhanced Fields
    gender = Column(String, nullable=True)
    expected_guests = Column(Integer, nullable=True)
    
    # Timestamps for actual check-in/check-out
    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    checked_out_at = Column(DateTime(timezone=True), nullable=True)
    checked_in_by = Column(String, ForeignKey("users.id"), nullable=True)  # Guard who checked in
    
    user_id = Column(String, ForeignKey("users.id"), nullable=False) # Resident who invited
    unit_id = Column(String, ForeignKey("units.id"), nullable=True)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False)
    
    user = sa_relationship("User", foreign_keys=[user_id], backref="invites")
    estate = sa_relationship("Estate", backref="invites")
    unit = sa_relationship("Unit")
    
    # Location Sharing
    location_latitude = Column(Float, nullable=True)
    location_longitude = Column(Float, nullable=True)
    location_accuracy = Column(Float, nullable=True)

class LiveActivityToken(Base):
    """
    Stores ActivityKit push tokens for Live Activities (iOS Dynamic Island).
    Tokens are sent by the iOS app when a Live Activity starts.
    """
    __tablename__ = "live_activity_tokens"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    activity_id = Column(String, unique=True, index=True, nullable=False)  # From iOS ActivityKit
    invite_id = Column(String, ForeignKey("visitor_invites.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    activity_push_token = Column(String, nullable=False)  # Hex/Base64 token from iOS
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = sa_relationship("User")
    invite = sa_relationship("VisitorInvite")

class HouseholdInvite(Base):
    __tablename__ = "household_invites"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, nullable=False, index=True)
    name = Column(String, nullable=True)
    relationship = Column(String, nullable=True)
    profile_image_url = Column(String, nullable=True)
    
    status = Column(Enum(InviteStatus), default=InviteStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    unit_id = Column(String, ForeignKey("units.id"), nullable=False)
    invited_by_user_id = Column(String, ForeignKey("users.id"), nullable=False) # Resident who invited
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False)
    
    unit = sa_relationship("Unit")
    invited_by = sa_relationship("User")


class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    RESPONDING = "responding"
    RESOLVED = "resolved"

class Alert(Base):
    __tablename__ = "alerts"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    type = Column(String, nullable=False) # "medical", "fire", "security"
    description = Column(String, nullable=True)
    status = Column(Enum(AlertStatus), default=AlertStatus.ACTIVE)
    location_lat = Column(String, nullable=True)
    location_long = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False)
    unit_id = Column(String, ForeignKey("units.id"), nullable=True)
    
    user = sa_relationship("User", backref="alerts")
    estate = sa_relationship("Estate", backref="alerts")
    unit = sa_relationship("Unit")

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(String, primary_key=True, default=generate_uuid7)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    user = sa_relationship("User", backref="notifications")

class SubscriptionPlan(str, enum.Enum):
    BASIC = "basic"     # Free features
    PREMIUM = "premium" # Invites, Vehicles, Alerts

class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELED = "canceled"

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    plan = Column(Enum(SubscriptionPlan), default=SubscriptionPlan.BASIC)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    start_date = Column(DateTime(timezone=True), server_default=func.now())
    end_date = Column(DateTime(timezone=True), nullable=True) # Null = Lifetime/Basic
    auto_renew = Column(Boolean, default=False)
    
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False) # One sub per user
    
    user = sa_relationship("User", backref=backref("subscription", uselist=False))

class WalletProfile(Base):
    __tablename__ = "wallet_profiles"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    provider = Column(String, nullable=False, default="nomba")
    status = Column(String, nullable=False, default="pending_kyc")
    nomba_account_ref = Column(String, nullable=True, unique=True)
    nomba_account_id = Column(String, nullable=True, unique=True)
    bank_name = Column(String, nullable=True)
    account_number = Column(String, nullable=True)
    account_name = Column(String, nullable=True)
    verification_reference = Column(String, nullable=True, index=True)
    kyc_tier = Column(Integer, nullable=True)
    kyc_message = Column(Text, nullable=True)
    kyc_requirements = Column(JSON, nullable=True)
    kyc_last_event = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = sa_relationship("User", backref=backref("wallet_profile", uselist=False))

class KYCSession(Base):
    __tablename__ = "kyc_sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String, nullable=False, default="nomba")
    reference = Column(String, nullable=False, unique=True, index=True)
    nomba_account_ref = Column(String, nullable=False)
    bvn_last4 = Column(String, nullable=True)
    status = Column(String, nullable=False, default="otp_requested")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = sa_relationship("User", backref="kyc_sessions")



class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    reference = Column(String, unique=True, nullable=False)
    provider = Column(String, nullable=False) # anchor, anchor_wallet, anchor_bill, etc.
    amount = Column(Integer, nullable=False) # In minor units (kobo/cents)
    currency = Column(String, default="NGN")
    status = Column(String, default="pending") # "success", "failed"
    metadata_json = Column(Text, nullable=True) # JSON string
    description = Column(String, nullable=True)
    transaction_type = Column(String, default="Credit") # Credit, Debit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user_id = Column(String, ForeignKey("users.id"), nullable=True) # Nullable if webhook comes before we identify user? 
    # Usually we pass user_id in metadata to provider.
    unit_id = Column(String, ForeignKey("units.id"), nullable=True) # For Wallet Funding


class RecurringBillingDuration(str, enum.Enum):
    MONTHLY = "monthly"
    BI_MONTHLY = "bi_monthly"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    YEARLY = "yearly"


class BillGenerationSource(str, enum.Enum):
    MANUAL = "manual"
    RECURRING = "recurring"


class RecurringBillingSetup(Base):
    __tablename__ = "recurring_billing_setups"
    __table_args__ = (UniqueConstraint("estate_id", "bill_type", name="uq_recurring_billing_setup_estate_type"),)

    id = Column(String, primary_key=True, default=generate_uuid)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False, index=True)
    bill_type = Column(String, nullable=False)
    title = Column(String, nullable=True)
    base_amount = Column(Integer, nullable=True)
    duration = Column(
        Enum(RecurringBillingDuration, values_callable=lambda x: [e.value for e in x]),
        default=RecurringBillingDuration.MONTHLY,
        nullable=False,
    )
    first_due_date = Column(DateTime(timezone=True), nullable=False)
    next_due_date = Column(DateTime(timezone=True), nullable=False)
    auto_renew = Column(Boolean, default=True)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    estate = sa_relationship("Estate", backref="recurring_billing_setups")


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (
        UniqueConstraint("recurring_setup_id", "cycle_due_date", name="uq_bills_recurring_setup_cycle"),
    )
    
    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    total_amount = Column(Integer, nullable=False) # In minor units
    due_date = Column(DateTime(timezone=True), nullable=True)
    generation_source = Column(
        Enum(BillGenerationSource, values_callable=lambda x: [e.value for e in x]),
        default=BillGenerationSource.MANUAL,
        nullable=False,
    )
    recurring_setup_id = Column(String, ForeignKey("recurring_billing_setups.id"), nullable=True, index=True)
    cycle_due_date = Column(DateTime(timezone=True), nullable=True)
    is_variable_amount = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False)
    
    assignments = sa_relationship("BillAssignment", back_populates="bill")
    recurring_setup = sa_relationship("RecurringBillingSetup", backref="generated_bills")

class BillAssignment(Base):
    __tablename__ = "bill_assignments"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    bill_id = Column(String, ForeignKey("bills.id"), nullable=False)
    unit_id = Column(String, ForeignKey("units.id"), nullable=False)
    
    base_amount = Column(Integer, nullable=True)
    app_charge_amount = Column(Integer, nullable=True)
    service_fee_amount = Column(Integer, nullable=True, default=0)
    resident_service_fee_amount = Column(Integer, nullable=True, default=0)
    estate_absorbed_service_fee_amount = Column(Integer, nullable=True, default=0)
    estate_net_amount = Column(Integer, nullable=True)
    total_amount = Column(Integer, nullable=True)
    amount_paid = Column(Integer, default=0)
    status = Column(String, default="PENDING") # PENDING, PARTIAL, PAID
    
    bill = sa_relationship("Bill", back_populates="assignments")
    unit = sa_relationship("Unit")

class WalletHistory(Base):
    __tablename__ = "wallet_history"
    
    id = Column(String, primary_key=True, default=generate_uuid7)
    unit_id = Column(String, ForeignKey("units.id"), nullable=False)
    amount = Column(Integer, nullable=False) # Positive (Credit) or Negative (Debit)
    description = Column(String, nullable=False) # "Top Up", "Bill Payment: Dec Levy"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    unit = sa_relationship("Unit")

class TwoFactorAuth(Base):
    __tablename__ = "two_factor_auth"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, index=True, nullable=False)
    secret = Column(Text, nullable=False)
    enabled = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    credential_id = Column(String, unique=True, nullable=False)
    public_key = Column(Text, nullable=False)
    sign_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = sa_relationship("User", backref="webauthn_credentials")

class BankDetails(Base):
    __tablename__ = "bank_details"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False, unique=True)
    bank_code = Column(String, nullable=True)
    bank_name = Column(String, nullable=False)
    account_number = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    estate = sa_relationship("Estate", backref=backref("bank_details", uselist=False))

class Payout(Base):
    __tablename__ = "payouts"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    amount_kobo = Column(Integer, nullable=True)
    status = Column(String, default="Pending") # Pending, Processing, Paid, Failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    requested_by_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    processed_by_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    blocked_by_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    bank_code_snapshot = Column(String, nullable=True)
    bank_name_snapshot = Column(String, nullable=True)
    account_number_snapshot = Column(String, nullable=True)
    account_name_snapshot = Column(String, nullable=True)
    review_deadline_at = Column(DateTime(timezone=True), nullable=True)
    auto_process_after = Column(DateTime(timezone=True), nullable=True)
    auto_process_enabled = Column(Boolean, default=True)
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    blocked_at = Column(DateTime(timezone=True), nullable=True)
    transfer_reference = Column(String, nullable=True, index=True)
    failure_reason = Column(Text, nullable=True)
    block_reason = Column(Text, nullable=True)
    internal_note = Column(Text, nullable=True)
    transfer_response_payload = Column(JSON, nullable=True)
    
    estate = sa_relationship("Estate", backref="payouts")
    blocked_by = sa_relationship("User", foreign_keys=[blocked_by_user_id], backref="blocked_payouts")


class ServiceChargeFeeConfig(Base):
    __tablename__ = "service_charge_fee_configs"
    __table_args__ = (UniqueConstraint("estate_id", name="uq_service_charge_fee_config_estate"),)

    id = Column(String, primary_key=True, default=generate_uuid)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=True, index=True)
    monthly_fee_amount = Column(Integer, nullable=False, default=100_000)
    discount_amount = Column(Integer, nullable=False, default=0)
    allocation_mode = Column(String, nullable=False, default="resident_pays_all")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    estate = sa_relationship("Estate", backref=backref("service_charge_fee_config", uselist=False))


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"

    id = Column(String, primary_key=True, default=generate_uuid)
    transaction_id = Column(String, ForeignKey("transactions.id"), nullable=True, index=True)
    bill_assignment_id = Column(String, ForeignKey("bill_assignments.id"), nullable=False, index=True)
    bill_id = Column(String, ForeignKey("bills.id"), nullable=False, index=True)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False, index=True)
    unit_id = Column(String, ForeignKey("units.id"), nullable=False, index=True)
    gross_amount = Column(Integer, nullable=False, default=0)
    service_fee_amount = Column(Integer, nullable=False, default=0)
    estate_net_amount = Column(Integer, nullable=False, default=0)
    allocation_status = Column(String, nullable=False, default="pending_transfer")
    allocation_source = Column(String, nullable=False, default="service_charge_payment")
    payment_reference = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    transaction = sa_relationship("Transaction", backref="payment_allocations")
    bill_assignment = sa_relationship("BillAssignment", backref="payment_allocations")
    bill = sa_relationship("Bill")
    estate = sa_relationship("Estate")
    unit = sa_relationship("Unit")


class ServiceChargeSplitTransfer(Base):
    __tablename__ = "service_charge_split_transfers"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_service_charge_split_transfer_idempotency_key"),)

    id = Column(String, primary_key=True, default=generate_uuid)
    transaction_id = Column(String, ForeignKey("transactions.id"), nullable=True, index=True)
    transfer_kind = Column(String, nullable=False)
    amount = Column(Integer, nullable=False, default=0)
    source_account_id = Column(String, nullable=True)
    destination_account_id = Column(String, nullable=False)
    provider_reference = Column(String, nullable=True, index=True)
    idempotency_key = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    failure_reason = Column(Text, nullable=True)
    request_payload = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    transaction = sa_relationship("Transaction", backref="service_charge_split_transfers")

class Broadcast(Base):
    __tablename__ = "broadcasts"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    target = Column(String, nullable=False) # 'all', 'block', 'specific'
    target_id = Column(String, nullable=True) # block_id or user_id or unit_id
    status = Column(String, default="sent")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    estate = sa_relationship("Estate", backref="broadcasts")

class OTPCode(Base):
    __tablename__ = "otp_codes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, index=True, nullable=False)
    code = Column(String, nullable=False)
    type = Column(String, nullable=False) # 'login', 'register', 'payout'
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    request_ip = Column(String, nullable=True)
    request_user_agent = Column(Text, nullable=True)
    request_path = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ServiceChargeFrequency(str, enum.Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    ONE_OFF = "one_off"

class ServiceChargeConfig(Base):
    __tablename__ = "service_charge_configs"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False, index=True)
    name = Column(String, nullable=False) # e.g., "Monthly Service Charge"
    amount = Column(Integer, nullable=False) # In minor units
    frequency = Column(Enum(ServiceChargeFrequency), default=ServiceChargeFrequency.MONTHLY)
    description = Column(Text, nullable=True)
    due_day = Column(Integer, default=1) # Day of the month/week/year
    grace_period = Column(Integer, default=7) # Given days before it becomes overdue
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    estate = sa_relationship("Estate", backref="service_charge_configs")

class DeviceToken(Base):
    __tablename__ = "device_tokens"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    token = Column(String, nullable=False, index=True) # ExponentPushToken[...]
    platform = Column(String, default="ios") # ios, android, web
    active_token_id = Column(String, nullable=True) # Linked to User Session
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    user = sa_relationship("User", backref="device_tokens")

class BankTransferReference(Base):
    __tablename__ = "bank_transfer_references"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    reference = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False)
    unit_id = Column(String, ForeignKey("units.id"), nullable=False)
    
    # Service details
    service_id = Column(String, nullable=False) # e.g., 'electricity', 'wallet_topup'
    customer_id = Column(String, nullable=False)
    provider_id = Column(String, nullable=True)
    amount = Column(Integer, nullable=False) # In minor units (kobo)
    
    # Account details snapshot for the transfer reference
    account_number = Column(String, nullable=True)
    bank_name = Column(String, nullable=True)
    account_name = Column(String, nullable=True)
    
    # Status
    status = Column(String, default="pending") # pending, successful, failed, expired
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = sa_relationship("User")
    estate = sa_relationship("Estate")
    unit = sa_relationship("Unit")

class WebhookLog(Base):
    __tablename__ = "webhook_logs"
    
    id = Column(String, primary_key=True, default=generate_uuid7)
    provider = Column(String, nullable=False) # anchor
    method = Column(String, default="POST")
    url = Column(String, nullable=True)
    headers = Column(JSON, default={})
    payload = Column(JSON, default={})
    event_type = Column(String, nullable=True) # charge.completed, etc.
    status = Column(String, default="received") # received, processed, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# ----------------------------------------------------
# Security Specific Models
# ----------------------------------------------------

class VerificationLog(Base):
    """
    Audit log for location-based visitor verifications.
    Tracks guard's location and distance from estate for compliance.
    """
    __tablename__ = "verification_logs"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    invite_id = Column(String, ForeignKey("visitor_invites.id"), nullable=False)
    verified_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    guard_id = Column(String, ForeignKey("users.id"), nullable=True)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=True)
    
    verification_method = Column(String, nullable=True) # "gate", "app"
    verification_type = Column(String, nullable=True) # "verify", "check-in", "check-out"
    verified_at = Column(DateTime(timezone=True), default=func.now())
    
    # Location data
    guard_latitude = Column(String, nullable=True)
    guard_longitude = Column(String, nullable=True)
    guard_accuracy = Column(String, nullable=True)
    
    estate_latitude = Column(String, nullable=True)
    estate_longitude = Column(String, nullable=True)
    
    distance_meters = Column(String, nullable=True)
    within_threshold = Column(Boolean, nullable=True)
    threshold_used = Column(Float, nullable=True)
    token_age_minutes = Column(String, nullable=True)
    
    # Relationships
    # Relationships
    invite = sa_relationship("VisitorInvite")
    verifier = sa_relationship("User", foreign_keys=[guard_id])

# ----------------------------------------------------
# Feed & Community Models
# ----------------------------------------------------

class Post(Base):
    __tablename__ = "feed_posts"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    author_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False, index=True)
    unit_id = Column(String, ForeignKey("units.id"), nullable=True, index=True)
    content = Column(Text, nullable=True)
    # [{"uri": "...", "type": "image" | "video"}]
    media = Column(JSON, default=[]) 
    media_urls = Column(JSON, default=[]) # for compatibility
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_deleted = Column(Boolean, default=False)
    
    reply_to_id = Column(String, ForeignKey("feed_posts.id"), nullable=True)
    repost_id = Column(String, ForeignKey("feed_posts.id"), nullable=True)
    poll_id = Column(String, ForeignKey("feed_polls.id"), nullable=True)
    
    # Relationships
    author = sa_relationship("User", backref="posts")
    estate = sa_relationship("Estate", back_populates="posts")
    unit = sa_relationship("Unit")
    poll = sa_relationship("Poll", back_populates="post", uselist=False)
    replies = sa_relationship(
        "Post", 
        backref=backref("parent_post", remote_side=[id]),
        foreign_keys=[reply_to_id]
    )
    reposted_post = sa_relationship(
        "Post",
        foreign_keys=[repost_id],
        remote_side=[id]
    )
    likes = sa_relationship("PostLike", back_populates="post", cascade="all, delete-orphan")
    reposts = sa_relationship("PostRepost", back_populates="post", cascade="all, delete-orphan")

class PostLike(Base):
    __tablename__ = "feed_post_likes"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    post_id = Column(String, ForeignKey("feed_posts.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    post = sa_relationship("Post", back_populates="likes")
    user = sa_relationship("User")

class PostRepost(Base):
    __tablename__ = "feed_post_reposts"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    post_id = Column(String, ForeignKey("feed_posts.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    post = sa_relationship("Post", back_populates="reposts")
    user = sa_relationship("User")

class Poll(Base):
    __tablename__ = "feed_polls"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    end_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    post = sa_relationship("Post", back_populates="poll", uselist=False)
    options = sa_relationship("PollOption", back_populates="poll", cascade="all, delete-orphan")
    votes = sa_relationship("PollVote", back_populates="poll", cascade="all, delete-orphan")

class PollOption(Base):
    __tablename__ = "feed_poll_options"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    poll_id = Column(String, ForeignKey("feed_polls.id"), nullable=False)
    text = Column(String, nullable=False)
    index = Column(Integer, nullable=False) 
    
    poll = sa_relationship("Poll", back_populates="options")

class PollVote(Base):
    __tablename__ = "feed_poll_votes"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    poll_id = Column(String, ForeignKey("feed_polls.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    option_index = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    poll = sa_relationship("Poll", back_populates="votes")
    user = sa_relationship("User")

class FavoriteUser(Base):
    __tablename__ = "user_favorites"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    favorite_user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = sa_relationship("User", foreign_keys=[user_id])
    favorite = sa_relationship("User", foreign_keys=[favorite_user_id])

# ----------------------------------------------------
# Messaging Models
# ----------------------------------------------------

class Conversation(Base):
    __tablename__ = "feed_conversations"
    
    id = Column(String, primary_key=True, default=generate_uuid7)
    estate_id = Column(String, ForeignKey("estates.id"), nullable=False, index=True)
    group_name = Column(String, nullable=True)
    is_group = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    participants = sa_relationship("ConversationParticipant", back_populates="conversation", cascade="all, delete-orphan")
    messages = sa_relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    estate = sa_relationship("Estate")

class ConversationParticipant(Base):
    __tablename__ = "feed_conversation_participants"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    conversation_id = Column(String, ForeignKey("feed_conversations.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    last_read_at = Column(DateTime(timezone=True), server_default=func.now())
    
    conversation = sa_relationship("Conversation", back_populates="participants")
    user = sa_relationship("User")

class Message(Base):
    __tablename__ = "feed_messages"
    
    id = Column(String, primary_key=True, default=generate_uuid7)
    conversation_id = Column(String, ForeignKey("feed_conversations.id"), nullable=False, index=True)
    from_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    text = Column(Text, nullable=True)
    media_urls = Column(JSON, default=[]) 
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    conversation = sa_relationship("Conversation", back_populates="messages")
    sender = sa_relationship("User")
