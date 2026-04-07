/**
 * OpenGrid  —  Real-time Power Grid Simulation Dashboard
 * ======================================================
 * Eco-Tech Green palette  ·  Force-directed topology  ·  Live charts
 */

// ============================  STATE  ============================
const state = {
    sessionId: null,
    taskId: null,
    observation: null,
    autoRunning: false,
    autoTimer: null,
    cumulativeReward: 0,
    freqHistory: [],
    rewardHistory: [],
    lastRewardComponents: null,
    done: false,
    nodePositions: {},
    hoveredNode: null,
    animFrame: null,
    particlePhase: 0,
};

const API = window.location.origin;

// ============================  PALETTE  ==========================
const BUS_COLORS = {
    slack:     '#e8f5e9',
    generator: '#00cc00',
    load:      '#e63946',
    battery:   '#a8dadc',
    solar:     '#ffb703',
    wind:      '#9b7fd4',
};
const BUS_LABELS = {
    slack: 'SLK', generator: 'GEN', load: 'LD',
    battery: 'BAT', solar: 'SOL', wind: 'WND',
};

// ============================  LOGGING  ==========================
function log(msg, level = 'info') {
    const body = document.getElementById('log-body');
    const now  = new Date().toLocaleTimeString('en-US', { hour12: false });
    const div  = document.createElement('div');
    div.className = `log-entry log-${level}`;
    div.innerHTML = `<span class="log-time">[${now}]</span> <span class="log-msg">${msg}</span>`;
    body.appendChild(div);
    body.scrollTop = body.scrollHeight;
    while (body.children.length > 200) body.removeChild(body.firstChild);
}
function clearLog() { document.getElementById('log-body').innerHTML = ''; }

