/**
 * Left Terminal Navigation Component
 * Dense, keyboard-accessible hierarchical navigation with Bloomberg-style category headers.
 */

import { ROUTES } from '../config.js';
import { terminalStore } from '../stores/terminalStore.js';

export function renderSidebar(container) {
  function update() {
    const s = terminalStore.getState();
    const active = s.activeRoute;

    // Group routes by category
    const categories = ['MARKET', 'OPTIONS', 'QUANT', 'STRATEGIES', 'PORTFOLIO', 'BACKTEST', 'RESEARCH', 'SYSTEM'];

    let html = `
      <div class="sidebar-inner">
        <div class="sidebar-header">
          <span class="sidebar-title">WORKSPACES</span>
          <button class="sidebar-collapse-btn" id="btn-collapse-sidebar" title="Toggle Sidebar">«</button>
        </div>
        <nav class="sidebar-nav">
    `;

    categories.forEach(cat => {
      const catRoutes = ROUTES.filter(r => r.category === cat);
      if (catRoutes.length === 0) return;

      html += `
        <div class="nav-category-group">
          <div class="nav-category-title">${cat}</div>
          <ul class="nav-item-list">
      `;

      catRoutes.forEach(route => {
        const isSelected = active === route.id;
        html += `
          <li class="nav-item ${isSelected ? 'active' : ''}" data-route="${route.id}">
            <span class="nav-item-text">${route.label}</span>
            ${route.shortcut ? `<span class="nav-shortcut">[${route.shortcut}]</span>` : ''}
          </li>
        `;
      });

      html += `
          </ul>
        </div>
      `;
    });

    html += `
        </nav>
        <div class="sidebar-footer">
          <div class="active-profile-info">
            <span class="profile-label">FEED:</span>
            <span class="profile-val text-amber">NIFTY 50 LIVE</span>
          </div>
          <div class="shortcut-legend">
            <span>[1..6] Quick Jump</span>
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
