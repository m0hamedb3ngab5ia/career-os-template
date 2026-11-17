from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from careeros import resumes

from careeros.ui.routers import ctx
from careeros.ui.services import profile_view as svc

router = APIRouter(tags=["profile"])


@router.get("/profile")
def get_profile(c=Depends(ctx)) -> svc.Profile:
    return svc.profile(c.settings)


@router.get("/settings")
def get_settings(c=Depends(ctx)) -> svc.SettingsView:
    return svc.settings_view(c.settings)


@router.get("/profile/master.pdf", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def master_pdf(c=Depends(ctx)) -> Response:
    """The master résumé's latest version, inline, for the Profile preview (REQ-151). 404 none; 409 not a PDF."""
    root = c.settings.root
    m = next((r for r in resumes.list_resumes(root) if r["type"] == "master"), None)
    if m is None:
        raise HTTPException(404, "no master résumé")
    try:
        data, name = resumes.download_name(root, m["rid"], m["latest"])
    except (resumes.Refused, LookupError) as e:
        raise HTTPException(409, str(e)) from e
    if not name.lower().endswith(".pdf"):
        raise HTTPException(409, "the master résumé isn't a PDF")
    body = data if isinstance(data, bytes) else data.read_bytes()
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": "inline; filename=\"master.pdf\""})
