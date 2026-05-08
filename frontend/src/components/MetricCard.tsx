import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

interface MetricCardProps {
  title: string;
  value: ReactNode;
  hint?: string;
  status?: string;
}

export function MetricCard({ title, value, hint, status }: MetricCardProps) {
  return (
    <motion.div
      layout
      className="group rounded-xl bg-surface-900 p-4 shadow-card ring-1 ring-surface-700/70 transition-all duration-200 hover:bg-surface-850 hover:ring-surface-700 md:p-5"
      initial={{ opacity: 0.95, y: 2 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">{title}</p>
        {status && <span className="rounded-full bg-surface-800 px-2 py-0.5 text-[10px] text-text-secondary">{status}</span>}
      </div>
      <p className="mt-3 text-[28px] font-semibold leading-none tracking-tight text-text-primary md:text-[32px]">{value}</p>
      {hint && <p className="mt-2 text-xs text-text-secondary">{hint}</p>}
    </motion.div>
  );
}
