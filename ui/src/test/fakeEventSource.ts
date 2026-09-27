// Mirrors the server (src/careeros/ui/routers/events.py): a named `hello` frame on connect, then named
// `changed` frames whose data is {jobs: [ids], runs: [ids], actions, config, status}.
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  static get last() {
    return FakeEventSource.instances.at(-1)!;
  }
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private listeners = new Map<string, ((e: MessageEvent) => void)[]>();
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  dispatch(type: string, data: unknown) {
    const e = new MessageEvent(type, { data: typeof data === "string" ? data : JSON.stringify(data) });
    for (const fn of this.listeners.get(type) ?? []) fn(e);
  }
  fail(closed: boolean) {
    this.readyState = closed ? 2 : 0;
    this.onerror?.();
  }
}

