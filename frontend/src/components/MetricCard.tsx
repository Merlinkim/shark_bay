import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

export function MetricCard({ title, value, hint }: { title: string; value: ReactNode; hint?: string }) {
  return (
    <motion.div
      layout
      className="rounded-xl border border-surface-700 bg-surface-900 p-4 shadow-card md:p-5"
      initial={{ opacity: 0.9, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{title}</p>
      <p className="mt-2 text-2xl font-semibold leading-tight text-text-primary md:text-3xl">{value}</p>
      {hint && <p className="mt-2 text-xs text-text-secondary">{hint}</p>}
    </motion.div>
  );
}
