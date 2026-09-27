import { useEffect, useState } from "react";

/** The current time, refreshed every `ms`, for relative labels ("synced 12 s ago") computed on the client. */
export function useNow(ms = 15_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}
