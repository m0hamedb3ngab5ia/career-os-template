"""Profile › Résumés (REQ-093, REQ-099, REQ-100): raw-body upload (DEC-006), list, versions, rename/retype,
set master, delete, the master.yaml diff from the master résumé (REQ-099: view / approve / reject), and the review
run + feedback lifecycle (REQ-094..097, FLOW-002): review on upload, apply (edit-resume run; its guarded rewrite
lands via PUT .../rewrite, 422 when the guard refuses), comment -> redraft, dismiss, hand edit = new version.
Any new master version launches extract-master (REQ-099)."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator, Literal

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from careeros import master_sync
from careeros import resume_feedback as fb
from careeros import resumes as store
from careeros.ui.routers import ctx

router = APIRouter(tags=["resumes"])

ResumeType = Literal["master", "variant", "other", "tailored"]


class Version(BaseModel):
    n: int
    author: str
    source: str
    at: str
    label: str = ""


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
    state: Literal["synced", "pending", "rejected", "stale"]
    diff: str


class Comment(BaseModel):
    text: str


class FeedbackItem(BaseModel):
    id: str
    section: str
    issue: str
    suggestion: str
    quote: str | None = None
    quotes: list[str] = []
    whole: bool = False
    kind: Literal["content", "format"] = "content"
    state: Literal["open", "redrafting", "applied", "dismissed"]
    comments: list[dict[str, str]] = []
    reason: str | None = None
    v: int
    applied_v: int | None = None


class ReviewState(BaseModel):
    state: Literal["running", "done", "failed"]
    run: str | None = None
    v: int
    at: str
    reason: str | None = None


class Feedback(BaseModel):
    review: ReviewState | None = None
    items: list[FeedbackItem]


class Started(BaseModel):
    kind: str
    run_id: str | None = None


class ResumeText(BaseModel):
    text: str


class Rewrite(ResumeText):
    base: int  # the version the rewrite was written from; not the latest -> 422


class DraftIn(BaseModel):
    rev: int  # the rev this save was based on; not the current one -> 409 (DEC-014)
    resume: dict[str, Any]
    author: Literal["user", "ai"]  # only a user write may set bullet origin "user" (DEC-018)


class Draft(BaseModel):
    rev: int
    resume: dict[str, Any]
    draft: bool  # hash(draft) != hash(latest version)


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
    except store.Conflict as e:  # revert refused: show both texts (DEC-015)
        raise HTTPException(409, {"message": str(e), "expected": e.expected, "current": e.current}) from None
    except store.Refused as e:
        raise HTTPException(409, str(e)) from None
    except (master_sync.Invalid, fb.Rejected) as e:
        raise HTTPException(422, str(e)) from None
    except ValueError as e:
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
    try:  # REQ-094: upload starts the review; if it can't start now: failed + Retry (POST .../review)
        review = _start(request, c, "review", m["rid"]).run_id
    except HTTPException as e:
        fb.set_review(c.settings.root, m["rid"], "failed", reason=str(e.detail))
        review = None
    if m["type"] == "master":  # the first résumé becomes the master -> extract-master too (REQ-099)
        _extract_master(request, c)
    return Uploaded(rid=m["rid"], n=1, review_run=review)


@router.get("/profile/resumes")
def list_resumes(c=Depends(ctx)) -> Resumes:
    return Resumes(resumes=[ResumeRow(**r) for r in store.list_resumes(c.settings.root)])


@router.get("/profile/resumes/{rid}")
def get_resume(rid: str, c=Depends(ctx)) -> Resume:
    with _refusals():
        return Resume(**store.get(c.settings.root, rid))


def _extract_master(request: Request, c: Any) -> None:
    """REQ-099: a new master -> launch the extract-master skill run. Best effort: if it can't start (busy, paused),
    master_sync.state() is `stale`, so readiness `master_synced` stays open until a proposal is approved."""
    from careeros.ui.services.runs import RunControl

    try:
        (getattr(request.app.state, "run_control", None) or RunControl)(c.settings).start_step("extract_master")
    except Exception as e:  # noqa: BLE001 - never fail set-master on the follow-up run; but say why it didn't start
        logging.getLogger(__name__).warning("extract_master run not started: %s", e)


def _start(request: Request, c: Any, kind: str, rid: str, item: str | None = None) -> Started:
    from careeros.ui.services.runs import RunControl

    try:
        out = (getattr(request.app.state, "run_control", None) or RunControl)(c.settings).start_step(
            kind, resume=rid, item=item)
    except Exception as e:  # noqa: BLE001 - busy, paused, claude missing: a commented item goes back to open
        if item:
            fb.reopen(c.settings.root, rid, item, f"re-draft not started: {e}")
        raise HTTPException(422 if isinstance(e, ValueError) else 409, f"{kind} run not started: {e}") from None
    return Started(kind=kind, run_id=(out or {}).get("run_id"))


def _new_version(request: Request, c: Any, meta: dict[str, Any]) -> Resume:
    if meta["type"] == "master":  # REQ-099: each new master version -> extract-master
        _extract_master(request, c)
    return Resume(**meta)


@router.post("/profile/resumes/{rid}/review", status_code=202)
def start_review(rid: str, request: Request, c=Depends(ctx)) -> Started:
    with _refusals():
        store.get(c.settings.root, rid)
    try:
        return _start(request, c, "review", rid)
    except HTTPException as e:
        fb.set_review(c.settings.root, rid, "failed", reason=str(e.detail))
        raise


@router.get("/profile/resumes/{rid}/file", response_class=FileResponse)
def resume_file(rid: str, v: int | None = None, download: bool = False, c=Depends(ctx)):
    """A version's file (default the latest), inline (UI "View") or as a download named 01_Name_Original.pdf."""
    with _refusals():
        n = v or store.get(c.settings.root, rid)["versions"][-1]["n"]
        path, name = store.download_name(c.settings.root, rid, n)
    return FileResponse(path, filename=name, content_disposition_type="attachment" if download else "inline")


