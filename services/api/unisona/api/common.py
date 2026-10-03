"""Shared API helpers: serialization, workspace-scoped fetch, generic CRUD routers."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import Base, get_db
from ..models import AuditLog
from ..security.auth import AuthContext, require_auth


def to_dict(obj: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    out = {}
    for col in obj.__table__.columns:
        if exclude and col.key in exclude:
            continue
        v = getattr(obj, col.key)
        out[col.key] = v.isoformat() if isinstance(v, datetime) else v
    return out


async def get_scoped(db: AsyncSession, model: type[Base], obj_id: str, auth: AuthContext):
    obj = await db.get(model, obj_id)
    if not obj or getattr(obj, "workspace_id", None) != auth.ws:
        raise HTTPException(404, f"{model.__name__} not found")
    return obj


async def audit(db: AsyncSession, auth: AuthContext, action: str, target: str = "", data: dict | None = None) -> None:
    db.add(AuditLog(workspace_id=auth.ws, actor=auth.email or auth.user_id, action=action, target=target, data=data or {}))


def crud_router(model: type[Base], prefix: str, *, writable: set[str], required: set[str] = frozenset(), filters: set[str] = frozenset(),
                order_by: str = "created_at", search: set[str] = frozenset(), on_create=None, on_update=None,
                min_role: str = "builder", exclude: set[str] | None = None) -> APIRouter:
    """List/get/create/update/delete for a workspace-owned model."""
    r = APIRouter(prefix=prefix)
    name = model.__name__

    @r.get("")
    async def list_(request: Request, limit: int = Query(200, le=1000), offset: int = 0, q: str | None = None,
                    auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
        stmt = select(model).where(model.workspace_id == auth.ws)
        for f in filters:
            v = request.query_params.get(f)
            if v is not None:
                stmt = stmt.where(getattr(model, f) == (v if v not in ("true", "false") else v == "true"))
        if q and search:
            from sqlalchemy import or_

            stmt = stmt.where(or_(*[getattr(model, s).ilike(f"%{q}%") for s in search]))
        total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
        col = getattr(model, order_by)
        rows = (await db.execute(stmt.order_by(col.desc() if order_by.endswith("_at") else col).limit(limit).offset(offset))).scalars().all()
        return {"items": [to_dict(x, exclude) for x in rows], "total": total}

    @r.get("/{obj_id}")
    async def get_(obj_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
        return to_dict(await get_scoped(db, model, obj_id, auth), exclude)

    @r.post("")
    async def create_(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
        auth.require(min_role)
        missing = [k for k in required if not body.get(k)]
        if missing:
            raise HTTPException(422, f"Missing: {', '.join(missing)}")
        data = {k: v for k, v in body.items() if k in writable}
        _parse_dates(model, data)
        obj = model(workspace_id=auth.ws, **data)
        db.add(obj)
        await db.flush()
        if on_create:
            await on_create(db, auth, obj)
        await audit(db, auth, f"{name.lower()}.create", obj.id)
        await db.commit()
        return to_dict(obj, exclude)

    @r.patch("/{obj_id}")
    async def update_(obj_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
        auth.require("agent" if min_role == "builder" else min_role)
        obj = await get_scoped(db, model, obj_id, auth)
        before = to_dict(obj)
        data = {k: v for k, v in body.items() if k in writable}
        _parse_dates(model, data)
        for k, v in data.items():
            setattr(obj, k, v)
        if on_update:
            await on_update(db, auth, obj, before)
        await db.commit()
        return to_dict(obj, exclude)

    @r.delete("/{obj_id}")
    async def delete_(obj_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
        auth.require(min_role)
        obj = await get_scoped(db, model, obj_id, auth)
        await db.delete(obj)
        await audit(db, auth, f"{name.lower()}.delete", obj_id)
        await db.commit()
        return {"ok": True}

    return r


def _parse_dates(model, data: dict) -> None:
    from sqlalchemy import DateTime

    for k, v in list(data.items()):
        col = model.__table__.columns.get(k)
        if col is not None and isinstance(col.type, DateTime) and isinstance(v, str):
            data[k] = datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None
