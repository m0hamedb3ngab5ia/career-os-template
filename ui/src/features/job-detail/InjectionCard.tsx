import { TriangleAlert } from "lucide-react";
import { Button } from "../../kit/Button";
import { Card } from "./Card";
import { errorText, useClearInjection } from "./api";

/** REQ-109: a flagged posting blocks prepare/apply until the user reads it and says "I checked it". */
export function InjectionCard({ jobId, reasons }: { jobId: string; reasons: string }) {
  const clear = useClearInjection(jobId);
  return (
    <Card title="Possible prompt injection" icon={<TriangleAlert size={16} aria-hidden="true" />}>
      <p>Flagged because: {reasons}. Prepare and apply stay blocked until you read the posting and confirm it is safe.</p>
      <div>
        <Button onClick={() => clear.mutate(undefined)} disabled={clear.isPending}>
          I checked it
        </Button>
      </div>
      {clear.isError ? <p role="alert">{errorText(clear.error)}</p> : null}
    </Card>
  );
}
