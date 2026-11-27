export function ScheduleData({ entries }: { entries: [string, string][] }) {
  return <dl className="schedule-data" aria-label="Datos del cronograma">
    {entries.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
  </dl>
}
