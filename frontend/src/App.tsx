import React, { useEffect } from 'react';
import { useTerminalStore } from './stores/terminalStore';
import { websocketService } from './services/websocket';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { StatusBar } from './components/StatusBar';
import { CommandPalette } from './components/CommandPalette';
import { ContractDetailDrawer } from './components/ContractDetailDrawer';

// Workspaces
import { OverviewWorkspace } from './workspaces/OverviewWorkspace';
import { OptionsChainWorkspace } from './workspaces/OptionsChainWorkspace';
import { VolatilityLabWorkspace } from './workspaces/VolatilityLabWorkspace';
import { MispricingScannerWorkspace } from './workspaces/MispricingScannerWorkspace';
import { StrategyLabWorkspace } from './workspaces/StrategyLabWorkspace';
import { BacktestingWorkspace } from './workspaces/BacktestingWorkspace';
import { MarketMonitorWorkspace } from './workspaces/MarketMonitorWorkspace';
import { PaperTradingWorkspace } from './workspaces/PaperTradingWorkspace';
import { HistoricalLedgerWorkspace } from './workspaces/HistoricalLedgerWorkspace';
import { RiskPortfolioWorkspace } from './workspaces/RiskPortfolioWorkspace';
import { PipelineFlowWorkspace } from './workspaces/PipelineFlowWorkspace';
import { ModelRegistryWorkspace } from './workspaces/ModelRegistryWorkspace';
import { WorkspaceId } from './types';

export const App: React.FC = () => {
  const {
    activeWorkspace,
    setActiveWorkspace,
    theme,
    density,
    sidebarCollapsed
  } = useTerminalStore();

  // Initialize WebSocket tick streaming on mount
  useEffect(() => {
    websocketService.connect();
    return () => {
      websocketService.disconnect();
    };
  }, []);

  // Synchronize document root theme and density attributes
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-density', density);
  }, [theme, density]);

  // Global Keyboard Shortcuts (Workstation Hotkeys 1-9, 0, -, =)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if user is currently typing in an input, textarea, or select
      const activeEl = document.activeElement;
      if (
        activeEl &&
        (activeEl.tagName === 'INPUT' ||
          activeEl.tagName === 'TEXTAREA' ||
          activeEl.tagName === 'SELECT' ||
          (activeEl as HTMLElement).isContentEditable)
      ) {
        return;
      }

      if (e.ctrlKey || e.metaKey || e.altKey) return;

      const shortcutMap: Record<string, WorkspaceId> = {
        '1': 'overview',
        '2': 'option-chain',
        '3': 'volatility-lab',
        '4': 'mispricing-scanner',
        '5': 'strategy-lab',
        '6': 'backtesting',
        '7': 'market-monitor',
        '8': 'paper-terminal',
        '9': 'historical-ledger',
        '0': 'risk-portfolio',
        '-': 'pipeline-operations',
        '=': 'model-registry'
      };

      if (shortcutMap[e.key]) {
        e.preventDefault();
        setActiveWorkspace(shortcutMap[e.key]);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setActiveWorkspace]);

  // Workspace View Renderer
  const renderWorkspace = () => {
    switch (activeWorkspace) {
      case 'overview':
        return <OverviewWorkspace />;
      case 'option-chain':
        return <OptionsChainWorkspace />;
      case 'volatility-lab':
        return <VolatilityLabWorkspace />;
      case 'mispricing-scanner':
        return <MispricingScannerWorkspace />;
      case 'strategy-lab':
        return <StrategyLabWorkspace />;
      case 'backtesting':
        return <BacktestingWorkspace />;
      case 'market-monitor':
        return <MarketMonitorWorkspace />;
      case 'paper-terminal':
        return <PaperTradingWorkspace />;
      case 'historical-ledger':
        return <HistoricalLedgerWorkspace />;
      case 'risk-portfolio':
        return <RiskPortfolioWorkspace />;
      case 'pipeline-operations':
        return <PipelineFlowWorkspace />;
      case 'model-registry':
        return <ModelRegistryWorkspace />;
      default:
        return <OverviewWorkspace />;
    }
  };

  return (
    <div className="terminal-shell flex flex-col h-screen w-screen overflow-hidden bg-[#06090e] text-[#f1f5f9]">
      {/* Top Header */}
      <header className="shell-topbar shrink-0 z-30">
        <Header />
      </header>

      {/* Main Workstation Body: Left Sidebar + Center Dynamic Stage */}
      <div className="shell-body flex flex-1 overflow-hidden">
        {/* Left Navigation Sidebar */}
        <aside
          className={`shell-sidebar shrink-0 transition-all duration-200 border-r border-[#172033] ${
            sidebarCollapsed ? 'w-[48px]' : 'w-[200px]'
          }`}
        >
          <Sidebar />
        </aside>

        {/* Dynamic Center Stage */}
        <main className="shell-stage flex-1 flex flex-col overflow-hidden bg-[#080b11]">
          {renderWorkspace()}
        </main>
      </div>

      {/* Sticky Bottom Status Bar */}
      <footer className="shell-statusbar shrink-0 border-t border-[#172033] z-30 bg-[#06090e]">
        <StatusBar />
      </footer>

      {/* Slide-out Contract Inspector Drawer */}
      <ContractDetailDrawer />

      {/* Global Command Palette Modal (Ctrl+K) */}
      <CommandPalette />
    </div>
  );
};
export default App;
