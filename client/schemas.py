from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any, Dict
from datetime import datetime, date

# Common / Global
class HTTPValidationError(BaseModel):
    detail: List[Any]

class EstateBrandingResponse(BaseModel):
    estate_id: str
    estate_name: str
    logo_url: Optional[str] = None
    has_custom_logo: bool
    primary_color: str
    secondary_color: str

# Auth
class ClientLoginV(BaseModel):
    email: EmailStr
    password: str
    device_token: Optional[str] = None
    platform: Optional[str] = "ios"

class ClientSignup(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    phone_number: Optional[str] = None

    class Config:
        populate_by_name = True

class ClientTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user_id: str
    full_name: str
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    estate_id: Optional[str] = None
    unit_id: Optional[str] = None
    is_household_admin: bool = False
    

class ClientRefreshToken(BaseModel):
    refresh_token: str


class EstateJoinRequest(BaseModel):
    estate_code: str = Field(..., alias="estateCode")

    class Config:
        populate_by_name = True


class EstateJoinResponse(BaseModel):
    estate_id: str = Field(..., alias="estateId")
    estate_name: str = Field(..., alias="estateName")
    unit_id: str = Field(..., alias="unitId")
    unit_number: str = Field(..., alias="unitNumber")
    block_name: str = Field(..., alias="blockName")
    is_primary: bool = Field(..., alias="isPrimary")
    message: str

    class Config:
        populate_by_name = True

# User & Profile
class UserProfileResponse(BaseModel):
    id: str
    estate_id: Optional[str] = Field(None, alias="estateId")
    email: str
    full_name: str = Field(..., alias="fullName")
    first_name: Optional[str] = Field(None, alias="firstName")
    middle_name: Optional[str] = Field(None, alias="middleName")
    last_name: Optional[str] = Field(None, alias="lastName")
    phone_number: str = Field(..., alias="phoneNumber")
    profile_image_url: Optional[str] = Field(None, alias="profileImageUrl")
    unit_id: Optional[str] = Field(None, alias="unitId")
    role: str
    is_household_admin: bool = Field(False, alias="isHouseholdAdmin")
    is_active: bool = Field(..., alias="isActive")
    subscription_status: str = Field(..., alias="subscriptionStatus") # "active", "expired"
    subscription_days_remaining: int = Field(..., alias="subscriptionDaysRemaining")
    settings_location_enabled: bool = Field(False, alias="settingsLocationEnabled")
    settings_push_enabled: bool = Field(True, alias="settingsPushEnabled")
    transaction_pin_set: bool = Field(False, alias="transactionPinSet")
    date_of_birth: Optional[date] = Field(None, alias="dateOfBirth")
    gender: Optional[str] = None

    class Config:
        from_attributes = True
        populate_by_name = True

class PinVerifyRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=4)

class PinChangeRequest(BaseModel):
    old_pin: Optional[str] = Field(None, min_length=4, max_length=4)
    new_pin: str = Field(..., min_length=4, max_length=4)

class UserProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    profile_image_url: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None

class UnitSimpleResponse(BaseModel):
    id: str
    unit_number: str
    block_name: str
    estate_name: str
    role: str

class DeviceTokenCreate(BaseModel):
    token: str
    platform: str # "ios" | "android"

# Wallet
class WalletBalanceResponse(BaseModel):
    balance: float  # Naira - Backend converts from Kobo
    currency: str = "NGN"

class Transaction(BaseModel):
    id: str
    type: str # credit, debit
    category: str
    amount: float # Naira
    status: str
    date: str
    title: str

class TopUpRequest(BaseModel):
    amount: float # Naira
    paymentRef: Optional[str] = None # Spec name
    metadata: Optional[Dict[str, Any]] = None # Capture {"service_type": "rent", "id": "..."}

class TopUpResponse(BaseModel):
    success: bool
    newBalance: float # Naira

