import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiSend } from "../../api/client";
import type { components } from "../../api/schema.gen";
import { runKeys } from "../runs/api";
import type { RunDetail } from "../runs/types";

export type SavedAnswer = components["schemas"]["SavedAnswer"];
export type SampleChange = components["schemas"]["SampleChange"];
type Samples = components["schemas"]["Samples"];
type Lesson = components["schemas"]["Lesson"];
type ResumeRow = components["schemas"]["ResumeRow"];

export interface ReadinessItem {
  id: string;
  label: string;
  must: boolean;
  done: boolean;
  fix_link: string;
}
export interface Readiness {
  ready: boolean;
  items: ReadinessItem[];
}

export const useReadiness = () => useQuery({ queryKey: ["readiness"], queryFn: () => apiFetch<Readiness>("/api/readiness") });
export const useAnswers = () =>
  useQuery({ queryKey: ["profile", "answers"], queryFn: () => apiFetch<{ answers: SavedAnswer[] }>("/api/profile/answers") });
export const useSamples = () => useQuery({ queryKey: ["profile", "samples"], queryFn: () => apiFetch<Samples>("/api/profile/samples") });
export const useLessons = () =>
  useQuery({ queryKey: ["profile", "lessons"], queryFn: () => apiFetch<{ lessons: Lesson[] }>("/api/learning/lessons") });
export const useResumes = () =>
  useQuery({ queryKey: ["profile", "resumes"], queryFn: () => apiFetch<{ resumes: ResumeRow[] }>("/api/profile/resumes") });

/** Raw-body upload (DEC-006): the file is the request body, its name a query parameter. */
export function upload<T>(path: string, file: File): Promise<T> {
  return apiFetch<T>(`${path}${path.includes("?") ? "&" : "?"}filename=${encodeURIComponent(file.name)}`, {
    method: "PUT",
    headers: { "X-CareerOS": "1", "Content-Type": "application/octet-stream" },
    body: file,
  });
}

/** Any profile write: refetch the profile lists and the readiness checklist. */
export function useProfileWrite<V, T = unknown>(fn: (v: V) => Promise<T>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["profile"] });
      void qc.invalidateQueries({ queryKey: ["readiness"] });
    },
  });
}

const answerQuery = (a: SavedAnswer) =>
  a.scope === "eeo" ? "?eeo=true" : a.company ? `?company=${encodeURIComponent(a.company)}` : "";

export const editAnswer = ({ a, answer }: { a: SavedAnswer; answer: string }) =>
  apiSend<SavedAnswer>("PUT", `/api/profile/answers/${encodeURIComponent(a.key)}`, {
    answer,
    company: a.scope === "company" ? a.company : null,
    eeo: a.scope === "eeo",
  });
export const deleteAnswer = (a: SavedAnswer) =>
  apiSend<void>("DELETE", `/api/profile/answers/${encodeURIComponent(a.key)}${answerQuery(a)}`);
export const deleteLesson = (id: string) => apiSend<void>("DELETE", `/api/learning/lessons/${encodeURIComponent(id)}`);
export const removeSample = (name: string) => apiSend<SampleChange>("DELETE", `/api/profile/samples/${encodeURIComponent(name)}`);
export const relearn = () => apiSend<SampleChange>("POST", "/api/profile/samples/learn");
/** One upload action (E2E-005-01): store every file first, then start learn-voice once. */
export async function uploadSamples(files: File[]): Promise<SampleChange> {
  for (const f of files) await upload<SampleChange>("/api/profile/samples?learn=false", f);
  return relearn();
}
/** Follow the learn-voice run the last sample change started, until it ends. */
export const useLearnRun = (id: string | null | undefined) =>
  useQuery({
    queryKey: runKeys.detail(id ?? ""),
    queryFn: () => apiFetch<RunDetail>(`/api/runs/${encodeURIComponent(id ?? "")}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && q.state.data.state !== "running" ? false : 1000),
    retry: (n) => n < 30, // the record appears once the spawned step starts
  });
export const makeMaster = (rid: string) => apiSend<unknown>("POST", `/api/profile/resumes/${encodeURIComponent(rid)}/master`);
export const deleteResume = (rid: string) => apiSend<void>("DELETE", `/api/profile/resumes/${encodeURIComponent(rid)}`);

export type MasterProposal = components["schemas"]["MasterProposal"];
export type Feedback = components["schemas"]["Feedback"];
export type FeedbackItem = components["schemas"]["FeedbackItem"];
const rp = (rid: string) => `/api/profile/resumes/${encodeURIComponent(rid)}`;
/** REQ-099: the master.yaml diff. Polls while stale (extract-master is running or never ran). */
export const useMasterProposal = () =>
  useQuery({
    queryKey: ["profile", "master"],
    queryFn: () => apiFetch<MasterProposal>("/api/profile/master/proposal"),
    refetchInterval: (q) => (q.state.data?.state === "stale" ? 5000 : false),
  });
export const approveMaster = () => apiSend<MasterProposal>("POST", "/api/profile/master/proposal/approve");
export const rejectMaster = () => apiSend<MasterProposal>("POST", "/api/profile/master/proposal/reject");
/** REQ-094..096: a résumé's review feedback. Polls while the review or a redraft runs. */
export const useFeedback = (rid: string) =>
  useQuery({
    queryKey: ["profile", "feedback", rid],
    queryFn: () => apiFetch<Feedback>(`${rp(rid)}/feedback`),
    refetchInterval: (q) =>
      q.state.data?.review?.state === "running" || q.state.data?.items.some((i) => i.state === "redrafting") ? 2000 : false,
  });
export const applyFeedback = ({ rid, fid }: { rid: string; fid: string }) =>
  apiSend<unknown>("POST", `${rp(rid)}/feedback/${encodeURIComponent(fid)}/apply`);
export const dismissFeedback = ({ rid, fid }: { rid: string; fid: string }) =>
  apiSend<FeedbackItem>("POST", `${rp(rid)}/feedback/${encodeURIComponent(fid)}/dismiss`);
export const commentFeedback = ({ rid, fid, text }: { rid: string; fid: string; text: string }) =>
  apiSend<unknown>("POST", `${rp(rid)}/feedback/${encodeURIComponent(fid)}/comment`, { text });
export const retryReview = (rid: string) => apiSend<unknown>("POST", `${rp(rid)}/review`);
