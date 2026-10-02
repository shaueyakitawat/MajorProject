/**
 * Bloomberg Terminal Institutional Workstation Bootstrap
 * Orchestrates shell layout, route lifecycle, keyboard event bus, and real-time streaming services.
 */

import { terminalStore } from './stores/terminalStore.js';
import { websocketService } from './services/websocket.js';
import { apiService } from './services/api.js';

// Shell components
import { renderTopBar } from './components/TopBar.js';
import { renderSidebar } from './components/Sidebar.js';
import { renderStatusBar } from './components/StatusBar.js';
import { renderCommandPalette } from './components/CommandPalette.js';
import { renderEvaluationModal } from './components/EvaluationModal.js';
import { renderOptionDetailDrawer } from './components/OptionDetailDrawer.js';

// Workspace pages
import { renderCommandCenter } from './pages/CommandCenter.js';
import { renderVolatilityCockpit } from './pages/VolatilityCockpit.js';
import { renderRegimeTerminal } from './pages/RegimeTerminal.js';
import { renderOptionChainGrid } from './pages/OptionChainGrid.js';
import { renderSurfaces3D } from './pages/Surfaces3D.js';
import { renderMispricingScanner } from './pages/MispricingScanner.js';
import { renderStrategyBuilder } from './pages/StrategyBuilder.js';
import { renderPortfolioRisk } from './pages/PortfolioRisk.js';
import { renderBacktestReplay } from './pages/BacktestReplay.js';
import { renderResearchWorkbench } from './pages/ResearchWorkbench.js';
import { renderSystemMonitors } from './pages/SystemMonitors.js';

export class TerminalApp {
  constructor() {
    this.currentMountedRoute = null;
  }

  init() {
    console.log('[TERMINAL] Initializing Institutional Quantitative Workstation...');

    // Mount persistent shell regions
    renderTopBar(document.getElementById('topbar-container'));
    renderSidebar(document.getElementById('sidebar-container'));
    renderStatusBar(document.getElementById('statusbar-container'));
    renderCommandPalette(document.getElementById('command-palette-container'));
    renderEvaluationModal(document.getElementById('evaluation-modal-container'));
    renderOptionDetailDrawer(document.getElementById('option-drawer-container'));

    // Bind Global Keyboard Navigation
    this.setupKeyboardShortcuts();

    // Subscribe to router changes
    terminalStore.subscribe((state) => {
      if (state.activeRoute !== this.currentMountedRoute) {
        this.currentMountedRoute = state.activeRoute;
        this.mountActivePage(state.activeRoute);
      }
    });

    // Mount initial page
    this.currentMountedRoute = terminalStore.getState().activeRoute;
    this.mountActivePage(this.currentMountedRoute);

    // Connect real-time WebSocket tick stream
    websocketService.connect();

    // Initial background sync with backend
    this.syncInitialBackendState();
  }

  async syncInitialBackendState() {
    try {
      const s = terminalStore.getState();

      // Parallel fetch of initial institutional state
      const [stratRes, chainRes, candleRes, backtestRes] = await Promise.allSettled([
        apiService.getStrategy('NIFTY', s.timeframe, s.tradingHorizon),
        apiService.getOptionChain('NIFTY', s.selectedExpiry, 25),
        apiService.getNiftyCandles('NIFTY', s.timeframe),
        apiService.getBacktest('^NSEI', '1d'),
      ]);

      const updates = {
        systemStatus: {
          ...terminalStore.getState().systemStatus,
          api: 'CONNECTED',
          data: 'LIVE'
        }
      };

      if (stratRes.status === 'fulfilled' && stratRes.value?.success && stratRes.value.data) {
        const d = stratRes.value.data;
        updates.niftySpot = d.spot_price || s.niftySpot;
        updates.forecastVolatility = d.forecast_volatility || s.forecastVolatility;
        updates.bsFairPrice = d.fair_price || s.bsFairPrice;
        updates.marketPrice = d.market_price || s.marketPrice;
        updates.regime = d.regime || s.regime;
        updates.marketIv = d.implied_volatility || s.marketIv;
        updates.selectedExpiry = d.selected_expiry || s.selectedExpiry;
        updates.availableExpiries = d.available_expiries || s.availableExpiries;
        updates.activeSignal = d.strategy || null;
      }

      if (chainRes.status === 'fulfilled' && chainRes.value?.success && chainRes.value.data) {
        updates.optionChain = chainRes.value.data.chain || [];
        if (chainRes.value.data.spotPrice) updates.niftySpot = chainRes.value.data.spotPrice;
        if (chainRes.value.data.atmStrike) updates.atmStrike = chainRes.value.data.atmStrike;
      }

      if (candleRes.status === 'fulfilled' && candleRes.value?.success && candleRes.value.candles?.length > 0) {
        const candles = candleRes.value.candles;
        const last = candles[candles.length - 1];
        const prev = candles.length > 1 ? candles[candles.length - 2] : last;
        const change = last.Close - prev.Close;
        const changePct = prev.Close > 0 ? (change / prev.Close) * 100 : 0;
        updates.niftySpot = last.Close;
        updates.niftyOpen = last.Open;
        updates.niftyHigh = last.High;
        updates.niftyLow = last.Low;
        updates.niftyPrevClose = prev.Close;
        updates.niftyChange = Math.round(change * 100) / 100;
        updates.niftyChangePct = Math.round(changePct * 100) / 100;
        updates.niftyVolume = last.Volume || s.niftyVolume;
      }

      if (backtestRes.status === 'fulfilled' && backtestRes.value?.success && backtestRes.value.data) {
        updates.backtestSummary = backtestRes.value.data;
        updates.backtestTradeLog = backtestRes.value.data.trades || [];
      }

      terminalStore.setState(updates);
    } catch (err) {
      console.warn('[TERMINAL] Initial sync warning:', err);
    }
  }

