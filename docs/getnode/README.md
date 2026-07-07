# GetNode App Capabilities

This document explains what the GetNode resident app can do in plain language.
It is written for product, operations, support, and business teams, not only engineers.

## Quick Summary

GetNode is a resident-facing estate management app. It helps residents join an estate, manage their profile, pay estate bills, fund and use a wallet, invite visitors, manage household members, register vehicles, report issues, receive updates, and communicate with other residents.

The backend currently exposes **110 endpoints**. An endpoint is simply a doorway the mobile app or web app uses to ask the backend to do something, such as logging in, paying a bill, listing visitors, or sending a message.

## Main Capabilities

### 1. Account and Estate Access

Residents can create an account, log in, reset their password, and join an estate using an estate code. This allows people to sign up first, then connect their account to the right estate and unit.

What this supports:

- new resident signup
- login and logout
- session refresh so users stay signed in
- password reset
- joining an estate with a code
- leaving an estate

### 2. Resident Profile and Digital Identity

Residents can view and update their profile, check their assigned units, manage their transaction PIN, request account deletion, and access a digital ID.

What this supports:

- profile view and update
- unit list
- transaction PIN setup, verification, change, and recovery
- digital resident ID
- account deletion request

### 3. Wallet and Bank Payments

GetNode includes a wallet system for residents. Users can check their balance, view transactions, set up their wallet, get virtual account details, and withdraw money to a bank account.

The app connects to Nomba for wallet and bank-related actions.

What this supports:

- wallet balance
- wallet transaction history
- wallet setup
- wallet status
- virtual account details for funding
- Nigerian bank list
- bank account name confirmation
- wallet withdrawal or transfer-out

### 4. KYC Verification

Residents can submit the information needed for wallet verification. This is part of making wallet and money movement safer.

What this supports:

- KYC submission
- wallet verification flow

### 5. Estate Bills and Rent

Residents can see and pay different kinds of estate bills, including service charge, rent, and assigned estate bills.

What this supports:

- service charge summary
- service charge payment
- rent setup/configuration visibility
- rent details
- rent payment
- general assigned bills
- bill payment from wallet

### 6. Utility and Everyday Service Payments

Residents can browse service categories, view billers, verify customer details, validate phone networks, and pay for services from their wallet.

What this supports:

- utility/service categories
- biller list
- biller items/products
- customer verification before payment
- phone network validation
- wallet-based service payment

### 7. Visitors and Access Codes

Residents can create visitor invites, view active invites, see invite history, extend or revoke invites, and verify access codes.

What this supports:

- visitor invite creation
- active invite list
- invite history
- invite extension
- invite revocation
- invite deletion
- access-code verification

### 8. Household Management

Residents can manage people linked to their household or unit. They can list members, add members, invite members, remove members, and retrieve a household code.

What this supports:

- household member list
- adding household members
- inviting household members
- removing household members
- household code retrieval

### 9. Vehicles

Residents can register their vehicles, view registered vehicles, remove vehicles, and check the estate vehicle sticker fee.

What this supports:

- vehicle registration
- vehicle list
- vehicle removal
- vehicle sticker fee

### 10. Complaints and Incident Reports

Residents can submit complaints and incident reports. Complaints can also be listed so users can track what they have already submitted.

What this supports:

- complaint submission
- complaint list
- incident report submission

### 11. Community Feed

Residents can interact with a community feed. They can create posts, view posts, like posts, reply to posts, vote in polls, view another resident's posts, and manage favorites.

What this supports:

- feed posts
- post creation
- post details
- post deletion
- likes and unlikes
- poll voting
- replies
- favorite residents
- posts by a specific resident

### 12. Direct Messaging

Residents can find other residents, start conversations, send messages, add people to group conversations, mark messages as read, leave conversations, and delete conversations or messages.

Messaging currently lives under the `/feed` path in the backend, because it is closely tied to the resident community experience.

What this supports:

- resident search
- grouped resident search
- conversations
- group conversations
- message list
- sending messages
- unread/read status
- leaving conversations
- deleting conversations
- unsending messages

### 13. Notifications and Live Updates

The app supports notifications, device push tokens, Apple Live Activities tokens, and real-time event streaming. This helps the app show fresh information without users manually refreshing everything.

What this supports:

- notification list
- mark one notification as read
- mark all notifications as read
- mobile device token registration
- Apple Live Activities token registration
- real-time event stream

### 14. Dashboard and Home Screen

The app has endpoints for the resident dashboard and home configuration. These help the frontend show the right summary information and home-screen content.

What this supports:

- dashboard summary
- home screen configuration
- subscription status

### 15. Estate Branding and Public Information

The app can fetch estate branding, such as the estate identity needed by the frontend.

What this supports:

- estate branding by estate ID

### 16. Uploads

The app supports direct file upload and presigned upload links. This can be used for profile images, documents, KYC files, complaints, or other media-supported features.

What this supports:

- file upload
- presigned upload URL

### 17. Support and Webhooks

