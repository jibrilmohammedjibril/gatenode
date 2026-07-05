import pytest
import uuid
import secrets

pytestmark = pytest.mark.asyncio

async def test_api_register_user(async_client, test_state):
    email = f"api_test_{uuid.uuid4().hex[:6]}@example.com"
    access_code = secrets.token_hex(4).upper()
    
    # 0. The app flow implies the backend Administrator generates a resident 
    # and they receive an access_code to finish onboarding. We seed one here.
    from core.db import AsyncSessionLocal
    from core.models import User, Estate
    from sqlalchemy.future import select
    
    async with AsyncSessionLocal() as db:
        estate = (await db.execute(select(Estate).limit(1))).scalars().first()
        if not estate:
            pytest.skip("No Estate found to test against")
            
        user = User(
            email=email,
            full_name="API Tester",
            hashed_password="temp",
            estate_id=estate.id,
            access_code=access_code,
            is_active=False
        )
        db.add(user)
        await db.commit()
    
    payload = {
        "access_code": access_code,
        "password": "hashed_pass"
    }
    
    # 1. Register (Signup)
    response = await async_client.post("/auth/signup", json=payload)
    assert response.status_code == 200, f"Registration failed: {response.text}"
    
    data = response.json()
    assert "token" in data
    
    test_state["email"] = email
    test_state["password"] = "hashed_pass"
    test_state["jwt_token"] = data["token"]

async def test_api_login_user(async_client, test_state):
    # 2. Login
    payload = {
        "email": test_state["email"].upper(),
        "password": test_state["password"]
    }
    
    # Login endpoint uses JSON payload (ClientLoginV) in this API
    response = await async_client.post("/auth/login", json=payload)
    assert response.status_code == 200, f"Login failed: {response.text}"
    
    data = response.json()
    assert "access_token" in data
    assert data["full_name"] == "API Tester"
    
    # Update token
    test_state["jwt_token"] = data["access_token"]

async def test_api_get_current_user(async_client, test_state):
    # 3. Fetch Profile with Bearer token
    token = test_state.get("jwt_token")
    headers = {"Authorization": f"Bearer {token}"}
    
    response = await async_client.get("/user/profile", headers=headers)
    assert response.status_code == 200, f"User fetch failed: {response.text}"
    
    data = response.json()
    assert data["email"] == test_state["email"]

async def test_api_password_reset_normalizes_email(async_client, test_state):
    from core.db import AsyncSessionLocal
    from core.models import OTPCode
    from sqlalchemy.future import select

    uppercase_email = test_state["email"].upper()
    request_response = await async_client.post(
        "/auth/request-password-reset",
        json={"email": uppercase_email},
    )
    assert request_response.status_code == 200, f"Password reset request failed: {request_response.text}"

    async with AsyncSessionLocal() as db:
        otp = (
            await db.execute(
                select(OTPCode)
                .where(OTPCode.email == test_state["email"], OTPCode.type == "reset")
                .order_by(OTPCode.created_at.desc())
            )
        ).scalars().first()

    assert otp is not None
    assert otp.email == test_state["email"]

    new_password = "new_hashed_pass"
    reset_response = await async_client.post(
        "/auth/reset-password",
        json={"email": uppercase_email, "otp": otp.code, "new_password": new_password},
    )
    assert reset_response.status_code == 200, f"Password reset failed: {reset_response.text}"

    login_response = await async_client.post(
        "/auth/login",
        json={"email": uppercase_email, "password": new_password},
    )
    assert login_response.status_code == 200, f"Login with reset password failed: {login_response.text}"

    test_state["password"] = new_password
    test_state["jwt_token"] = login_response.json()["access_token"]
