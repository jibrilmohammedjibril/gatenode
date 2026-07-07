# GateNode Feed Frontend Integration Guide

This document explains how the frontend should integrate with the current GateNode community feed API.

## Base Notes

- Feed routes live under the client API `feed` router.
- Feed posts, replies, likes, polls, and favorites all live here.
- Some feed endpoints require estate and unit context headers.
- Post and reply media use `mediaUrls`.

## Required Headers for Feed-Context Endpoints

The following endpoints require both of these headers:

- `X-Estate-ID`
- `X-Unit-ID`

These headers are validated against the authenticated user's linked unit and estate.

Feed-context endpoints:

- `GET /feed/posts`
- `POST /feed/posts`
- `POST /feed/posts/{post_id}/like`
- `DELETE /feed/posts/{post_id}/like`
- `POST /feed/posts/{post_id}/replies`
- `GET /feed/posts/{post_id}/replies`

If the selected unit does not belong to the logged-in user in that estate, the backend returns `403`.

## Main Endpoints

### 1. Get community feed

`GET /feed/posts?cursor=...&limit=20`

Headers:

- `X-Estate-ID`
- `X-Unit-ID`

Behavior:

- returns top-level posts only
- excludes deleted posts
- newest first
- supports pagination

Response shape:

```json
{
  "posts": [
    {
      "id": "post_id",
      "author_id": "user_id",
      "author_name": "John Doe",
      "author_avatar": "https://...",
      "author_unit": "Block A, 7",
      "content": "Good morning neighbors",
      "media_urls": [],
      "media": [],
      "created_at": "2026-03-27T10:30:00+00:00",
      "like_count": 3,
      "reply_count": 2,
      "repost_count": 0,
      "is_liked": false,
      "is_reposted": false,
      "reply_to_id": null,
      "reply_to_author": null,
      "poll": null
    }
  ],
  "next_cursor": "post_id"
}
```

Frontend usage:

- render estate feed
- keep `next_cursor` for infinite scroll
- treat `next_cursor` as opaque and send it back exactly as returned

Important:

- pagination is currently ID-based in the backend
- frontend should not try to interpret the cursor

### 2. Create a post

`POST /feed/posts`

Headers:

- `X-Estate-ID`
- `X-Unit-ID`

Request:

```json
{
  "content": "There is a water shutdown by 4pm",
  "mediaUrls": [],
  "poll": null
}
```

Post with poll:

```json
{
  "content": "What day should we hold the estate meeting?",
  "mediaUrls": [],
  "poll": {
    "options": ["Saturday", "Sunday"],
    "endAt": "2026-04-01T18:00:00Z"
  }
}
```

Rules:

- post must have at least one of:
  - content
  - media
  - poll
- poll must have 2 to 4 options

Response:

Returns the created post with zeroed counters.

Frontend usage:

- optimistic UI is fine
- reconcile with backend response after creation

## Recommended Feed Image Upload Flow

This is the important part for feed images.

### Do not upload feed images by sending the whole file through `POST /upload` unless you absolutely have to

That route sends the file through the backend server first.

It works, but it is the slower path because:

- the app uploads the file to your backend
- then the backend uploads the same file again to MinIO/S3
- the upload route uses server-side `upload_fileobj`, so the backend sits in the middle of the transfer

### Recommended path: use presigned upload

Use:

`GET /presigned-url?file_name=photo.jpg&content_type=image/jpeg&folder=feed`

This route returns:

```json
{
  "upload_url": "https://...",
  "public_url": "https://...",
  "key": "feed/uuid.jpg"
}
```

### Exact frontend flow for posting an image to feed

1. User picks an image from device
2. Frontend gets file name and MIME type
3. Frontend calls:

`GET /presigned-url?file_name={original_name}&content_type={mime_type}&folder=feed`

4. Backend returns:

- `upload_url`
- `public_url`
- `key`

5. Frontend uploads the raw file directly to `upload_url` using `PUT`

Required header for the upload request:

- `Content-Type: {same mime type used when requesting the presigned URL}`

