# GateNode Client

GateNode is a residential management platform built around a public resident client for estate communities.
It supports direct signup, estate-code onboarding, wallet funding, rent and utility payments, visitor access, household features, notifications, feed, and direct messages.

## What lives here

- direct resident signup and login
- estate-code onboarding with default unit assignment
- wallet, KYC, bills, utility payments, and transfer-out
- invites, household membership, notifications, feed, and DM
- public branding and support flows

## Local development

- `docker compose up --build`
- Client API: `http://localhost:8000`
- Database: PostgreSQL on `localhost:5440`

## Environment

See [docs/WORKING_CONTEXT.md](docs/WORKING_CONTEXT.md) for the current runtime and integration notes.
