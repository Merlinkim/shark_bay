import { motion } from 'framer-motion';
import type { Severity } from '../types/status';

const styles: Record<Severity, string> = {
  ok: 'bg-accent-green/12 text-accent-green',
  warn: 'bg-accent-amber/12 text-accent-amber',
  error: 'bg-accent-red/12 text-accent-red',
  unknown: 'bg-surface-800 text-text-secondary',
};

export function StatusPill({ label, severity }: { label: string; severity: Severity }) {
  return (
    <motion.span
      initial={{ opacity: 0.85 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.18 }}
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium ${styles[severity]}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </motion.span>
  );
}
