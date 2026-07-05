import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class FeedBackendRegressionTests(unittest.TestCase):
    def test_feed_like_state_is_user_specific(self):
        source = (ROOT / "client/routes/feed.py").read_text()
        self.assertIn("async def _load_like_data(", source)
        self.assertIn("PostLike.post_id.in_(post_ids)", source)
        self.assertIn("PostLike.user_id == current_user_id", source)
        self.assertIn('"is_liked": post.id in liked_post_ids', source)

    def test_profile_feed_reuses_main_feed_serializer(self):
        source = (ROOT / "client/routes/feed.py").read_text()
        self.assertIn('@router.get("/users/{user_id}/posts", response_model=FeedListResponse, response_model_by_alias=False)', source)
        self.assertIn("context: Dict[str, Any] = Depends(require_feed_context)", source)
        self.assertIn("Post.estate_id == current_user.estate_id", source)
        self.assertIn("Post.reply_to_id == None", source)
        self.assertIn("await _serialize_posts(", source)
        self.assertIn("async def _load_reply_counts(", source)
        self.assertNotIn("enriched.append({", source)
        self.assertIn('return {"posts": enriched, "next_cursor":', source)

    def test_post_delete_cleans_related_feed_records(self):
        source = (ROOT / "client/routes/feed.py").read_text()
        self.assertIn("select(Post.id, Post.poll_id).where(Post.reply_to_id == post.id, Post.is_deleted == False)", source)
        self.assertIn("delete(PostLike).where(PostLike.post_id.in_(target_post_ids))", source)
        self.assertIn("delete(PostRepost).where(PostRepost.post_id.in_(target_post_ids))", source)
        self.assertIn("delete(PollVote).where(PollVote.poll_id.in_(target_poll_ids))", source)
        self.assertIn("delete(PollOption).where(PollOption.poll_id.in_(target_poll_ids))", source)
        self.assertIn(".values(is_deleted=True, media=[], media_urls=[])", source)

    def test_chat_delete_conversation_endpoint_exists(self):
        source = (ROOT / "client/routes/dm.py").read_text()
        self.assertIn('@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)', source)
        self.assertIn("async def delete_conversation(", source)
        self.assertIn("async def _remove_conversation_membership(", source)
        self.assertIn('raise HTTPException(status_code=404, detail="Conversation not found for this user")', source)

    def test_poll_vote_and_feed_post_include_user_vote(self):
        source = (ROOT / "client/routes/feed.py").read_text()
        schemas = (ROOT / "client/schemas.py").read_text()
        feed_doc = (ROOT / "client/FEED_FRONTEND_INTEGRATION.md").read_text()
        self.assertIn("async def _load_poll_data_map(", source)
        self.assertIn("select(PollVote.poll_id, PollVote.option_index).where(", source)
        self.assertIn('poll_payload["user_vote"] = user_votes.get(poll_id)', source)
        self.assertIn('@router.get("/posts/{post_id}", response_model=FeedPostResponse, response_model_by_alias=False)', source)
        self.assertIn('@router.post("/posts/{post_id}/poll/vote", response_model=PollVoteResponse, response_model_by_alias=False)', source)
        self.assertIn('"poll": await _build_poll_data(db, post, current_user_id=current_user.id)', source)
        self.assertIn("class PollVoteResponse", schemas)
        self.assertIn('user_vote: Optional[int] = Field(None, alias="userVote")', schemas)
        self.assertIn('"user_vote": 1', feed_doc)
        self.assertIn("GET /feed/posts/{post_id}", feed_doc)

    def test_feed_routes_batch_enrichment_queries(self):
        source = (ROOT / "client/routes/feed.py").read_text()
        self.assertIn("reply_counts = await _load_reply_counts(db, [post.id for post in posts])", source)
        self.assertIn("like_counts, liked_post_ids = await _load_like_data(", source)
        self.assertIn("author_units = await _load_post_unit_labels(db, posts)", source)
        self.assertIn("poll_payloads = await _load_poll_data_map(", source)

    def test_feed_routes_use_estate_scoped_post_lookup_and_time_cursor(self):
        source = (ROOT / "client/routes/feed.py").read_text()
        self.assertIn("async def _get_estate_post(", source)
        self.assertIn("Post.id == post_id,", source)
        self.assertIn("Post.estate_id == estate_id,", source)
        self.assertIn("def _encode_post_cursor(post: Post) -> str:", source)
        self.assertIn("def _parse_post_cursor(cursor: str) -> tuple[datetime | None, str]:", source)
        self.assertIn(".order_by(desc(Post.created_at), desc(Post.id))", source)
        self.assertIn("Post.created_at < cursor_created_at,", source)
        self.assertIn("and_(Post.created_at == cursor_created_at, Post.id < cursor_post_id)", source)

    def test_frontend_docs_reflect_feed_parity_and_chat_delete(self):
        feed_doc = (ROOT / "client/FEED_FRONTEND_INTEGRATION.md").read_text()
        chat_doc = (ROOT / "client/CHAT_FRONTEND_INTEGRATION.md").read_text()
        self.assertIn("this route now returns the same post shape as `GET /feed/posts`", feed_doc)
        self.assertNotIn("user-profile feed endpoint is simpler than main feed", feed_doc)
        self.assertIn("`DELETE /feed/conversations/{conversation_id}`", chat_doc)
        self.assertIn("removes the conversation from the authenticated user's chat list", chat_doc)


if __name__ == "__main__":
    unittest.main()
