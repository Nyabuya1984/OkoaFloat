import React, { useEffect, useMemo, useState } from 'react';
import { Bell, ChevronDown, Menu, Moon, Search, Sun } from 'react-feather';

const Topbar = ({ currentUser, onMenu, onLogout, onOpenProfile, onNavigate, darkMode, onToggleTheme, onToggleSidebar, dashboardLabel }) => {
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState('');
  const role = String(currentUser?.role || 'employee').toLowerCase();
  const canViewCalendar = role === 'manager' || role === 'hr_admin' || role === 'system_admin' || role === 'super_admin';
  const options = useMemo(() => [
    ['Dashboard', 'dashboard'], ['Apply for leave', 'apply-leave'], ['My leave', 'my-leave'],
    ['Leave history', 'history'], ['Handover report', 'delegations'], ...(canViewCalendar ? [['Team calendar', 'team-calendar']] : []),
    ['Sales reports', 'sales-reports'], ['Edit profile', 'profile'],
  ].filter(([label]) => label.toLowerCase().includes(query.trim().toLowerCase())), [canViewCalendar, query]);

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

  const goTo = (section) => {
    setSearchOpen(false);
    setQuery('');
    onNavigate?.(section, `/dashboard#${section}`);
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
        <strong>Dashboard</strong>
      </nav>
    </div>

    <div className="topbar-actions">
      <button className="topbar-search" type="button" onClick={() => setSearchOpen((value) => !value)} aria-label="Open command palette">
        <Search size={15} aria-hidden="true" />
        <span>Search</span>
        <kbd>⌘K</kbd>
      </button>

      <button className="icon-button has-badge" onClick={() => onNavigate?.('chat', '/dashboard#chat')} aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`}>
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
          <span className="topbar-user-role">{currentUser?.role || 'employee'}</span>
        </div>
        <ChevronDown size={14} />
      </button>

      <button className="sign-out-button" onClick={onLogout}>Sign out</button>
      {searchOpen && <div className="topbar-command-menu" role="dialog" aria-label="Dashboard search"><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search dashboard" />{options.length === 0 ? <p>No matching section.</p> : options.map(([label, section]) => <button type="button" key={section} onClick={() => goTo(section)}>{label}</button>)}</div>}
    </div>
  </header>;
};

export default Topbar;
