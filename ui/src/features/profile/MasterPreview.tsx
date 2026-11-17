import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import styles from "./Lists.module.css";

/** REQ-151: the master résumé itself, read-only. Fetched as a blob so a 409 (not a PDF, no LaTeX) shows a sentence, not raw JSON. */
export function MasterPreview({ rid, version }: { rid: string; version: number }) {
  const q = useQuery({
    queryKey: ["master-pdf", rid, version],
    queryFn: async () => {
      const res = await fetch("/api/profile/master.pdf");
      if (!res.ok) throw new Error(res.status === 409 ? "It can’t be shown here (not a PDF, or no PDF renderer installed). Ask in chat to see it." : "Couldn’t load it.");
      return res.blob();
    },
    staleTime: 60_000,
  });
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!q.data) return;
    const u = URL.createObjectURL(q.data);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [q.data]);
  return (
    <section aria-label="Master résumé preview">
      <h2 className={styles.heading}>Master résumé</h2>
      {url ? (
        <iframe className={styles.preview} src={url} title="Master résumé" />
      ) : (
        <p className={styles.note}>{q.isError ? (q.error as Error).message : "Loading…"}</p>
      )}
    </section>
  );
}
