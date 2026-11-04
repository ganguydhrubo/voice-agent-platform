# API

Generated from the running application by `scripts/export_api_docs.py`.
In development mode the same detail is at `/api/docs`.

Admin routes need a logged-in user. Writing routes also need a role that allows the action.

## HTTP routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/admin/agents` | List Agents |
| POST | `/api/admin/agents` | Create Agent |
| GET | `/api/admin/agents/{agent_id}` | Get Agent |
| PUT | `/api/admin/agents/{agent_id}` | Update Agent |
| DELETE | `/api/admin/agents/{agent_id}` | Delete Agent |
| POST | `/api/admin/agents/{agent_id}/evaluate` | Evaluate Agent |
| POST | `/api/admin/agents/{agent_id}/publish` | Publish Agent |
| GET | `/api/admin/audit-log` | Audit Log |
| GET | `/api/admin/conversations` | List Conversations |
| GET | `/api/admin/conversations/{conversation_id}` | Get Conversation |
| DELETE | `/api/admin/conversations/{conversation_id}` | Delete Conversation |
| DELETE | `/api/admin/documents/{document_id}` | Delete Document |
| GET | `/api/admin/escalations` | List Escalations |
| POST | `/api/admin/escalations/{escalation_id}/close` | Close Escalation |
| GET | `/api/admin/knowledge-bases` | List Bases |
| POST | `/api/admin/knowledge-bases` | Create Base |
| DELETE | `/api/admin/knowledge-bases/{kb_id}` | Delete Base |
| GET | `/api/admin/knowledge-bases/{kb_id}/documents` | List Documents |
| POST | `/api/admin/knowledge-bases/{kb_id}/documents` | Upload Document |
| POST | `/api/admin/knowledge-bases/{kb_id}/faqs` | Add Faq |
| POST | `/api/admin/knowledge-bases/{kb_id}/search` | Test Search |
| POST | `/api/admin/knowledge-bases/{kb_id}/urls` | Add Url |
| GET | `/api/admin/latency` | Latency |
| GET | `/api/admin/overview` | Overview |
| GET | `/api/admin/settings` | Get Settings |
| PUT | `/api/admin/settings` | Update Settings |
| GET | `/api/admin/system` | System |
| GET | `/api/admin/users` | List Users |
| POST | `/api/admin/users` | Create User |
| PUT | `/api/admin/users/{user_id}` | Update User |
| DELETE | `/api/admin/users/{user_id}` | Delete User |
| POST | `/api/auth/change-password` | Change Password |
| POST | `/api/auth/forgot-password` | Forgot Password |
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/auth/me` | Me |
| POST | `/api/auth/reset-password` | Reset Password |
| GET | `/api/health` | Health |
| GET | `/api/public/agents` | List Agents |
| POST | `/api/public/conversations` | Start Conversation |
| DELETE | `/api/public/conversations/{conversation_id}` | Delete Conversation |
| GET | `/api/public/conversations/{conversation_id}/messages` | Conversation Messages |
| GET | `/api/ready` | Ready |

## Voice WebSocket: `/ws/voice`

The browser opens this socket after `POST /api/conversations` has given it a conversation `id` and `token`.

The browser sends one JSON message first:

```json
{"type": "start", "id": "<conversation id>", "token": "<token>", "mode": "voice", "resume": false}
```

After that the browser sends binary frames of 16 kHz, mono, 16-bit PCM, 20 ms each, and these JSON messages:

| Message | Meaning |
| --- | --- |
| `{"type": "text", "text": "..."}` | A typed question. |
| `{"type": "interrupt"}` | The caller pressed Interrupt. |
| `{"type": "playback", "turn": 3, "played_ms": 1200, "finished": false}` | How much of the reply has reached the speaker. Sent every 250 ms. |
| `{"type": "audible", "turn": 3, "after_speech_end_ms": 2100}` | The moment the first sound of a reply was heard. |
| `{"type": "language", "language": "hi"}` | Change language. |
| `{"type": "voice", "voice": "hi-rohan"}` | Change voice. |
| `{"type": "mode", "mode": "text"}` | Change between voice and text. |
| `{"type": "end"}` | End the conversation. |

The server sends JSON messages and binary audio.

| Message | Meaning |
| --- | --- |
| `ready` | The session is ready. |
| `state` | `listening`, `thinking`, `speaking` and so on. |
| `level` | Speech probability for the waveform. |
| `speech_start`, `speech_end` | The caller began or stopped talking. |
| `partial` | Live words while the caller talks. |
| `final` | The finished transcript of the turn. |
| `agent_start`, `agent_text`, `sources`, `turn_end` | The reply, its sources and its timings. |
| `flush` | Stop playing the named turn now. |
| `escalation` | A person is needed. Has a severity. |
| `notice` | A safe approved reply replaced the model's text, with the reason. |
| `language`, `voice`, `mode` | The setting changed. |
| `error`, `ended` | The reason for a stop. |

Each binary audio frame has a 12-byte header of three little-endian 32-bit numbers (turn, chunk index, sample rate), then 16-bit PCM.

Close codes: `4401` bad token, `4403` not allowed, `4503` all lines busy.