class TopUpInitResponse(BaseModel):
    reference: str
    publicKey: str
    amount: int
    email: str
    currency: str = "NGN"

class TopUpDynamicAccountRequest(BaseModel):
    amount: int

class TopUpDynamicAccountResponse(BaseModel):
    account_number: str
    bank_name: str
    expiry_date: Optional[str] = None
    transfer_amount: float
    transfer_note: Optional[str] = None


class WalletTransferOutRequest(BaseModel):
    bank_name: str = Field(..., alias="bankName")
    bank_code: str = Field(..., alias="bankCode")
    account_number: str = Field(..., alias="accountNumber")
    account_name: str = Field(..., alias="accountName")
    amount: float
    transaction_pin: str = Field(..., min_length=4, max_length=4, alias="transactionPin")
    narration: Optional[str] = None

    class Config:
        populate_by_name = True


class WalletBankLookupRequest(BaseModel):
    bank_name: str = Field(..., alias="bankName")
    bank_code: str = Field(..., alias="bankCode")
    account_number: str = Field(..., alias="accountNumber")
    account_name: Optional[str] = Field(None, alias="accountName")

    class Config:
        populate_by_name = True


class WalletBankLookupResponse(BaseModel):
    bank_name: str = Field(..., alias="bankName")
    bank_code: str = Field(..., alias="bankCode")
    account_number: str = Field(..., alias="accountNumber")
    account_name: str = Field(..., alias="accountName")
    verified: bool = True
    matches_provided_account_name: Optional[bool] = Field(None, alias="matchesProvidedAccountName")
    source: str = "nomba"

    class Config:
        populate_by_name = True


class WalletTransferOutResponse(BaseModel):
    status: str
    reference: str
    amount: float
    bank_name: str = Field(..., alias="bankName")
    account_number: str = Field(..., alias="accountNumber")
    account_name: str = Field(..., alias="accountName")
    provider_reference: Optional[str] = Field(None, alias="providerReference")
    message: str

    class Config:
        populate_by_name = True

class KYCReferenceData(BaseModel):
    reference: str


class KYCSubmitRequest(BaseModel):
    bvn: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    phone_number: Optional[str] = None


class WalletSetupRequest(KYCSubmitRequest):
    pass


class KYCActionResponse(BaseModel):
    status: str
    message: str
    data: Optional[KYCReferenceData] = None
    virtualAccount: Optional["VirtualAccountData"] = None
    walletStatus: Optional[str] = None


class VirtualAccountData(BaseModel):
    bank_name: str
    account_number: str
    account_name: str
    assigned: bool = True


class WalletSetupResponse(BaseModel):
    status: str
    message: str
    data: Optional[KYCReferenceData] = None
    virtualAccount: Optional[VirtualAccountData] = None
    walletStatus: Optional[str] = None

    class Config:
        populate_by_name = True

class WalletVirtualAccountEnvelope(BaseModel):
    virtualAccount: VirtualAccountData

class RequiredDocumentResponse(BaseModel):
    id: Optional[str] = None
    type: str
    description: Optional[str] = None
    status: Optional[str] = None

class WalletStatusResponse(BaseModel):
    status: str
    nextAction: Optional[str] = None
    message: Optional[str] = None
    reason: Optional[str] = None
    requiredDocuments: List[RequiredDocumentResponse] = Field(default_factory=list)
    virtualAccountAssigned: bool = False
    virtualAccount: Optional[VirtualAccountData] = None


class DirectPaymentInitResponse(BaseModel):
    reference: str
    amount: float # Naira
    email: str
    currency: str = "NGN"
    publicKey: Optional[str] = None
    authorizationUrl: Optional[str] = None
    accessCode: Optional[str] = None


# Subscription
class SubscriptionStatusResponse(BaseModel):
    status: str
    amount: int
    daysRemaining: int

class SubscriptionPayRequest(BaseModel):
    reference: str
    amount: int

