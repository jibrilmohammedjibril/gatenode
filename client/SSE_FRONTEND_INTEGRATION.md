# ProGate Client SSE Frontend Integration

## Overview

The client app uses Server-Sent Events for real-time updates.

SSE endpoint:

`GET /events?token={access_token}`

Important:

- SSE does not use the normal `Authorization` header in this backend
- the client must send the current access token as a query parameter
- when the access token changes, close the old SSE connection and open a new one with the new token

## Connection Rule

Connect after login.

Close the stream on logout.

Reconnect when:

- app comes back online
- app returns to foreground if your app lifecycle requires it
- token is refreshed and the access token changes

## JavaScript Example

```javascript
const eventSource = new EventSource(
  `${API_BASE_URL}/events?token=${accessToken}`
);

eventSource.onopen = () => {
  console.log("SSE connected");
};

eventSource.onerror = (error) => {
  console.log("SSE error", error);
};

eventSource.addEventListener("ping", (event) => {
  const data = JSON.parse(event.data);
  console.log("heartbeat", data.timestamp);
});
```

## Heartbeat

If there is no user event, the backend sends:

- event: `ping`

Payload:

```json
{
  "timestamp": "2026-03-28T12:00:00.000000"
}
```

You can ignore this event or use it to detect a live connection.

## Real Event Types

### 1. Wallet balance updated

Event:

`wallet:balance_updated`

Payload shape:

```json
{
  "new_balance": 5000,
  "old_balance": 5200,
  "change_amount": 200,
  "change_type": "debit",
  "timestamp": "2026-03-28T12:00:00+00:00"
}
```

Notes:

- `old_balance` may be missing on some paths
- update wallet UI from `new_balance`

### 2. Wallet transaction created

Event:

`wallet:transaction_created`

Payload:

```json
{
  "transaction_id": "txn_id",
  "amount": 200,
  "type": "debit",
  "description": "Rent Payment",
  "timestamp": "2026-03-28T12:00:00+00:00"
}
```

### 3. Notification

Event:

`notification`

Payload:

```json
{
  "title": "Test Notification",
  "message": "This is a notification."
}
```

Use this for in-app banners, toast, or notification center refresh.

### 4. Emergency alert

Event:

`alert:triggered`

Payload:

```json
{
  "alert_id": "alert_id",
  "unit_id": "unit_id",
  "triggered_by": "user_id",
  "location": {
    "lat": 0.0,
    "lng": 0.0
  },
  "timestamp": "2026-03-28T12:00:00+00:00"
}
```

### 5. Visitor arrived

Event:

`visitor:invite_used`

Payload:

```json
{
  "invite_id": "invite_id",
  "visitor_name": "Vendor Name",
  "access_code": "123456",
  "status": "arrived",
  "timestamp": "2026-03-28T12:00:00+00:00"
}
```

### 6. Household member removed

Event:

`household:member_removed`

Payload:

```json
{
  "removed_user_id": "user_id",
  "full_name": "John Doe",
  "timestamp": "2026-03-28T12:00:00+00:00"
}
```

### 7. New chat message

Event:

`feed:message_new`

Payload:

```json
{
  "id": "message_id",
  "fromId": "user_id",
  "fromName": "John Doe",
  "text": "Hello",
  "createdAt": "2026-03-28T12:00:00+00:00",
  "mediaUrls": [],
  "readAt": null,
  "conversationId": "conversation_id"
}
```

Frontend behavior:

- append message if that conversation is open
- otherwise update conversation preview and unread state

### 8. Chat message deleted

Event:

`feed:message_deleted`

Payload:

```json
{
  "conversationId": "conversation_id",
  "messageId": "message_id"
}
```

### 9. Group member left conversation

Event:

`feed:conversation_member_left`

Payload:

```json
{
  "conversationId": "conversation_id",
  "userId": "user_id",
  "userName": "John Doe"
}
```

### 10. Debug test event

Event:

`debug:test`

Payload:

```json
{
  "message": "Hello World",
  "timestamp": "2026-03-28T12:00:00+00:00"
}
```

## Debug Endpoints

These are useful for manual frontend testing after login.

### `POST /events/debug/trigger`

Emits:

- `debug:test`

### `POST /events/debug/trigger-wallet`

Emits:

- `wallet:balance_updated`

### `POST /events/debug/trigger-notification`

Emits:

- `notification`

## Frontend Recommendations

- keep exactly one SSE connection per logged-in user session
- reconnect with a new URL when token changes
- handle `ping` silently
- parse `event.data` as JSON
- do not assume every event has the same payload shape
- route events by `event.type`

## Practical Event Routing

Suggested app handling:

- `wallet:balance_updated` -> refresh wallet balance state
- `wallet:transaction_created` -> prepend transaction list item
- `notification` -> show in-app notification UI
- `alert:triggered` -> show emergency state or alert screen update
- `visitor:invite_used` -> refresh visitor/invite screen
- `household:member_removed` -> refresh household members
- `feed:message_new` -> update DM state
- `feed:message_deleted` -> remove deleted message locally
- `feed:conversation_member_left` -> update group metadata or participant list
