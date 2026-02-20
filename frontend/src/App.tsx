import { useEffect, useState } from "react";
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from "react-router-dom";
import { Home, Settings, BarChart2, FileText, FolderKanban, RefreshCw, Moon, Sun } from "lucide-react";
import Dashboard from "./Pages/Dashboard";
import RulePacks from "./Pages/RulePacks";
import Analytics from "./Pages/Analytics";
import SettingsPage from "./Pages/Settings";
import ProjectsPage from "./Pages/ProjectsPage";
import Login from "./Pages/Login";
import companyLogo from "./assets/company-logo.svg";

function AppShell({
  uiConfig,
  userName,
  onLogout,
}: {
  uiConfig: { app_footer: string; platform_title: string };
  userName: string;
  onLogout: () => void;
}) {
  const location = useLocation();
  const [refreshingHeader, setRefreshingHeader] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(() => localStorage.getItem("hb_theme") === "dark");

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDarkMode);
    localStorage.setItem("hb_theme", isDarkMode ? "dark" : "light");
  }, [isDarkMode]);

  function handleHeaderRefresh() {
    setRefreshingHeader(true);
    window.setTimeout(() => {
      window.location.reload();
    }, 250);
  }

  const navItems = [
    { name: "Dashboard", path: "/", icon: <Home size={18} /> },
    { name: "Projects", path: "/projects", icon: <FolderKanban size={18} /> },
    { name: "Rule Packs", path: "/rule-packs", icon: <FileText size={18} /> },
    { name: "Analytics", path: "/analytics", icon: <BarChart2 size={18} /> },
    { name: "Settings", path: "/settings", icon: <Settings size={18} /> },
  ];

  return (
    <div className="flex min-h-screen bg-slate-100 text-slate-800 dark:bg-slate-950 dark:text-slate-100">
      <aside className="w-64 flex flex-col border-r border-slate-700 bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-slate-100 dark:border-slate-700 dark:from-slate-950 dark:via-slate-900 dark:to-slate-800">
        <div className="border-b border-slate-700/80 bg-slate-900 px-5 py-4 dark:border-slate-700 dark:bg-slate-900">
          <div className="text-xs font-semibold uppercase tracking-widest text-slate-300 dark:text-slate-400">Navigation</div>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          {navItems.map((item) => (
            <Link
              key={item.name}
              to={item.path}
              className={`flex items-center w-full rounded-md px-3 py-2 text-sm font-medium transition ${
                location.pathname === item.path
                  ? "bg-slate-700 text-white shadow-sm ring-1 ring-inset ring-blue-300/40 dark:bg-slate-700 dark:text-white"
                  : "text-slate-200 hover:bg-slate-700/80 hover:text-white dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
              }`}
            >
              <span className="mr-3">{item.icon}</span>
              {item.name}
            </Link>
          ))}
        </nav>

        <div className="border-t border-slate-700/80 bg-slate-900 px-6 py-3 text-xs text-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
          {uiConfig.app_footer}
        </div>
      </aside>

      <main className="flex-1 flex flex-col bg-slate-100">
        <header className="flex items-center justify-between border-b border-slate-700 bg-slate-800 px-8 py-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center gap-3">
            <div className="inline-flex rounded-md border border-slate-200 bg-white p-1 shadow-sm">
              <img src={companyLogo} alt="Company logo" className="h-9 w-9" />
            </div>
            <h1 className="text-2xl font-semibold text-slate-100 dark:text-indigo-300">
              {uiConfig.platform_title}
            </h1>
          </div>
          <div className="flex items-center space-x-4">
            <button
              onClick={handleHeaderRefresh}
              className="inline-flex items-center justify-center rounded border border-slate-500 p-2 text-slate-100 hover:bg-slate-700 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              title="Refresh page"
              aria-label="Refresh page"
            >
              <RefreshCw size={16} className={refreshingHeader ? "animate-spin" : ""} />
            </button>
            <button
              onClick={() => setIsDarkMode((prev) => !prev)}
              className="inline-flex items-center justify-center rounded border border-slate-500 p-2 text-slate-100 hover:bg-slate-700 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              title={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
              aria-label={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
            >
              {isDarkMode ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <div className="text-sm text-slate-200 dark:text-slate-300">{userName}</div>
            <div className="w-8 h-8 rounded-full bg-indigo-500 flex items-center justify-center text-white dark:bg-indigo-300 dark:text-slate-900">
              {(userName[0] || "A").toUpperCase()}
            </div>
            <button
              onClick={onLogout}
              className="text-xs px-3 py-1.5 rounded border border-slate-500 text-slate-100 hover:bg-slate-700 dark:border-slate-700 dark:hover:bg-slate-800"
            >
              Logout
            </button>
          </div>
        </header>

        <section className="flex-1 overflow-y-auto bg-slate-100">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/rule-packs" element={<RulePacks />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
          </Routes>
        </section>
      </main>
    </div>
  );
}

export default function App() {
  const [uiConfig, setUiConfig] = useState({
    app_footer: "Zalaris Code Governance",
    platform_title: "Zalaris Code Governance Platform",
    default_user: "name@zalaris.com",
  });
  const [isAuthenticated, setIsAuthenticated] = useState(
    () => !!localStorage.getItem("hb_user_email")
  );
  const [userName, setUserName] = useState(
    () => localStorage.getItem("hb_user") || "name@zalaris.com"
  );

  useEffect(() => {
    const isDarkMode = localStorage.getItem("hb_theme") === "dark";
    document.documentElement.classList.toggle("dark", isDarkMode);
  }, []);

  useEffect(() => {
    let active = true;
    const loadUiConfig = async () => {
      try {
        const res = await fetch("/api/ui-config");
        if (!res.ok) return;
        const data = await res.json();
        if (!active) return;
        setUiConfig({
          app_footer: data?.app_footer || "Zalaris Code Governance",
          platform_title: data?.platform_title || "Zalaris Code Governance Platform",
          default_user: data?.default_user || "name@zalaris.com",
        });
        if (!localStorage.getItem("hb_user")) {
          setUserName(data?.default_user || "name@zalaris.com");
        }
      } catch {
        // keep defaults when backend config is unavailable
      }
    };
    void loadUiConfig();
    return () => {
      active = false;
    };
  }, []);

  function handleLogin(nextUserName: string, userEmail: string) {
    setIsAuthenticated(true);
    setUserName(nextUserName);
    localStorage.setItem("hb_user", nextUserName);
    localStorage.setItem("hb_user_email", userEmail);
  }

  function handleLogout() {
    setIsAuthenticated(false);
    localStorage.removeItem("hb_user");
    localStorage.removeItem("hb_user_email");
  }

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <Router>
      <AppShell uiConfig={uiConfig} userName={userName} onLogout={handleLogout} />
    </Router>
  );
}
