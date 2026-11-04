"""Log In, Log Out, password change and password reset for the admin console."""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from backend.db import later_iso, now_iso
from backend.deps import COOKIE, CurrentUser, audit, current_user, get_runtime, optional_user
from backend.runtime import Runtime
from backend.security import PASSWORD_RULE, client_ip, hash_password, hash_token, new_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("vap.auth")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL.match(value) or len(value) > 120:
        raise ValueError("Enter a valid Email ID.")
    return value


def check_password_strength(value: str) -> str:
    if not PASSWORD_RULE.match(value):
        raise ValueError("Password must be 10 to 128 characters with at least one letter and one number.")
    return value


class LoginBody(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False

    _email = field_validator("email")(check_email)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str

    _password = field_validator("new_password")(check_password_strength)


class ForgotBody(BaseModel):
    email: str = Field(max_length=120)

    _email = field_validator("email")(check_email)


class ResetBody(BaseModel):
    token: str = Field(min_length=20, max_length=120)
    new_password: str

    _password = field_validator("new_password")(check_password_strength)


def _public_user(user: CurrentUser) -> dict:
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, runtime: Runtime = Depends(get_runtime)) -> dict:
    if not runtime.login_limiter.allow(client_ip(request)):
        raise HTTPException(429, "Too many Log In attempts. Please wait a minute and try again.")
    settings = runtime.settings
    row = runtime.db.one("SELECT * FROM users WHERE email = ?", (body.email,))
    if row and row["locked_until"] and row["locked_until"] > now_iso():
        raise HTTPException(423, f"This account is locked. Try again in {settings.login_lock_minutes} minutes.")
    if not verify_password(row["password_hash"] if row else None, body.password) or not (row and row["is_active"]):
        if row:
            attempts = row["failed_logins"] + 1
            locked = later_iso(minutes=settings.login_lock_minutes) if attempts >= settings.login_attempts_before_lock else None
            runtime.db.execute(
                "UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
                (0 if locked else attempts, locked, row["id"]),
            )
            runtime.db.audit(row["tenant_id"], body.email, "login_failed", "", {}, client_ip(request))
        raise HTTPException(401, "The Email ID or password is incorrect.")

    token = new_token()
    hours = settings.remember_days * 24 if body.remember else settings.session_hours
    runtime.db.execute("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = ?", (row["id"],))
    runtime.db.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, tenant_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (hash_token(token), row["id"], row["tenant_id"], now_iso(), later_iso(hours=hours)),
    )
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=settings.public_origin.startswith("https"),
        max_age=hours * 3600 if body.remember else None,
        path="/",
    )
    user = CurrentUser(row["id"], row["tenant_id"], row["email"], row["full_name"], row["role"])
    audit(runtime, request, user, "login")
    return {"user": _public_user(user)}


@router.post("/logout")
def logout(request: Request, response: Response, runtime: Runtime = Depends(get_runtime)) -> dict:
    token = request.cookies.get(COOKIE)
    if token:
        runtime.db.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (hash_token(token),))
    response.delete_cookie(COOKIE, path="/")
    return {"message": "Logged out successfully."}


@router.get("/me")
def me(user: CurrentUser | None = Depends(optional_user)) -> dict:
    return {"user": _public_user(user) if user else None}


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    request: Request,
    user: CurrentUser = Depends(current_user),
    runtime: Runtime = Depends(get_runtime),
) -> dict:
    row = runtime.db.one("SELECT password_hash FROM users WHERE id = ?", (user.id,))
    if not verify_password(row["password_hash"], body.current_password):
        raise HTTPException(422, "Current Password is incorrect.")
    if body.new_password == body.current_password:
        raise HTTPException(422, "New Password must be different from Current Password.")
    runtime.db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.new_password), user.id))
    # Every other device must Log In again.
    runtime.db.execute(
        "DELETE FROM auth_sessions WHERE user_id = ? AND token_hash != ?",
        (user.id, hash_token(request.cookies.get(COOKIE, ""))),
    )
    audit(runtime, request, user, "password_changed")
    return {"message": "Password changed successfully."}


@router.post("/forgot-password")
def forgot_password(body: ForgotBody, request: Request, runtime: Runtime = Depends(get_runtime)) -> dict:
    if not runtime.login_limiter.allow(client_ip(request)):
        raise HTTPException(429, "Too many attempts. Please wait a minute and try again.")
    row = runtime.db.one("SELECT id, tenant_id FROM users WHERE email = ? AND is_active = 1", (body.email,))
    if row:
        token = new_token()
        runtime.db.execute(
            "INSERT INTO password_resets (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (hash_token(token), row["id"], later_iso(minutes=30)),
        )
        # A self-hosted install has no mail service by default. The server owner reads this line
        # from the console, which also proves they control the machine. See docs/15_OPERATIONS.md.
        log.warning("Password reset for %s: %s/reset-password?token=%s", body.email, runtime.settings.public_origin, token)
        runtime.db.audit(row["tenant_id"], body.email, "password_reset_requested", "", {}, client_ip(request))
    # The same reply either way, so this cannot be used to discover accounts.
    return {"message": "If this Email ID has an account, a reset link has been issued by the server."}


@router.post("/reset-password")
def reset_password(body: ResetBody, request: Request, runtime: Runtime = Depends(get_runtime)) -> dict:
    digest = hash_token(body.token)
    row = runtime.db.one(
        "SELECT user_id FROM password_resets WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
        (digest, now_iso()),
    )
    if not row:
        raise HTTPException(422, "This reset link is invalid or has expired.")
    runtime.db.execute(
        "UPDATE users SET password_hash = ?, failed_logins = 0, locked_until = NULL WHERE id = ?",
        (hash_password(body.new_password), row["user_id"]),
    )
    runtime.db.execute("UPDATE password_resets SET used_at = ? WHERE token_hash = ?", (now_iso(), digest))
    runtime.db.execute("DELETE FROM auth_sessions WHERE user_id = ?", (row["user_id"],))
    return {"message": "Password reset successfully. Please Log In."}
