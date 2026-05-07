export function SimplePlaceholderPage({ title, notes }: { title: string; notes: string[] }) {
  return (
    <div className="rounded-xl border border-terminal-border bg-terminal-panel/70 p-6">
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-terminal-muted">Future intent</p>
      <ul className="mt-4 list-disc space-y-2 pl-5 text-terminal-text">
        {notes.map((note) => <li key={note}>{note}</li>)}
      </ul>
    </div>
  );
}
