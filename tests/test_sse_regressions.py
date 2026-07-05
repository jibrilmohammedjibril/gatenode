import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SSERegressionTests(unittest.TestCase):
    def test_client_sse_route_and_debug_endpoints_exist(self):
        source = (ROOT / "client/routes/events.py").read_text()
        self.assertIn('@router.get("/events")', source)
        self.assertIn("token: str = Query(...)", source)
        self.assertIn("return EventSourceResponse(event_generator())", source)
        self.assertIn('"event": "ping"', source)
        self.assertIn('@router.post("/events/debug/trigger")', source)
        self.assertIn('@router.post("/events/debug/trigger-wallet")', source)
        self.assertIn('@router.post("/events/debug/trigger-notification")', source)
        self.assertIn("from datetime import datetime, timezone", source)

    def test_client_sse_doc_covers_token_auth_and_chat_events(self):
        doc = (ROOT / "client/SSE_FRONTEND_INTEGRATION.md").read_text()
        self.assertIn("GET /events?token={access_token}", doc)
        self.assertIn("the client must send the current access token as a query parameter", doc)
        self.assertIn("`feed:message_new`", doc)
        self.assertIn("`feed:message_deleted`", doc)
        self.assertIn("`feed:conversation_member_left`", doc)


if __name__ == "__main__":
    unittest.main()
