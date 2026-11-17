import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { components } from "../../api/schema.gen";

export type Profile = components["schemas"]["Profile"];
export type SettingsView = components["schemas"]["SettingsView"];

// Read-only views (GET /api/profile, GET /api/settings). Changes happen in chat or the CLI (docs/CHAT.md).
export const useProfile = () => useQuery({ queryKey: ["profile"], queryFn: () => apiFetch<Profile>("/api/profile"), staleTime: 30_000 });
export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: () => apiFetch<SettingsView>("/api/settings"), staleTime: 30_000 });
