import { Navigate, Route, Routes } from 'react-router-dom';
import { ConsoleLayout } from './layouts/ConsoleLayout';
import { DashboardPage } from './pages/DashboardPage';
import { MarketDataPage } from './pages/MarketDataPage';
import { SimplePlaceholderPage } from './pages/SimplePlaceholderPage';

export default function App() {
  return (
    <Routes>
      <Route element={<ConsoleLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/market-data" element={<MarketDataPage />} />
        <Route path="/research" element={<SimplePlaceholderPage title="Research Workspace" notes={['Strategy registry', 'Parameter sweeps', 'Run comparison', 'AI-assisted analysis', 'Feature engineering']} />} />
        <Route path="/strategies" element={<SimplePlaceholderPage title="Strategies" notes={['Execution graph', 'Versioned strategy manifests', 'Scenario simulation queue']} />} />
        <Route path="/agents" element={<SimplePlaceholderPage title="Agent Operations" notes={['OpenClaw orchestration', 'Agent monitoring', 'Autonomous backtest execution', 'Anomaly investigation', 'Supervised execution approval']} />} />
        <Route path="/operations" element={<SimplePlaceholderPage title="Operations Monitoring" notes={['Docker services', 'Uptime', 'Memory', 'CPU', 'Reconnect events', 'Deployment history']} />} />
        <Route path="/risk-control" element={<SimplePlaceholderPage title="Risk Control" notes={['Kill switch', 'Max drawdown controls', 'Emergency trading disable', 'Position exposure', 'Trade approval workflow']} />} />
        <Route path="/infrastructure" element={<SimplePlaceholderPage title="Infrastructure" notes={['Cluster topology', 'Data bus latency', 'Storage replication', 'Secret rotation state']} />} />
        <Route path="/settings" element={<SimplePlaceholderPage title="Settings" notes={['Exchange configs', 'Model configs', 'Deployment configs', 'Agent permissions']} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
