"""Profile page (REQ-107): Saved answers (view / edit / delete profile/standard_answers.yaml, general, per company
and EEO) and Writing samples (REQ-101: upload / list / remove profile/voice/samples/; any change re-runs learn-voice
in the background, removing the last sample clears the learned style). Writes go through careeros.learning / voice."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from careeros import learning, voice
from careeros.ui.routers import ctx

router = APIRouter(tags=["profile"])


class SavedAnswer(BaseModel):
    scope: Literal["general", "company", "eeo"]
    key: str
    company: str | None = None
    answer: str | None = None
    match: list[str] = []
    note: str | None = None


class SavedAnswers(BaseModel):
    answers: list[SavedAnswer]


class AnswerEdit(BaseModel):
    answer: str
    company: str | None = None
    eeo: bool = False


class Sample(BaseModel):
    name: str
    size: int


class Samples(BaseModel):
    samples: list[Sample]
    learned: str


class SampleChange(BaseModel):
    samples: list[Sample]
    learn_run: str | None = None
    learn_error: str | None = None
    learn_info: str | None = None


def _change(c: Any, fn: Any) -> None:
    try:
        fn()
    except KeyError:
        raise HTTPException(404, "not found") from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.get("/profile/answers")
def list_answers(c=Depends(ctx)) -> SavedAnswers:
    return SavedAnswers(answers=[SavedAnswer(**r) for r in learning.list_answers(c.settings)])


@router.put("/profile/answers/{key}")
def edit_answer(key: str, body: AnswerEdit, c=Depends(ctx)) -> SavedAnswer:
    _change(c, lambda: learning.edit_answer(c.settings, key=key, answer=body.answer, company=body.company,
                                            eeo=body.eeo))
    scope = "eeo" if body.eeo else "company" if body.company else "general"
    return next(SavedAnswer(**r) for r in learning.list_answers(c.settings) if r["key"] == key and r["scope"] == scope
                and (scope != "company" or r["company"].strip().lower() == body.company.strip().lower()))


@router.delete("/profile/answers/{key}", status_code=204)
def delete_answer(key: str, company: str | None = None, eeo: bool = False, c=Depends(ctx)) -> Response:
    _change(c, lambda: learning.delete_answer(c.settings, key=key, company=company, eeo=eeo))
    return Response(status_code=204)


def _samples(c: Any) -> list[Sample]:
    return [Sample(**x) for x in voice.list_samples(c.settings.root)]


def _learn(request: Request, c: Any) -> SampleChange:
    """Re-run learn-voice on the current samples; with none left, clear the learned style instead (UC-005 alt).
    If the run can't start (busy, paused, claude missing) the sample change stands and learn_error says why (Retry)."""
    from careeros.ui.services.runs import Busy, RunControl

    samples = _samples(c)
    if not samples:
        voice.clear_learned(c.settings.root)
        return SampleChange(samples=samples)
    try:
        out = (getattr(request.app.state, "run_control", None) or RunControl)(c.settings).start_step("learn_voice")
    except Busy as e:
        if "learn_voice" in str(e.holder.get("note") or e.holder.get("owner") or ""):
            return SampleChange(samples=samples, learn_info="voice update already running; new samples are used next run")
        return SampleChange(samples=samples, learn_error=f"learn-voice not started: {e}")
    except Exception as e:  # noqa: BLE001 - never lose the upload over the follow-up run
        return SampleChange(samples=samples, learn_error=f"learn-voice not started: {e}")
    return SampleChange(samples=samples, learn_run=(out or {}).get("run_id"))


@router.get("/profile/samples")
def list_samples(c=Depends(ctx)) -> Samples:
    return Samples(samples=_samples(c), learned=voice.learned(c.settings.root))


_RAW = {"requestBody": {"required": True, "content": {"application/octet-stream": {
    "schema": {"type": "string", "format": "binary"}}}}}


@router.put("/profile/samples", status_code=201, openapi_extra=_RAW)
async def upload_sample(request: Request, filename: str, learn: bool = True, c=Depends(ctx)) -> SampleChange:
    """`learn=false`: more files of the same upload follow; the UI then calls POST /profile/samples/learn once."""
    data = bytearray()
    async for chunk in request.stream():  # streamed cap: never buffer more than MAX_BYTES + one chunk
        data += chunk
        if len(data) > voice.MAX_BYTES:
            raise HTTPException(413, f"{filename}: larger than 5 MB")
    try:
        voice.add_sample(c.settings.root, filename, bytes(data))
    except voice.Unsupported as e:
        raise HTTPException(415, str(e)) from None
    except voice.TooLarge as e:
        raise HTTPException(413, str(e)) from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return _learn(request, c) if learn else SampleChange(samples=_samples(c))


@router.delete("/profile/samples/{name}")
def remove_sample(name: str, request: Request, c=Depends(ctx)) -> SampleChange:
    _change(c, lambda: voice.remove_sample(c.settings.root, name))
    return _learn(request, c)


@router.post("/profile/samples/learn", status_code=202)
def relearn(request: Request, c=Depends(ctx)) -> SampleChange:
    return _learn(request, c)