  mountActivePage(routeId) {
    const stage = document.getElementById('workspace-stage');
    if (!stage) return;
    stage.innerHTML = '';

    console.log(`[TERMINAL] Routing to workspace: ${routeId}`);

    switch (routeId) {
      case 'overview':
      case 'nifty-chart':
      case 'market-depth':
        renderCommandCenter(stage);
        break;

      case 'volatility-cockpit':
      case 'egarch-model':
      case 'realized-vol':
      case 'vrp-terminal':
        renderVolatilityCockpit(stage);
        break;

      case 'hmm-regime':
        renderRegimeTerminal(stage);
        break;

      case 'option-chain':
        renderOptionChainGrid(stage);
        break;

      case 'iv-surface':
      case 'dislocation-surface':
      case 'greeks-surface':
        renderSurfaces3D(stage);
        break;

      case 'mispricing-scanner':
      case 'option-scanner':
        renderMispricingScanner(stage);
        break;

      case 'strategy-signals':
      case 'strategy-builder':
      case 'payoff-matrix':
        renderStrategyBuilder(stage);
        break;

      case 'portfolio-positions':
      case 'portfolio-risk':
        renderPortfolioRisk(stage);
        break;

      case 'backtest-overview':
      case 'trade-replay':
        renderBacktestReplay(stage);
        break;

      case 'research-workbench':
        renderResearchWorkbench(stage);
        break;

      case 'data-monitor':
      case 'model-monitor':
      case 'alerts-feed':
        renderSystemMonitors(stage);
        break;

      default:
        renderCommandCenter(stage);
        break;
    }
  }

  setupKeyboardShortcuts() {
    window.addEventListener('keydown', (e) => {
      // Don't intercept if user is typing in an input or textarea
      const targetTag = e.target.tagName.toLowerCase();
      const isInput = targetTag === 'input' || targetTag === 'textarea' || targetTag === 'select';

      // Command Palette: Ctrl+K or Cmd+K
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        const cur = terminalStore.getState().commandPaletteOpen;
        terminalStore.setCommandPalette(!cur);
        return;
      }

      // Quick Search: Ctrl+F
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        terminalStore.setCommandPalette(true);
        return;
      }

      // Close modals / drawers with Escape
      if (e.key === 'Escape') {
        terminalStore.setCommandPalette(false);
        terminalStore.setEvaluationModal(false);
        terminalStore.closeOptionDetail();
        return;
      }

      if (isInput) return;

      // Fast Navigation Keys: 1..6
      switch (e.key) {
        case '1':
          e.preventDefault();
          terminalStore.setActiveRoute('overview');
          break;
        case '2':
          e.preventDefault();
          terminalStore.setActiveRoute('option-chain');
          break;
        case '3':
          e.preventDefault();
          terminalStore.setActiveRoute('mispricing-scanner');
          break;
        case '4':
          e.preventDefault();
          terminalStore.setActiveRoute('strategy-builder');
          break;
        case '5':
          e.preventDefault();
          terminalStore.setActiveRoute('portfolio-positions');
          break;
        case '6':
          e.preventDefault();
          terminalStore.setActiveRoute('backtest-overview');
          break;
      }
    });
  }
}

// Auto-boot upon DOM ready
document.addEventListener('DOMContentLoaded', () => {
  const app = new TerminalApp();
  app.init();
});
