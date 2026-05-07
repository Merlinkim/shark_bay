import { motion } from 'framer-motion';
import type { Severity } from '../types/status';

const styles: Record<Severity, string> = {
  ok: 'bg-accent-green/15 text-accent-green border-accent-green/25',
  warn: 'bg-accent-amber/15 text-accent-amber border-accent-amber/25',
  error: 'bg-accent-red/15 text-accent-red border-accent-red/25',
  unknown: 'bg-surface-800 text-text-secondary border-surface-700',
};

export function StatusPill({ label, severity }: { label: string; severity: Severity }) {
  return (
    <motion.span
      initial={{ opacity: 0.8 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${styles[severity]}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </motion.span>
  );
}
