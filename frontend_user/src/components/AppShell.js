import React, { useEffect, useState } from 'react';
import Sidebar from './Sidebar';
import Topbar from './Topbar';

const AppShell = ({ children, currentUser, onOpenProfile, onLogout, onNavigate }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('okoa_theme') === 'dark');

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
    localStorage.setItem('okoa_theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  const role = String(currentUser?.role || 'employee').toLowerCase();
  const dashboardLabel = role === 'super_admin' && currentUser?.is_superuser ? 'Super Admin' : role === 'system_admin' ? 'System Admin' : role === 'hr_admin' ? 'HR Admin' : role === 'manager' ? 'Manager' : 'Employee';

  return (
    <div className={`app-shell ${darkMode ? 'dark-shell' : ''}`}>
      <Sidebar
        isOpen={sidebarOpen}
        isCollapsed={sidebarCollapsed}
        onClose={() => setSidebarOpen(false)}
        onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
        onLogout={onLogout}
        onNavigate={onNavigate}
        currentUser={currentUser}
      />
      <div className={`app-shell-content ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
        <Topbar
          currentUser={currentUser}
          onOpenProfile={onOpenProfile}
          onMenu={() => setSidebarOpen(true)}
          onLogout={onLogout}
          darkMode={darkMode}
          onToggleTheme={() => setDarkMode((value) => !value)}
          onToggleSidebar={() => setSidebarCollapsed((value) => !value)}
          dashboardLabel={dashboardLabel}
          onNavigate={onNavigate}
        />
        <div className="app-shell-body">{children}</div>
      </div>
    </div>
  );
};

export default AppShell;
