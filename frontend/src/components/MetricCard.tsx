import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

export function MetricCard({ title, value, hint }: { title: string; value: ReactNode; hint?: string }) {
  return (
    <motion.div
      layout
      className="rounded-xl border border-terminal-border bg-terminal-panel/80 p-4 shadow-glow"
      initial={{ opacity: 0.8, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <p className="text-xs uppercase tracking-widest text-terminal-muted">{title}</p>
      <p className="mt-2 text-2xl font-semibold text-terminal-text">{value}</p>
      {hint && <p className="mt-1 text-xs text-terminal-muted">{hint}</p>}
    </motion.div>
  );
}