The app can receive support-related webhooks and payment webhooks. Webhooks are automatic messages sent from another service into GetNode, for example when a payment provider sends an update.

What this supports:

- Nomba payment/wallet webhook
- alternate Nomba webhook path
- Chatwoot support webhook

### 18. Aura AI

The app includes an Aura interaction endpoint. This appears to support an AI assistant or AI-powered interaction inside the product.

What this supports:

- AI interaction request

## Endpoint Count by Area

| Area | Number of endpoints | What it mainly covers |
| --- | ---: | --- |
| Auth | 9 | Signup, login, password reset, joining/leaving estate |
| User | 11 | Profile, units, PIN, digital ID, account deletion |
| Wallet | 8 | Balance, transactions, wallet setup, virtual account, bank transfer |
| KYC | 1 | Verification submission |
| Bills | 9 | Service charge, rent, estate bills, bill payment |
| Services | 6 | Utility/service billers, verification, payment |
| Invites | 7 | Visitor invite creation, history, update, verification |
| Household | 5 | Household members and household code |
| Vehicles | 4 | Vehicle registration, sticker fee, vehicle list/removal |
| Complaints | 2 | Complaint submission and list |
| Incidents | 1 | Incident report submission |
| Feed | 13 | Posts, likes, replies, polls, favorites |
| Messaging | 11 | Conversations, messages, resident search |
| Notifications | 3 | Notification list and read status |
| Events | 4 | Real-time event stream and debug triggers |
| Device Tokens | 1 | Push notification device token |
| Live Activities | 1 | Apple Live Activities token |
| Dashboard | 1 | Resident dashboard summary |
| Config | 1 | Home screen configuration |
| Subscription | 1 | Subscription status |
| Public | 1 | Estate branding |
| Uploads | 2 | Upload and presigned upload link |
| Webhooks | 3 | Nomba and Chatwoot incoming updates |
| Community | 2 | Alerts and community spending |
| Aura AI | 1 | AI interaction |
| System | 2 | Root welcome and health check |
| **Total** | **110** | Full resident app backend |

## Endpoint Catalogue

This section lists the endpoints in a simple way. The technical request and response details are intentionally left out here so the document stays easy to read.

### Account and Estate

| Endpoint | Purpose |
| --- | --- |
| `POST /auth/signup` | Create a new resident account |
| `POST /auth/login` | Sign in with account details |
| `POST /auth/token` | Sign in using token-style login |
| `POST /auth/refresh` | Refresh the user's session |
| `POST /auth/logout` | Sign the user out |
| `POST /auth/request-password-reset` | Start password reset |
| `POST /auth/reset-password` | Complete password reset |
| `POST /auth/join-estate` | Join an estate using an estate code |
| `POST /auth/leave-estate` | Leave the current estate |

### User Profile and PIN

| Endpoint | Purpose |
| --- | --- |
| `GET /user/` | Get the current user's profile summary |
| `GET /user/profile` | Get full profile details |
| `PATCH /user/profile` | Update profile details |
| `GET /user/units` | View units linked to the resident |
| `DELETE /user/account` | Request account deletion |
| `POST /user/pin/verify` | Confirm a transaction PIN |
| `POST /user/pin/change` | Change the transaction PIN |
| `POST /user/pin/forgot` | Start forgotten PIN recovery |
| `GET /user/pin/status` | Check whether PIN is set |
| `GET /user/digital-id` | View the resident digital ID |
| `POST /user/digital-id/refresh` | Refresh the digital ID |

### Wallet and KYC

| Endpoint | Purpose |
| --- | --- |
| `GET /wallet/status` | Check wallet setup and verification status |
| `POST /wallet/setup` | Set up the resident wallet |
| `GET /wallet/balance` | View wallet balance |
| `GET /wallet/transactions` | View wallet transaction history |
| `GET /wallet/virtual-account` | View wallet funding account details |
| `GET /wallet/banks` | View supported banks |
| `POST /wallet/resolve-bank-account` | Confirm bank account name |
| `POST /wallet/transfer-out` | Send money from wallet to bank |
| `POST /kyc/submit` | Submit KYC information |

### Bills, Rent, and Services

| Endpoint | Purpose |
| --- | --- |
| `GET /bills/service-charge` | View service charge details |
| `POST /bills/service-charge/pay` | Pay service charge |
| `GET /bills/rent-config` | Check rent setup for the estate |
| `GET /bills/rent-details` | View rent details |
| `POST /bills/rent/pay` | Pay rent |
| `GET /bills/` | View assigned bills |
| `GET /bills/bill` | View estate bill summary |
| `POST /bills/bill/pay` | Pay an estate bill |
| `POST /bills/{assignment_id}/pay` | Pay a specific assigned bill |
| `GET /services/categories` | View service categories |
| `GET /services/billers` | View billers or service providers |
| `GET /services/billers/{biller_code}/items` | View products/items for a biller |
| `POST /services/verify` | Verify customer details before paying |
| `POST /services/validate-phone` | Validate phone network details |
| `POST /services/pay` | Pay for a service from wallet |