# Services (Bills)
class ServiceProviderOption(BaseModel):
    id: str
    name: str # e.g. Prepaid, Postpaid

class ServiceProvider(BaseModel):
    id: Optional[str] = None # Original ID (nullable if grouped)
    name: str # e.g. Ikeja Electric
    logoUrl: Optional[str] = None
    type: str # e.g. electricity
    options: List[ServiceProviderOption] = []

class ServiceVerifyRequest(BaseModel):
    serviceId: str
    provider: Optional[str] = None
    accountNumber: str

class ServiceVerifyResponse(BaseModel):
    valid: bool
    accountName: str

class ServicePayRequest(BaseModel):
    serviceId: str
    amount: float # Naira
    providerId: Optional[str] = None
    accountNumber: Optional[str] = None
    transaction_pin: str = Field(..., min_length=4, max_length=4, alias="transactionPin")

    class Config:
        populate_by_name = True
    
class ServicePayInitResponse(BaseModel):
    reference: str
    publicKey: str
    amount: int
    email: str
    currency: str = "NGN"

class PhoneValidationRequest(BaseModel):
    phoneNumber: str
    network: Optional[str] = None # Optional: If provided, we verify match.

class PhoneValidationResponse(BaseModel):
    valid: bool
    network: Optional[str]
    formatted: Optional[str]
    message: Optional[str]


# Household
class HouseholdMemberResponse(BaseModel):
    user_id: str
    full_name: str
    role: str
    phone_number: Optional[str] = None
    email: str
    profile_image_url: Optional[str] = None

class HouseholdAddRequest(BaseModel):
    email: EmailStr
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    role: str = "other" # Default
    relationship: Optional[str] = None
    profile_image_url: Optional[str] = Field(None, alias="profileImageUrl")

class HouseholdCodeResponse(BaseModel):
    code: str


class StickerFeeResponse(BaseModel):
    amount: int
    currency: str = "NGN"
    deliveryFee: int = 0
    total: int

# Complaints
class ComplaintCreate(BaseModel):
    category: str
    priority: str
    description: str
    unitId: Optional[str] = None
    attachments: List[str] = []

class ComplaintResponse(BaseModel):
    id: str
    ticket_number: str = Field(..., alias="ticketNumber")
    category: str
    priority: str
    description: str
    status: str
    created_at: datetime = Field(..., alias="createdAt")
    attachments: List[str] = []

    class Config:
        from_attributes = True
        populate_by_name = True


class IncidentCreate(BaseModel):
    title: str
    location: str
    description: str
    category: str
    priority: Optional[str] = "high"
    attachments: List[str] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class IncidentResponse(BaseModel):
    id: str
    ticket_number: str = Field(..., alias="ticketNumber")
    status: str
    title: str
    location: str
    description: str
    category: str
    priority: str
    attachments: List[str] = Field(default_factory=list)
    created_at: datetime = Field(..., alias="createdAt")

    class Config:
        from_attributes = True
        populate_by_name = True


# Aura
class AuraRequest(BaseModel):
    input_type: str # text, audio
    content: str

class AuraResponse(BaseModel):
    intent: str
    parameters: dict
    response_text: str
    action_required: str

# Upload
class UploadResponse(BaseModel):
    url: str
    key: str
    mime_type: Optional[str] = None


class PresignedUrlResponse(BaseModel):
    upload_url: str
    public_url: str
    key: str
    fields: Optional[Dict[str, Any]] = None  # For POST uploads (optional)


class SignupResponse(BaseModel):
    user_id: str
    estate_id: Optional[str] = None
    token: str
    refresh_token: str
    token_type: str


# Visitor Invites
class LocationData(BaseModel):
    latitude: float
    longitude: float
    accuracy: Optional[float] = None

