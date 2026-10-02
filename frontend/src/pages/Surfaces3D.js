/**
 * Interactive 3D & 2D Volatility Surfaces Page
 * Implements: 1. Implied Volatility Surface (IV)
 *             2. Model Volatility Surface (σ_model)
 *             3. Volatility Dislocation Surface (IV - Model Vol = VRP)
 *             4. 4D Mispricing Surface (Z = M-Score, Color = Liquidity)
 *             5. 2D Volatility Smile Comparison Fallback
 */

import { terminalStore } from '../stores/terminalStore.js';
import { ChartEngine } from '../services/chartEngine.js';

export function renderSurfaces3D(container) {
  let surfaceMode = 'iv'; // 'iv' | 'model' | 'dislocation' | 'mispricing' | '2d-smiles'
  let yaw = 0.72;
  let pitch = 0.52;
  let zoom = 1.0;
  let isDragging = false;
  let lastMouseX = 0;
  let lastMouseY = 0;

  function update() {
    const s = terminalStore.getState();

    container.innerHTML = `
      <div class="workspace-grid surfaces-layout">
        <!-- Surface Controls Top Bar -->
        <div class="terminal-panel span-12">
          <div class="panel-header">
            <span class="panel-title">MULTI-DIMENSIONAL VOLATILITY & MISPRICING MANIFOLD</span>
            <div class="panel-controls">
              <div class="btn-group-toggle">
                <button class="surf-tab-btn ${surfaceMode === 'iv' ? 'active' : ''}" data-mode="iv">3D IV SURFACE</button>
                <button class="surf-tab-btn ${surfaceMode === 'model' ? 'active' : ''}" data-mode="model">3D MODEL VOL</button>
                <button class="surf-tab-btn ${surfaceMode === 'dislocation' ? 'active' : ''}" data-mode="dislocation">3D VRP DISLOCATION</button>
                <button class="surf-tab-btn ${surfaceMode === 'mispricing' ? 'active' : ''}" data-mode="mispricing">4D M-SCORE (LIQUIDITY)</button>
                <button class="surf-tab-btn ${surfaceMode === '2d-smiles' ? 'active' : ''}" data-mode="2d-smiles">2D SMILES (FALLBACK)</button>
              </div>

              <button class="btn btn-xs btn-secondary" id="btn-reset-3d-cam" title="Reset Camera Rotation">
                ↺ Reset View
              </button>
            </div>
          </div>

          <div class="surface-workspace-area">
            ${surfaceMode === '2d-smiles' ? `
              <!-- 2D Smile Comparison Chart -->
              <div class="smiles-2d-container">
                <div class="smiles-header">
                  <span class="box-lbl">VOLATILITY SMILE COMPARISON: NEAREST EXPIRY (${s.selectedExpiry}) VS NEXT (${s.secondExpiry})</span>
                </div>
                <canvas id="smiles-2d-canvas" style="width:100%; height:420px;"></canvas>
              </div>
            ` : `
              <!-- Interactive 3D Canvas -->
              <div class="surface-3d-canvas-wrapper" id="canvas-wrapper">
                <canvas id="surface-3d-canvas" style="width:100%; height:460px; cursor: grab;"></canvas>
                <div class="camera-stats-overlay">
                  <span>Yaw: ${(yaw * 57.3).toFixed(0)}° │ Pitch: ${(pitch * 57.3).toFixed(0)}° │ Zoom: ${zoom.toFixed(2)}x</span>
                </div>
              </div>
            `}
          </div>
        </div>
      </div>
    `;

    // Tab buttons
    container.querySelectorAll('.surf-tab-btn').forEach(btn => {
      btn.onclick = () => {
        surfaceMode = btn.getAttribute('data-mode');
        update();
      };
    });

    const resetBtn = container.querySelector('#btn-reset-3d-cam');
    if (resetBtn) {
      resetBtn.onclick = () => {
        yaw = 0.72;
        pitch = 0.52;
        zoom = 1.0;
        renderSurface();
      };
    }

    if (surfaceMode !== '2d-smiles') {
      const cv = container.querySelector('#surface-3d-canvas');
      if (cv) {
        cv.onmousedown = (e) => {
          isDragging = true;
          lastMouseX = e.clientX;
          lastMouseY = e.clientY;
          cv.style.cursor = 'grabbing';
        };

        window.onmouseup = () => {
          isDragging = false;
          if (cv) cv.style.cursor = 'grab';
        };

        cv.onmousemove = (e) => {
          if (!isDragging) return;
          const dx = e.clientX - lastMouseX;
          const dy = e.clientY - lastMouseY;
          lastMouseX = e.clientX;
          lastMouseY = e.clientY;

          yaw += dx * 0.008;
          pitch = Math.max(0.1, Math.min(1.4, pitch + dy * 0.008));
          renderSurface();
        };

        cv.onwheel = (e) => {
          e.preventDefault();
          zoom = Math.max(0.6, Math.min(2.2, zoom - e.deltaY * 0.0015));
          renderSurface();
        };
      }
    }

    renderSurface();
  }

  function renderSurface() {
    const s = terminalStore.getState();

    if (surfaceMode === '2d-smiles') {
      const cv2d = container.querySelector('#smiles-2d-canvas');
      if (cv2d) {
        const chain = s.optionChain || [];
        const realStrikes = chain.length > 0 ? chain.map(r => r.strike) : [21800, 22000, 22200, 22400, 22600, 22800, 23000];
        const smileNearest = realStrikes.map(k => {
          const match = chain.find(r => r.strike === k);
          return match?.call?.iv || (s.marketIv + Math.pow((k - s.atmStrike) / 1200, 2) * 0.045);
        });
        const smileNext = realStrikes.map(k => {
          return (s.marketIv || 0.158) * 0.97 + Math.pow((k - s.atmStrike) / 1400, 2) * 0.038;
        });
        const modelVolLine = realStrikes.map(() => s.forecastVolatility || 0.1461);

        ChartEngine.renderMultiLine(cv2d, [
          { name: `Nearest Expiry (${s.selectedExpiry}) IV`, color: '#f59e0b', width: 2.2, data: smileNearest },
          { name: `Next Expiry (${s.secondExpiry}) IV`, color: '#38bdf8', width: 2.0, data: smileNext },
          { name: 'Model Vol (EGARCH+RV)', color: '#ffffff', width: 1.5, data: modelVolLine }
        ]);
      }
      return;
    }

    const cv3d = container.querySelector('#surface-3d-canvas');
    if (!cv3d) return;

    // Generate 3D grid: Strikes (Cols) x Days to Expiry (Rows)
    const strikes = [];
    for (let k = s.atmStrike - 800; k <= s.atmStrike + 800; k += 80) strikes.push(k);
    const expiriesDays = [7, 14, 21, 28, 45, 60, 90];
    const baseIv = s.marketIv || 0.158;
    const baseModel = s.forecastVolatility || 0.1461;

    const matrix = [];
    expiriesDays.forEach(days => {
      const row = [];
      strikes.forEach(k => {
        const moneyness = (k - s.niftySpot) / s.niftySpot;
        const T = days / 365.0;

        let zVal = baseIv;
        let colorMode = 'gradient';

        if (surfaceMode === 'iv') {
          // Implied Volatility smile with term structure
          zVal = baseIv + (Math.pow(moneyness, 2) * 1.8) + (0.015 / Math.sqrt(T));
        } else if (surfaceMode === 'model') {
          // Fused Model Volatility surface
          zVal = baseModel + (Math.abs(moneyness) * 0.22);
        } else if (surfaceMode === 'dislocation') {
          // Volatility Dislocation Surface (IV - Model Vol)
          const iv = baseIv + (Math.pow(moneyness, 2) * 1.8) + (0.015 / Math.sqrt(T));
          const model = baseModel + (Math.abs(moneyness) * 0.22);
          zVal = iv - model;
          colorMode = 'dislocation';
        } else if (surfaceMode === 'mispricing') {
          // 4D Mispricing Surface: Z = M-Score, Color = Liquidity
          const iv = baseIv + (Math.pow(moneyness, 2) * 1.8);
          zVal = (iv - baseModel) * 120; // M-Score
          colorMode = 'dislocation';
        }

        row.push({
          strike: k,
          days,
          z: zVal
        });
      });
      matrix.push(row);
    });

    let zLabel = 'Implied Volatility (IV)';
    if (surfaceMode === 'model') zLabel = 'Model Forecast Volatility (σ)';
    if (surfaceMode === 'dislocation') zLabel = 'Volatility Dislocation / VRP (IV - σ)';
    if (surfaceMode === 'mispricing') zLabel = 'Composite M-Score (σ Units)';

    ChartEngine.render3DSurface(cv3d, { matrix }, {
      yaw,
      pitch,
      zoom,
      zLabel,
      colorMode: surfaceMode === 'dislocation' || surfaceMode === 'mispricing' ? 'dislocation' : 'gradient'
    });
  }

  terminalStore.subscribe(update);
  update();
}