@router.get("/profile/resumes/{rid}/feedback")
def get_feedback(rid: str, c=Depends(ctx)) -> Feedback:
    with _refusals():
        return Feedback(**fb.load(c.settings.root, rid))


@router.post("/profile/resumes/{rid}/feedback/{fid}/apply", status_code=202)
def apply_feedback(rid: str, fid: str, request: Request, c=Depends(ctx)) -> Started:
    with _refusals():
        it = next((i for i in fb.load(c.settings.root, rid)["items"] if i["id"] == fid), None)
        if it is None or it["state"] != "open":
            raise HTTPException(404 if it is None else 409, f"feedback item {fid} is " + (it["state"] if it else "unknown"))
    return _start(request, c, "resume_edit", rid, fid)


@router.put("/profile/resumes/{rid}/feedback/{fid}/rewrite")
def rewrite_feedback(rid: str, fid: str, body: Rewrite, request: Request, c=Depends(ctx)) -> Resume:
    """The edit-resume skill's rewrite: zero-fabrication guard, 422 with the reasons if refused (REQ-095)."""
    with _refusals():
        meta = fb.apply(c.settings.root, rid, fid, body.text, base=body.base)
    return _new_version(request, c, meta)


@router.post("/profile/resumes/{rid}/feedback/{fid}/comment", status_code=202)
def comment_feedback(rid: str, fid: str, body: Comment, request: Request, c=Depends(ctx)) -> Started:
    with _refusals():
        fb.comment(c.settings.root, rid, fid, body.text)
    return _start(request, c, "resume_edit", rid, fid)


@router.post("/profile/resumes/{rid}/feedback/{fid}/dismiss")
def dismiss_feedback(rid: str, fid: str, c=Depends(ctx)) -> FeedbackItem:
    with _refusals():
        return FeedbackItem(**fb.dismiss(c.settings.root, rid, fid))


@router.put("/profile/resumes/{rid}/text")
def edit_resume(rid: str, body: ResumeText, request: Request, c=Depends(ctx)) -> Resume:
    """REQ-097: hand edit -> new version author=user, no guard."""
    with _refusals():
        meta = fb.edit(c.settings.root, rid, body.text)
    return _new_version(request, c, meta)


@router.get("/profile/resumes/{rid}/draft")
def get_draft(rid: str, c=Depends(ctx)) -> Draft:
    with _refusals():
        return Draft(**store.get_draft(c.settings.root, rid))


@router.put("/profile/resumes/{rid}/draft")
def put_draft(rid: str, body: DraftIn, c=Depends(ctx)) -> Draft:
    """Autosave (DEC-014): stale `rev` -> 409 (reload); AI write setting origin -> 422."""
    with _refusals():
        return Draft(**store.put_draft(c.settings.root, rid, body.resume, rev=body.rev, author=body.author))


@router.get("/profile/resumes/{rid}/draft/changes")
def draft_changes(rid: str, c=Depends(ctx)) -> list[dict[str, Any]]:
    """History (DEC-015): draft.changes.jsonl, oldest first."""
    with _refusals():
        return store.changes(c.settings.root, rid)


@router.post("/profile/resumes/{rid}/draft/changes/{cid}/revert")
def revert_change(rid: str, cid: str, c=Depends(ctx)) -> Draft:
    """Inverse change author=user; target no longer holds the change's `after` -> 409 {expected, current}."""
    with _refusals():
        return Draft(**store.revert_change(c.settings.root, rid, cid))


@router.patch("/profile/resumes/{rid}")
def patch_resume(rid: str, body: ResumePatch, request: Request, c=Depends(ctx)) -> Resume:
    with _refusals():
        was = store.get(c.settings.root, rid)["type"]
        out = Resume(**store.update(c.settings.root, rid, name=body.name, type=body.type))
    if body.type == "master" and was != "master":
        _extract_master(request, c)
    return out


@router.post("/profile/resumes/{rid}/master")
def set_master(rid: str, request: Request, c=Depends(ctx)) -> Resume:
    with _refusals():
        was = store.get(c.settings.root, rid)["type"]
        out = Resume(**store.update(c.settings.root, rid, type="master"))
    if was != "master":
        _extract_master(request, c)
    return out


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


@router.post("/profile/master/proposal/refresh", status_code=202)
def refresh_master_proposal(request: Request, c=Depends(ctx)) -> Started:
    """Re-run extract-master when the last run failed or never started (UI "Re-read")."""
    return _start(request, c, "extract_master", None)  # type: ignore[arg-type]


@router.post("/profile/master/proposal/approve")
def approve_master_proposal(c=Depends(ctx)) -> MasterProposal:
    with _refusals():
        return MasterProposal(**master_sync.approve(c.settings.root))


@router.post("/profile/master/proposal/reject")
def reject_master_proposal(c=Depends(ctx)) -> MasterProposal:
    with _refusals():
        return MasterProposal(**master_sync.reject(c.settings.root))