class InviteCreate(BaseModel):
    visitor_name: str = Field(..., alias="visitorName")
    visitor_phone: Optional[str] = Field(None, alias="visitorPhone")
    valid_hours: Optional[int] = Field(24, alias="validHours")
    valid_from: Optional[str] = Field(None, alias="validFrom")
    valid_until: Optional[str] = Field(None, alias="validUntil")
    invite_type: str = Field("single", alias="inviteType") # "single", "group", "recurring"
    location: Optional[LocationData] = None
    
    # New Fields
    visitor_gender: Optional[str] = Field(None, alias="visitorGender")
    expected_guests: Optional[int] = Field(None, alias="expectedGuests")

    class Config:
        populate_by_name = True

class InviteResponse(BaseModel):
    id: str
    access_code: str = Field(..., alias="accessCode")
    visitor_name: str = Field(..., alias="visitorName")
    valid_from: datetime = Field(..., alias="validFrom")
    valid_until: datetime = Field(..., alias="validUntil")
    status: str
    invite_type: str = Field(..., alias="inviteType")
    qr_code_data: Optional[str] = Field(None, alias="qrCodeData")
    
    class Config:
        from_attributes = True
        populate_by_name = True

class InviteExtendRequest(BaseModel):
    valid_until: Optional[str] = Field(None, alias="validUntil")
    valid_hours: Optional[int] = Field(None, alias="validHours", gt=0)

    class Config:
        populate_by_name = True

# Vehicles
class VehicleCreate(BaseModel):
    make: str
    model: str
    plate_number: str = Field(..., alias="plateNumber")
    color: str
    payment_reference: Optional[str] = Field(None, alias="paymentReference")

class VehicleResponse(BaseModel):
    id: str
    make: str
    model: str
    plate_number: str = Field(..., alias="plateNumber")
    status: str
    qr_code_data: Optional[str] = Field(None, alias="qrCodeData")
    
    class Config:
        from_attributes = True
        populate_by_name = True

# Alerts
class AlertCreate(BaseModel):
    type: str # "medical", "fire", "security"
    description: Optional[str] = None
    location_lat: Optional[str] = Field(None, alias="locationLat")
    location_long: Optional[str] = Field(None, alias="locationLong")

class AlertResponse(BaseModel):
    id: str
    type: str
    status: str
    created_at: datetime = Field(..., alias="createdAt")
    
    class Config:
        from_attributes = True
        populate_by_name = True

class NotificationResponse(BaseModel):
    id: str
    title: str
    message: str
    is_read: bool = Field(..., alias="isRead")
    created_at: datetime = Field(..., alias="createdAt")

    class Config:
        from_attributes = True
        populate_by_name = True

# Subscriptions
class SubscriptionCreate(BaseModel):
    plan: str # "basic", "premium"

class SubscriptionResponse(BaseModel):
    plan: str
    status: str
    start_date: str
    end_date: Optional[str] = None
    

class BillView(BaseModel):
    id: str # Assignment ID
    bill_type: str = Field(..., alias="billType")
    bill_title: str = Field(..., alias="billTitle")
    bill_description: Optional[str] = Field(None, alias="billDescription")
    total_amount: float = Field(..., alias="totalAmount") # Naira
    amount_paid: float = Field(..., alias="amountPaid")   # Naira
    amount_left: float = Field(..., alias="amountLeft")   # Naira
    status: str
    due_date: Optional[str] = Field(None, alias="dueDate")

class PayBillRequest(BaseModel):
    amount: float # Naira
    transaction_pin: str = Field(..., min_length=4, max_length=4, alias="transactionPin")

    class Config:
        populate_by_name = True

class ServiceChargeResponse(BaseModel):
    unit_id: str
    total_outstanding: float  # Naira - sum of all unpaid service charges
    total_paid: float         # Naira
    bills_count: int
    oldest_due_date: Optional[datetime] = None
    status: str               # "overdue" / "due" / "partial" / "paid"
    currency: str = "NGN"

