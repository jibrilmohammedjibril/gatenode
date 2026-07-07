# GateNode Client

GateNode is a resident-facing estate management platform. It gives residents a public client for onboarding, wallet funding, billing, and day-to-day estate services without requiring a private admin app.

## Overview

This repository contains the public resident client for GateNode. It provides the core workflows residents use to sign up, join an estate, fund their wallet, and interact with estate services.

## Included Features

- direct resident signup and login
- estate-code onboarding with default unit assignment
- wallet setup, KYC, bills, utility payments, and transfer-out
- invites, household membership, notifications, feed, and direct messages
- public branding and support flows

## Local development

Start the full local stack with Docker Compose:

```bash
docker compose up --build
```

The client API runs at `http://localhost:8000`.
The PostgreSQL database is available on `localhost:5440`.

## Environment

See [docs/WORKING_CONTEXT.md](docs/WORKING_CONTEXT.md) for the current runtime and integration notes.
