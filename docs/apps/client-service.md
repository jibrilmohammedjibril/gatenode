# Client Service

## Role

The Client service is the public resident backend. It owns direct signup, estate-code onboarding, household membership, wallet, KYC, billing, invites, vehicles, notifications, uploads, feed, DM, and resident support flows.

## Entrypoint

- App file: [client/main.py](/Users/jibrilmjibril/Desktop/JMJ/Projects/gatenode/client/main.py)
- Base API prefix: root-level route prefixes from each router
- Health check: `GET /health`

## Route Groups

- `/auth`
  - signup, login, refresh, logout
  - join estate with code
  - password reset request and completion
- `/user`
  - profile read and update
  - unit listing
  - account deletion
  - transaction PIN verify, change, forgot, status
  - digital ID fetch and refresh
- `/kyc`
  - wallet/KYC verification lifecycle
  - upload KYC document
- `/wallet`
  - balance
  - transaction history
  - wallet status
  - virtual account details
  - live bank list from Nomba
  - bank transfer-out withdrawals
- `/bills`
  - service-charge summary
  - rent availability and rent details
  - wallet rent payment
  - list assigned manual rent and service-charge bills
  - wallet bill payment
- `/services`
  - service categories
  - billers by category
  - biller items/products
  - customer/account verification
  - phone validation
  - wallet-only utility payment
- `/vehicles`
  - sticker fee lookup
  - create, delete, list vehicles
- `/incidents`
  - incident report intake
- `/invites`
  - create, list, history, revoke, delete, extend, verify
- `/household`
  - list members
  - add member
  - invite alias
  - remove member
  - household code
- `/complaints`
  - create and list complaints
- `/notifications`
  - list
  - mark one read
  - mark all read
- `/community`
  - resident alerts
  - community spending
- `/events`
  - realtime event stream
  - debug triggers
- `/upload`
  - file upload
- `/device-tokens`
  - register device token
- `/subscriptions`
  - subscription status
- `/dashboard`
  - resident dashboard summary
- `/config`
  - home configuration
- `/public`
  - estate branding
- `/support`
  - support request intake
- `/aura`
  - AI interaction endpoint
- `/webhooks`
  - Nomba webhook
- `/live-activities`
  - ActivityKit push token registration
- `/feed`
  - posts, likes, replies, favorites
- `/dm`
  - conversations, messages, resident search, read state

## Core Models

Defined in [client/core/models.py](/Users/jibrilmjibril/Desktop/JMJ/Projects/gatenode/client/core/models.py).

Primary domain objects:

- `Estate`, `Block`, `Unit`
- `User`, `UserUnit`, `HouseholdRole`
- `Complaint`
- `Vehicle`
- `VisitorInvite`, `HouseholdInvite`, `LiveActivityToken`
- `Alert`
- `Notification`
- `Subscription`
- `Transaction`
- `Bill`, `BillAssignment`
- `WalletHistory`
- `WalletProfile`
- `WebhookLog`

## Integrations

- PostgreSQL via async SQLAlchemy
- APScheduler startup job in the client app
- Nomba wallet APIs and webhook flow
- FCM and APNs push delivery
- ZeptoMail / email receipt flows
- MinIO uploads

## Important Responsibilities

- resident authentication and session lifecycle
- estate-code membership management
- wallet onboarding, status tracking, and transfer-out
- rent, bill, and utility payments
- invite lifecycle
- resident vehicles
- uploads, branding consumption, dashboard aggregation
- device-token registration and push notification history
- resident social and messaging flows

## Known Hotspots

- payment flow: kyc, wallet, bills, services, webhooks, notifications
- auth/session flow: auth, device tokens, push filtering
- household flow: user, user-unit, invite, notification side effects
- scheduled work: subscription checks and service-charge generation

## Cross-Feature Dependencies

- Estate membership affects billing, household, feed, DM, invites, and resident alerts.
- Wallet transfer-out depends on transaction PIN verification, Nomba transfer responses, webhook reconciliation, and transaction history.
- Wallet setup starts on first funding attempt, creates a Nomba virtual account, and returns the resident's bank details for future wallet top-ups.
- Public signup must work before estate membership is assigned.
