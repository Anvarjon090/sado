/* Meter fill by how full it is. Neutral while there is room; amber, then red,
   only when the number calls for action (DESIGN.md: status colour is for
   status, and indigo is never decoration). */
export function meterTone(percent: number): string {
  if (percent >= 90) return 'bg-destructive';
  if (percent >= 80) return 'bg-warning';
  return 'bg-foreground/55';
}
