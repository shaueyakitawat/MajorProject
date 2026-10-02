/**
 * High-Performance Institutional Canvas 2D & 3D Financial Chart Engine
 * Built specifically for high information-density quantitative workstations.
 * Features: High-DPI rendering, synchronized crosshairs, interactive 3D surface projection,
 * financial candlesticks with EMA/VWAP overlays, and dynamic options payoff curves.
 */

export class ChartEngine {
  /**
   * Configures canvas for Retina / High-DPI displays
   */
  static setupCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(10, rect.width || canvas.width);
    const height = Math.max(10, rect.height || canvas.height);

    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr;
      canvas.height = height * dpr;
    }

    const ctx = canvas.getContext('2d');
    ctx.resetTransform?.();
    ctx.scale(dpr, dpr);
    return { ctx, width, height, dpr };
  }

  /**
   * 1. Financial Candlestick Chart with Volume & Overlays
   */
  static renderCandlestick(canvas, candles, options = {}) {
    const { ctx, width, height } = this.setupCanvas(canvas);
    if (!candles || candles.length === 0) {
      this.drawEmptyState(ctx, width, height, 'No candlestick data available');
      return;
    }

    const padLeft = 10;
    const padRight = 60;
    const padTop = 20;
    const padBottom = 30;
    const chartW = width - padLeft - padRight;
    const chartH = height - padTop - padBottom;
    const volH = chartH * 0.22;
    const priceH = chartH - volH - 10;

    // Background
    ctx.fillStyle = options.bgColor || '#090d15';
    ctx.fillRect(0, 0, width, height);

    // Compute Price and Volume bounds
    let minP = Infinity, maxP = -Infinity;
    let maxV = 0;
    for (const c of candles) {
      if (c.Low < minP) minP = c.Low;
      if (c.High > maxP) maxP = c.High;
      if (c.Volume > maxV) maxV = c.Volume;
    }

    const pRange = (maxP - minP) || 1;
    minP -= pRange * 0.05;
    maxP += pRange * 0.05;
    const totalRange = maxP - minP;

    // Draw Grid Lines
    ctx.strokeStyle = '#171f2e';
    ctx.lineWidth = 1;
    const gridRows = 5;
    for (let i = 0; i <= gridRows; i++) {
      const y = padTop + (priceH / gridRows) * i;
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();

      // Right axis price labels
      const pVal = maxP - (totalRange / gridRows) * i;
      ctx.fillStyle = '#64748b';
      ctx.font = '10px monospace';
      ctx.textAlign = 'left';
      ctx.fillText(pVal.toFixed(1), width - padRight + 6, y + 3);
    }

    // Candle metrics
    const n = candles.length;
    const candleW = Math.max(2, Math.min(18, (chartW / n) * 0.75));
    const stepX = chartW / n;

    // Moving average buffers
    const ema20 = [];
    const ema50 = [];
    let k20 = 2 / (20 + 1);
    let k50 = 2 / (50 + 1);
    let prev20 = candles[0].Close;
    let prev50 = candles[0].Close;

    // Draw Candles & Volume
    candles.forEach((c, i) => {
      const x = padLeft + i * stepX + stepX / 2;
      const isUp = c.Close >= c.Open;
      const col = isUp ? '#00e676' : '#ff5252';

      // Y coordinates
      const yHigh = padTop + priceH * (1 - (c.High - minP) / totalRange);
      const yLow = padTop + priceH * (1 - (c.Low - minP) / totalRange);
      const yOpen = padTop + priceH * (1 - (c.Open - minP) / totalRange);
      const yClose = padTop + priceH * (1 - (c.Close - minP) / totalRange);

      // Wick
      ctx.strokeStyle = col;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x, yHigh);
      ctx.lineTo(x, yLow);
      ctx.stroke();

      // Body
      ctx.fillStyle = col;
      const bodyTop = Math.min(yOpen, yClose);
      const bodyH = Math.max(2, Math.abs(yClose - yOpen));
      ctx.fillRect(x - candleW / 2, bodyTop, candleW, bodyH);

      // Volume bar
      if (maxV > 0) {
        const vRatio = c.Volume / maxV;
        const vBarH = volH * vRatio;
        const vY = padTop + priceH + 10 + (volH - vBarH);
        ctx.fillStyle = isUp ? 'rgba(0, 230, 118, 0.25)' : 'rgba(255, 82, 82, 0.25)';
        ctx.fillRect(x - candleW / 2, vY, candleW, vBarH);
      }

      // Compute EMAs
      prev20 = c.Close * k20 + prev20 * (1 - k20);
      prev50 = c.Close * k50 + prev50 * (1 - k50);
      ema20.push({ x, y: padTop + priceH * (1 - (prev20 - minP) / totalRange) });
      ema50.push({ x, y: padTop + priceH * (1 - (prev50 - minP) / totalRange) });
    });

    // Draw EMA 20 (Amber)
    if (ema20.length > 1) {
      ctx.strokeStyle = '#f59e0b';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(ema20[0].x, ema20[0].y);
      for (let i = 1; i < ema20.length; i++) {
        ctx.lineTo(ema20[i].x, ema20[i].y);
      }
      ctx.stroke();
    }

    // Draw EMA 50 (Blue)
    if (ema50.length > 1) {
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(ema50[0].x, ema50[0].y);
      for (let i = 1; i < ema50.length; i++) {
        ctx.lineTo(ema50[i].x, ema50[i].y);
      }
      ctx.stroke();
    }

    // Legend
    ctx.fillStyle = '#f59e0b';
    ctx.fillText('— EMA 20', padLeft + 10, padTop + 14);
    ctx.fillStyle = '#38bdf8';
    ctx.fillText('— EMA 50', padLeft + 75, padTop + 14);
    ctx.fillStyle = '#64748b';
    ctx.fillText('Vol (bottom)', padLeft + 140, padTop + 14);
  }

  /**
   * 2. Synchronized Multi-Line Time Series Chart
   */
  static renderMultiLine(canvas, seriesList, options = {}) {
    const { ctx, width, height } = this.setupCanvas(canvas);
    if (!seriesList || seriesList.length === 0 || !seriesList[0].data || seriesList[0].data.length === 0) {
      this.drawEmptyState(ctx, width, height, 'No volatility time-series data');
      return;
    }

    const padLeft = 10;
    const padRight = 55;
    const padTop = 20;
    const padBottom = 25;
    const chartW = width - padLeft - padRight;
    const chartH = height - padTop - padBottom;

    ctx.fillStyle = options.bgColor || '#090d15';
    ctx.fillRect(0, 0, width, height);

    // Compute common bounds
    let minY = Infinity, maxY = -Infinity;
    seriesList.forEach(s => {
      if (s.visible === false) return;
      s.data.forEach(pt => {
        const val = typeof pt === 'number' ? pt : pt.y;
        if (val !== null && isFinite(val)) {
          if (val < minY) minY = val;
          if (val > maxY) maxY = val;
        }
      });
    });

    if (!isFinite(minY)) { minY = 0; maxY = 1; }
    const yMargin = (maxY - minY) * 0.1 || 0.05;
    minY -= yMargin;
    maxY += yMargin;
    const rangeY = maxY - minY;

    // Grid
    ctx.strokeStyle = '#171f2e';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padTop + (chartH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();

      const labelVal = maxY - (rangeY / 4) * i;
      ctx.fillStyle = '#64748b';
      ctx.font = '10px monospace';
      ctx.textAlign = 'left';
      ctx.fillText((labelVal * 100).toFixed(1) + '%', width - padRight + 5, y + 3);
    }

    // Zero reference line if across 0
    if (minY < 0 && maxY > 0) {
      const zeroY = padTop + chartH * (1 - (0 - minY) / rangeY);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(padLeft, zeroY);
      ctx.lineTo(width - padRight, zeroY);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Draw each series
    seriesList.forEach(s => {
      if (s.visible === false || !s.data || s.data.length < 2) return;
      const pts = s.data;
      const stepX = chartW / (pts.length - 1);

      ctx.strokeStyle = s.color || '#38bdf8';
      ctx.lineWidth = s.width || 1.8;
      ctx.beginPath();

      pts.forEach((pt, i) => {
        const val = typeof pt === 'number' ? pt : pt.y;
        const x = padLeft + i * stepX;
        const y = padTop + chartH * (1 - (val - minY) / rangeY);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    });

    // Legend
    let legX = padLeft + 10;
    seriesList.forEach(s => {
      if (s.visible === false) return;
      ctx.fillStyle = s.color || '#38bdf8';
      ctx.font = '10px monospace';
      ctx.fillText(`■ ${s.name}`, legX, padTop - 6);
      legX += (s.name.length * 7) + 25;
    });
  }

  /**
   * 3. Interactive 3D Surface Engine with Real-Time Perspective Projection
   * Supports: Strike (X) x Days to Expiry (Y) x Volatility/M-score (Z)
   * Mouse rotation and 4D vertex coloring.
   */
  static render3DSurface(canvas, gridData, options = {}) {
    const { ctx, width, height } = this.setupCanvas(canvas);
    if (!gridData || !gridData.matrix || gridData.matrix.length === 0) {
      this.drawEmptyState(ctx, width, height, 'No 3D Surface grid data');
      return;
    }

    ctx.fillStyle = options.bgColor || '#070a10';
    ctx.fillRect(0, 0, width, height);

    const yaw = options.yaw || 0.65;     // Horizontal rotation angle
    const pitch = options.pitch || 0.55; // Vertical tilt angle
    const zoom = options.zoom || 1.0;

    const rows = gridData.matrix.length; // Y: Expiries
    const cols = gridData.matrix[0].length; // X: Strikes

    // Find min and max Z
    let minZ = Infinity, maxZ = -Infinity;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = gridData.matrix[r][c].z;
        if (v < minZ) minZ = v;
        if (v > maxZ) maxZ = v;
      }
    }
    const rangeZ = (maxZ - minZ) || 1;

    // Project 3D point (x, y, z) into 2D screen coordinate
    const project = (normX, normY, normZ) => {
      // Centered at 0 (-0.5 to 0.5)
      const cx = normX - 0.5;
      const cy = normY - 0.5;
      const cz = (normZ - 0.5) * 0.8;

      // Rotate around Y axis (yaw)
      const cosY = Math.cos(yaw), sinY = Math.sin(yaw);
      const x1 = cx * cosY + cy * sinY;
      const y1 = -cx * sinY + cy * cosY;
      const z1 = cz;

      // Rotate around X axis (pitch)
      const cosP = Math.cos(pitch), sinP = Math.sin(pitch);
      const x2 = x1;
      const y2 = y1 * cosP - z1 * sinP;
      const z2 = y1 * sinP + z1 * cosP;

      const scale = Math.min(width, height) * 0.65 * zoom;
      const screenX = width / 2 + x2 * scale;
      const screenY = height / 2 - z2 * scale + y2 * scale * 0.35;
      return { x: screenX, y: screenY, depth: y2 };
    };

    // Build Projected Quads & Sort by Depth for Painter's Algorithm
    const quads = [];
    for (let r = 0; r < rows - 1; r++) {
      for (let c = 0; c < cols - 1; c++) {
        const p00 = gridData.matrix[r][c];
        const p10 = gridData.matrix[r + 1][c];
        const p11 = gridData.matrix[r + 1][c + 1];
        const p01 = gridData.matrix[r][c + 1];

        const pt00 = project(c / (cols - 1), r / (rows - 1), (p00.z - minZ) / rangeZ);
        const pt10 = project(c / (cols - 1), (r + 1) / (rows - 1), (p10.z - minZ) / rangeZ);
        const pt11 = project((c + 1) / (cols - 1), (r + 1) / (rows - 1), (p11.z - minZ) / rangeZ);
        const pt01 = project((c + 1) / (cols - 1), r / (rows - 1), (p01.z - minZ) / rangeZ);

        const avgZ = (p00.z + p10.z + p11.z + p01.z) / 4;
        const normVal = (avgZ - minZ) / rangeZ;
        const avgDepth = (pt00.depth + pt10.depth + pt11.depth + pt01.depth) / 4;

        // 4D Color mapping: default uses Z elevation, or optional 4th dimension (e.g. liquidity)
        let quadColor;
        if (options.colorMode === 'dislocation') {
          // Diverging blue (negative) -> cyan -> amber -> red (positive)
          quadColor = avgZ >= 0 ? `rgba(255, 82, 82, ${0.4 + normVal * 0.5})` : `rgba(0, 230, 118, ${0.4 + (1 - normVal) * 0.5})`;
        } else {
          // Cool to warm institutional quant gradient
          const hue = 220 - normVal * 160; // 220 (Blue) down to 60 (Amber/Red)
          quadColor = `hsla(${hue}, 85%, 52%, ${0.55 + normVal * 0.35})`;
        }

        quads.push({
          pts: [pt00, pt10, pt11, pt01],
          depth: avgDepth,
          color: quadColor,
        });
      }
    }

    // Sort back-to-front
    quads.sort((a, b) => a.depth - b.depth);

    // Draw quads
    quads.forEach(q => {
      ctx.beginPath();
      ctx.moveTo(q.pts[0].x, q.pts[0].y);
      ctx.lineTo(q.pts[1].x, q.pts[1].y);
      ctx.lineTo(q.pts[2].x, q.pts[2].y);
      ctx.lineTo(q.pts[3].x, q.pts[3].y);
      ctx.closePath();

      ctx.fillStyle = q.color;
      ctx.fill();

      // Wireframe overlay
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.18)';
      ctx.lineWidth = 0.8;
      ctx.stroke();
    });

    // Draw Axis Metadata
    ctx.fillStyle = '#f59e0b';
    ctx.font = '11px monospace';
    ctx.textAlign = 'left';
    ctx.fillText(`Z: ${options.zLabel || 'Implied Volatility'} [Min: ${(minZ * 100).toFixed(1)}% | Max: ${(maxZ * 100).toFixed(1)}%]`, 12, 18);
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(`X: Strike Range | Y: Days to Expiry | Drag mouse to rotate 3D view`, 12, 34);
  }

  /**
   * 4. Institutional 2D Heatmap Matrix
   */
  static renderHeatmap(canvas, xLabels, yLabels, matrix, options = {}) {
    const { ctx, width, height } = this.setupCanvas(canvas);
    if (!matrix || matrix.length === 0) {
      this.drawEmptyState(ctx, width, height, 'No heatmap data');
      return;
    }

    const padLeft = 85;
    const padBottom = 35;
    const padTop = 15;
    const padRight = 20;
    const w = width - padLeft - padRight;
    const h = height - padTop - padBottom;

    ctx.fillStyle = options.bgColor || '#090d15';
    ctx.fillRect(0, 0, width, height);

    const rows = matrix.length;
    const cols = matrix[0].length;
    const cellW = w / cols;
    const cellH = h / rows;

    let minV = Infinity, maxV = -Infinity;
    matrix.forEach(row => row.forEach(val => {
      if (val < minV) minV = val;
      if (val > maxV) maxV = val;
    }));
    const rV = (maxV - minV) || 1;

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const val = matrix[r][c];
        const norm = (val - minV) / rV;
        const x = padLeft + c * cellW;
        const y = padTop + r * cellH;

        // Diverging or sequential
        let fill;
        if (minV < 0 && maxV > 0) {
          fill = val >= 0
            ? `rgba(255, 82, 82, ${Math.min(1, 0.2 + (val / maxV) * 0.8)})`
            : `rgba(0, 230, 118, ${Math.min(1, 0.2 + (Math.abs(val) / Math.abs(minV)) * 0.8)})`;
        } else {
          fill = `rgba(56, 189, 248, ${0.15 + norm * 0.85})`;
        }

        ctx.fillStyle = fill;
        ctx.fillRect(x + 1, y + 1, cellW - 2, cellH - 2);

        // Value text if cell is wide enough
        if (cellW > 35 && cellH > 18) {
          ctx.fillStyle = '#f8fafc';
          ctx.font = '10px monospace';
          ctx.textAlign = 'center';
          ctx.fillText(val.toFixed(1), x + cellW / 2, y + cellH / 2 + 3);
        }
      }

      // Y-axis label
      ctx.fillStyle = '#94a3b8';
      ctx.font = '10px monospace';
      ctx.textAlign = 'right';
      ctx.fillText(yLabels[r] || '', padLeft - 6, padTop + r * cellH + cellH / 2 + 3);
    }

    // X-axis labels
    ctx.textAlign = 'center';
    for (let c = 0; c < cols; c++) {
      const x = padLeft + c * cellW + cellW / 2;
      ctx.fillStyle = '#94a3b8';
      ctx.font = '10px monospace';
      ctx.fillText(xLabels[c] || '', x, height - padBottom + 16);
    }
  }

  /**
   * 5. Quantitative Scatter Plot with Regression / Parity Lines
   */
  static renderScatter(canvas, points, options = {}) {
    const { ctx, width, height } = this.setupCanvas(canvas);
    if (!points || points.length === 0) {
      this.drawEmptyState(ctx, width, height, 'No scatter data');
      return;
    }

    const padLeft = 45;
    const padRight = 20;
    const padTop = 20;
    const padBottom = 35;
    const chartW = width - padLeft - padRight;
    const chartH = height - padTop - padBottom;

    ctx.fillStyle = options.bgColor || '#090d15';
    ctx.fillRect(0, 0, width, height);

    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;

    points.forEach(p => {
      if (p.x < minX) minX = p.x;
      if (p.x > maxX) maxX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.y > maxY) maxY = p.y;
    });

    const rangeX = (maxX - minX) || 1;
    const rangeY = (maxY - minY) || 1;

    // Grid
    ctx.strokeStyle = '#171f2e';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padTop + (chartH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();

      const yVal = maxY - (rangeY / 4) * i;
      ctx.fillStyle = '#64748b';
      ctx.font = '10px monospace';
      ctx.textAlign = 'right';
      ctx.fillText(yVal.toFixed(2), padLeft - 6, y + 3);
    }

    // 45-degree parity reference line if requested
    if (options.showParityLine) {
      const p1x = padLeft;
      const p1y = padTop + chartH * (1 - (minX - minY) / rangeY);
      const p2x = padLeft + chartW;
      const p2y = padTop + chartH * (1 - (maxX - minY) / rangeY);

      ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(p1x, p1y);
      ctx.lineTo(p2x, p2y);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Draw Points
    points.forEach(p => {
      const cx = padLeft + ((p.x - minX) / rangeX) * chartW;
      const cy = padTop + chartH * (1 - (p.y - minY) / rangeY);
      const radius = p.size || 3.5;

      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fillStyle = p.color || '#38bdf8';
      ctx.fill();
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
      ctx.lineWidth = 0.8;
      ctx.stroke();
    });

    // Axis titles
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(options.xLabel || 'X Axis', padLeft + chartW / 2, height - 6);
  }

  /**
   * 6. Options Payoff Curve with Breakevens and Theoretical P&L
   */
  static renderPayoff(canvas, points, breakevens = [], currentSpot = 22400, options = {}) {
    const { ctx, width, height } = this.setupCanvas(canvas);
    if (!points || points.length === 0) {
      this.drawEmptyState(ctx, width, height, 'Configure legs to display payoff');
      return;
    }

    const padLeft = 60;
    const padRight = 30;
    const padTop = 25;
    const padBottom = 35;
    const chartW = width - padLeft - padRight;
    const chartH = height - padTop - padBottom;

    ctx.fillStyle = options.bgColor || '#090d15';
    ctx.fillRect(0, 0, width, height);

    const minSpot = points[0].spot;
    const maxSpot = points[points.length - 1].spot;
    const spotRange = maxSpot - minSpot;

    let minPnl = Infinity, maxPnl = -Infinity;
    points.forEach(p => {
      if (p.expiryPnl < minPnl) minPnl = p.expiryPnl;
      if (p.expiryPnl > maxPnl) maxPnl = p.expiryPnl;
      if (p.theoreticalPnl < minPnl) minPnl = p.theoreticalPnl;
      if (p.theoreticalPnl > maxPnl) maxPnl = p.theoreticalPnl;
    });

    const pnlMargin = Math.max(100, (maxPnl - minPnl) * 0.15);
    minPnl -= pnlMargin;
    maxPnl += pnlMargin;
    const pnlRange = maxPnl - minPnl;

    // Zero P&L horizontal reference line
    const zeroY = padTop + chartH * (1 - (0 - minPnl) / pnlRange);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padLeft, zeroY);
    ctx.lineTo(width - padRight, zeroY);
    ctx.stroke();

    // Zero label
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px monospace';
    ctx.textAlign = 'right';
    ctx.fillText('₹0', padLeft - 6, zeroY + 3);

    // Current Spot price vertical line
    const spotX = padLeft + ((currentSpot - minSpot) / spotRange) * chartW;
    ctx.strokeStyle = '#f59e0b';
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(spotX, padTop);
    ctx.lineTo(spotX, height - padBottom);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = '#f59e0b';
    ctx.font = '10px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(`Spot: ${currentSpot}`, spotX, padTop - 6);

    // Draw Theoretical curve (dashed blue)
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 1.6;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    points.forEach((p, i) => {
      const x = padLeft + ((p.spot - minSpot) / spotRange) * chartW;
      const y = padTop + chartH * (1 - (p.theoreticalPnl - minPnl) / pnlRange);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw Expiry Payoff curve (solid green/red)
    ctx.strokeStyle = '#00e676';
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    points.forEach((p, i) => {
      const x = padLeft + ((p.spot - minSpot) / spotRange) * chartW;
      const y = padTop + chartH * (1 - (p.expiryPnl - minPnl) / pnlRange);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Breakeven markers
    breakevens.forEach(be => {
      const beX = padLeft + ((be - minSpot) / spotRange) * chartW;
      ctx.fillStyle = '#ff9800';
      ctx.beginPath();
      ctx.arc(beX, zeroY, 4, 0, Math.PI * 2);
      ctx.fill();

      ctx.font = '9px monospace';
      ctx.fillText(`BE: ${be}`, beX, zeroY + 16);
    });

    // Legend
    ctx.fillStyle = '#00e676';
    ctx.textAlign = 'left';
    ctx.fillText('— Expiry Payoff', padLeft + 10, padTop + 12);
    ctx.fillStyle = '#38bdf8';
    ctx.fillText('-- T+0 Theoretical', padLeft + 120, padTop + 12);
  }

  static drawEmptyState(ctx, width, height, text) {
    ctx.fillStyle = '#090d15';
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = '#64748b';
    ctx.font = '11px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(text, width / 2, height / 2);
  }
}
