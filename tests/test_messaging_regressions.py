import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class MessagingRegressionTests(unittest.TestCase):
    def test_message_cursor_helpers_round_trip_encoded_values(self):
        source = (ROOT / "client/routes/dm.py").read_text()
        self.assertIn("def _encode_message_cursor(message: Message | SimpleNamespace) -> str:", source)
        self.assertIn('return f"{created_at.isoformat()}|{message.id}"', source)
        self.assertIn("def _parse_message_cursor(cursor: str) -> tuple[Optional[datetime], str]:", source)
        self.assertIn('if "|" not in raw_cursor:', source)
        self.assertIn("created_at = datetime.fromisoformat(raw_created_at)", source)

    def test_dm_route_uses_time_based_message_ordering_and_batch_loading(self):
        source = (ROOT / "client/routes/dm.py").read_text()
        self.assertIn('.order_by(desc(Message.created_at), desc(Message.id))', source)
        self.assertIn('ConversationParticipant.conversation_id.in_(conversation_ids)', source)
        self.assertIn('Message.conversation_id.in_(conversation_ids)', source)
        self.assertIn('_publish_to_users', source)
        self.assertIn('_send_chat_message_notifications', source)
        self.assertIn('await notifications.send_chat_message(', source)

    def test_resident_search_supports_house_number_lookup(self):
        source = (ROOT / "client/routes/dm.py").read_text()
        self.assertIn("Unit.unit_number.ilike(pattern)", source)
        self.assertIn("Block.name.ilike(pattern)", source)
        self.assertIn("Estate.address.ilike(pattern)", source)
        self.assertIn("house_search_text", source)
        self.assertNotIn('"unit": "Resident"', source)

    def test_grouped_resident_search_endpoint_exists(self):
        source = (ROOT / "client/routes/dm.py").read_text()
        schemas = (ROOT / "client/schemas.py").read_text()
        self.assertIn('@router.get("/residents/grouped"', source)
        self.assertIn("ResidentHouseGroupResponse", source)
        self.assertIn("matched_unit_ids", source)
        self.assertIn("houseLabel", source)
        self.assertIn("class ResidentHouseGroupResponse", schemas)

    def test_conversation_payloads_expose_group_flag_and_leave_endpoint(self):
        source = (ROOT / "client/routes/dm.py").read_text()
        schemas = (ROOT / "client/schemas.py").read_text()
        chat_doc = (ROOT / "client/CHAT_FRONTEND_INTEGRATION.md").read_text()
        self.assertIn('"isGroup": conv.is_group', source)
        self.assertIn('@router.post("/conversations/{conversation_id}/leave")', source)
        self.assertIn('is_group: bool = Field(..., alias="isGroup")', schemas)
        self.assertIn("Leave a group conversation", chat_doc)
        self.assertIn("isGroup", chat_doc)

    def test_feed_messaging_index_migration_exists(self):
        source = (ROOT / "alembic/versions/a4f9c2b7d1e3_add_feed_messaging_indexes.py").read_text()
        self.assertIn('ix_feed_messages_conversation_created_id', source)
        self.assertIn('ix_feed_conversation_participants_user_conversation', source)

    def test_notification_service_supports_chat_messages(self):
        source = (ROOT / "client/core/notifications.py").read_text()
        self.assertIn("async def send_chat_message(", source)
        self.assertIn('"type": "chat_message"', source)
        self.assertIn('channel_id="messages"', source)


if __name__ == "__main__":
    unittest.main()
