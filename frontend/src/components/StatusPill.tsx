import { motion } from 'framer-motion';
import type { Severity } from '../types/status';

const styles: Record<Severity, string> = {
  ok: 'bg-neon-green/15 text-neon-green border-neon-green/50',
  warn: 'bg-neon-amber/15 text-neon-amber border-neon-amber/50',
  error: 'bg-neon-red/15 text-neon-red border-neon-red/50',
  unknown: 'bg-terminal-border/40 text-terminal-muted border-terminal-border',
};

export function StatusPill({ label, severity }: { label: string; severity: Severity }) {
  return (
    <motion.span
      initial={{ opacity: 0.75 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.25 }}
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${styles[severity]}`}
    >
      <span className="h-2 w-2 rounded-full bg-current shadow-[0_0_8px_currentColor]" />
      {label}
    </motion.span>
  );
}
