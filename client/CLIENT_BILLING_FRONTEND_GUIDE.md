# Client Billing Frontend Guide

## Current billing surfaces

- service charge summary
- rent summary and rent payment
- estate bill summary and bill payment
- utility payment
- wallet transfer-out

## Current flow

1. User signs up directly with email/password.
2. User joins an estate with an estate code.
3. The client app resolves the default unit from that code.
4. Billing routes use the resident's estate membership and household role.
5. Wallet payments and transfer-out use the resident PIN and Nomba-backed wallet services.

## Transfer-out

- Collect bank name, bank code, account number, account name, amount, and transaction PIN.
- Submit to `POST /wallet/transfer-out`.
- Show `pending`, `success`, and `failed` states from the API response and transaction history.

## UI guidance

- Show a clear "Join an estate" call to action when estate membership is missing.
- Do not block account creation behind estate assignment.
- Keep wallet and utility entry points available after signup, but gate estate-specific views behind membership.
