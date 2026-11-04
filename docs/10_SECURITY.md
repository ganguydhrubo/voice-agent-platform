# Security

## What is in place

| Area | Control | Proved by |
| --- | --- | --- |
| Passwords | Argon2. 10 to 128 characters with a letter and a number | `test_auth_and_roles.py` |
| Login limits | Account locks for 15 minutes after 5 failures; 20 tries a minute per address | `test_auth_and_roles.py` |
| Sessions | Random tokens, stored hashed. HttpOnly, SameSite=Strict, Secure in production | `test_auth_and_roles.py` |
| Roles | owner, admin, editor, viewer, checked on every writing route | `test_auth_and_roles.py` |
| Tenants | Every query names the tenant; retrieval names the knowledge bases | `test_knowledge_and_tenants.py` |
| Guest calls | A random token per conversation, stored hashed, sent in the first socket message and not in the address | `test_conversation.py` |
| Rate limits | 120 requests a minute per address | Met during `tests/e2e/admin.py`, which now waits between passes |
| Uploads | Type, size and content checks; a renamed file is refused | `test_ingestion.py` |
| Web addresses | HTTPS only; private addresses refused, and every redirect checked again, to stop server-side request forgery | `test_knowledge_and_tenants.py` |
| Web headers | CSP `script-src 'self'`, no framing, no sniffing, no referrer; HSTS in production | `test_auth_and_roles.py` |
| Origin | The socket checks the Origin header | `test_conversation.py` |
| Prompt injection | Refused before the model. Document text is marked as data. Sentence checks catch leaks | `test_guards.py`, evaluations |
| Audit log | Logins, changes and deletes, shown on the Audit Log page | Page opens in `tests/e2e/admin.py` |
| Metrics | `/metrics` only from this machine; refused when proxy headers are present | `test_conversation.py` |
| Interface docs | `/api/docs` hidden in production | Code only, no test |

## Privacy

1. Audio is never stored. The database has a check that allows only `none` for audio retention.
2. Transcripts are kept for 30 days by default. The System page changes this, and 0 keeps none.
3. A caller can delete their conversation. An admin can delete any.
4. Nothing goes to an outside service. There is no analytics or font service, and models run locally.
5. The privacy page is at `/privacy`.

## Going live

Behind a tunnel or reverse proxy, every request looks as if it came from this machine. So set:

```
VAP_ENVIRONMENT=production
VAP_TRUST_PROXY=true
VAP_PUBLIC_ORIGIN=https://your-address
```

Without `VAP_TRUST_PROXY`, rate limits would treat all callers as one. Do not set it when the server takes direct traffic, because anyone can forge those headers.

## Limits you should know

1. **There is no email service.** A password reset link is written to the server console, so an admin must hand it over.
2. **Not audited.** No outside security review has been done.
3. **Healthcare and banking law.** The product is not certified for any law. Real patient or bank data needs a legal review first.
4. **A quick tunnel link is guessable only by luck, but it is public.** Anyone with the link can call. Admin pages still need a login. Use a strong owner password.
5. **GPU, Docker and shared server setups** have not been tested for security.
6. **The word grounding check is not proof.** A small model can state something wrong using words from the document, which is why agents are limited to information work.
7. **A guest token sits in the page's memory.** A browser extension could read it.

## Reporting

Report security problems to the repository owner through a private GitHub security advisory.
