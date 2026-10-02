/**
 * Global Command Palette (Ctrl+K / Cmd+K)
 * Fast fuzzy search across screens, symbols, options strikes, actions, and terminal commands.
 */

import { ROUTES } from '../config.js';
import { terminalStore } from '../stores/terminalStore.js';

export function renderCommandPalette(container) {
  function update() {
    const s = terminalStore.getState();
    if (!s.commandPaletteOpen) {
      container.innerHTML = '';
      container.style.display = 'none';
      return;
    }

    container.style.display = 'flex';
    container.innerHTML = `
      <div class="cmd-palette-backdrop" id="cmd-backdrop">
        <div class="cmd-palette-modal">
          <div class="cmd-palette-header">
            <span class="cmd-prompt-icon">›</span>
            <input type="text" id="cmd-input" class="cmd-input" placeholder="Jump to screen, search strike (e.g. 22400 CE), or type command..." autofocus />
            <kbd class="cmd-esc-hint">ESC</kbd>
          </div>
          <div class="cmd-palette-body">
            <div class="cmd-results" id="cmd-results-list"></div>
          </div>
          <div class="cmd-palette-footer">
            <span>↑↓ Navigate</span>
            <span>↵ Select</span>
            <span>ESC Close</span>
            <span>[1..6] Fast Key</span>
          </div>
        </div>
      </div>
    `;

    const input = container.querySelector('#cmd-input');
    const resultsContainer = container.querySelector('#cmd-results-list');
    const backdrop = container.querySelector('#cmd-backdrop');

    backdrop.onclick = (e) => {
      if (e.target === backdrop) terminalStore.setCommandPalette(false);
    };

    function populateResults(query = '') {
      const q = query.trim().toLowerCase();
      let matches = [];

      // 1. Screens
      ROUTES.forEach(r => {
        if (!q || r.label.toLowerCase().includes(q) || r.category.toLowerCase().includes(q)) {
          matches.push({
            type: 'SCREEN',
            title: r.label,
            category: r.category,
            shortcut: r.shortcut ? `[${r.shortcut}]` : '',
            action: () => {
              terminalStore.setActiveRoute(r.id);
              terminalStore.setCommandPalette(false);
            }
          });
        }
      });

      // 2. Options Strike parser (e.g. "22400 CE" or "22500")
      const strikeMatch = q.match(/(\d{5})\s*(ce|pe)?/);
      if (strikeMatch) {
        const strike = parseInt(strikeMatch[1]);
        const type = (strikeMatch[2] || 'ce').toLowerCase();
        matches.unshift({
          type: 'OPTION',
          title: `NIFTY ${strike} ${type.toUpperCase()}`,
          category: 'INSPECT OPTION',
          shortcut: '↵',
          action: () => {
            terminalStore.openOptionDetail({
              strike,
              type,
              ltp: 303.0,
              fairPrice: 92.65,
              iv: 0.158,
              mScore: 3.74,
              mispricingPct: 227.0,
            });
            terminalStore.setCommandPalette(false);
          }
        });
      }

      // 3. Quick Actions
      const actions = [
        { title: 'Academic Evaluation Walkthrough', category: 'GUIDED TOUR', action: () => { terminalStore.setEvaluationModal(true); terminalStore.setCommandPalette(false); } },
        { title: 'Toggle Theme (Dark / Light)', category: 'APPEARANCE', action: () => { terminalStore.toggleTheme(); terminalStore.setCommandPalette(false); } },
        { title: 'Toggle Density (Compact / Normal)', category: 'APPEARANCE', action: () => { terminalStore.toggleDensity(); terminalStore.setCommandPalette(false); } },
        { title: 'Export Current View to CSV', category: 'DATA EXPORT', action: () => { alert('Exporting dataset to CSV...'); terminalStore.setCommandPalette(false); } },
      ];

      actions.forEach(a => {
        if (!q || a.title.toLowerCase().includes(q) || a.category.toLowerCase().includes(q)) {
          matches.push({ ...a, type: 'ACTION', shortcut: '⌘' });
        }
      });

      if (matches.length === 0) {
        resultsContainer.innerHTML = `<div class="cmd-no-results">No matching commands or strikes for "${query}"</div>`;
        return;
      }

      resultsContainer.innerHTML = matches.slice(0, 10).map((m, idx) => `
        <div class="cmd-result-item ${idx === 0 ? 'selected' : ''}" data-idx="${idx}">
          <div class="cmd-result-left">
            <span class="cmd-type-tag tag-${m.type.toLowerCase()}">${m.type}</span>
            <span class="cmd-result-title">${m.title}</span>
            <span class="cmd-result-category">${m.category}</span>
          </div>
          <span class="cmd-result-shortcut">${m.shortcut || ''}</span>
        </div>
      `).join('');

      resultsContainer.querySelectorAll('.cmd-result-item').forEach(el => {
        el.onclick = () => {
          const idx = parseInt(el.getAttribute('data-idx'));
          matches[idx]?.action();
        };
      });
    }

    input.oninput = (e) => populateResults(e.target.value);
    populateResults();

    input.focus();
  }

  terminalStore.subscribe(update);
  update();
}
