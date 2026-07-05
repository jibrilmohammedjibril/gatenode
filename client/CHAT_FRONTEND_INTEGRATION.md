# ProGate Chat Frontend Note

Use `isGroup` as the source of truth.

## How to tell chat type

- if `isGroup` is `false`, it is a one-to-one chat
- if `isGroup` is `true`, it is a group chat

Do not guess from participant count.

## What frontend should show

### One-to-one chat

- show the other participant's name
- show the other participant's avatar
- ignore `groupName`

Example:

```json
{
  "id": "conversation_123",
  "participants": [
    {"id": "me", "name": "You", "avatar": null},
    {"id": "user_2", "name": "John Doe", "avatar": "https://..."}
  ],
  "isGroup": false,
  "groupName": null
}
```

### Group chat

- show `groupName` when available
- use group-style UI
- show group actions like add members or leave group

Example:

```json
{
  "id": "conversation_456",
  "participants": [
    {"id": "me", "name": "You", "avatar": null},
    {"id": "user_2", "name": "John Doe", "avatar": "https://..."},
    {"id": "user_3", "name": "Mary Doe", "avatar": "https://..."}
  ],
  "isGroup": true,
  "groupName": "House 7 Family"
}
```

## Creation rule

- send `participantId` to create a one-to-one chat
- send `participantIds` to create a group chat
- optional `groupName` is for group chats

## Group actions

Leave a group conversation:

- `POST /feed/conversations/{conversation_id}/leave`

Remove a conversation from the chat list:

- `DELETE /feed/conversations/{conversation_id}`
- removes the conversation from the authenticated user's chat list
