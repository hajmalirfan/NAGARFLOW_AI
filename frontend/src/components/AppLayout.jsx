import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { can, ROLE_LABELS } from "../auth/permissions.js";
import { BrandMark } from "./common.jsx";
import ErrorBoundary from "./ErrorBoundary.jsx";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: "grid", permission: "dashboard.read" },
  { to: "/scenarios", label: "Scenarios", icon: "layers", permission: "records.read" },
  { to: "/depot", label: "Depot Management", icon: "home", permission: "records.read" },
  { to: "/vehicles", label: "Vehicles", icon: "truck", permission: "records.read" },
  { to: "/storage-points", label: "Storage Points", icon: "pin", permission: "records.read" },
  { to: "/facility", label: "Processing Facility", icon: "factory", permission: "records.read" },
  { to: "/route-optimization", label: "Route Optimization", icon: "route", permission: "optimization.read" },
  { to: "/route-preview", label: "Route Preview", icon: "route", permission: "scenarios.names" },
  { to: "/history", label: "History", icon: "clock", permission: "history.read" },
  { to: "/reports", label: "Reports", icon: "chart", permission: "reports.read" },
  { to: "/team", label: "Team", icon: "layers", permission: "team.manage" },
  { to: "/settings", label: "Settings", icon: "cog" },
];

const ICON_PATHS = {
  grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  layers: "M12 3 3 8l9 5 9-5zM3 13l9 5 9-5",
  home: "M4 11 12 4l8 7M6 10v10h12V10",
  truck: "M3 7h11v9H3zM14 11h4l3 3v2h-7M6.5 19.5a1.6 1.6 0 1 0 0-3.2 1.6 1.6 0 0 0 0 3.2M17.5 19.5a1.6 1.6 0 1 0 0-3.2 1.6 1.6 0 0 0 0 3.2",
  factory: "M4 20V10l5 3V10l5 3V8l5 3v9zM4 20h16",
  pin: "M12 21s6.5-6.1 6.5-11A6.5 6.5 0 0 0 5.5 10c0 4.9 6.5 11 6.5 11m0-9.2a1.9 1.9 0 1 0 0-3.8 1.9 1.9 0 0 0 0 3.8",
  route: "M6 4.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4M18 15.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4M6 8.5v3a3 3 0 0 0 3 3h6a3 3 0 0 1 3 3",
  chart: "M4 20V5m0 15h16M8 20v-6m4 6V9m4 11v-8",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M12 7v5l3 2",
  cog: "M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2 2 2 0 1 1-4 0 1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3 15a2 2 0 1 1 0-4 1.7 1.7 0 0 0 1.3-2.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 10 4a2 2 0 1 1 4 0 1.7 1.7 0 0 0 2.9 1.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1A1.7 1.7 0 0 0 21 11a2 2 0 1 1 0 4 1.7 1.7 0 0 0-1.6 0z",
};

function NavIcon({ name }) {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d={ICON_PATHS[name]}
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Sidebar({ user, isOpen, onNavigate, onSignOut }) {
  return (
    <aside className={`sidebar${isOpen ? " sidebar-open" : ""}`} id="main-sidebar">
      <div className="sidebar-brand">
        <BrandMark />
      </div>
      <nav className="sidebar-nav" aria-label="Main navigation">
        {NAV_ITEMS.filter((item) => !item.permission || can(user, item.permission)).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`}
            onClick={onNavigate}
          >
            <NavIcon name={item.icon} />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        <button type="button" className="nav-link nav-logout" onClick={onSignOut}>
          <svg className="nav-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M15 17l5-5-5-5M20 12H9M12 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
}

function TopNav({ user, onToggleSidebar, isSidebarOpen, onSignOut }) {
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [search, setSearch] = useState("");
  const initial = user.name.trim().charAt(0).toUpperCase() || "?";

  return (
    <header className="topnav">
      <button
        type="button"
        className="sidebar-toggle"
        onClick={onToggleSidebar}
        aria-label={isSidebarOpen ? "Close navigation" : "Open navigation"}
        aria-expanded={isSidebarOpen}
        aria-controls="main-sidebar"
      >
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      </button>

      <div className="mobile-topnav-brand"><BrandMark /></div>

      <form className="topnav-search" role="search" onSubmit={(event) => event.preventDefault()}>
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.7" />
          <path d="m16 16 4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search scenarios, vehicles, storage points…"
          aria-label="Search"
        />
      </form>

      <div className="topnav-actions">
        <button type="button" className="icon-button" aria-label="Notifications">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M18 15.5V11a6 6 0 1 0-12 0v4.5L4.5 18h15zM10 21h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>

        <div className="profile-wrap">
          <button
            type="button"
            className="profile-button"
            onClick={() => setIsProfileOpen((open) => !open)}
            aria-expanded={isProfileOpen}
          >
            <span className="profile-avatar">{initial}</span>
            <span className="profile-text">
              <strong>{user.name}</strong>
              <small>{ROLE_LABELS[user.role]}</small>
            </span>
            <svg className="profile-chevron" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="m7 10 5 5 5-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          {isProfileOpen && (
            <div className="profile-menu" role="menu">
              <div className="profile-menu-head">
                <strong>{user.name}</strong>
                <small>{user.email}</small>
              </div>
              <button type="button" role="menuitem" onClick={onSignOut}>Sign out</button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

export default function AppLayout() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setIsSidebarOpen(false);
  }, [location.pathname]);

  function handleSignOut() {
    signOut();
    navigate("/login", { replace: true });
  }

  return (
    <div className="app-shell">
      <Sidebar
        user={user}
        isOpen={isSidebarOpen}
        onNavigate={() => setIsSidebarOpen(false)}
        onSignOut={handleSignOut}
      />
      {isSidebarOpen && (
        <button
          type="button"
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}
      <div className="app-main">
        <TopNav
          user={user}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen((open) => !open)}
          onSignOut={handleSignOut}
        />
        <main className="app-content">
          <ErrorBoundary key={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
