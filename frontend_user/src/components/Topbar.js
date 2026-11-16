import React, { useEffect, useMemo, useState } from 'react';
import { Bell, ChevronDown, Menu, Moon, Search, Sun } from 'react-feather';
import { useLocation, useNavigate } from 'react-router-dom';
import { accessibleNavSections, getUserDesignation, isSuperAdminUser } from '../navigation';

const Topbar = ({ currentUser, onMenu, onLogout, onOpenProfile, darkMode, onToggleTheme, onToggleSidebar, dashboardLabel }) => {
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState('');
  const location = useLocation();
  const navigate = useNavigate();
  const isSuperAdmin = isSuperAdminUser(currentUser?.role, currentUser?.is_superuser === true);
  const userDesignation = dashboardLabel || getUserDesignation(currentUser);
  const navigationAssignment = useMemo(() => ({
    ...currentUser?.active_assignment,
    department: currentUser?.active_assignment?.department || currentUser?.department,
    department_name: currentUser?.active_assignment?.department_name || currentUser?.department_name,
  }), [currentUser?.active_assignment, currentUser?.department, currentUser?.department_name]);
  const options = useMemo(() => [...new Map(
    accessibleNavSections(currentUser?.role, isSuperAdmin, currentUser?.dashboard_features || {}, navigationAssignment)
      .flatMap((section) => section.items)
      .filter((item) => item.action !== 'logout')
      .map((item) => [item.path, [item.label, item.path]]),
  ).values()].filter(([label]) => label.toLowerCase().includes(query.trim().toLowerCase())),
  [currentUser?.dashboard_features, currentUser?.role, isSuperAdmin, navigationAssignment, query]);
  const pageTitle = accessibleNavSections(currentUser?.role, isSuperAdmin, currentUser?.dashboard_features || {}, navigationAssignment)
    .flatMap((section) => section.items)
    .find((item) => item.path === location.pathname)?.label || 'Dashboard';

  useEffect(() => {
    const handleShortcut = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener('keydown', handleShortcut);
    return () => window.removeEventListener('keydown', handleShortcut);
  }, []);

  const goTo = (path) => {
    setSearchOpen(false);
    setQuery('');
    navigate(path);
  };

  const unreadCount = Number(currentUser?.unread_chat_count || 0);

  return <header className="app-topbar">
    <div className="topbar-left">
      <button className="menu-toggle" onClick={onMenu} aria-label="Open navigation">
        <Menu size={18} />
      </button>
      <button className="icon-button ghost" onClick={onToggleSidebar} aria-label="Collapse sidebar">
        <Menu size={18} />
      </button>
      <nav className="topbar-breadcrumbs" aria-label="Breadcrumb">
        <span>{dashboardLabel}</span>
        <span className="crumb-separator">/</span>
        <strong>{pageTitle}</strong>
      </nav>
    </div>

    <div className="topbar-actions">
      <button className="topbar-search" type="button" onClick={() => setSearchOpen((value) => !value)} aria-label="Open command palette">
        <Search size={15} aria-hidden="true" />
        <span>Search</span>
        <kbd>⌘K</kbd>
      </button>

      <button className="icon-button has-badge" onClick={() => navigate('/dashboard/chat')} aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`}>
        <Bell size={18} />
        {unreadCount > 0 && <span className="notif-badge">{unreadCount}</span>}
      </button>

      <button className="icon-button" onClick={onToggleTheme} aria-label={darkMode ? 'Use light theme' : 'Use dark theme'}>
        {darkMode ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      <button className="topbar-user" type="button" onClick={onOpenProfile} aria-label={`Edit profile for ${currentUser?.name || 'employee'}`}>
        <span className="topbar-avatar">{currentUser?.profile_photo_url ? <img src={currentUser.profile_photo_url} alt="" /> : (currentUser?.name || 'E').charAt(0).toUpperCase()}</span>
        <div className="topbar-user-meta">
          <span className="topbar-user-name">{currentUser?.name || 'Employee'}</span>
          <span className="topbar-user-role">{userDesignation}</span>
        </div>
        <ChevronDown size={14} />
      </button>

      <button className="sign-out-button" onClick={onLogout}>Sign out</button>
      {searchOpen && <div className="topbar-command-menu" role="dialog" aria-label="Dashboard search"><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search dashboard" />{options.length === 0 ? <p>No matching page.</p> : options.map(([label, path]) => <button type="button" key={path} onClick={() => goTo(path)}>{label}</button>)}</div>}
    </div>
  </header>;
};

export default Topbar;
