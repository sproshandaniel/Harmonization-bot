import { useEffect, useState } from "react";
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from "react-router-dom";
import { Home, Settings, BarChart2, FileText, FolderKanban, RefreshCw, Moon, Sun } from "lucide-react";
import Dashboard from "./Pages/Dashboard";
import RulePacks from "./Pages/RulePacks";
import Analytics from "./Pages/Analytics";
import SettingsPage from "./Pages/Settings";
import ProjectsPage from "./Pages/ProjectsPage";
import Login from "./Pages/Login";
import companyLogo from "./assets/company-logo.png";

function AppShell({
  uiConfig,
  userName,
  onLogout,
  themeName,
  onThemeChange,
}: {
  uiConfig: { app_footer: string; platform_title: string };
  userName: string;
  onLogout: () => void;
  themeName: string;
  onThemeChange: (value: string) => void;
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
    <div className="hb-shell">
      <aside className="hb-sidebar">
        <div className="hb-sidebar-head">
          <div className="hb-sidebar-label">Navigation</div>
        </div>
        <nav className="flex-1 space-y-2 p-4">
          {navItems.map((item) => (
            <Link
              key={item.name}
              to={item.path}
              className={`hb-nav-link ${
                location.pathname === item.path
                  ? "hb-nav-link-active"
                  : "hb-nav-link-idle"
              }`}
            >
              <span className="mr-3">{item.icon}</span>
              {item.name}
            </Link>
          ))}
        </nav>

        <div className="hb-sidebar-footer">
          {uiConfig.app_footer}
        </div>
      </aside>

      <main className="hb-main">
        <header className="hb-header">
          <div className="flex items-center gap-3">
            <div className="hb-logo-wrap">
              <img src={companyLogo} alt="Company logo" className="h-12 w-12 object-contain" />
            </div>
            <h1 className="hb-title">
              {uiConfig.platform_title}
            </h1>
          </div>
          <div className="flex items-center space-x-4">
            <button
              onClick={handleHeaderRefresh}
              className="hb-icon-btn"
              title="Refresh page"
              aria-label="Refresh page"
            >
              <RefreshCw size={16} className={refreshingHeader ? "animate-spin" : ""} />
            </button>
            <button
              onClick={() => setIsDarkMode((prev) => !prev)}
              className="hb-icon-btn"
              title={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
              aria-label={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
            >
              {isDarkMode ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <div className="hb-user-name">{userName}</div>
            <div className="hb-avatar">
              {(userName[0] || "A").toUpperCase()}
            </div>
            <button
              onClick={onLogout}
              className="hb-logout-btn"
            >
              Logout
            </button>
          </div>
        </header>

        <section className="hb-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/rule-packs" element={<RulePacks />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route
              path="/settings"
              element={<SettingsPage themeName={themeName} onThemeChange={onThemeChange} />}
            />
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
  const [themeName, setThemeName] = useState(
    () => localStorage.getItem("hb_theme_name") || "aurora"
  );

  useEffect(() => {
    const isDarkMode = localStorage.getItem("hb_theme") === "dark";
    document.documentElement.classList.toggle("dark", isDarkMode);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", themeName);
    localStorage.setItem("hb_theme_name", themeName);
  }, [themeName]);

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
      <AppShell
        uiConfig={uiConfig}
        userName={userName}
        onLogout={handleLogout}
        themeName={themeName}
        onThemeChange={setThemeName}
      />
    </Router>
  );
}


