"""Request helpers: the runtime, the signed-in user, role checks and list paging."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Query, Request

from backend.db import now_iso
from backend.runtime import Runtime
from backend.security import client_ip, hash_token

COOKIE = "vap_session"
ROLE_ORDER = {"viewer": 0, "editor": 1, "admin": 2, "owner": 3}
PAGE_SIZES = (10, 20, 50, 100)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    tenant_id: str
    email: str
    full_name: str
    role: str

    def can(self, role: str) -> bool:
        return ROLE_ORDER[self.role] >= ROLE_ORDER[role]


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def current_user(request: Request, runtime: Runtime = Depends(get_runtime)) -> CurrentUser:
    token = request.cookies.get(COOKIE)
    if token:
        row = runtime.db.one(
            "SELECT u.id, u.tenant_id, u.email, u.full_name, u.role, s.expires_at FROM auth_sessions s"
            " JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND u.is_active = 1",
            (hash_token(token),),
        )
        if row and row["expires_at"] > now_iso():
            return CurrentUser(row["id"], row["tenant_id"], row["email"], row["full_name"], row["role"])
    raise HTTPException(401, "Please Log In to continue.")


def optional_user(request: Request, runtime: Runtime = Depends(get_runtime)) -> CurrentUser | None:
    """The signed-in user, or nobody. Visitors are normal on public pages, so this is not an error."""
    try:
        return current_user(request, runtime)
    except HTTPException:
        return None


def require(role: str):
    def check(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not user.can(role):
            raise HTTPException(403, "You do not have permission to do this.")
        return user

    return check


@dataclass(frozen=True)
class Page:
    page: int
    size: int
    search: str

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    @property
    def like(self) -> str:
        escaped = self.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"


def paging(
    page: int = Query(1, ge=1, le=100000),
    size: int = Query(10),
    search: str = Query("", max_length=120),
) -> Page:
    if size not in PAGE_SIZES:
        raise HTTPException(422, "Records per page must be 10, 20, 50 or 100.")
    return Page(page, size, search.strip())


def paged(items: list[dict], total: int, page: Page) -> dict:
    """Count and rows always travel together, so a table's total cannot disagree with its rows."""
    return {"items": items, "total": total, "page": page.page, "size": page.size}


def audit(runtime: Runtime, request: Request, user: CurrentUser | None, action: str, target: str = "", detail: dict | None = None) -> None:
    runtime.db.audit(user.tenant_id if user else None, user.email if user else "guest", action, target, detail or {}, client_ip(request))
