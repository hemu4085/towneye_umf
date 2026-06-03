import { BrowserRouter, Route, Routes } from 'react-router-dom';
import AppShell from './components/AppShell';
import { ParcelProvider } from './context/ParcelContext';
import Dashboard from './pages/Dashboard';
import Home from './pages/Home';
import ReportPage from './pages/ReportPage';

export default function App() {
  return (
    <BrowserRouter>
      <ParcelProvider>
        <AppShell>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/report/:reportId" element={<ReportPage />} />
          </Routes>
        </AppShell>
      </ParcelProvider>
    </BrowserRouter>
  );
}