### Visitors and Household

| Endpoint | Purpose |
| --- | --- |
| `POST /invites` | Create a visitor invite |
| `GET /invites` | View active visitor invites |
| `GET /invites/history` | View past visitor invites |
| `POST /invites/{invite_id}/revoke` | Revoke a visitor invite |
| `DELETE /invites/{invite_id}` | Delete a visitor invite |
| `POST /invites/{invite_id}/extend` | Extend a visitor invite |
| `POST /invites/verify/{access_code}` | Verify a visitor access code |
| `GET /household` | View household members |
| `POST /household` | Add a household member |
| `POST /household/invite` | Invite a household member |
| `DELETE /household/{target_user_id}` | Remove a household member |
| `GET /household/code` | Get the household code |

### Vehicles, Complaints, and Incidents

| Endpoint | Purpose |
| --- | --- |
| `GET /vehicles` | View registered vehicles |
| `POST /vehicles` | Register a vehicle |
| `DELETE /vehicles/{vehicle_id}` | Remove a vehicle |
| `GET /vehicles/sticker-fee` | View vehicle sticker fee |
| `POST /complaints` | Submit a complaint |
| `GET /complaints` | View submitted complaints |
| `POST /incidents` | Submit an incident report |

### Community Feed and Messaging

| Endpoint | Purpose |
| --- | --- |
| `GET /feed/posts` | View community posts |
| `POST /feed/posts` | Create a community post |
| `GET /feed/posts/{post_id}` | View one post |
| `DELETE /feed/posts/{post_id}` | Delete a post |
| `POST /feed/posts/{post_id}/like` | Like a post |
| `DELETE /feed/posts/{post_id}/like` | Remove a like |
| `POST /feed/posts/{post_id}/poll/vote` | Vote in a poll |
| `GET /feed/posts/{post_id}/replies` | View replies |
| `POST /feed/posts/{post_id}/replies` | Reply to a post |
| `GET /feed/users/{user_id}/posts` | View posts by one resident |
| `GET /feed/favorites` | View favorite residents |
| `POST /feed/favorites` | Add a favorite resident |
| `DELETE /feed/favorites/{fav_user_id}` | Remove a favorite resident |
| `GET /feed/residents` | Search residents |
| `GET /feed/residents/grouped` | Search residents grouped by household/unit |
| `GET /feed/conversations` | View conversations |
| `POST /feed/conversations` | Start a conversation |
| `DELETE /feed/conversations/{conversation_id}` | Delete a conversation |
| `POST /feed/conversations/{conversation_id}/leave` | Leave a group conversation |
| `GET /feed/conversations/{conversation_id}/messages` | View messages |
| `POST /feed/conversations/{conversation_id}/messages` | Send a message |
| `DELETE /feed/conversations/{conversation_id}/messages/{message_id}` | Unsend a message |
| `POST /feed/conversations/{conversation_id}/participants` | Add people to a conversation |
| `POST /feed/conversations/{conversation_id}/read` | Mark a conversation as read |

### Notifications, Updates, and App Setup

| Endpoint | Purpose |
| --- | --- |
| `GET /notifications/` | View notifications |
| `POST /notifications/{notification_id}/read` | Mark one notification as read |
| `POST /notifications/read-all` | Mark all notifications as read |
| `POST /device-tokens/` | Register a mobile device for push notifications |
| `POST /live-activities/tokens` | Register Apple Live Activities token |
| `GET /events` | Receive real-time updates |
| `POST /events/debug/trigger` | Test a real-time event |
| `POST /events/debug/trigger-wallet` | Test a wallet event |
| `POST /events/debug/trigger-notification` | Test a notification event |
| `GET /dashboard` | View resident dashboard summary |
| `GET /config/home` | Get home screen configuration |
| `GET /subscription` | Check subscription status |

### Public, Uploads, Support, AI, and System

| Endpoint | Purpose |
| --- | --- |
| `GET /public/estate-branding/{estate_id}` | Get estate branding |
| `POST /upload` | Upload a file |
| `GET /presigned-url` | Get a secure upload link |
| `POST /alerts/` | Trigger a resident alert |
| `GET /community/spending` | View community spending |
| `POST /aura/interact` | Send an AI interaction request |
| `POST /webhooks/nomba` | Receive Nomba webhook updates |
| `POST /webhook/nomba` | Receive Nomba webhook updates on alternate path |
| `POST /webhooks/chatwoot` | Receive Chatwoot support webhook updates |
| `GET /` | Welcome response |
| `GET /health` | Health check for the service |

## Important Notes

- The app is mainly built for residents of estate communities.
- A user can create an account before joining an estate.
- Many features depend on the user being connected to an estate and unit.
- Wallet, bills, services, and transfers are connected closely, because payments move through the wallet system.
- Notifications, device tokens, live activities, and real-time events help the app stay updated.
- Some debug endpoints exist for testing events and should be treated carefully in production.

