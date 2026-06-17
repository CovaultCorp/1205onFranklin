export function StatusBadge({ value }: { value?: string | null }) {
  const status = value ?? "unknown";
  return <span className={`status ${status}`}>{status.replaceAll("_", " ")}</span>;
}
