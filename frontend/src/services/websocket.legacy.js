/**
 * Real-Time WebSocket Streaming Client
 * Connects to FastAPI /ws streaming endpoint, measures tick latency, and maintains heartbeat.
 * Dynamically updates spot, ATM strike, active option quotes, and pushes live alerts to the store.
 */

import { WS_BASE } from '../config.js';
import { terminalStore } from '../stores/terminalStore.js';

class WebSocketService {
  constructor() {
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 20;
    this.reconnectDelay = 2000;
    this.pingInterval = null;
    this.lastPingSentTime = 0;
    this.isConnected = false;
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      const url = `${WS_BASE}/ws`;
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectAttempts = 0;
        terminalStore.setState({
          systemStatus: {
            ...terminalStore.getState().systemStatus,
            ws: 'CONNECTED',
            data: 'LIVE',
          }
        });

        // Start periodic heartbeat
        if (this.pingInterval) clearInterval(this.pingInterval);
        this.pingInterval = setInterval(() => this.sendPing(), 3000);
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          this.handleMessage(msg);
        } catch (err) {
          console.error('[WS] Failed to parse message:', err);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        if (this.pingInterval) clearInterval(this.pingInterval);

        terminalStore.setState({
          systemStatus: {
            ...terminalStore.getState().systemStatus,
            ws: 'DISCONNECTED',
            data: 'DATA STALE',
          }
        });

        this.scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        console.warn('[WS] Socket error:', err);
        this.ws.close();
      };
    } catch (err) {
      console.warn('[WS] Connection attempt failed:', err);
      this.scheduleReconnect();
    }
  }

  sendPing() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.lastPingSentTime = performance.now();
      this.ws.send(JSON.stringify({ action: 'PING' }));
    }
  }

  handleMessage(msg) {
    if (msg.type === 'PONG') {
      const latencyMs = Math.round(performance.now() - this.lastPingSentTime);
      terminalStore.setState({
        systemStatus: {
          ...terminalStore.getState().systemStatus,
          latencyMs,
          lastTickTime: new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }),
          lastUpdateEpoch: Date.now(),
        }
      });
    } else if (msg.type === 'TICK') {
      const current = terminalStore.getState();
      const prevSpot = current.niftySpot;
      const newSpot = msg.spot || prevSpot;
      const change = newSpot - current.niftyPrevClose;
      const changePct = current.niftyPrevClose > 0 ? (change / current.niftyPrevClose) * 100 : 0;
      const newAtm = msg.atm_strike || Math.round(newSpot / 50) * 50;

      // Update Option Chain quotes for ATM strike dynamically
      let updatedChain = current.optionChain;
      if (updatedChain && updatedChain.length > 0 && (msg.atm_call_ltp || msg.atm_put_ltp)) {
        updatedChain = updatedChain.map(row => {
          if (row.strike === newAtm) {
            const c = row.call ? { ...row.call, ltp: msg.atm_call_ltp || row.call.ltp } : null;
            const p = row.put ? { ...row.put, ltp: msg.atm_put_ltp || row.put.ltp } : null;
            return { ...row, call: c, put: p };
          }
          return row;
        });
      }

      // Add alert if message triggered a dislocation alert
      if (msg.alert) {
        terminalStore.addAlert(msg.alert);
      }

      terminalStore.setState({
        niftySpot: newSpot,
        niftyChange: Math.round(change * 100) / 100,
        niftyChangePct: Math.round(changePct * 100) / 100,
        atmStrike: newAtm,
        optionChain: updatedChain,
        systemStatus: {
          ...current.systemStatus,
          lastTickTime: new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }),
          lastUpdateEpoch: Date.now(),
          serverRequestsCount: current.systemStatus.serverRequestsCount + 1,
        }
      });
    }
  }

  scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn('[WS] Max reconnect attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(10000, this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1));
    setTimeout(() => {
      this.connect();
    }, delay);
  }
}

export const websocketService = new WebSocketService();