6. If the PUT upload succeeds, frontend creates the feed post with:

```json
{
  "content": "My new update",
  "mediaUrls": ["public_url_from_step_4"]
}
```

7. Frontend then calls:

`POST /feed/posts`

with the normal feed headers:

- `X-Estate-ID`
- `X-Unit-ID`

### Example

Step 1: get presigned URL

`GET /presigned-url?file_name=estate-update.jpg&content_type=image/jpeg&folder=feed`

Step 2: upload file directly

```http
PUT {upload_url}
Content-Type: image/jpeg
```

Step 3: create feed post

```json
{
  "content": "Generator maintenance starts by 5pm",
  "mediaUrls": ["{public_url}"]
}
```

### Accepted content types for presigned upload

Currently allowed:

- `image/jpeg`
- `image/png`
- `image/gif`
- `image/webp`
- `application/pdf`

### What likely makes it feel slow

If the frontend is currently doing this:

1. call `POST /upload`
2. wait for backend to proxy the file to storage
3. then call `POST /feed/posts`

that is likely the slower path.

### Recommendation for your frontend person

For feed images:

- use `GET /presigned-url`
- upload directly with `PUT`
- then send the returned `public_url` inside `mediaUrls`

That is the correct and faster integration path for feed media.

### 3. Like a post

`POST /feed/posts/{post_id}/like`

Headers:

- `X-Estate-ID`
- `X-Unit-ID`

Response:

```json
{
  "like_count": 4
}
```

Notes:

- backend rejects duplicate likes with `400`

### 4. Unlike a post

`DELETE /feed/posts/{post_id}/like`

Headers:

- `X-Estate-ID`
- `X-Unit-ID`

Response:

```json
{
  "like_count": 3
}
```

### 5. Vote in a poll

`POST /feed/posts/{post_id}/poll/vote`

Request:

```json
{
  "optionIndex": 1
}
```

Response:

```json
{
  "success": true,
  "poll": {
    "options": ["Saturday", "Sunday"],
    "votes": [4, 5],
    "user_vote": 1,
    "end_at": "2026-04-01T18:00:00+00:00"
  }
}
```

Rules:

- only valid for poll posts
- one vote per user
- invalid option index returns `400`

Frontend usage:

- disable repeat voting after success
- persist `poll.user_vote` locally so voted state survives app reload
- patch local `poll.votes` and `poll.user_vote` from the response or refetch the post

### 6. Delete a post

`DELETE /feed/posts/{post_id}`

Behavior:

- soft deletes the post
- if it is a reply, it disappears from the parent thread and parent `replyCount` drops on the next fetch
- if it is a top-level post, its replies are also removed from feed reads
- only the post author can delete

Response:

- HTTP `204 No Content`

### 7. Get a user's posts

`GET /feed/users/{user_id}/posts?cursor=...&limit=20`

Behavior:

- returns posts for a specific user
- excludes deleted posts
- excludes replies
- supports pagination

Notes:

- this route now returns the same post shape as `GET /feed/posts`
- fields such as `mediaUrls`, `media`, `replyCount`, `likeCount`, `isLiked`, `authorName`, `authorAvatar`, and `authorUnit` are populated the same way as the main feed

Frontend usage:

- user profile timeline

### 8. Reply to a post

`POST /feed/posts/{post_id}/replies`

Headers:

- `X-Estate-ID`
- `X-Unit-ID`

Request:

```json
{
  "content": "Thanks for the update",
  "mediaUrls": [],
  "replyToAuthor": "John Doe"
}
```

Rules:

- parent post must exist
- reply must contain content or media

Response:

Returns the created reply.

Notes:

- if the reply author is different from the parent post author, backend sends a notification in the background

### 9. Get replies for a post

`GET /feed/posts/{post_id}/replies`

Headers:

- `X-Estate-ID`
- `X-Unit-ID`

Behavior:

- returns a flat array
- oldest first
- excludes deleted replies

Response shape:

