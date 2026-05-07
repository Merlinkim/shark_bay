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
      {mobileOpen && <div className="fixed inset-0 z-20 bg-black/50 md:hidden" onClick={() => setMobileOpen(false)} />}
      <aside className={`fixed inset-y-0 left-0 z-30 border-r border-surface-700 bg-surface-900 transition-all md:static ${mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'} ${collapsed ? 'md:w-20' : 'w-72 md:w-64'}`}>
        <div className="flex items-center justify-between p-3">
          {!collapsed && <p className="text-sm font-semibold tracking-tight">Shark Bay Console</p>}
          <button onClick={() => setMobileOpen(false)} className="rounded-md p-2 md:hidden"><X size={16} /></button>
          <button onClick={() => setCollapsed((v) => !v)} className="hidden rounded-md p-2 md:block"><Menu size={16} /></button>
        </div>
        <nav className="space-y-1 px-2 pb-4">
          {navItems.map(({ label, path, icon: Icon }) => (
            <NavLink key={path} to={path} onClick={() => setMobileOpen(false)} className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${isActive ? 'bg-surface-800 text-text-primary' : 'text-text-secondary hover:bg-surface-800/80 hover:text-text-primary'}`}>
              <Icon size={16} /> {!collapsed && label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="flex-1">
        <header className="sticky top-0 z-10 border-b border-surface-700 bg-surface-950/95 px-4 py-3 backdrop-blur">
          <div className="mb-3 flex items-center justify-between md:hidden">
            <button onClick={() => setMobileOpen(true)} className="rounded-md border border-surface-700 p-2"><Menu size={16} /></button>
            <span className="text-xs text-text-secondary">UTC {utcTime}</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
            <div className="rounded-md bg-surface-900 px-2 py-1.5">ENV <span className="text-text-secondary">LOCAL</span></div>
            <div className="rounded-md bg-surface-900 px-2 py-1.5">API <span className="text-accent-green">ONLINE</span></div>
            <div className="rounded-md bg-surface-900 px-2 py-1.5">INGEST <span className="text-accent-green">ACTIVE</span></div>
            <div className="rounded-md bg-surface-900 px-2 py-1.5">DB <span className="text-accent-green">HEALTHY</span></div>
            <div className="rounded-md bg-surface-900 px-2 py-1.5">CANDLE <span className="text-text-secondary">LIVE</span></div>
            <div className="rounded-md bg-surface-900 px-2 py-1.5">UTC <span className="text-text-secondary">{utcTime}</span></div>
          </div>
        </header>
        <div className="p-4 md:p-6"><Outlet /></div>
      </main>
    </div>
  );
}
