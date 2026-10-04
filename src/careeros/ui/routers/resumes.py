"""Profile › Résumés (REQ-093, REQ-099, REQ-100): raw-body upload (DEC-006), list, versions, rename/retype,
set master, delete, and the master.yaml diff from the master résumé (REQ-099: view / approve / reject).
Review runs (REQ-094) come with a later task."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Literal

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from careeros import master_sync
from careeros import resumes as store
from careeros.ui.routers import ctx

router = APIRouter(tags=["resumes"])

ResumeType = Literal["master", "variant", "other", "tailored"]


class Version(BaseModel):
    n: int
    author: str
    source: str
    at: str


class Resume(BaseModel):
    rid: str
    name: str
    type: ResumeType
    category: str | None = None
    versions: list[Version]


class ResumeRow(BaseModel):
    rid: str
    name: str
    type: ResumeType
    category: str | None = None
    latest: int
    at: str


class Resumes(BaseModel):
    resumes: list[ResumeRow]


class Uploaded(BaseModel):
    rid: str
    n: int
    review_run: str | None = None


class VersionDetail(Version):
    rid: str
    text: str
    ats: dict[str, Any]


class MasterProposal(BaseModel):
    state: Literal["synced", "pending", "rejected"]
    diff: str


class ResumePatch(BaseModel):
    name: str | None = None
    type: ResumeType | None = None


@contextmanager
def _refusals() -> Iterator[None]:
    try:
        yield
    except LookupError as e:
        raise HTTPException(404, str(e).strip("'\"")) from None
    except store.TooLarge as e:
        raise HTTPException(413, str(e)) from None
    except store.BadType as e:
        raise HTTPException(415, str(e)) from None
    except store.Refused as e:
        raise HTTPException(409, str(e)) from None
    except master_sync.Invalid as e:
        raise HTTPException(422, str(e)) from None


_RAW = {"requestBody": {"required": True, "content": {"application/octet-stream": {
    "schema": {"type": "string", "format": "binary"}}}}}


@router.put("/profile/resumes", status_code=201, openapi_extra=_RAW)
async def upload(request: Request, filename: str, name: str | None = None, c=Depends(ctx)) -> Uploaded:
    if int(request.headers.get("content-length") or 0) > store.MAX_BYTES:
        raise HTTPException(413, f"{filename}: larger than {store.MAX_BYTES // (1024 * 1024)} MB")
    data = bytearray()
    async for chunk in request.stream():  # streamed cap: never buffer more than MAX_BYTES + one chunk
        data += chunk
        if len(data) > store.MAX_BYTES:
            raise HTTPException(413, f"{filename}: larger than {store.MAX_BYTES // (1024 * 1024)} MB")
    with _refusals():
        m = await anyio.to_thread.run_sync(lambda: store.add(c.settings.root, filename, bytes(data), name=name))
    return Uploaded(rid=m["rid"], n=1)


@router.get("/profile/resumes")
def list_resumes(c=Depends(ctx)) -> Resumes:
    return Resumes(resumes=[ResumeRow(**r) for r in store.list_resumes(c.settings.root)])


@router.get("/profile/resumes/{rid}")
def get_resume(rid: str, c=Depends(ctx)) -> Resume:
    with _refusals():
        return Resume(**store.get(c.settings.root, rid))


@router.patch("/profile/resumes/{rid}")
def patch_resume(rid: str, body: ResumePatch, c=Depends(ctx)) -> Resume:
    with _refusals():
        return Resume(**store.update(c.settings.root, rid, name=body.name, type=body.type))


@router.post("/profile/resumes/{rid}/master")
def set_master(rid: str, c=Depends(ctx)) -> Resume:
    with _refusals():
        return Resume(**store.update(c.settings.root, rid, type="master"))


@router.delete("/profile/resumes/{rid}", status_code=204)
def delete_resume(rid: str, c=Depends(ctx)) -> Response:
    with _refusals():
        store.delete(c.settings.root, rid)
    return Response(status_code=204)


@router.get("/profile/resumes/{rid}/versions/{n}")
def get_version(rid: str, n: int, c=Depends(ctx)) -> VersionDetail:
    with _refusals():
        return VersionDetail(**store.version(c.settings.root, rid, n))


@router.delete("/profile/resumes/{rid}/versions/{n}")
def delete_version(rid: str, n: int, c=Depends(ctx)) -> Resume:
    with _refusals():
        return Resume(**store.delete_version(c.settings.root, rid, n))


@router.get("/profile/master/proposal")
def get_master_proposal(c=Depends(ctx)) -> MasterProposal:
    return MasterProposal(**master_sync.state(c.settings.root))


@router.post("/profile/master/proposal/approve")
def approve_master_proposal(c=Depends(ctx)) -> MasterProposal:
    with _refusals():
        return MasterProposal(**master_sync.approve(c.settings.root))


@router.post("/profile/master/proposal/reject")
def reject_master_proposal(c=Depends(ctx)) -> MasterProposal:
    with _refusals():
        return MasterProposal(**master_sync.reject(c.settings.root))
