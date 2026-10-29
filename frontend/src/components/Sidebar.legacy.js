/**
 * frontend/src/components/Sidebar.js
 * ================================================================================
 * Left Terminal Navigation Component
 * Streamlined, high-density Bloomberg-style workspace switcher.
 * Provides immediate access to the 5 core quantitative workspaces with zero clutter.
 * ================================================================================
 */

import { ROUTES } from '../config.js';
import { terminalStore } from '../stores/terminalStore.js';

export function renderSidebar(container) {
  function update() {
    const s = terminalStore.getState();
    const active = s.activeRoute;

    let html = `
      <div class="sidebar-inner">
        <div class="sidebar-header">
          <span class="sidebar-title">QUANT WORKSPACES</span>
          <button class="sidebar-collapse-btn" id="btn-collapse-sidebar" title="Toggle Sidebar">«</button>
        </div>
        <nav class="sidebar-nav">
          <div class="nav-category-group">
            <div class="nav-category-title">CORE MODULES</div>
            <ul class="nav-item-list">
    `;

    ROUTES.forEach(route => {
      const isSelected = active === route.id;
      html += `
        <li class="nav-item ${isSelected ? 'active' : ''}" data-route="${route.id}">
          <span class="nav-item-icon">${route.icon || '⚡'}</span>
          <span class="nav-item-text">${route.label}</span>
          ${route.shortcut ? `<span class="nav-shortcut">[${route.shortcut}]</span>` : ''}
        </li>
      `;
    });

    html += `
            </ul>
          </div>
        </nav>
        <div class="sidebar-footer">
          <div class="active-profile-info">
            <span class="profile-label">ENGINE:</span>
            <span class="profile-val text-amber">NSE LIVE (pnsea)</span>
          </div>
          <div class="shortcut-legend">
            <span>[1..7] Direct Switch</span>
          </div>
        </div>
      </div>
    `;

    container.innerHTML = html;

    // Bind click events
    container.querySelectorAll('.nav-item').forEach(el => {
      el.onclick = () => {
        const routeId = el.getAttribute('data-route');
        if (routeId) terminalStore.setActiveRoute(routeId);
      };
    });

    const collapseBtn = container.querySelector('#btn-collapse-sidebar');
    if (collapseBtn) {
      collapseBtn.onclick = () => {
        const cur = terminalStore.getState().sidebarCollapsed;
        terminalStore.setState({ sidebarCollapsed: !cur });
      };
    }
  }

  terminalStore.subscribe(update);
  update();
}
