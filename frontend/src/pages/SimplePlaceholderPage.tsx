export function SimplePlaceholderPage({ title, notes }: { title: string; notes: string[] }) {
  return (
    <div className="rounded-xl border border-surface-700 bg-surface-900 p-5 shadow-card md:p-6">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-1 text-sm text-text-secondary">Planned capabilities</p>
      <ul className="mt-4 space-y-2 text-sm text-text-primary">
        {notes.map((note) => (
          <li key={note} className="rounded-lg bg-surface-800 px-3 py-2">{note}</li>
        ))}
      </ul>
    </div>
  );
}
