import httpx

from core.whatsapp import _format_whatsapp_error
from schemas import InviteExtendRequest


def test_invite_extend_request_accepts_camel_and_snake_case_valid_until():
    camel_case = InviteExtendRequest.model_validate({"validUntil": "2026-04-03T18:00:00Z"})
    snake_case = InviteExtendRequest.model_validate({"valid_until": "2026-04-03T18:00:00Z"})

    assert camel_case.valid_until == "2026-04-03T18:00:00Z"
    assert snake_case.valid_until == "2026-04-03T18:00:00Z"


def test_invite_extend_request_accepts_camel_and_snake_case_valid_hours():
    camel_case = InviteExtendRequest.model_validate({"validHours": 4})
    snake_case = InviteExtendRequest.model_validate({"valid_hours": 4})

    assert camel_case.valid_hours == 4
    assert snake_case.valid_hours == 4


def test_format_whatsapp_error_highlights_expired_token():
    response = httpx.Response(
        401,
        json={
            "error": {
                "message": (
                    "Error validating access token: Session has expired on Wednesday, "
                    "18-Mar-26 09:00:00 PDT. The current time is Friday, 03-Apr-26 10:25:15 PDT."
                ),
                "type": "OAuthException",
                "code": 190,
                "error_subcode": 463,
            }
        },
    )

    message = _format_whatsapp_error(response)

    assert "Meta access token expired" in message
    assert "WHATSAPP_API_TOKEN" in message
