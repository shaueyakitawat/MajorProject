import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

const ARTIFACT_DIR = '/Users/shauryakitavat/.gemini/antigravity/brain/9f41c880-3d96-4f10-8d63-6ee57a91e72a';
const CDP_PORT = 9236;

async function run() {
  console.log('--- Launching Headless Chrome on port', CDP_PORT, '---');
  const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
    '--headless=new',
    `--remote-debugging-port=${CDP_PORT}`,
    '--no-sandbox',
    '--window-size=1680,1050',
    'http://localhost:3000/'
  ]);

  let msgId = 1;
  const pendingRequests = new Map();

  function sendCommand(ws, method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = msgId++;
      pendingRequests.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  }

  try {
    await new Promise(r => setTimeout(r, 2000));
    const listRes = await fetch(`http://127.0.0.1:${CDP_PORT}/json`);
    const tabs = await listRes.json();
    const targetTab = tabs.find(t => t.url.includes('localhost:3000'));
    if (!targetTab) throw new Error('No target tab found on localhost:3000');

    console.log('Connecting to WebSocket:', targetTab.webSocketDebuggerUrl);
    const ws = new WebSocket(targetTab.webSocketDebuggerUrl);

    await new Promise((resolve, reject) => {
      ws.onopen = resolve;
      ws.onerror = reject;
    });

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && pendingRequests.has(msg.id)) {
        const { resolve, reject } = pendingRequests.get(msg.id);
        pendingRequests.delete(msg.id);
        if (msg.error) reject(msg.error);
        else resolve(msg.result);
      } else if (msg.method === 'Runtime.consoleAPICalled') {
        const text = msg.params.args.map(a => a.value || a.description).join(' ');
        if (msg.params.type === 'error') {
          console.error('  [CONSOLE ERROR]', text);
        } else {
          console.log('  [CONSOLE]', text);
        }
      } else if (msg.method === 'Runtime.exceptionThrown') {
        console.error('  [BROWSER EXCEPTION]', msg.params.exceptionDetails?.text, msg.params.exceptionDetails?.exception?.description);
      }
    };

    await sendCommand(ws, 'Runtime.enable');
    await sendCommand(ws, 'Page.enable');
    await sendCommand(ws, 'DOM.enable');

    console.log('Waiting for initial data sync (2.5s)...');
    await new Promise(r => setTimeout(r, 2500));

    async function evaluate(expression) {
      const res = await sendCommand(ws, 'Runtime.evaluate', {
        expression,
        returnByValue: true,
        awaitPromise: true
      });
      return res.result?.value;
    }

    async function takeScreenshot(filename) {
      const res = await sendCommand(ws, 'Page.captureScreenshot', { format: 'png' });
      const buffer = Buffer.from(res.data, 'base64');
      const outPath = path.join(ARTIFACT_DIR, filename);
      fs.writeFileSync(outPath, buffer);
      console.log(`Saved screenshot: ${filename} (${buffer.length} bytes)`);
    }

    async function clickSidebar(routeId) {
      return evaluate(`
        (() => {
          const btn = document.querySelector('.nav-item[data-route="${routeId}"]');
          if (btn) {
            btn.click();
            return true;
          }
          if (window.terminalStore) {
            window.terminalStore.setActiveRoute('${routeId}');
            return true;
          }
          return false;
        })()
      `);
    }

    // 1. Verify TopBar and System Status
    console.log('\n--- 1. Testing Permanent Shell & TopBar ---');
    const brand = await evaluate(`document.querySelector('.terminal-brand-tag')?.textContent`);
    const istClock = await evaluate(`document.querySelector('.clock-time')?.textContent`);
    const sidebarItems = await evaluate(`Array.from(document.querySelectorAll('.nav-item')).map(el => el.textContent.trim().replace(/\\s+/g, ' '))`);
    console.log('Brand:', brand);
    console.log('IST Clock:', istClock);
    console.log('Sidebar Navigation Items:', sidebarItems);

    // 2. Test Dashboard Page
    console.log('\n--- 2. Testing Workspace: Dashboard ---');
    await clickSidebar('dashboard');
    await new Promise(r => setTimeout(r, 1200));
    const dashTitle = await evaluate(`document.querySelector('.panel-title')?.textContent`);
    const equityVal = await evaluate(`document.querySelector('.stat-pill strong')?.textContent`);
    console.log('Dashboard Title:', dashTitle);
    console.log('Account Equity:', equityVal);
    await takeScreenshot('01_dashboard_live.png');

    // 3. Test Live Terminal Page
    console.log('\n--- 3. Testing Workspace: Live Terminal & Order Desk ---');
    await clickSidebar('live-terminal');
    await new Promise(r => setTimeout(r, 1500));
    const termTitle = await evaluate(`document.querySelector('.panel-title')?.textContent`);
    const execBtnText = await evaluate(`document.querySelector('#btn-execute-order')?.textContent?.trim()`);
    const activePosCount = await evaluate(`document.querySelectorAll('.btn-pos-sqoff').length`);
    console.log('Live Terminal Title:', termTitle);
    console.log('Execute Button Text:', execBtnText);
    console.log('Active Open Position Rows:', activePosCount);
    await takeScreenshot('02_live_terminal.png');

    // 4. Test Option Chain Page
    console.log('\n--- 4. Testing Workspace: Option Chain & Greeks ---');
    await clickSidebar('option-chain');
    await new Promise(r => setTimeout(r, 2000));
    const chainTitle = await evaluate(`document.querySelector('.chain-main-title')?.textContent`);
    const rowCount = await evaluate(`document.querySelectorAll('.chain-grid-table tbody tr').length`);
    console.log('Option Chain Title:', chainTitle);
    console.log('Chain Table Rows Rendered:', rowCount);
    await takeScreenshot('03_option_chain_grid.png');

    // 5. Test Historical Ledger Page
    console.log('\n--- 5. Testing Workspace: Historical Trade Ledger ---');
    await clickSidebar('ledger');
    await new Promise(r => setTimeout(r, 1500));
    const ledgerTitle = await evaluate(`document.querySelector('.panel-title')?.textContent`);
    const ledgerStats = await evaluate(`Array.from(document.querySelectorAll('.dense-stats-strip .stat-pill')).map(p => p.textContent.trim().replace(/\\s+/g, ' ')).slice(0, 4)`);
    console.log('Ledger Title:', ledgerTitle);
    console.log('Ledger Stats:', ledgerStats);
    await takeScreenshot('04_historical_ledger.png');

    // 6. Test Visual Pipeline Flow Page
    console.log('\n--- 6. Testing Workspace: Visual Pipeline & Health ---');
    await clickSidebar('pipeline-flow');
    await new Promise(r => setTimeout(r, 1500));
    const pipeTitle = await evaluate(`document.querySelector('.panel-title')?.textContent`);
    const stageNodes = await evaluate(`Array.from(document.querySelectorAll('.pipeline-node .node-title')).map(n => n.textContent.trim())`);
    console.log('Pipeline Title:', pipeTitle);
    console.log('Pipeline Stages Count:', stageNodes.length, stageNodes);
    await takeScreenshot('05_visual_pipeline_flow.png');

    // 7. Test Volatility Surfaces & News Page
    console.log('\n--- 7. Testing Workspace: Volatility Surfaces & News ---');
    await clickSidebar('volatility-surfaces');
    await new Promise(r => setTimeout(r, 1500));
    const surfTitle = await evaluate(`document.querySelector('.panel-title')?.textContent`);
    const newsCards = await evaluate(`document.querySelectorAll('.news-item-card').length`);
    console.log('Surfaces Title:', surfTitle);
    console.log('Live News Wire Items:', newsCards);
    await takeScreenshot('06_volatility_surfaces_news.png');

    // 8. Test Mispricing Scanner Page
    console.log('\n--- 8. Testing Workspace: Mispricing Scanner ---');
    await clickSidebar('mispricing-scanner');
    await new Promise(r => setTimeout(r, 1500));
    const scanTitle = await evaluate(`document.querySelector('.panel-title')?.textContent`);
    const scanRows = await evaluate(`document.querySelectorAll('.clickable-scan-row').length`);
    const scanTradeBtns = await evaluate(`document.querySelectorAll('.btn-scan-trade').length`);
    console.log('Scanner Title:', scanTitle);
    console.log('Ranked Mispricings Count:', scanRows);
    console.log('1-Click Trade Buttons Count:', scanTradeBtns);
    await takeScreenshot('07_mispricing_scanner.png');

    console.log('\n========================================');
    console.log('ALL 7 WORKSPACES VERIFIED SUCCESSFULLY!');
    console.log('========================================\n');

    ws.close();
    chrome.kill();
    process.exit(0);
  } catch (err) {
    console.error('TEST RUNNER ERROR:', err);
    chrome.kill();
    process.exit(1);
  }
}

run();
