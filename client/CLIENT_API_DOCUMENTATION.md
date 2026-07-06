# Client API Documentation

This document summarizes the public resident client API.

Latest update: direct resident signup, estate-code onboarding, Nomba wallet funding, and Nomba bank transfer-out.

## Auth

- `POST /auth/signup`
  - Create a resident account directly with email, password, and name fields.
- `POST /auth/login`
  - Login with email and password.
- `POST /auth/join-estate`
  - Join an estate using an estate code and attach the user to the default unit.

## Wallet

- `GET /wallet/status`
- `GET /wallet/balance`
- `GET /wallet/transactions`
- `POST /wallet/setup`
  - Accepts BVN and creates the resident's Nomba virtual account on first funding.
- `GET /wallet/virtual-account`
- `POST /wallet/transfer-out`
  - Verifies transaction PIN.
  - Validates Nigerian bank details.
  - Creates a Nomba bank transfer.
  - Tracks pending, success, and failed states.

## Bills and Services

- `GET /bills/service-charge`
- `POST /bills/service-charge/pay`
- `GET /bills/rent-config`
- `GET /bills/rent-details`
- `POST /bills/rent/pay`
- `GET /bills`
- `POST /bills/{assignment_id}/pay`
- `POST /services/pay`

## Resident Features

- `GET /dashboard`
- `GET /notifications`
- `GET /household`
- `GET /invites`
- `GET /vehicles`
- `GET /incidents`
  - `/incidents`: submit resident incident reports
- `GET /feed/posts`
- `GET /dm/conversations`
- `GET /public/estate-branding/{estate_id}`

## Webhooks

- `POST /webhooks/nomba`
- `POST /webhook/nomba`

Both URLs point to the same Nomba webhook handler. Use whichever one is easiest to register in the provider dashboard.

## Behavior Notes

- Pre-join users should still be able to create accounts and sign in.
- Estate-scoped routes should prompt the user to join an estate instead of assuming a missing estate is an error.
- Estate membership is resolved by code and default unit selection, not by an admin creating the user.
- Wallet setup should remain explicit: users can sign up and join an estate first, then create a Nomba virtual account when they first choose to fund their wallet.
