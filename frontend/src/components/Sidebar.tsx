/**
 * QuantLens Terminal — Left Workstation Navigation
 * Streamlined Bloomberg-grade workspace selector for all 12 modules.
 */

import React from 'react';
import { useTerminalStore } from '../stores/terminalStore';
import { WORKSPACES } from '../config/routes';
import {
  LayoutDashboard,
  Grid,
  Activity,
  Crosshair,
  Cpu,
  FlaskConical,
  Radio,
  Terminal,
  BookOpen,
  ShieldAlert,
  Workflow,
  Archive,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

const iconMap: Record<string, React.ReactNode> = {
  LayoutDashboard: <LayoutDashboard size={14} />,
  Grid: <Grid size={14} />,
  Activity: <Activity size={14} />,
  Crosshair: <Crosshair size={14} />,
  Cpu: <Cpu size={14} />,
  FlaskConical: <FlaskConical size={14} />,
  Radio: <Radio size={14} />,
  Terminal: <Terminal size={14} />,
  BookOpen: <BookOpen size={14} />,
  ShieldAlert: <ShieldAlert size={14} />,
  Workflow: <Workflow size={14} />,
  Archive: <Archive size={14} />
};

export const Sidebar: React.FC = () => {
  const store = useTerminalStore();
  const active = store.activeWorkspace;

  // Group by category
  const categories = ['CORE', 'OPTIONS', 'RESEARCH', 'EXECUTION', 'OPERATIONS'] as const;

  return (
    <div className={`sidebar-inner ${store.sidebarCollapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        {!store.sidebarCollapsed && <span className="sidebar-title">QUANT WORKSPACES</span>}
        <button
          className="sidebar-collapse-btn"
          onClick={store.toggleSidebar}
          title="Toggle Sidebar Collapse"
        >
          {store.sidebarCollapsed ? <ChevronRight size={13} /> : <ChevronLeft size={13} />}
        </button>
      </div>

      <nav className="sidebar-nav">
        {categories.map((cat) => {
          const routesInCat = WORKSPACES.filter((r) => r.category === cat);
          if (routesInCat.length === 0) return null;

          return (
            <div key={cat} className="nav-category-group">
              {!store.sidebarCollapsed && <div className="nav-category-title">{cat}</div>}
              <ul className="nav-item-list">
                {routesInCat.map((route) => {
                  const isSelected = active === route.id;
                  return (
                    <li
                      key={route.id}
                      className={`nav-item ${isSelected ? 'active' : ''}`}
                      onClick={() => store.setActiveWorkspace(route.id)}
                      title={route.description}
                    >
                      <span className="nav-item-icon">{iconMap[route.iconName] || '⚡'}</span>
                      {!store.sidebarCollapsed && (
                        <>
                          <span className="nav-item-text">{route.label}</span>
                          <span className="nav-shortcut">[{route.shortcut}]</span>
                        </>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      {!store.sidebarCollapsed && (
        <div className="sidebar-footer">
          <div className="active-profile-info">
            <span className="profile-label">ENGINE:</span>
            <span className="profile-val text-amber font-mono font-bold">
              {store.marketData.feedMode === 'NSE_LIVE' ? 'NSE LIVE (pnsea)' : 'SIMULATION'}
            </span>
          </div>
          <div className="shortcut-legend">
            <span>[1..9, 0, -, =] Direct Switch</span>
          </div>
        </div>
      )}
    </div>
  );
};

