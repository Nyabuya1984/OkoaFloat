import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import { getUserDesignation } from '../navigation';

const AppShell = ({ children, currentUser, onLogout, dashboardFeatures, featureError }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('okoa_theme') === 'dark');
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
    localStorage.setItem('okoa_theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  useEffect(() => {
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    setSidebarOpen(false);
  }, [location.pathname]);

  const dashboardLabel = getUserDesignation(currentUser);
  const shellUser = {
    ...currentUser,
    active_assignment: currentUser?.active_assignment,
    dashboard_features: dashboardFeatures || currentUser?.dashboard_features || {},
  };

  return (
    <div className={`app-shell ${darkMode ? 'dark-shell' : ''}`}>
      <Sidebar
        isOpen={sidebarOpen}
        isCollapsed={sidebarCollapsed}
        onClose={() => setSidebarOpen(false)}
        onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
        onLogout={onLogout}
        currentUser={shellUser}
      />
      <div className={`app-shell-content ${sidebarCollapsed ? 'sidebar-collapsed' : ''} ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <div className="role-banner">{dashboardLabel} Dashboard</div>
        <Topbar
          currentUser={shellUser}
          onOpenProfile={() => navigate('/dashboard/profile/edit')}
          onMenu={() => setSidebarOpen(true)}
          onLogout={onLogout}
          darkMode={darkMode}
          onToggleTheme={() => setDarkMode((value) => !value)}
          onToggleSidebar={() => setSidebarCollapsed((value) => !value)}
          dashboardLabel={dashboardLabel}
        />
        <div className="app-shell-body">
          {featureError && <div className="leave-alert error" role="alert">{featureError}</div>}
          {children}
        </div>
      </div>
    </div>
  );
};

export default AppShell;
