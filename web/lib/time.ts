/** ClickHouse can return a UTC timestamp without an explicit zone. */
export function archiveDate(value: string): Date {
  const explicitZone = /(?:Z|[+-]\d\d:\d\d)$/i.test(value);
  return new Date(explicitZone ? value : `${value}Z`);
}

export function archiveLocal(value: string): string {
  return value ? archiveDate(value).toLocaleString() : "";
}
