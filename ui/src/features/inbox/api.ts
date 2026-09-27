import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { InboxDetailResponse, InboxResponse } from "./types";

export function useInbox() {
  return useQuery({ queryKey: ["inbox"], queryFn: () => apiFetch<InboxResponse>("/api/inbox") });
}

export function useInboxThread(jobId: string | undefined) {
  return useQuery({
    queryKey: ["inbox", jobId],
    queryFn: () => apiFetch<InboxDetailResponse>(`/api/inbox/${encodeURIComponent(jobId!)}`),
    enabled: Boolean(jobId),
  });
}
