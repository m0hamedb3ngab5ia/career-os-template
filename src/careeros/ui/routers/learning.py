"""Learning: lessons apply-job reads before a session (GET /learning/lessons?ats=&company=) and records after one
(POST /learning/lessons). Answers are learned through POST /actions/{id}/answer (routers/actions.py)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from careeros.ui.routers import ctx

router = APIRouter(tags=["learning"])


class NewLesson(BaseModel):
    text: str
    ats: str | None = None
    company: str | None = None
    job_id: str | None = None
    tags: list[str] = []


class Lesson(BaseModel):
    id: str
    text: str
    ats: str | None = None
    company: str | None = None
    job_id: str | None = None
    added: str | None = None
    tags: list[str] = []


class Lessons(BaseModel):
    lessons: list[Lesson]


@router.get("/learning/lessons")
def list_lessons(ats: str | None = None, company: str | None = None, c=Depends(ctx)) -> Lessons:
    from careeros.learning import lessons_for

    return Lessons(lessons=[Lesson(**x) for x in lessons_for(c.settings, ats=ats, company=company)])


@router.post("/learning/lessons")
def add_lesson(body: NewLesson, c=Depends(ctx)) -> Lesson:
    from careeros.learning import learn_lesson

    e = learn_lesson(c.settings, text=body.text, ats=body.ats, company=body.company, job_id=body.job_id,
                     tags=tuple(body.tags))
    return Lesson(**e)


@router.delete("/learning/lessons/{lid}", status_code=204)
def delete_lesson(lid: str, c=Depends(ctx)) -> Response:
    from careeros.learning import delete_lesson as _delete

    try:
        _delete(c.settings, lid)
    except KeyError:
        raise HTTPException(404, f"lesson {lid} not found") from None
    return Response(status_code=204)
