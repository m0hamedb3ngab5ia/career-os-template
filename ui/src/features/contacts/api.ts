import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiSend } from "../../api/client";
import type { ContactsResponse, MarkBody, MarkResult } from "./types";

export function useContacts() {
  return useQuery({ queryKey: ["contacts"], queryFn: () => apiFetch<ContactsResponse>("/api/contacts") });
}

/** Same code as `careeros outreach mark <job_id> <name> --degree N --mutuals N`. */
export function useMarkContact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, name, body }: { jobId: string; name: string; body: MarkBody }) =>
      apiSend<MarkResult>(
        "POST",
        `/api/contacts/${encodeURIComponent(jobId)}/${encodeURIComponent(name)}/mark`,
        body,
      ),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["contacts"] });
    },
  });
}