// ============================  API  ==============================
async function apiGet(path) {
    const r = await fetch(`${API}${path}`);
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
}
async function apiPost(path, body = null) {
    const opts = { method: 'POST', headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(`${API}${path}`, opts);
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
}

// ============================  LAYOUT  ===========================
function computeLayout(obs) {
    const buses = obs.buses, lines = obs.lines, n = buses.length;
    const canvas = document.getElementById('topology-canvas');
    const W = canvas.clientWidth || canvas.width;
    const H = canvas.clientHeight || canvas.height;
    const cx = W / 2, cy = H / 2;
    const rad = Math.min(W, H) * 0.35;

    const pos = {};
    buses.forEach((b, i) => {
        const a = (2 * Math.PI * i) / n - Math.PI / 2;
        pos[b.id] = { x: cx + rad * Math.cos(a), y: cy + rad * Math.sin(a) };
    });

    const iters = 80, repK = 8000, attK = 0.005, ideal = rad * 0.7;
    for (let it = 0; it < iters; it++) {
        const f = {};
        buses.forEach(b => { f[b.id] = { x: 0, y: 0 }; });

        for (let i = 0; i < n; i++) {
            for (let j = i + 1; j < n; j++) {
                const a = buses[i].id, b = buses[j].id;
                let dx = pos[a].x - pos[b].x, dy = pos[a].y - pos[b].y;
                let d = Math.sqrt(dx * dx + dy * dy) || 1;
                let fr = repK / (d * d);
                f[a].x += (dx / d) * fr; f[a].y += (dy / d) * fr;
                f[b].x -= (dx / d) * fr; f[b].y -= (dy / d) * fr;
            }
        }

        lines.forEach(l => {
            const p = l.id.split('_');
            const u = +p[1], v = +p[2];
            if (!pos[u] || !pos[v]) return;
            let dx = pos[v].x - pos[u].x, dy = pos[v].y - pos[u].y;
            let d = Math.sqrt(dx * dx + dy * dy) || 1;
            let fa = attK * (d - ideal);
            f[u].x += (dx / d) * fa; f[u].y += (dy / d) * fa;
            f[v].x -= (dx / d) * fa; f[v].y -= (dy / d) * fa;
        });

        buses.forEach(b => {
            f[b.id].x += (cx - pos[b.id].x) * 0.01;
            f[b.id].y += (cy - pos[b.id].y) * 0.01;
        });

        const damp = 0.85, mx = 10;
        buses.forEach(b => {
            pos[b.id].x += Math.max(-mx, Math.min(mx, f[b.id].x * damp));
            pos[b.id].y += Math.max(-mx, Math.min(mx, f[b.id].y * damp));
            pos[b.id].x = Math.max(50, Math.min(W - 50, pos[b.id].x));
            pos[b.id].y = Math.max(50, Math.min(H - 50, pos[b.id].y));
        });
    }
    state.nodePositions = pos;
}

// ============================  TOPOLOGY  =========================
function drawTopology() {
    const canvas = document.getElementById('topology-canvas');
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    canvas.width  = canvas.clientWidth  * dpr;
    canvas.height = canvas.clientHeight * dpr;
    ctx.scale(dpr, dpr);
    const W = canvas.clientWidth, H = canvas.clientHeight;
    ctx.clearRect(0, 0, W, H);

    if (!state.observation) {
        ctx.fillStyle = 'rgba(165,214,167,0.18)';
        ctx.font = '500 14px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('Reset a task to view grid topology', W / 2, H / 2);
        return;
    }

    const obs = state.observation, pos = state.nodePositions;
    state.particlePhase += 0.02;

    // ---- Lines ----
    obs.lines.forEach(line => {
        const p = line.id.split('_');
        const u = +p[1], v = +p[2];
        if (!pos[u] || !pos[v]) return;
        const x1 = pos[u].x, y1 = pos[u].y, x2 = pos[v].x, y2 = pos[v].y;

        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
        if (!line.connected) {
            ctx.strokeStyle = 'rgba(100,100,100,0.15)';
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 6]);
        } else {
            const rho = Math.abs(line.rho);
            ctx.strokeStyle = rho > 0.9 ? 'rgba(230,57,70,0.8)'
                            : rho > 0.7 ? 'rgba(255,183,3,0.65)'
                            : 'rgba(0,153,0,0.3)';
            ctx.lineWidth = 1.2 + rho * 2.5;
            ctx.setLineDash([]);
        }
        ctx.stroke(); ctx.setLineDash([]);

        // Particles
        if (line.connected && Math.abs(line.flow) > 0.5) {
            const fl = line.flow, cnt = Math.min(4, Math.ceil(Math.abs(fl) / 15));
            for (let i = 0; i < cnt; i++) {
                let t = ((state.particlePhase * (fl > 0 ? 1 : -1) + i / cnt) % 1 + 1) % 1;
                ctx.beginPath();
                ctx.arc(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, 2.2, 0, Math.PI * 2);
                const rho = Math.abs(line.rho);
                ctx.fillStyle = rho > 0.9 ? 'rgba(230,57,70,0.85)'
                              : rho > 0.7 ? 'rgba(255,183,3,0.75)'
                              : 'rgba(0,204,0,0.6)';
                ctx.fill();
            }
        }

        // Flow label
        if (line.connected) {
            ctx.fillStyle = 'rgba(165,214,167,0.45)';
            ctx.font = '500 8px "JetBrains Mono", monospace';
            ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText(`${line.flow.toFixed(1)}`, (x1 + x2) / 2, (y1 + y2) / 2 - 7);
        }
    });

    // ---- Nodes ----
    obs.buses.forEach(bus => {
        const p = pos[bus.id]; if (!p) return;
        const col = BUS_COLORS[bus.type] || '#a5d6a7';
        const r = 20, hov = state.hoveredNode === bus.id;

        // Glow on hover
        if (hov) {
            const g = ctx.createRadialGradient(p.x, p.y, r, p.x, p.y, r + 18);
            g.addColorStop(0, col + '35'); g.addColorStop(1, 'transparent');
            ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.x, p.y, r + 18, 0, Math.PI * 2); ctx.fill();
        }

        // Ring
        ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fillStyle = col + '18'; ctx.fill();
        ctx.strokeStyle = col; ctx.lineWidth = hov ? 2.5 : 1.5; ctx.stroke();

        // SoC arc
        if (bus.type === 'battery' && bus.soc > 0) {
            ctx.beginPath();
            ctx.arc(p.x, p.y, r - 3, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (bus.soc / 50));
            ctx.strokeStyle = col + '90'; ctx.lineWidth = 2.5; ctx.stroke();
        }

        // Label inside node
        ctx.font = '600 9px "JetBrains Mono", monospace';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillStyle = col; ctx.fillText(BUS_LABELS[bus.type] || '?', p.x, p.y);

        // ID below
        ctx.fillStyle = 'rgba(232,245,233,0.7)';
        ctx.font = '600 9px Inter, sans-serif';
        ctx.fillText(`B${bus.id}`, p.x, p.y + r + 11);

        // Power
        ctx.fillStyle = bus.p_injection >= 0 ? 'rgba(0,204,0,0.65)' : 'rgba(230,57,70,0.65)';
        ctx.font = '500 8px "JetBrains Mono", monospace';
        ctx.fillText(`${bus.p_injection >= 0 ? '+' : ''}${bus.p_injection.toFixed(1)}`, p.x, p.y + r + 21);
    });

    // Blackout overlay
    if (obs.is_blackout) {
        ctx.fillStyle = 'rgba(230,57,70,0.06)'; ctx.fillRect(0, 0, W, H);
        ctx.fillStyle = '#e63946'; ctx.font = '800 26px Inter';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText('BLACKOUT', W / 2, H / 2);
    }
}

