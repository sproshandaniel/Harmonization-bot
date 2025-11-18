import { BrowserRouter as Router, Routes, Route, Link } from "react-router-dom";
import { Home, Settings, BarChart2, FileText } from "lucide-react";
import Dashboard from "./Pages/Dashboard";
import RulePacks from "./Pages/RulePacks";
import Analytics from "./Pages/Analytics";
import SettingsPage from "./Pages/Settings";

export default function App() {
  const navItems = [
    { name: "Dashboard", path: "/", icon: <Home size={18} /> },
    { name: "Rule Packs", path: "/rule-packs", icon: <FileText size={18} /> },
    { name: "Analytics", path: "/analytics", icon: <BarChart2 size={18} /> },
    { name: "Settings", path: "/settings", icon: <Settings size={18} /> },
  ];

  return (
    <Router>
      <div className="flex min-h-screen bg-gray-50 text-gray-800">
        {/* Sidebar */}
        <aside className="w-64 bg-indigo-700 text-white flex flex-col">
          <div className="px-6 py-5 text-xl font-bold border-b border-indigo-600">
            Harmonization Bot
          </div>

          <nav className="flex-1 p-4 space-y-2">
            {navItems.map((item) => (
              <Link
                key={item.name}
                to={item.path}
                className="flex items-center w-full px-3 py-2 rounded-md text-sm font-medium transition hover:bg-indigo-600/70"
              >
                <span className="mr-3">{item.icon}</span>
                {item.name}
              </Link>
            ))}
          </nav>

          <div className="px-6 py-3 border-t border-indigo-600 text-xs text-indigo-200">
            © 2025 Harmonization Dashboard
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 flex flex-col">
          {/* Topbar */}
          <header className="flex items-center justify-between bg-white px-8 py-4 shadow-sm">
            <h1 className="text-2xl font-semibold text-indigo-700">Harmonization Dashboard</h1>
            <div className="flex items-center space-x-4">
              <div className="text-sm text-gray-600">Architect User</div>
              <div className="w-8 h-8 rounded-full bg-indigo-500 flex items-center justify-center text-white">
                A
              </div>
            </div>
          </header>

          {/* Page Routes */}
          <section className="flex-1 overflow-y-auto">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/rule-packs" element={<RulePacks />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </section>
        </main>
      </div>
    </Router>
  );
}