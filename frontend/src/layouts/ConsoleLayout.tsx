import { useMemo, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { Activity, BarChart3, Bot, Database, Gauge, Radar, Server, Settings, ShieldAlert, Menu } from 'lucide-react';

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
  const utcTime = useMemo(() => new Date().toISOString().slice(11, 19), []);

  return (
    <div className="flex min-h-screen bg-terminal-bg text-terminal-text">
      <aside className={`border-r border-terminal-border bg-[#090d13] ${collapsed ? 'w-20' : 'w-64'} transition-all`}>
        <button onClick={() => setCollapsed((v) => !v)} className="m-3 rounded-md border border-terminal-border p-2"><Menu size={16} /></button>
        <nav className="px-2 pb-3">
          {navItems.map(({ label, path, icon: Icon }) => (
            <NavLink key={path} to={path} className={({ isActive }) => `mb-1 flex items-center gap-3 rounded-md px-3 py-2 text-sm ${isActive ? 'bg-neon-cyan/10 text-neon-cyan' : 'text-terminal-muted hover:bg-terminal-border/30'}`}>
              <Icon size={16} /> {!collapsed && label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="flex-1">
        <header className="sticky top-0 z-10 grid grid-cols-2 gap-2 border-b border-terminal-border bg-terminal-bg/95 p-3 backdrop-blur md:grid-cols-6 text-xs">
          <div>ENV: <span className="text-neon-cyan">LOCAL</span></div><div>API: ONLINE</div><div>INGESTION: ACTIVE</div><div>DB: HEALTHY</div><div>CANDLE: LIVE</div><div>UTC: {utcTime}</div>
        </header>
        <div className="p-4 md:p-6"><Outlet /></div>
      </main>
    </div>
  );
}
