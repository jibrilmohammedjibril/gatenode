# ProGate Working Context

This is the living reference for the public client app. Update it whenever a route, model, integration, or workflow changes.

## Purpose

Use this docs set to:

- keep stable context while making changes
- avoid deleting endpoints or models accidentally
- track cross-feature dependencies before refactors
- record the intended role of the client app

## Service Map

- Client service: resident-facing product with direct signup, estate-code onboarding, household membership, wallet, KYC, billing, invites, vehicles, support, feed, DM, notifications, and public branding

Detailed references:

- [Client Service](./apps/client-service.md)

## Shared Architecture Notes

- Stack: FastAPI + async SQLAlchemy + PostgreSQL + Alembic
- Repo shape: one public client app with `main.py`, `core/`, `routes/`, and `schemas.py`
- Data model strategy: shared resident, estate, unit, wallet, billing, and notification models inside the client service
- Realtime: SSE/event endpoints power wallet, feed, messaging, and resident activity updates
- Payments: Nomba wallet funding, Nomba transfer-out, utility payments, wallet history, transactions
- Notifications: persisted notifications plus push delivery through FCM/APNs

## Required Environment Variables

Minimum required secrets and service credentials should come from environment, not code defaults:

- `SECRET_KEY`
- `DATABASE_URL` or the `POSTGRES_*` settings
- `ZEPTOMAIL_API_KEY` if email delivery is enabled
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `NOMBA_CLIENT_ID`
- `NOMBA_CLIENT_SECRET`
- `NOMBA_ACCOUNT_ID`
- `FIREBASE_CREDENTIALS` for FCM push delivery
- `APPLE_TEAM_ID`, `APPLE_KEY_ID`, and `APPLE_P8_PATH` or `APPLE_P8_KEY` for APNs

## Core Contracts

- `User`, `Estate`, `Block`, `Unit`, `UserUnit`, `VisitorInvite`, `Bill`, `BillAssignment`, `Transaction`, `WalletProfile`, and `Notification` are the main resident-facing business concepts.
- Users can sign up directly without an admin-issued access code.
- Estate membership is assigned later by joining with an estate code that also selects the default unit.
- Wallet transfers are bank-transfer only in v1 and use Nomba.
- Pre-join state should be explicit so the UI can prompt users to join an estate instead of failing silently.

## Canonical Reference Docs

- [README.md](../README.md)
- [client/CLIENT_API_DOCUMENTATION.md](../client/CLIENT_API_DOCUMENTATION.md)
- [client/CLIENT_BILLING_FRONTEND_GUIDE.md](../client/CLIENT_BILLING_FRONTEND_GUIDE.md)
- [docs/apps/client-service.md](./apps/client-service.md)
- [REALTIME_EVENTS_DOCUMENTATION.md](../REALTIME_EVENTS_DOCUMENTATION.md)

## Change Rules

- Before removing a route, check whether it is referenced by another route, webhook flow, or markdown doc.
- Before changing a shared model field, compare the related client routes, schemas, and migrations.
- Before changing a payment flow, check wallet history, transactions, notifications, webhooks, and transfer-reference handling together.
- Before changing auth or session handling, check device tokens and push-delivery filtering.
- Keep this docs set updated in the same change when possible.

## Route / Model Mutation Guard

Before deleting or renaming anything, do this quick pass:

- search the repo for route path usage, schema usage, and helper usage
- check markdown docs for references that will become stale
- check webhook and scheduled-job paths for indirect use
- update the relevant service doc in this folder in the same change
