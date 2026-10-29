/**
 * QuantLens Terminal — Global Command Palette (Ctrl+K / Cmd+K)
 * Fast fuzzy search across all 12 screens, option strikes, and system commands.
 */

import React, { useState, useEffect } from 'react';
import { useTerminalStore } from '../stores/terminalStore';
import { WORKSPACES } from '../config/routes';
import { Search } from 'lucide-react';
import { WorkspaceId } from '../types';

export const CommandPalette: React.FC = () => {
  const store = useTerminalStore();
  const [query, setQuery] = useState('');

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        store.setCommandPalette(!store.commandPaletteOpen);
      }
      if (e.key === 'Escape' && store.commandPaletteOpen) {
        store.setCommandPalette(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [store.commandPaletteOpen]);

  if (!store.commandPaletteOpen) return null;

  const q = query.trim().toLowerCase();
  const filteredWorkspaces = WORKSPACES.filter(
    (w) => !q || w.label.toLowerCase().includes(q) || w.category.toLowerCase().includes(q)
  );

  return (
    <div
      className="cmd-palette-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) store.setCommandPalette(false);
      }}
      style={{ display: 'flex' }}
    >
      <div className="cmd-palette-modal">
        <div className="cmd-palette-header">
          <Search size={14} className="cmd-prompt-icon" />
          <input
            type="text"
            className="cmd-input"
            placeholder="Jump to workspace, search contract (e.g. 22950 CE), or type command..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <kbd className="cmd-esc-hint">ESC</kbd>
        </div>

        <div className="cmd-palette-body">
          <div className="cmd-results">
            {filteredWorkspaces.map((w) => (
              <div
                key={w.id}
                className="cmd-result-item"
                onClick={() => {
                  store.setActiveWorkspace(w.id);
                  store.setCommandPalette(false);
                }}
              >
                <div className="cmd-res-left">
                  <span className="cmd-res-tag">{w.category}</span>
                  <span className="cmd-res-title">{w.label}</span>
                </div>
                <div className="cmd-res-right">
                  <kbd className="cmd-shortcut-badge">[{w.shortcut}]</kbd>
                </div>
              </div>
            ))}

            <div className="cmd-section-divider">SYSTEM COMMANDS</div>

            <div
              className="cmd-result-item"
              onClick={() => {
                store.toggleKillSwitch();
                store.setCommandPalette(false);
              }}
            >
              <div className="cmd-res-left">
                <span className="cmd-res-tag">SAFETY</span>
                <span className="cmd-res-title">Toggle Execution Kill Switch</span>
              </div>
              <div className="cmd-res-right">
                <span className={store.killSwitchActive ? 'color-bear font-bold' : 'text-bull font-bold'}>
                  {store.killSwitchActive ? 'ACTIVE (HALTED)' : 'NOMINAL'}
                </span>
              </div>
            </div>

            <div
              className="cmd-result-item"
              onClick={() => {
                store.toggleDensity();
                store.setCommandPalette(false);
              }}
            >
              <div className="cmd-res-left">
                <span className="cmd-res-tag">UI</span>
                <span className="cmd-res-title">Toggle Terminal Density (Compact / Normal)</span>
              </div>
              <div className="cmd-res-right">
                <span>{store.density.toUpperCase()}</span>
              </div>
            </div>

            <div
              className="cmd-result-item"
              onClick={() => {
                store.toggleTheme();
                store.setCommandPalette(false);
              }}
            >
              <div className="cmd-res-left">
                <span className="cmd-res-tag">UI</span>
                <span className="cmd-res-title">Toggle Dark / Light Mode</span>
              </div>
              <div className="cmd-res-right">
                <span>{store.theme.toUpperCase()}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="cmd-palette-footer">
          <span>↑↓ Navigate</span>
          <span>↵ Select</span>
          <span>ESC Close</span>
          <span>[1..9, 0, -, =] Direct Switch</span>
        </div>
      </div>
    </div>
  );
};