class RentSummaryResponse(BaseModel):
    unit_id: str
    total_outstanding: float  # Naira - sum of all unpaid rent assignments
    total_paid: float         # Naira
    bills_count: int
    oldest_due_date: Optional[datetime] = None
    status: str               # "overdue" / "due" / "partial" / "paid"
    currency: str = "NGN"

class BillSummaryResponse(BaseModel):
    unit_id: str
    total_outstanding: float  # Naira - sum of all unpaid bill assignments
    amount: float = 0.0       # Naira - compatibility mirror of total_outstanding
    total_paid: float         # Naira
    bills_count: int
    oldest_due_date: Optional[datetime] = None
    status: str               # "overdue" / "due" / "partial" / "paid"
    currency: str = "NGN"
    bill_title: Optional[str] = None
    billTitle: Optional[str] = None
    bill_description: Optional[str] = None
    billDescription: Optional[str] = None

class ServiceChargePayRequest(BaseModel):
    unitId: str
    amount: float  # Naira
    transaction_pin: str = Field(..., min_length=4, max_length=4, alias="transactionPin")

    class Config:
        populate_by_name = True

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

class RentPayRequest(BaseModel):
    unitId: str
    amount: float # Naira
    transaction_pin: str = Field(..., min_length=4, max_length=4, alias="transactionPin")

    class Config:
        populate_by_name = True

class BillPayRequest(BaseModel):
    unitId: str
    amount: float # Naira
    transaction_pin: str = Field(..., min_length=4, max_length=4, alias="transactionPin")

    class Config:
        populate_by_name = True

class WalletVerifyBVNRequest(BaseModel):
    bvn: str
    account_number: str = Field(..., alias="accountNumber")
    bank_code: str = Field(..., alias="bankCode")

class BVNConsentRequest(BaseModel):
    bvn: str
    firstname: str
    lastname: str
    redirect_url: str = Field(..., alias="redirectUrl")

class VirtualAccountCreateRequest(BaseModel):
    email: EmailStr
    firstname: str
    lastname: str
    phonenumber: str
    bvn: str
    reference: str

class VirtualAccountResponse(BaseModel):
    account_number: str = Field(..., alias="accountNumber")
    bank_name: str = Field(..., alias="bankName")
    reference: str



class ServicePayDynamicRequest(BaseModel):
    service_id: str = Field(..., alias="serviceId")
    provider_id: str = Field(..., alias="providerId")
    customer_id: str = Field(..., alias="accountNumber") # Display name match
    amount: int

class DashboardResponse(BaseModel):
    greeting: str
    wallet_balance: float = Field(..., alias="walletBalance") # Naira
    active_invites_count: int = Field(..., alias="activeInvitesCount")
    pending_bills_count: int = Field(..., alias="pendingBillsCount")
    recent_activities: List[dict] = Field(..., alias="recentActivities") # Generic dict for now or specific Activity model
    unread_notifications_count: int = Field(0, alias="unreadNotificationsCount")

    class Config:
        populate_by_name = True

class QuickAction(BaseModel):
    id: str
    label: str
    animationUrl: Optional[str] = None
    route: str
    enabled: bool

class HomeConfigResponse(BaseModel):
    quickActions: List[QuickAction]



class DigitalIDResponse(BaseModel):
    token: str
    refreshed_at: Optional[datetime] = Field(None, alias="refreshedAt")

    class Config:
        populate_by_name = True

# ── Feed & Community ──────────────────────────────────────────────────────────

class FeedPollOption(BaseModel):
    text: str

class FeedPollResponse(BaseModel):
    options: List[str]
    votes: List[int]
    user_vote: Optional[int] = Field(None, alias="userVote")
    end_at: Optional[datetime] = Field(None, alias="endAt")

    class Config:
        populate_by_name = True

class FeedPostCreate(BaseModel):
    content: Optional[str] = None
    media_urls: List[str] = Field(default_factory=list, alias="mediaUrls")
    poll: Optional[Dict[str, Any]] = None # {"options": ["A", "B"], "endAt": "..."}

    class Config:
        populate_by_name = True

