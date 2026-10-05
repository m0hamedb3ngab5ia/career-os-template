import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiSend } from "../../api/client";
import type { components } from "../../api/schema.gen";

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
  return apiFetch<T>(`${path}?filename=${encodeURIComponent(file.name)}`, {
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
export const makeMaster = (rid: string) => apiSend<unknown>("POST", `/api/profile/resumes/${encodeURIComponent(rid)}/master`);
export const deleteResume = (rid: string) => apiSend<void>("DELETE", `/api/profile/resumes/${encodeURIComponent(rid)}`);
