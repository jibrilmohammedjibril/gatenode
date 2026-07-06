# Gatenode Resident Client Frontend Technical Guide

This document is the frontend handoff for the public resident client.

## 1. Product Shape

The app is a resident-facing client with:

- direct signup
- estate-code onboarding
- wallet funding through Nomba virtual accounts
- bank transfer-out withdrawals
- utility payments
- service charge, rent, and bill payment
- household management
- invites, vehicles, incidents, complaints
- notifications, feed, and direct messaging
- resident profile, PIN, and digital ID flows

## 2. Base API Rules

- Base URL is the backend host for the environment being used.
- All authenticated requests use `Authorization: Bearer <access_token>`.
- Most estate-scoped routes require the user to have joined an estate first.
- The backend returns explicit state values for wallet setup and estate membership.

## 3. Core Onboarding Flow

### Step 1: Sign up

`POST /auth/signup`

Use this for direct account creation. No admin-issued code is required.

Request body:

```json
{
  "email": "resident@example.com",
  "password": "secret1234",
  "first_name": "Jide",
  "middle_name": "A",
  "last_name": "Adeyemi",
  "phone_number": "08012345678"
}
```

### Step 2: Join an estate

`POST /auth/join-estate`

The resident enters an estate code and gets attached to the estate and default unit.

Request body:

```json
{
  "estateCode": "AB12CD34"
}
```

### Step 3: Wallet setup on first funding

`POST /wallet/setup`

When the user first taps Add Money, prompt for BVN and send it here. This creates the Nomba virtual account.

Request body:

```json
{
  "bvn": "22345678901",
  "date_of_birth": "1990-01-01",
  "gender": "MALE",
  "phone_number": "08012345678"
}
```

Wallet setup is explicit:

- `wallet_setup_required`
- `wallet_setup_failed`
- `pending_verification`
- `account_pending`
- `active`

### Step 4: Funding and transfer history

- `GET /wallet/status`
- `GET /wallet/virtual-account`
- `GET /wallet/balance`
- `GET /wallet/transactions`

The wallet screen should show:

- setup required state
- setup retry state
- virtual account details after setup
- current balance
- transaction history

## 4. Auth and Session

### Endpoints

- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /auth/request-password-reset`
- `POST /auth/reset-password`

### Client expectations

- persist access and refresh tokens securely
- refresh the access token when a request returns unauthorized
- keep the user signed in across app restarts if refresh is valid
- show a join-estate CTA if the user has no estate yet

## 5. Wallet Flows

### Wallet status

`GET /wallet/status`

Use this first to decide what the wallet screen should show.

### Wallet balance

`GET /wallet/balance`

Only available when wallet status is ready enough to show balance.

### Virtual account

`GET /wallet/virtual-account`

Use this to show the resident’s funding destination after setup.

### Bank picker

`GET /wallet/banks?q=first`

Use this to populate the transfer-out bank selector from the live Nomba bank directory.
The response is already normalized to:

```json
{
  "banks": [
    {
      "bankName": "First Bank of Nigeria",
      "bankCode": "011"
    }
  ],
  "count": 1,
  "source": "nomba"
}
```

### Transfer out

`POST /wallet/transfer-out`

Request body:

```json
{
  "bankName": "First Bank",
  "bankCode": "011",
  "accountNumber": "0123456789",
  "accountName": "Jide Adeyemi",
  "amount": 5000,
  "transactionPin": "1234",
  "narration": "Wallet withdrawal"
}
```

Frontend rules:

- verify PIN before submit
- validate bank details in the form
- show pending/success/failed states from the response and transaction history

### Transaction list

`GET /wallet/transactions`

Show these categories clearly:

- funding
- transfer_out
- airtime
- data
- electricity
- cable
- bills
- service_charge

## 6. Bills and Service Charge

### Service charge summary

`GET /bills/service-charge`

### Service charge payment

`POST /bills/service-charge/pay`

Request body:

```json
{
  "unitId": "unit_123",
  "amount": 25000,
  "transactionPin": "1234"
}
```

### Rent

- `GET /bills/rent-config`
- `GET /bills/rent-details?unit_id=...`
- `POST /bills/rent/pay`

### Estate bill

- `GET /bills/bill`
- `POST /bills/bill/pay`
- `GET /bills/`
- `POST /bills/{assignment_id}/pay`

### UI rule

- if the user is not in an estate, do not show estate billing as an error state
- show a join-estate prompt instead

## 7. Utility Payments

### Categories

`GET /services/categories`

Supported slugs:

- `electricity`
- `data`
- `airtime`
- `cable`
- `internet`

### Billers and products

- `GET /services/billers?category=airtime`
- `GET /services/billers/{biller_code}/items`

### Validation

- `POST /services/verify`
- `POST /services/validate-phone`

### Pay utility

`POST /services/pay`

Request body:

```json
{
  "serviceId": "service_123",
  "amount": 2000,
  "providerId": "product_abc",
  "accountNumber": "08012345678",
  "transactionPin": "1234"
}
```

Use one payment UI for:

- airtime
- data
- electricity
- cable

## 8. Estate, Household, and Resident Management

### Profile

- `GET /user/profile`
- `PATCH /user/profile`
- `GET /user/units`
- `DELETE /user/account`

### PIN

- `POST /user/pin/verify`
- `POST /user/pin/change`
- `POST /user/pin/forgot`
- `GET /user/pin/status`

### Digital ID

- `GET /user/digital-id`
- `POST /user/digital-id/refresh`

### Household

- `GET /household`
- `POST /household`
- `POST /household/invite`
- `DELETE /household/{target_user_id}`
- `GET /household/code`

### Vehicles

- `GET /vehicles/sticker-fee`
- `POST /vehicles`
- `GET /vehicles`
- `DELETE /vehicles/{vehicle_id}`

### Complaints

- `POST /complaints`
- `GET /complaints`

### Incidents

- `POST /incidents`

## 9. Invites and Visitor Access

- `POST /invites`
- `GET /invites`
- `GET /invites/history`
- `POST /invites/{invite_id}/revoke`
- `DELETE /invites/{invite_id}`
- `POST /invites/{invite_id}/extend`
- `POST /invites/verify/{access_code}`

The invite QR / code view should remain available as long as the user has an estate and a unit.

## 10. Notifications and Realtime

- `GET /notifications/`
- `POST /notifications/{notification_id}/read`
- `POST /notifications/read-all`
- `GET /events`
- `POST /device-tokens/`
- `POST /live-activities/tokens`

The frontend should register push tokens after login and keep them updated per device.

## 11. Feed and Messaging

### Feed

- `GET /feed/posts`
- `GET /feed/posts/{post_id}`
- `POST /feed/posts`
- `POST /feed/posts/{post_id}/like`
- `DELETE /feed/posts/{post_id}/like`
- `POST /feed/posts/{post_id}/poll/vote`
- `DELETE /feed/posts/{post_id}`
- `GET /feed/users/{user_id}/posts`
- `GET /feed/favorites`
- `POST /feed/favorites`
- `DELETE /feed/favorites/{fav_user_id}`
- `POST /feed/posts/{post_id}/replies`
- `GET /feed/posts/{post_id}/replies`

### Messaging

Messaging routes are also mounted under the `/feed` prefix:

- `GET /feed/conversations`
- `POST /feed/conversations`
- `POST /feed/conversations/{conversation_id}/participants`
- `POST /feed/conversations/{conversation_id}/leave`
- `DELETE /feed/conversations/{conversation_id}`
- `GET /feed/conversations/{conversation_id}/messages`
- `POST /feed/conversations/{conversation_id}/messages`
- `DELETE /feed/conversations/{conversation_id}/messages/{message_id}`
- `POST /feed/conversations/{conversation_id}/read`
- `GET /feed/residents`
- `GET /feed/residents/grouped`

## 12. Home, Branding, and Support

- `GET /config/home`
- `GET /public/estate-branding/{estate_id}`
- `POST /support`
- `POST /aura/interact`

`GET /config/home` controls the home quick actions, while `/public/estate-branding/{estate_id}` is used before or during login to style the client.

## 13. Uploads

- `POST /upload`
- `GET /presigned-url`

Use uploads for:

- profile photos
- complaint attachments
- incident attachments
- feed media
- invite graphics where applicable

If storage is not configured, show a clean disabled state for upload features.

## 14. Useful Response States

The frontend should handle these states explicitly:

- `wallet_setup_required`
- `wallet_setup_failed`
- `pending_verification`
- `awaiting_document`
- `manual_review`
- `reenter_information`
- `rejected`
- `account_pending`
- `active`

For estate membership:

- no estate linked yet
- estate linked but unit not yet resolved
- joined estate with primary unit assigned

## 15. Suggested Screen Map

- Auth screens: signup, login, reset password
- Estate join screen: enter code
- Home dashboard: summary cards, quick actions, wallet preview, notifications
- Wallet screen: balance, top up instructions, virtual account, transfer out, transaction history
- Bills screen: service charge, rent, estate bill
- Services screen: airtime, data, electricity, cable
- Household screen: members, add member, household code
- Invites screen: create and manage visitor invites
- Feed screen: posts, likes, replies, favorites
- Messages screen: conversations and chats
- Profile screen: profile, PIN, digital ID, settings

## 16. Practical UI Rules

- Do not block signup behind estate membership.
- If estate membership is missing, show a join-estate call to action.
- If wallet setup is missing, show Add Money as the trigger to collect BVN and create the virtual account.
- For utility and billing actions, require a transaction PIN.
- For transfer out, validate bank details before submit.

## 17. Recommended API Handling

- Treat `404` on wallet balance as “wallet not ready.”
- Treat `409` as “action blocked by current account state.”
- Treat `502` as an upstream provider issue that should be retryable.
- Treat `503` on upload features as storage unavailable.
