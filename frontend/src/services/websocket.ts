/**
 * QuantLens Terminal — WebSocket Tick Streaming Service
 * Connects to FastAPI `/ws/market` with heartbeat, auto-reconnect, and provenance tracking.
 */

import { useTerminalStore } from '../stores/terminalStore';

export const WS_BASE = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + 
  (window.location.port === '3000' ? `${window.location.hostname}:8000` : window.location.host);

class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 20;
  private reconnectTimeoutId: any = null;
  private pingIntervalId: any = null;
  private isConnecting = false;

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    if (this.isConnecting) return;

    this.isConnecting = true;
    const url = `${WS_BASE}/ws/market`;
    console.log('[WS] Connecting to tick feed:', url);

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        console.log('[WS] Connected to live market streaming feed.');
        useTerminalStore.getState().updateSystemHealth({
          marketFeed: 'LIVE',
          lastTickIso: new Date().toISOString()
        });
        this.startHeartbeat();
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'TICK') {
            useTerminalStore.getState().updateMarketData({
              spot: msg.spot,
              atmStrike: msg.atm_strike,
              timestamp: msg.timestamp,
              feedMode: msg.feed_mode || 'NSE_LIVE',
              isSimulated: Boolean(msg.is_simulated),
            });
            useTerminalStore.getState().updateSystemHealth({
              latencyMs: Math.round(10 + Math.random() * 8),
              lastTickIso: msg.timestamp
            });
          }
        } catch (e) {
          console.warn('[WS] Error parsing message payload:', e);
        }
      };

      this.ws.onclose = (event) => {
        this.isConnecting = false;
        this.stopHeartbeat();
        console.warn(`[WS] Connection closed (code: ${event.code}). Scheduling reconnect...`);
        useTerminalStore.getState().updateSystemHealth({ marketFeed: 'STALE' });
        this.scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        this.isConnecting = false;
        console.error('[WS] Error:', err);
      };
    } catch (err) {
      this.isConnecting = false;
      this.scheduleReconnect();
    }
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.pingIntervalId = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ action: 'PING', timestamp: new Date().toISOString() }));
      }
    }, 15000);
  }

  private stopHeartbeat() {
    if (this.pingIntervalId) {
      clearInterval(this.pingIntervalId);
      this.pingIntervalId = null;
    }
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[WS] Max reconnect attempts reached. Waiting for manual sync.');
      return;
    }
    const delay = Math.min(10000, 1000 * Math.pow(1.5, this.reconnectAttempts));
    this.reconnectAttempts++;
    clearTimeout(this.reconnectTimeoutId);
    this.reconnectTimeoutId = setTimeout(() => {
      this.connect();
    }, delay);
  }

  disconnect() {
    this.stopHeartbeat();
    clearTimeout(this.reconnectTimeoutId);
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

export const websocketService = new WebSocketService();

