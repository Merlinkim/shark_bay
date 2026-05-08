import { useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { Activity, BarChart3, Bot, Database, Gauge, Menu, Radar, Server, Settings, ShieldAlert, X } from 'lucide-react';

const navItems = [
  { label: 'Dashboard', path: '/', icon: Gauge },
  { label: 'Market Data', path: '/market-data', icon: BarChart3 },
  { label: 'Research', path: '/research', icon: Radar },
  { label: 'Strategies', path: '/strategies', icon: Activity },
  { label: 'Agents', path: '/agents', icon: Bot },
  { label: 'Operations', path: '/operations', icon: Server },
  { label: 'Risk Control', path: '/risk-control', icon: ShieldAlert },
  { label: 'Infrastructure', path: '/infrastructure', icon: Database },
  { label: 'Settings', path: '/settings', icon: Settings },
];

export function ConsoleLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [utcTime, setUtcTime] = useState(new Date().toISOString().slice(11, 19));

  useEffect(() => {
    const timer = setInterval(() => setUtcTime(new Date().toISOString().slice(11, 19)), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="min-h-screen bg-surface-950 text-text-primary md:flex">
      {mobileOpen && <div className="fixed inset-0 z-20 bg-black/45 md:hidden" onClick={() => setMobileOpen(false)} />}
      <aside className={`fixed inset-y-0 left-0 z-30 bg-surface-900 ring-1 ring-surface-700/80 transition-all duration-200 md:static ${mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'} ${collapsed ? 'md:w-20' : 'w-72 md:w-64'}`}>
        <div className="flex items-center justify-between px-3 py-3.5">
          {!collapsed && <p className="text-sm font-semibold tracking-tight text-text-primary/95">Shark Bay Console</p>}
          <button onClick={() => setMobileOpen(false)} className="rounded-md p-2 text-text-secondary md:hidden"><X size={16} /></button>
          <button onClick={() => setCollapsed((v) => !v)} className="hidden rounded-md p-2 text-text-secondary transition-colors hover:bg-surface-800 hover:text-text-primary md:block"><Menu size={16} /></button>
        </div>
        <nav className="space-y-1 px-2 pb-4">
          {navItems.map(({ label, path, icon: Icon }) => (
            <NavLink key={path} to={path} onClick={() => setMobileOpen(false)} className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${isActive ? 'bg-surface-800 text-text-primary' : 'text-text-secondary hover:bg-surface-850 hover:text-text-primary'}`}>
              <Icon size={16} /> {!collapsed && label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="flex-1">
        <header className="sticky top-0 z-10 border-b border-surface-700/70 bg-surface-950/95 px-4 py-3 backdrop-blur">
          <div className="mb-3 flex items-center justify-between md:hidden">
            <button onClick={() => setMobileOpen(true)} className="rounded-md bg-surface-900 p-2 text-text-secondary ring-1 ring-surface-700/80"><Menu size={16} /></button>
            <span className="text-xs text-text-secondary">UTC {utcTime}</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
            {[
              ['ENV', 'LOCAL', 'text-text-secondary'],
              ['API', 'ONLINE', 'text-accent-green'],
              ['INGEST', 'ACTIVE', 'text-accent-green'],
              ['DB', 'HEALTHY', 'text-accent-green'],
              ['CANDLE', 'LIVE', 'text-text-secondary'],
              ['UTC', utcTime, 'text-text-secondary'],
            ].map(([k, v, cls]) => (
              <div key={k} className="rounded-lg bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">
                <span className="text-text-muted">{k}</span> <span className={cls}>{v}</span>
              </div>
            ))}
          </div>
        </header>
        <div className="p-4 pb-6 md:p-6"><Outlet /></div>
      </main>
    </div>
  );
}
