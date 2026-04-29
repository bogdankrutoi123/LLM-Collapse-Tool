import { NavLink } from "react-router-dom";
import { Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { canViewRules } from "../auth/permissions";

const navSections = [
  {
    title: "Dashboard",
    items: [
      { to: "/overview", label: "Overview" },
      { to: "/benchmark", label: "Benchmark" },
      { to: "/analysis", label: "Analysis" }
    ]
  },
  {
    title: "Data",
    items: [
      { to: "/models", label: "Models" },
      { to: "/prompts", label: "Prompts" }
    ]
  },
  {
    title: "Alerts",
    items: [
      { to: "/rules", label: "Alert Rules", hiddenForNonAdmins: true },
      { to: "/thresholds", label: "Thresholds", hiddenForNonAdmins: true },
      { to: "/notifications", label: "Notifications" }
    ]
  },
  {
    title: "Admin",
    items: [
      { to: "/users", label: "Users", hiddenForNonAdmins: true },
      { to: "/audit", label: "Audit Logs", hiddenForNonAdmins: true }
    ]
  }
];

export default function Layout() {
  const { user, logout } = useAuth();
  const showRules = canViewRules(user);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>LLM Collapse Detector</h1>
        {navSections.map((section) => (
          <div key={section.title} className="nav-section">
            <div className="nav-section-title">{section.title}</div>
            <div className="nav-section-list">
              {section.items.map((item) => (
                (item.hiddenForNonAdmins && !showRules) ? null : (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    isActive ? "nav-link active" : "nav-link"
                  }
                >
                  {item.label}
                </NavLink>
                )
              ))}
            </div>
          </div>
        ))}
      </aside>
      <main className="content">
        <div className="topbar">
          <div>
            <strong>{user?.username || "User"}</strong>
            <div className="small">{user?.role || ""}</div>
          </div>
          <button className="button secondary" onClick={logout}>Logout</button>
        </div>
        <Outlet />
      </main>
    </div>
  );
}
