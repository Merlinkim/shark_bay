import { Navigate, Route, Routes } from 'react-router-dom';
import { ConsoleLayout } from './layouts/ConsoleLayout';
import { DashboardPage } from './pages/DashboardPage';
import { MarketDataPage } from './pages/MarketDataPage';
import { LiveMarketChartPage } from './pages/LiveMarketChartPage';
import { SimplePlaceholderPage } from './pages/SimplePlaceholderPage';
import { OperationsPage } from './pages/OperationsPage';
import { InfrastructurePage } from './pages/InfrastructurePage';
import { StrategiesPage } from './pages/StrategiesPage';
import { AgentsPage } from './pages/AgentsPage';
import { RiskControlPage } from './pages/RiskControlPage';
import { ResearchPage } from './pages/ResearchPage';

export default function App() {
  return (
    <Routes>
      <Route element={<ConsoleLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/market-data" element={<MarketDataPage />} />
        <Route path="/market-data/live-chart" element={<LiveMarketChartPage />} />
        <Route path="/research" element={<ResearchPage />} />
        <Route path="/strategies" element={<StrategiesPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/operations" element={<OperationsPage />} />
        <Route path="/risk-control" element={<RiskControlPage />} />
        <Route path="/infrastructure" element={<InfrastructurePage />} />
        <Route path="/settings" element={<SimplePlaceholderPage title="Settings" notes={['Exchange configs', 'Model configs', 'Deployment configs', 'Agent permissions']} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