```json
[
  {
    "id": "reply_id",
    "author_id": "user_id",
    "author_name": "Mary Doe",
    "author_avatar": "https://...",
    "author_unit": "Block A, 7",
    "content": "Thanks for the update",
    "media_urls": [],
    "media": [],
    "created_at": "2026-03-27T11:00:00+00:00",
    "like_count": 0,
    "reply_count": 0,
    "repost_count": 0,
    "is_liked": false,
    "is_reposted": false,
    "reply_to_id": "parent_post_id",
    "reply_to_author": "John Doe",
    "poll": null
  }
]
```

## Favorites

Favorites are separate from posts, but live under the same router.

### 10. Get favorite residents

`GET /feed/favorites`

Response:

```json
[
  {
    "id": "user_id",
    "name": "John Doe",
    "avatar": "https://...",
    "unit": "Neighbor"
  }
]
```

Important:

- current backend returns `"Neighbor"` as the unit placeholder here
- frontend should not assume this is a real house label yet

### 11. Add favorite

`POST /feed/favorites`

Request:

```json
{
  "userId": "resident_user_id"
}
```

Response:

```json
{
  "success": true
}
```

If user is already favorited:

```json
{
  "success": true,
  "message": "Already in favorites"
}
```

### 12. Remove favorite

`DELETE /feed/favorites/{fav_user_id}`

Response:

- HTTP `204 No Content`

## Feed Post Fields

The frontend should expect these fields on feed post payloads:

- `id`
- `author_id`
- `author_name`
- `author_avatar`
- `author_unit`
- `content`
- `media_urls`
- `media`
- `created_at`
- `like_count`
- `reply_count`
- `repost_count`
- `is_liked`
- `is_reposted`
- `reply_to_id`
- `reply_to_author`
- `poll`

### Poll field

When a post has a poll:

```json
{
  "poll": {
    "options": ["Saturday", "Sunday"],
    "votes": [3, 5],
    "user_vote": 1,
    "end_at": "2026-04-01T18:00:00+00:00"
  }
}
```

## Recommended Frontend Flows

### Flow 1: Main estate feed

1. Load current unit and estate context
2. Call `GET /feed/posts`
3. Render post list
4. Save `next_cursor`
5. Use `next_cursor` for infinite scroll

### Flow 2: Create a normal post

1. Compose content and optional media URLs
2. Call `POST /feed/posts`
3. Prepend the returned post into local feed state

### Flow 3: Create a poll post

1. Compose content
2. Add 2 to 4 poll options
3. Set `endAt` if the app wants a closing date
4. Call `POST /feed/posts`

### Flow 4: Open post detail

1. Show post
2. Call `GET /feed/posts/{post_id}` if fresh post detail is needed
3. Call `GET /feed/posts/{post_id}/replies`
4. Render replies oldest first
5. Let user add reply with `POST /feed/posts/{post_id}/replies`

### Flow 5: Like/unlike

1. If not liked, call `POST /feed/posts/{post_id}/like`
2. If liked, call `DELETE /feed/posts/{post_id}/like`
3. Patch `like_count` and `is_liked` locally

### Flow 6: Vote in poll

1. User taps option
2. Call `POST /feed/posts/{post_id}/poll/vote`
3. Use response `poll.user_vote` as the source of truth for selected option
4. Patch local `poll.votes` and `poll.user_vote`, or refetch `GET /feed/posts/{post_id}`

## Current Backend Limitations

- repost count is currently always `0`
- `is_reposted` is currently always `false`
- there is no repost endpoint in the current live router
- favorites currently use a placeholder unit label
- feed pagination is still ID-based, not timestamp-plus-ID

## Practical Frontend Guidance

- treat `next_cursor` as opaque
- always send `X-Estate-ID` and `X-Unit-ID` for feed-context endpoints
- do not assume favorites contain a real house label yet
- do not build repost UI as active unless backend repost support is added
- poll voting should be treated as single-shot per user

## Related Docs

- Chat integration guide: [CHAT_FRONTEND_INTEGRATION.md](/Users/jibrilmjibril/Desktop/JMJ/Projects/gatenode/client/CHAT_FRONTEND_INTEGRATION.md)
