# TASK-035 handoff
Done: backend ui-state jobs_view (merge PUT) + openapi regen; reasons.ts, urlState tabs/view, JobsCards/JobsBoard/JobsPage wiring, StartPipeline tab=saved, new JobsViews.test.tsx.
Next: fix existing vitest (JobsPage/StartPipeline/Tour tests use old tabs), tsc, full pytest, ui static bundle rebuild + snapshots, PR.
Decisions: no stage sub-tabs/master-detail (not in Done-when); Closed column not a drop target; Start pipeline hidden outside Saved.