class FeedReplyCreate(BaseModel):
    content: Optional[str] = None
    media_urls: List[str] = Field(default_factory=list, alias="mediaUrls")
    reply_to_author: Optional[str] = Field(None, alias="replyToAuthor")

    class Config:
        populate_by_name = True

class FeedPostResponse(BaseModel):
    id: str
    author_id: str = Field(..., alias="authorId")
    author_name: str = Field(..., alias="authorName")
    author_avatar: Optional[str] = Field(None, alias="authorAvatar")
    author_unit: Optional[str] = Field(None, alias="authorUnit")
    content: Optional[str] = None
    media_urls: List[str] = Field(default_factory=list, alias="mediaUrls")
    media: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(..., alias="createdAt")
    like_count: int = Field(0, alias="likeCount")
    reply_count: int = Field(0, alias="replyCount")
    repost_count: int = Field(0, alias="repostCount")
    is_liked: bool = Field(False, alias="isLiked")
    is_reposted: bool = Field(False, alias="isReposted")
    reply_to_id: Optional[str] = Field(None, alias="replyToId")
    reply_to_author: Optional[str] = Field(None, alias="replyToAuthor")
    poll: Optional[FeedPollResponse] = None

    class Config:
        from_attributes = True
        populate_by_name = True

class FeedListResponse(BaseModel):
    posts: List[FeedPostResponse]
    next_cursor: Optional[str] = Field(None, alias="nextCursor")

class PollVoteRequest(BaseModel):
    option_index: int = Field(..., alias="optionIndex")


class PollVoteResponse(BaseModel):
    success: bool
    poll: FeedPollResponse

    class Config:
        populate_by_name = True

# ── Messaging ───────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    id: str
    from_id: str = Field(..., alias="fromId")
    from_name: str = Field(..., alias="fromName")
    text: Optional[str] = None
    created_at: datetime = Field(..., alias="createdAt")
    media_urls: List[str] = Field(default=[], alias="mediaUrls")
    read_at: Optional[datetime] = Field(None, alias="readAt")

    class Config:
        from_attributes = True
        populate_by_name = True

class ConversationParticipantResponse(BaseModel):
    id: str
    name: str
    avatar: Optional[str] = None

class ConversationResponse(BaseModel):
    id: str
    participants: List[ConversationParticipantResponse]
    is_group: bool = Field(..., alias="isGroup")
    last_message: Optional[Dict[str, Any]] = Field(None, alias="lastMessage")
    unread_count: int = Field(0, alias="unreadCount")
    group_name: Optional[str] = Field(None, alias="groupName")

    class Config:
        from_attributes = True
        populate_by_name = True

class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    next_cursor: Optional[str] = Field(None, alias="nextCursor")

class ConversationCreateRequest(BaseModel):
    participant_id: Optional[str] = Field(None, alias="participantId") # for 1:1
    participant_ids: Optional[List[str]] = Field(None, alias="participantIds") # for group
    group_name: Optional[str] = Field(None, alias="groupName")

class ParticipantAddRequest(BaseModel):
    participant_ids: List[str] = Field(..., alias="participantIds")

class MessageCreateRequest(BaseModel):
    text: Optional[str] = None
    media_urls: Optional[List[str]] = Field(None, alias="mediaUrls")

class ResidentResponse(BaseModel):
    id: str
    name: str
    avatar: Optional[str] = None
    unit: Optional[str] = None

    class Config:
        from_attributes = True


class ResidentHouseGroupResponse(BaseModel):
    unit_id: Optional[str] = Field(None, alias="unitId")
    house_label: str = Field(..., alias="houseLabel")
    block_name: Optional[str] = Field(None, alias="blockName")
    estate_address: Optional[str] = Field(None, alias="estateAddress")
    residents: List[ResidentResponse]

    class Config:
        from_attributes = True
        populate_by_name = True
