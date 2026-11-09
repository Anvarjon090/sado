export function shouldOpenDevTools(
  environment: Record<string, string | undefined> = process.env,
): boolean {
  return environment.SADO_OPEN_DEVTOOLS === '1';
}
