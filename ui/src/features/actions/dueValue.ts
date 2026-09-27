/** The due value sent to the server: "YYYY-MM-DD" for a date alone, else the local date + time as an ISO instant. */
export function dueValue(date: string, time: string): string | null {
  if (!date) return null;
  if (!time) return date;
  const t = new Date(`${date}T${time}`);
  return Number.isNaN(t.getTime()) ? date : t.toISOString();
}
