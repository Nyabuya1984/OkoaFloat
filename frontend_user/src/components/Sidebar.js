import React from 'react';
import { NavLink } from 'react-router-dom';
import { accessibleNavSections } from '../navigation';

const Sidebar = ({ isOpen, isCollapsed, onClose, onToggleCollapse, currentUser, onLogout, onNavigate }) => {
  const sections = accessibleNavSections(currentUser?.role || 'employee', currentUser?.is_superuser === true);
  const logoutItem = sections.flatMap((section) => section.items).find((item) => item.action === 'logout');
  const LogoutIcon = logoutItem?.icon;

  const getBadge = (badgeType) => {
    if (badgeType === 'unread') return currentUser?.unread_chat_count;
    if (badgeType === 'pendingApprovals') return currentUser?.pending_approval_count;
    return null;
  };

  return (
    <>
      <button className={`shell-backdrop ${isOpen ? 'visible' : ''}`} aria-label="Close navigation" onClick={onClose} type="button" />
      <aside className={`app-sidebar ${isOpen ? 'open' : ''} ${isCollapsed ? 'collapsed' : ''}`} aria-label="Primary navigation">
        <div className="sidebar-brand">
          <button className="sidebar-collapse-toggle" type="button" onClick={onToggleCollapse} aria-label="Toggle sidebar">
            <span aria-hidden="true">◀</span>
          </button>
          <div className="brand-mark"><img src="/Okoafloat.png" alt="Okoa Float" className="brand-logo" /></div>
        </div>
        <nav className="sidebar-nav" aria-label="Sidebar navigation">
          {sections.map((sectionGroup) => (
            <React.Fragment key={sectionGroup.title}>
              {!isCollapsed && <div className="nav-label">{sectionGroup.title}</div>}
              {sectionGroup.items.filter((item) => item.action !== 'logout').map((item) => {
                const { label, icon: Icon, path, action, section, badge } = item;
                const count = getBadge(badge);

                if (action === 'logout') {
                  return (
                    <button key={path || label} className="sidebar-link sidebar-button" type="button" onClick={onLogout} aria-label={label}>
                      <Icon size={16} aria-hidden="true" />
                      <span>{label}</span>
                    </button>
                  );
                }

                // If the item triggers a section state in LeaveDashboard (e.g. section: 'apply-leave')
                if (section) {
                  return (
                    <button
                      key={path || label}
                      className="sidebar-link sidebar-button"
                      type="button"
                      onClick={() => {
                        onNavigate?.(section, path);
                        onClose();
                      }}
                      aria-label={label}
                    >
                      <Icon size={16} aria-hidden="true" />
                      <span>{label}</span>
                      {count ? <span className="sidebar-badge" aria-label={`${count} pending`}>{count}</span> : null}
                    </button>
                  );
                }

                // Standard React Router Navigation
                return (
                  <NavLink
                    key={path}
                    to={path}
                    end={path === '/dashboard' || path === '/hr'}
                    className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
                    onClick={onClose}
                    aria-label={label}
                  >
                    <Icon size={16} aria-hidden="true" />
                    <span>{label}</span>
                    {count ? <span className="sidebar-badge" aria-label={`${count} pending`}>{count}</span> : null}
                  </NavLink>
                );
              })}
            </React.Fragment>
          ))}
        </nav>
        {logoutItem && <div className="sidebar-footer"><button type="button" className="sidebar-link sidebar-button sidebar-logout" onClick={onLogout} aria-label={logoutItem.label}><LogoutIcon size={16} aria-hidden="true" /><span>{logoutItem.label}</span></button></div>}
      </aside>
    </>
  );
};

export default Sidebar;