// ============================  SPARKLINES  =======================
function drawSparkline(canvasId, data, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const cw = canvas.clientWidth || 80, ch = canvas.clientHeight || 28;
    canvas.width = cw * dpr; canvas.height = ch * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, cw, ch);
    if (data.length < 2) return;

    const min = Math.min(...data), max = Math.max(...data);
    const range = max - min || 1;
    const toX = i => (i / (data.length - 1)) * cw;
    const toY = v => ch - 3 - ((v - min) / range) * (ch - 6);

    // Fill
    const grad = ctx.createLinearGradient(0, 0, 0, ch);
    grad.addColorStop(0, color + '25');
    grad.addColorStop(1, color + '00');
    ctx.beginPath(); ctx.moveTo(toX(0), toY(data[0]));
    for (let i = 1; i < data.length; i++) ctx.lineTo(toX(i), toY(data[i]));
    ctx.lineTo(toX(data.length - 1), ch); ctx.lineTo(0, ch); ctx.closePath();
    ctx.fillStyle = grad; ctx.fill();

    // Line
    ctx.beginPath(); ctx.moveTo(toX(0), toY(data[0]));
    for (let i = 1; i < data.length; i++) ctx.lineTo(toX(i), toY(data[i]));
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke();
}

// ============================  CHARTS  ===========================
function drawFreqChart() {
    const canvas = document.getElementById('freq-chart');
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * dpr; canvas.height = canvas.clientHeight * dpr;
    ctx.scale(dpr, dpr);
    const W = canvas.clientWidth, H = canvas.clientHeight;
    const pad = { l: 42, r: 14, t: 14, b: 22 };
    const gW = W - pad.l - pad.r, gH = H - pad.t - pad.b;
    ctx.clearRect(0, 0, W, H);

    const yMin = 48.5, yMax = 51.5;
    const toX = i => pad.l + (i / Math.max(1, state.freqHistory.length - 1)) * gW;
    const toY = v => pad.t + (1 - (v - yMin) / (yMax - yMin)) * gH;

    // Grid
    ctx.strokeStyle = 'rgba(0,153,0,0.06)'; ctx.lineWidth = 1;
    for (let hz = 49; hz <= 51; hz += 0.5) {
        const y = toY(hz);
        ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
        ctx.fillStyle = 'rgba(165,214,167,0.28)'; ctx.font = '500 8px "JetBrains Mono"';
        ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
        ctx.fillText(hz.toFixed(1), pad.l - 5, y);
    }

    // Band
    ctx.fillStyle = 'rgba(0,204,0,0.04)';
    ctx.fillRect(pad.l, toY(50.5), gW, toY(49.5) - toY(50.5));

    // Nominal
    ctx.strokeStyle = 'rgba(0,153,0,0.2)'; ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(pad.l, toY(50)); ctx.lineTo(W - pad.r, toY(50)); ctx.stroke();
    ctx.setLineDash([]);

    if (state.freqHistory.length > 1) {
        // Fill
        const g = ctx.createLinearGradient(0, pad.t, 0, pad.t + gH);
        g.addColorStop(0, 'rgba(0,153,0,0.12)'); g.addColorStop(1, 'rgba(0,153,0,0)');
        ctx.beginPath(); ctx.moveTo(toX(0), toY(state.freqHistory[0]));
        for (let i = 1; i < state.freqHistory.length; i++) ctx.lineTo(toX(i), toY(state.freqHistory[i]));
        ctx.lineTo(toX(state.freqHistory.length - 1), pad.t + gH); ctx.lineTo(toX(0), pad.t + gH);
        ctx.closePath(); ctx.fillStyle = g; ctx.fill();

        // Line
        ctx.beginPath(); ctx.moveTo(toX(0), toY(state.freqHistory[0]));
        for (let i = 1; i < state.freqHistory.length; i++) ctx.lineTo(toX(i), toY(state.freqHistory[i]));
        ctx.strokeStyle = '#00cc00'; ctx.lineWidth = 1.8; ctx.stroke();

        // Dot
        const lx = toX(state.freqHistory.length - 1);
        const ly = toY(state.freqHistory[state.freqHistory.length - 1]);
        ctx.beginPath(); ctx.arc(lx, ly, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = '#00cc00'; ctx.fill();
        ctx.strokeStyle = '#050a06'; ctx.lineWidth = 1.5; ctx.stroke();
    }

    ctx.fillStyle = 'rgba(165,214,167,0.25)'; ctx.font = '500 8px Inter';
    ctx.textAlign = 'center'; ctx.fillText('Timestep', W / 2, H - 3);
}

function drawRewardChart() {
    const canvas = document.getElementById('reward-chart');
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * dpr; canvas.height = canvas.clientHeight * dpr;
    ctx.scale(dpr, dpr);
    const W = canvas.clientWidth, H = canvas.clientHeight;
    const pad = { l: 42, r: 14, t: 14, b: 22 };
    const gW = W - pad.l - pad.r, gH = H - pad.t - pad.b;
    ctx.clearRect(0, 0, W, H);

    if (state.rewardHistory.length < 1) {
        ctx.fillStyle = 'rgba(165,214,167,0.18)'; ctx.font = '500 11px Inter';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText('Rewards will appear here', W / 2, H / 2);
        return;
    }

    const cum = []; let s = 0;
    state.rewardHistory.forEach(r => { s += r; cum.push(s); });

    let yMin = Math.min(0, ...cum), yMax = Math.max(1, ...cum);
    const yP = (yMax - yMin) * 0.1 || 1; yMin -= yP; yMax += yP;

    const toX = i => pad.l + (i / Math.max(1, cum.length - 1)) * gW;
    const toY = v => pad.t + (1 - (v - yMin) / (yMax - yMin)) * gH;

    // Zero
    ctx.strokeStyle = 'rgba(0,153,0,0.08)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad.l, toY(0)); ctx.lineTo(W - pad.r, toY(0)); ctx.stroke();

    // Y labels
    for (let i = 0; i <= 4; i++) {
        const v = yMin + (yMax - yMin) * i / 4;
        ctx.fillStyle = 'rgba(165,214,167,0.28)'; ctx.font = '500 8px "JetBrains Mono"';
        ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
        ctx.fillText(v.toFixed(0), pad.l - 5, toY(v));
    }

    // Bars
    const bw = Math.max(2, gW / state.rewardHistory.length - 1);
    state.rewardHistory.forEach((r, i) => {
        const x = toX(i) - bw / 2;
        const yt = toY(Math.max(0, r)), yb = toY(Math.min(0, r));
        ctx.fillStyle = r >= 0 ? 'rgba(0,204,0,0.22)' : 'rgba(230,57,70,0.22)';
        ctx.fillRect(x, yt, bw, yb - yt || 1);
    });

    // Cumulative line
    if (cum.length > 1) {
        const g = ctx.createLinearGradient(0, pad.t, 0, pad.t + gH);
        g.addColorStop(0, 'rgba(155,127,212,0.12)'); g.addColorStop(1, 'rgba(155,127,212,0)');
        ctx.beginPath(); ctx.moveTo(toX(0), toY(cum[0]));
        for (let i = 1; i < cum.length; i++) ctx.lineTo(toX(i), toY(cum[i]));
        const lx = toX(cum.length - 1);
        ctx.lineTo(lx, pad.t + gH); ctx.lineTo(toX(0), pad.t + gH);
        ctx.closePath(); ctx.fillStyle = g; ctx.fill();

        ctx.beginPath(); ctx.moveTo(toX(0), toY(cum[0]));
        for (let i = 1; i < cum.length; i++) ctx.lineTo(toX(i), toY(cum[i]));
        ctx.strokeStyle = '#9b7fd4'; ctx.lineWidth = 1.8; ctx.stroke();

        const ly = toY(cum[cum.length - 1]);
        ctx.beginPath(); ctx.arc(lx, ly, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = '#9b7fd4'; ctx.fill();
        ctx.strokeStyle = '#050a06'; ctx.lineWidth = 1.5; ctx.stroke();
    }

    ctx.fillStyle = 'rgba(165,214,167,0.25)'; ctx.font = '500 8px Inter';
    ctx.textAlign = 'center'; ctx.fillText('Timestep', W / 2, H - 3);
}

// ============================  STATS UPDATE  =====================
function updateStats() {
    const obs = state.observation; if (!obs) return;

    // Frequency
    const freq = obs.grid_frequency;
    const vf = document.getElementById('val-frequency');
    vf.textContent = freq.toFixed(2);
    const dev = Math.abs(freq - 50);
    vf.style.color = dev > 1 ? '#e63946' : dev > 0.5 ? '#ffb703' : '#00cc00';
    const bf = document.getElementById('bar-frequency');
    bf.style.width = `${Math.max(0, Math.min(100, (1 - dev / 2) * 100))}%`;
    bf.style.background = dev > 1 ? '#e63946' : dev > 0.5 ? '#ffb703' : '#00cc00';

    // Timestep
    document.getElementById('val-timestep').textContent = obs.timestep;
    const bt = document.getElementById('bar-timestep');
    bt.style.width = `${(obs.timestep / 50) * 100}%`;
    bt.style.background = '#00cc00';
    document.getElementById('delta-timestep').textContent = obs.timestep > 0 ? `Step ${obs.timestep}` : '';

    // Reward
    document.getElementById('val-reward').textContent = state.cumulativeReward.toFixed(1);
    const br = document.getElementById('bar-reward');
    br.style.width = `${Math.max(0, Math.min(100, (state.cumulativeReward + 100) / 200 * 100))}%`;
    br.style.background = state.cumulativeReward >= 0 ? '#9b7fd4' : '#e63946';

    // Score
    document.getElementById('val-score').textContent = '--';

    // Status
    const vb = document.getElementById('val-blackout');
    const bb = document.getElementById('bar-blackout');
    if (obs.is_blackout) {
        vb.textContent = 'BLACKOUT'; vb.style.color = '#e63946';
        bb.style.width = '100%'; bb.style.background = '#e63946';
    } else if (state.done) {
        vb.textContent = 'Complete'; vb.style.color = '#00cc00';
        bb.style.width = '100%'; bb.style.background = '#00cc00';
    } else {
        vb.textContent = 'Online'; vb.style.color = '#00cc00';
        bb.style.width = '100%'; bb.style.background = '#00cc00';
    }

    // Sparklines
    drawSparkline('spark-freq', state.freqHistory, '#00cc00');
    const cumR = []; let cs = 0;
    state.rewardHistory.forEach(r => { cs += r; cumR.push(cs); });
    drawSparkline('spark-reward', cumR, '#9b7fd4');
}

// ============================  TABLES  ===========================
function updateBusTable() {
    const tbody = document.getElementById('bus-table-body');
    const obs = state.observation; if (!obs) return;
    tbody.innerHTML = '';
    obs.buses.forEach(bus => {
        const c = BUS_COLORS[bus.type] || '#a5d6a7';
        const lbl = BUS_LABELS[bus.type] || '?';
        const soc = bus.type === 'battery' ? `${bus.soc.toFixed(1)} / 50` : '--';
        const ramp = bus.ramp_rate > 0 ? `${bus.ramp_rate.toFixed(0)}` : '--';
        const pc = bus.p_injection >= 0 ? '#00cc00' : '#e63946';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><span style="color:${c};font-weight:600">${lbl} B${bus.id}</span></td>
            <td><span class="badge" style="background:${c}14;color:${c}">${bus.type}</span></td>
            <td style="color:${pc}">${bus.p_injection >= 0 ? '+' : ''}${bus.p_injection.toFixed(2)} MW</td>
            <td>${soc}</td>
            <td>${ramp}</td>`;
        tbody.appendChild(tr);
    });
}

function updateLineTable() {
    const tbody = document.getElementById('line-table-body');
    const obs = state.observation; if (!obs) return;
    tbody.innerHTML = '';
    obs.lines.forEach(line => {
        const rho = Math.abs(line.rho);
        let rc, bc;
        if (!line.connected)   { rc = '#66bb6a'; bc = 'badge-off'; }
        else if (rho > 0.9)    { rc = '#e63946'; bc = 'badge-danger'; }
        else if (rho > 0.7)    { rc = '#ffb703'; bc = 'badge-warn'; }
        else                   { rc = '#00cc00'; bc = 'badge-ok'; }
        const cd = obs.cooldowns[line.id] || 0;
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="font-weight:600">${line.id}</td>
            <td><span class="badge ${line.connected ? 'badge-ok' : 'badge-off'}">${line.connected ? 'Active' : 'Open'}</span></td>
            <td>${line.connected ? line.flow.toFixed(2) + ' MW' : '--'}</td>
            <td><div class="rho-bar-wrap"><div class="rho-bar-bg"><div class="rho-bar-fill" style="width:${rho * 100}%;background:${rc}"></div></div><span class="rho-val" style="color:${rc}">${rho.toFixed(2)}</span></div></td>
            <td>${cd > 0 ? `<span class="badge badge-warn">${cd}</span>` : '--'}</td>`;
        tbody.appendChild(tr);
    });
}

function updateBreakdown() {
    const panel = document.getElementById('panel-breakdown');
    const box   = document.getElementById('breakdown-cards');
    if (!state.lastRewardComponents) { panel.style.display = 'none'; return; }
    panel.style.display = 'block';
    const comps = state.lastRewardComponents;
    box.innerHTML = '';
    Object.entries(comps).forEach(([k, v]) => {
        const cls = v > 0 ? 'bd-pos' : v < 0 ? 'bd-neg' : 'bd-zero';
        const d = document.createElement('div');
        d.className = 'bd-card';
        d.innerHTML = `<div class="bd-label">${k}</div><div class="bd-value ${cls}">${v >= 0 ? '+' : ''}${v.toFixed(3)}</div>`;
        box.appendChild(d);
    });
    const total = Object.values(comps).reduce((a, b) => a + b, 0);
    const tc = total > 0 ? 'bd-pos' : total < 0 ? 'bd-neg' : 'bd-zero';
    const td = document.createElement('div');
    td.className = 'bd-card';
    td.innerHTML = `<div class="bd-label">Total</div><div class="bd-value ${tc}">${total >= 0 ? '+' : ''}${total.toFixed(3)}</div>`;
    box.appendChild(td);
}

function setStatus(text, cls = '') {
    document.querySelector('.status-text').textContent = text;
    document.querySelector('.status-dot').className = 'status-dot ' + cls;
}

// ============================  ACTIONS  ==========================
async function resetEnv() {
    const taskId = document.getElementById('task-select').value;
    try {
        setStatus('Resetting...', 'running');
        log(`Resetting: ${taskId}`, 'info');
        const data = await apiPost(`/reset?task_id=${taskId}`);
        state.sessionId = data.session_id;
        state.taskId = taskId;
        state.observation = data.observation;
        state.cumulativeReward = 0;
        state.freqHistory = [data.observation.grid_frequency];
        state.rewardHistory = [];
        state.lastRewardComponents = null;
        state.done = false;
        state.particlePhase = 0;
        document.getElementById('session-id-display').textContent = data.session_id.substring(0, 16) + '...';
        document.getElementById('btn-step').disabled = false;
        document.getElementById('btn-auto').disabled = false;
        document.getElementById('btn-grade').disabled = false;
        computeLayout(state.observation);
        updateAll();
        setStatus('Ready', 'active');
        log(`Session started: ${data.session_id.substring(0, 12)}... | ${state.observation.buses.length} buses, ${state.observation.lines.length} lines`, 'success');
    } catch (err) {
        log(`Reset failed: ${err.message}`, 'error');
        setStatus('Error', 'error');
    }
}

function computeHeuristicAction(obs) {
    const adj = [], fe = obs.grid_frequency - 50.0;
    obs.buses.forEach(b => {
        if (b.type === 'battery' && Math.abs(fe) > 0.1) {
            let c = Math.max(-10, Math.min(10, -fe * 2));
            if ((c > 0 && b.soc > 0) || (c < 0 && b.soc < 50))
                adj.push({ bus_id: b.id, delta: c });
        }
    });
    obs.lines.forEach(l => {
        if (l.rho > 0.95 && l.connected) {
            obs.buses.forEach(b => {
                if (b.type === 'slack' && b.p_injection > 5)
                    adj.push({ bus_id: b.id, delta: -3.0 });
            });
        }
    });
    return { bus_adjustments: adj, topology_actions: [] };
}

async function stepOnce() {
    if (!state.sessionId || state.done) return;
    try {
        setStatus('Stepping...', 'running');
        const action = computeHeuristicAction(state.observation);
        const result = await apiPost(`/step?session_id=${state.sessionId}`, action);
        state.observation = result.observation;
        const reward = result.reward.value;
        const freq = result.observation.grid_frequency;
        state.cumulativeReward += reward;
        state.rewardHistory.push(reward);
        state.freqHistory.push(freq);
        state.lastRewardComponents = result.reward.components;
        state.done = result.done;
        updateAll();

        const tag = result.done ? (result.observation.is_blackout ? '[FAIL]' : '[DONE]') : '[STEP]';
        log(`${tag} Step ${result.observation.timestep}: freq=${freq.toFixed(2)} Hz, reward=${reward.toFixed(3)}, done=${result.done}`,
            result.done ? (result.observation.is_blackout ? 'error' : 'success') : 'info');

        if (result.done) {
            stopAutoStep();
            setStatus(result.observation.is_blackout ? 'Blackout!' : 'Complete',
                      result.observation.is_blackout ? 'error' : 'active');
            document.getElementById('btn-step').disabled = true;
            document.getElementById('btn-auto').disabled = true;
        } else {
            setStatus('Running', 'active');
        }
    } catch (err) {
        log(`Step failed: ${err.message}`, 'error');
        setStatus('Error', 'error');
        stopAutoStep();
    }
}

function toggleAutoStep() { state.autoRunning ? stopAutoStep() : startAutoStep(); }

function startAutoStep() {
    if (state.done || !state.sessionId) return;
    state.autoRunning = true;
    const btn = document.getElementById('btn-auto');
    btn.classList.add('is-running'); btn.textContent = 'Stop';
    setStatus('Auto Running', 'running');
    log('Auto-step started (heuristic policy)', 'info');
    autoLoop(parseInt(document.getElementById('speed-select').value));
}

async function autoLoop(speed) {
    if (!state.autoRunning || state.done) return;
    await stepOnce();
    if (state.autoRunning && !state.done)
        state.autoTimer = setTimeout(() => autoLoop(speed), speed);
}

function stopAutoStep() {
    state.autoRunning = false;
    if (state.autoTimer) { clearTimeout(state.autoTimer); state.autoTimer = null; }
    const btn = document.getElementById('btn-auto');
    btn.classList.remove('is-running'); btn.textContent = 'Auto Run';
    if (!state.done) setStatus('Paused', 'active');
    log('Auto-step stopped', 'warn');
}

async function gradeSession() {
    if (!state.sessionId) return;
    try {
        log('Requesting grade...', 'info');
        const result = await apiGet(`/grader?session_id=${state.sessionId}`);
        const score = result.score;
        document.getElementById('val-score').textContent = score.toFixed(4);
        const bs = document.getElementById('bar-score');
        bs.style.width = `${Math.min(100, score * 100)}%`;
        bs.style.background = score > 0.8 ? '#00cc00' : score > 0.5 ? '#ffb703' : '#e63946';
        // Show scoring context
        const ds = document.getElementById('delta-score');
        if (ds) {
            const label = score >= 0.85 ? 'Excellent' : score >= 0.5 ? 'Good' : 'Poor';
            ds.textContent = label;
            ds.style.color = score >= 0.85 ? '#00cc00' : score >= 0.5 ? '#ffb703' : '#e63946';
        }
        log(`[GRADE] score=${score.toFixed(4)} | reward=${result.cumulative_reward.toFixed(2)} | floor=${result.reward_floor.toFixed(1)} | ceiling=${result.reward_ceiling.toFixed(1)} | blackout=${result.is_blackout}`, 'success');
        log(`[SCORE] Analytical ceiling: ${result.reward_ceiling.toFixed(1)} (max_steps × 1.2) | Floor: ${result.reward_floor.toFixed(1)} (adversarial thrashing)`, 'info');
    } catch (err) {
        log(`Grading failed: ${err.message}`, 'error');
    }
}

// ============================  RENDER ALL  =======================
function updateAll() {
    updateStats();
    drawTopology();
    drawFreqChart();
    drawRewardChart();
    updateBusTable();
    updateLineTable();
    updateBreakdown();
}

// ============================  INTERACTIVITY  ====================
function setupCanvasHover() {
    const canvas = document.getElementById('topology-canvas');
    const tip = document.getElementById('topology-tooltip');
    canvas.addEventListener('mousemove', e => {
        if (!state.observation) return;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left, my = e.clientY - rect.top;
        let found = false;
        state.observation.buses.forEach(bus => {
            const p = state.nodePositions[bus.id]; if (!p) return;
            if ((mx - p.x) ** 2 + (my - p.y) ** 2 < 26 * 26) {
                found = true; state.hoveredNode = bus.id;
                tip.style.display = 'block';
                tip.style.left = (mx + 14) + 'px'; tip.style.top = (my - 8) + 'px';
                let h = `<strong style="color:${BUS_COLORS[bus.type]}">${BUS_LABELS[bus.type]} Bus ${bus.id} (${bus.type})</strong><br>`;
                h += `P: ${bus.p_injection.toFixed(2)} MW<br>`;
                if (bus.type === 'battery') h += `SoC: ${bus.soc.toFixed(1)} / 50 MWh<br>`;
                if (bus.ramp_rate > 0) h += `Ramp: ${bus.ramp_rate.toFixed(0)} MW/step`;
                tip.innerHTML = h;
                drawTopology();
            }
        });
        if (!found) { state.hoveredNode = null; tip.style.display = 'none'; drawTopology(); }
    });
    canvas.addEventListener('mouseleave', () => {
        state.hoveredNode = null; tip.style.display = 'none'; drawTopology();
    });
}

// ============================  ANIMATION  ========================
function animLoop() {
    if (state.observation && !state.done) drawTopology();
    state.animFrame = requestAnimationFrame(animLoop);
}

// ============================  INIT  =============================
window.addEventListener('DOMContentLoaded', () => {
    drawTopology(); drawFreqChart(); drawRewardChart();
    setupCanvasHover(); animLoop();
    log('OpenGrid Dashboard v4 loaded. Scoring: analytical ceiling (max_steps × 1.2). Select a task and click Reset.', 'success');
});

window.addEventListener('resize', () => {
    if (state.observation) { computeLayout(state.observation); updateAll(); }
    else { drawTopology(); drawFreqChart(); drawRewardChart(); }
});
