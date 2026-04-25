// OpenGrid Control Room
const API = window.location.origin;
const AGENT_COLORS = ['#00bfff','#ff69b4','#ff6347','#32cd32','#9370db','#ffa500'];
const AGENT_NAMES = ['Bengaluru','Mysuru','Kalburagi','Hassan','Tumakuru','Bagalkot'];

// Real Karnataka state boundary path (source: @svg-maps/india)
const KARNATAKA_PATH = "m 124.338,505.46021 -0.617,-0.44733 0.776,-0.16422 -0.063,-0.8604 1.544,-0.77275 0.48,-0.70223 0.476,0.96821 0.881,0.0413 1.521,-0.74857 0.512,-1.53442 -0.938,-0.17228 0.62,-0.86141 0.404,0.86745 0.379,-0.0181 -0.412,-1.05888 1.641,-3.03861 -0.711,-0.35364 -0.968,0.47151 -0.458,-0.38889 1.391,-1.25837 1.141,0.50879 -0.068,-1.30269 0.567,-0.8997 -0.205,-0.93495 -1.688,-0.57629 -0.027,-0.50476 -1.422,-0.24583 -0.407,0.51987 0.312,-0.51181 -0.538,-0.73446 0.051,-1.1828 0.369,-0.24886 0.389,0.56622 0.156,-0.64581 -0.554,-0.135 -0.079,-1.12941 -0.891,-0.14911 0.075,-0.95309 -0.652,0.58133 -0.327,-0.41207 0.683,-0.18639 -0.196,-0.9007 0.79,0.92891 0.32,-1.12336 0.758,-0.0786 -0.063,0.39998 0.572,0.23676 0.284,-1.11026 1.444,-0.57126 0.104,-1.2241 0.432,0.74655 1.118,-0.14407 0.474,1.77622 1.304,-0.51987 0.135,-0.67805 0.996,0.0504 -0.625,-0.72439 0.746,-0.8191 0.043,-0.88055 3.282,-1.21706 1.441,0.0192 -0.248,-1.88302 1.091,-0.48057 0.066,-0.60249 -0.842,-0.44329 0.238,-0.33752 1.924,-0.0121 0.034,0.3486 1.225,-0.50375 1.062,1.64625 1.016,0 -0.135,0.69014 0.684,0.0373 1.401,-0.74252 0.119,-1.76514 1.19,0.0494 1.035,-0.52289 0.759,0.28311 0.772,-0.47957 0.515,0.92992 1.629,-0.45438 0.114,-0.9672 0.706,0.10276 0.024,0.73447 0.719,0.40703 0.619,-0.20251 -0.049,-1.65431 -0.596,-0.0151 0.725,-0.57931 0.002,-0.68712 -1.057,-1.6664 0.714,-0.83722 -0.047,-1.16568 -1.129,-0.91884 0.15,-0.85738 -0.592,-0.16422 -0.131,-0.72741 0.78,-0.19646 0.414,-1.88201 0.878,0.4302 0.285,0.99642 0.96,-0.20352 1.367,1.13646 0.469,-1.15761 0.779,0.81405 0.529,-0.69215 0.134,1.39841 0.785,0.64883 2.583,-0.66294 0.506,0.53196 0.889,-0.79693 0.877,0.55916 0.264,0.96015 -0.072,-1.13243 1.508,-0.56823 0.659,0.96922 1.418,-0.42618 0.181,0.86343 0.616,-0.0262 0.552,-1.2634 -0.964,-0.12593 0.234,-1.3037 -0.827,0.0463 -0.06,-0.80197 0.926,-0.54304 -0.661,-0.0191 0.474,-0.61155 -0.546,-0.44733 -0.175,-1.14955 1.758,-0.20553 0.273,-0.88459 1.268,-0.35766 -0.062,-1.16265 0.781,-0.0373 0.001,-0.96115 1.038,-0.0242 -0.001,1.27348 0.863,-1.45483 1.02,1.77017 0.573,0.1743 0.159,-1.01455 0.617,-0.24079 -0.249,-0.98735 0.985,-0.11384 0.532,-0.86746 -1.061,-0.67301 0.067,-0.90271 1.3,0.65386 2.379,-1.03067 0.026,-2.60337 0.773,-0.14206 -0.16,-0.75159 0.445,-0.51584 -0.957,-0.41912 0.661,-1.51628 0.707,-0.0796 0.755,0.56923 0.186,-0.46546 0.52,0.69316 1.072,-0.008 -0.279,-0.93496 1.14,-0.47453 0.43,-1.41956 0.746,0.0645 -0.226,-0.76772 1.039,-1.27851 -0.101,-0.84126 1.616,-0.99742 0.517,0.51987 0.577,-0.38386 0.002,1.03772 0.845,0.269 -1.074,1.7198 1.624,0.0917 0.607,1.02866 0.938,-0.40804 -0.015,-0.62465 0.847,0.33953 0,0 1.11,0.2952 -0.81,1.70972 0.701,1.07298 0.059,1.15661 -1.148,1.00649 0.974,0.96115 1.129,0.37378 0.151,0.52592 -0.197,0.50576 -0.424,-0.25087 -0.15,1.209 -0.657,-0.11788 0.241,0.83219 -0.501,-0.0524 -0.482,1.20598 -0.497,-0.19243 -0.316,0.55916 -0.134,0.41509 1.287,0.40501 -0.083,0.37479 -2.338,1.22814 -0.218,2.41597 1.049,0.33349 0.243,0.55815 0.54,-0.71029 0.439,0.5229 0.867,-0.29319 0.04,0.66193 1.965,0.59442 -0.034,0.72036 -0.752,-0.18336 0.098,-0.48461 -0.258,0.59946 -0.617,0.134 -0.007,0.56521 -0.783,-0.21964 -0.013,0.54203 -1.307,0.0504 0.531,0.50879 -0.157,0.70222 -0.605,0.39595 -0.995,-0.35968 -0.368,1.80544 0.429,0.27202 -1.552,1.23318 0.386,0.24079 -0.812,1.03369 2.148,1.26239 0.77,2.12078 -0.963,2.15403 0.372,2.84517 -0.704,-0.0887 -0.296,1.50218 0.909,0.0564 -0.037,0.73648 -1.015,0.33852 0.343,0.5511 0.763,-0.2025 -0.109,1.3712 -1.522,0.41509 0.5,1.0357 -0.758,0.15516 -0.268,0.58132 -1.458,-0.16019 -0.097,0.3899 -1.189,0.12191 1.036,1.42158 1.22,0.50879 1.44,0.37176 1.732,-0.28613 2.033,0.83622 -0.027,1.10724 -0.53,-0.23676 -0.653,0.7657 -0.682,-0.11284 -0.286,0.39393 0.025,0.55614 0.46,0.0212 -0.568,1.41352 0.064,0.93395 0.476,0.26698 -0.391,1.59084 0.405,0.6186 -0.014,1.7742 0,0 -5.454,-0.80499 -2.208,0.37379 -1.622,0.9007 -0.915,1.47195 0.871,0.1884 -0.433,1.93137 1.711,1.64222 -0.184,0.7385 -0.728,-0.6045 -1.092,0.41408 -0.056,2.91167 -1.145,-0.13803 -0.032,0.3355 1.193,1.21202 0.715,2.46333 1.007,-0.11788 0.12,0.81406 0.68,0.0907 0.34,0.5773 -0.906,0.82212 0.78,0.59543 -0.01,0.97425 -0.536,0.13601 0.459,0.48158 -1.574,2.61647 -0.792,-0.11788 0.123,-0.51583 -0.967,-0.008 -0.395,0.4171 -2.2,-0.39796 -1.67,-1.34803 -0.475,0.42113 0.216,1.18784 -0.435,1.01455 1.342,0.40904 0.765,-0.2821 -0.329,3.46982 -1.432,0.53599 0.371,0.96821 -0.793,2.87338 0.828,1.60897 0.583,0.10075 0.893,1.1828 2.16,-0.21258 -0.62,0.71835 -0.046,0.98633 -0.596,-0.30325 -0.627,0.50375 -0.084,0.94805 1.486,1.13344 -0.528,0.47251 0.271,0.69316 2.34,0.0121 0.538,0.65286 0.623,-0.0846 0.143,-1.60595 0.842,-1.08709 1.67,0.57729 1.03,-0.43423 -0.033,1.19086 1.667,0.1471 -0.081,0.84932 0.594,0.82615 0.668,-0.43524 -0.852,-1.8004 0.223,-0.64278 1.187,0.32743 0.259,0.81305 0.87,0.009 0.087,2.61143 -2.317,-0.3093 -0.272,0.77174 -0.606,0.11284 -0.067,0.61155 0.946,-0.48662 0.12,0.32643 -1.45,1.73995 1.197,0.3365 -0.162,0.82514 1.151,0.008 -0.48,0.70525 0.413,0.58032 -0.744,0.63372 -0.03,-0.38487 -0.881,0.0242 0.114,-1.85279 -0.843,-0.91682 -3.478,0.71734 -0.549,-1.09213 -2.039,-0.23978 -0.322,-0.96921 0.241,-1.61301 -1.637,-0.35766 -0.098,0.50577 -0.954,0.14911 -0.162,0.60449 0.907,0.0826 1.005,1.33896 -0.919,0.91884 2.193,2.09761 0.114,0.60853 -0.502,0.0876 -1.023,1.70468 0.506,1.54953 0.395,0.21158 0.313,-0.83522 0.706,0.70324 0.737,-0.47554 1.493,0.134 -0.091,-1.42461 -0.803,-0.6186 0.809,-0.16422 -0.137,-0.92488 0.441,-0.37983 0.037,1.24325 0.547,-0.46042 0.138,0.42617 0.467,-0.72339 0.348,1.19691 1.182,-0.38386 0.274,0.68006 0.826,-0.4302 1.362,0.2277 -0.332,0.77476 1.021,0.0474 -0.161,2.61646 0.695,-0.0846 0.092,-0.58435 0.522,0.45539 0.154,-1.25535 0.762,0.59141 0.828,-0.58536 0.537,0.3496 0.324,-0.16926 -0.55,-0.43624 0.809,-0.44028 0.442,-0.0363 -0.136,0.54505 0.666,-0.19746 0.276,0.6186 0.086,-1.24527 1.374,-0.48259 -0.051,-0.49669 1.082,-0.53297 -0.447,-1.03671 0.25,-0.56723 1.438,0.0796 0.515,0.73345 1.148,-1.15156 0.243,1.23519 -0.745,0.2831 0.044,1.30169 0.444,-0.005 0.406,-0.89566 1.102,0.18941 0.07,-0.73145 1.516,0.98937 0.098,1.37926 -0.697,0.93798 0.512,0.50173 -0.084,0.55715 -0.865,-0.0816 -0.12,0.4574 0.469,0.68309 1.57,-0.28815 0.1,0.54506 0.7,0.15616 -0.224,1.28859 0.93,-0.66394 3.414,0.19545 -0.746,4.80576 0.884,0.48965 -0.636,0.26497 0.508,0.35262 0.695,-0.33146 0.241,0.44632 0.749,-0.20553 1.027,1.12638 0.729,-0.94402 0.457,0.80499 -0.184,1.24425 -0.581,0.36573 0.589,0.66091 -1.263,0.79391 0.402,0.47957 -0.545,0.33751 0.056,0.62163 -1.11,0.45639 0.133,1.46793 -0.738,-0.11486 0.275,1.46087 -1.203,0.11788 -0.689,-0.70726 -0.886,1.73994 -1.298,-0.005 -0.428,2.03715 0,0 -2.093,-0.37478 -1.548,-1.55457 -0.666,-0.0756 -0.281,1.08406 -0.42,-0.004 -0.75,-1.15459 -0.435,0.7657 -0.326,-0.17833 0.528,-0.73245 -0.35,-0.48057 -2.781,0.95812 0.306,1.00952 -1.425,2.63964 -0.578,-0.20956 -0.533,0.52994 -0.504,-0.54002 -1.339,0.35666 0.157,0.78484 -0.582,1.35407 0.177,1.09314 0.583,0.15515 -0.649,0.67402 1.043,-0.19042 -0.107,1.47699 -0.34,1.17273 -1.279,1.50318 -1.518,0.46849 -0.095,1.27851 5.457,0.74958 0.881,1.32285 -1.654,2.04924 -0.607,1.53744 -3.686,0.12292 -0.157,1.20799 -0.505,-0.269 0.073,1.05888 -0.775,1.89308 -1.251,-0.60147 -0.699,0.42415 -0.864,-0.84327 -0.902,-0.0877 -0.308,0.39997 -2.601,0.44129 0.136,1.076 -0.789,-0.26195 -0.316,-1.11429 -0.716,0.26598 0.195,-0.41106 -0.57,-0.40803 -0.663,0.0413 -0.276,0.76872 -1.254,-0.38788 -1.49,2.97816 0.469,0.90473 -0.285,0.58435 -0.435,-0.48562 -1.471,-0.28512 -3.897,0.009 -0.412,-1.29161 -0.758,-0.58939 -1.106,0.91783 -0.584,-0.0897 0,0 -0.566,-0.89365 0.471,-0.34255 -0.235,-0.77678 -1.521,0.48561 -1.318,-1.56061 -1.12,0.0746 -0.722,-1.36415 -1.59,0.27001 -0.003,-2.55803 -2.375,1.01354 -2.464,-0.37278 -1.096,-0.93294 -0.517,-1.86185 -1.73,0.19444 -0.323,-0.81909 -0.82,0.19545 -0.572,-1.09817 -1.219,-0.17933 -1.97,-2.90361 -1.331,-0.005 0.047,-1.72382 -1.168,-0.86343 0.021,-0.95712 1.17,-0.18034 -0.168,-0.78686 -1.542,0.8725 -0.125,-0.73447 -1.125,-0.59946 -0.09,-0.98634 1.068,-0.45136 -1.071,-0.56823 -1.126,1.05183 -0.449,-1.34098 -0.885,0.17329 -0.339,-0.3496 0.161,-0.92388 -1.351,-0.46042 -0.063,0.67401 -0.739,0.13602 0.039,-1.17374 -0.891,0.11788 0.106,-0.29318 -0.574,-0.15012 0.499,-0.65689 -0.342,-0.6448 -2.621,0.77376 0,0 -0.965,-2.10365 -2.634,-10.6573 -0.512,-6.16488 -1.337,-5.02237 -0.768,-1.72786 -0.809,-0.39594 -0.627,-1.24728 -0.64,-3.47486 -0.611,-0.87048 -1.843,-6.03994 0.826,-0.61357 -0.599,-0.48662 -0.181,0.68611 -0.971,0.0302 -0.313,-1.75002 -0.524,-0.54808 0.32,-0.28814 -0.384,-1.61905 -0.669,-0.71633 -0.622,0.65084 -2.291,-1.75103 0.587,-0.13299 0.157,-0.89768 -0.396,-0.0121 -0.308,-1.05989 0,0 0.879,-0.538 0.754,0.24986 -0.068,-0.91279 0.831,0.64278 1.22,-0.98231 -0.176,-0.52289 0.851,-1.06593 -0.502,-1.21605 0.235,-1.02664 0.676,-0.8876 -0.318,-0.85033 -1.029,-0.74857 1.761,-0.76671 -0.278,-1.61602 -0.957,-0.46446 -0.003,-1.18481 -0.548,-1.00952 0.647,-0.7939 -0.69,-0.86645 0.298,-0.95108 -0.278,-0.97123 -0.496,-0.26799 -0.384,0.38083 -0.483,-0.69517 -0.35,0.62969 -0.986,0.0383 z";

let state = {
    sessionId: null, task: 'task_karnataka', step: 0, done: false,
    numAgents: 0, zoneInfo: {}, observations: {}, taskConfigs: {},
    rewardHistory: [], freqHistory: [], perAgentRewards: {},
    totalReward: 0, autoRunning: false, autoTimer: null,
    safetyTotal: 0, lastOversight: null, mapScale: 1, alarms: []
};

// --- Init ---
function isKarnatakaTask(taskId) {
    return taskId.includes('karnataka');
}

function buildTaskButtons(tasks) {
    const procContainer = document.getElementById('proceduralTasks');
    const kaContainer = document.getElementById('karnatakaTasks');
    procContainer.innerHTML = '';
    kaContainer.innerHTML = '';

    // Display-friendly names
    const nameMap = {
        'task_easy': 'Easy', 'task_medium': 'Medium', 'task_hard': 'Hard',
        'task_karnataka': 'Full ★',
        'karnataka_easy': 'Easy', 'karnataka_medium': 'Medium', 'karnataka_hard': 'Hard',
    };

    tasks.forEach(t => {
        const btn = document.createElement('button');
        btn.className = 'task-btn' + (t.id === state.task ? ' active' : '');
        if (isKarnatakaTask(t.id)) btn.classList.add('ka');
        btn.dataset.task = t.id;
        const label = nameMap[t.id] || t.id.replace('task_','').replace('karnataka_','');
        btn.innerHTML = `<span class="task-name">${label}</span><span class="task-info">${t.num_buses}b · ${t.num_agents}a</span>`;
        btn.addEventListener('click', () => {
            document.querySelectorAll('.task-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.task = t.id;
            // Destroy map so it reinitializes with correct bounds
            if (leafletMap) { leafletMap.remove(); leafletMap = null; mapLayers = {lines:null,nodes:null,badges:null}; }
            mapFitted = false;
            resetEpisode();
        });
        if (t.id.startsWith('task_') && !t.id.includes('karnataka')) {
            procContainer.appendChild(btn);
        } else {
            kaContainer.appendChild(btn);
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    fetch(`${API}/tasks`).then(r=>r.json()).then(d=>{
        d.forEach(t => state.taskConfigs[t.id] = t);
        buildTaskButtons(d);
        resetEpisode();
        setTimeout(() => document.getElementById('loading').classList.add('hidden'), 800);
    });
});

// --- API Calls ---
async function resetEpisode() {
    stopAutoRun();
    state.step = 0; state.done = false; state.totalReward = 0;
    state.rewardHistory = []; state.freqHistory = []; state.safetyTotal = 0;
    state.alarms = [];
    mapFitted = false;
    document.getElementById('alarmLog').innerHTML = '';
    document.getElementById('simStatus').textContent = 'RUNNING';
    try {
        const r = await fetch(`${API}/reset_multi?task_id=${state.task}`, {method:'POST'});
        const d = await r.json();
        state.sessionId = d.session_id;
        state.numAgents = d.num_agents;
        state.zoneInfo = d.zone_info;
        state.observations = d.observations;
        state.perAgentRewards = {};
        for (let i = 0; i < d.num_agents; i++) state.perAgentRewards[i] = [];
        updateAll();
    } catch(e) { showAlert('critical', 'Reset failed: ' + e.message); }
}

async function stepEpisode() {
    if (!state.sessionId || state.done) return;
    const actions = {};
    for (let i = 0; i < state.numAgents; i++) {
        const obs = state.observations[String(i)];
        actions[String(i)] = generateHeuristicAction(i, obs);
    }
    try {
        const r = await fetch(`${API}/step_multi?session_id=${state.sessionId}`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({agent_actions: actions})
        });
        const d = await r.json();
        state.step++;
        state.observations = d.observations;
        state.totalReward += d.team_reward;
        state.rewardHistory.push(d.team_reward);
        state.lastOversight = d.oversight_report;
        state.done = d.done;
        const freq = getAvgFreq(d.observations);
        state.freqHistory.push(freq);
        // safety_reports is a string-keyed dict {"0": {...}, "1": {...}}, not an array
        Object.values(d.safety_reports || {}).forEach(sr => { if (sr.was_corrected) state.safetyTotal++; });
        for (const [aid, rew] of Object.entries(d.rewards)) {
            if (!state.perAgentRewards[aid]) state.perAgentRewards[aid] = [];
            state.perAgentRewards[aid].push(rew.value);
        }
        if (d.done) {
            document.getElementById('simStatus').textContent = d.info.is_blackout ? 'BLACKOUT' : 'COMPLETE';
            stopAutoRun();
        }
        updateAll(d);
    } catch(e) { showAlert('critical', 'Step failed: ' + e.message); stopAutoRun(); }
}

async function getGrade() {
    if (!state.sessionId) return;
    try {
        const r = await fetch(`${API}/grader?session_id=${state.sessionId}`);
        const d = await r.json();
        document.getElementById('episodeScore').textContent = d.score.toFixed(4);
        document.getElementById('episodeScore').style.color =
            d.score > 0.7 ? 'var(--status-normal)' : d.score > 0.4 ? 'var(--status-warning)' : 'var(--status-critical)';
    } catch(e) { showAlert('warning', 'Grade failed: ' + e.message); }
}

// --- Heuristic Agent ---
function generateHeuristicAction(agentId, obs) {
    if (!obs) return {bus_adjustments: [], topology_actions: []};
    const freq = obs.grid_frequency || 50;
    const error = 50.0 - freq;
    const buses = obs.local_buses || [];
    const adjs = [];
    buses.forEach(b => {
        // Exclude slack — physics solver overwrites its injection; adjusting it wastes the action
        if (b.type === 'battery' || b.type === 'generator') {
            let delta = error * 8;
            delta = Math.max(-15, Math.min(15, delta));
            if (Math.abs(delta) > 0.5) adjs.push({bus_id: b.id, delta: Math.round(delta*10)/10});
        }
    });
    return {bus_adjustments: adjs, topology_actions: []};
}

// --- Auto Run ---
function toggleAutoRun() {
    if (state.autoRunning) { stopAutoRun(); }
    else { state.autoRunning = true; document.getElementById('btnAutoRun').classList.add('active'); autoStep(); }
}
function stopAutoRun() {
    state.autoRunning = false;
    if (state.autoTimer) clearTimeout(state.autoTimer);
    document.getElementById('btnAutoRun').classList.remove('active');
}
async function autoStep() {
    if (!state.autoRunning || state.done) { stopAutoRun(); return; }
    await stepEpisode();
    if (state.autoRunning && !state.done) state.autoTimer = setTimeout(autoStep, 200);
}

// --- UI Updates ---
function updateAll(stepData) {
    updateHeader();
    updateFrequency();
    updateSystemSummary();
    updateOversight();
    updateAgentCards(stepData);
    updateLeaderboard();
    updateGridMap();
    updateCharts();
    updateAlarmLog(stepData);
}

function getAvgFreq(obs) {
    let sum=0, n=0;
    for (const o of Object.values(obs||state.observations)) { sum += (o.grid_frequency||50); n++; }
    return n ? sum/n : 50;
}

function updateHeader() {
    const maxSteps = state.taskConfigs[state.task]?.max_steps || 50;
    document.getElementById('headerStep').textContent = `${state.step} / ${maxSteps}`;
    document.getElementById('headerAgents').textContent = `${state.numAgents} Active`;
    document.getElementById('headerReward').textContent = state.totalReward.toFixed(2);
    document.getElementById('headerEpisode').textContent = state.task.replace('task_','').toUpperCase();
    const freq = getAvgFreq();
    const el = document.getElementById('headerFreq');
    el.textContent = freq.toFixed(2) + ' Hz';
    el.className = 'value ' + freqClass(freq);
    document.getElementById('totalSteps').textContent = state.step;
    document.getElementById('blackoutStatus').textContent = state.done && document.getElementById('simStatus').textContent==='BLACKOUT' ? 'Yes' : 'No';
}

function updateFrequency() {
    const freq = getAvgFreq();
    const cls = freqClass(freq);
    const colors = {normal:'#00e5a0',warning:'#ffd700',critical:'#ff3d3d'};
    const col = colors[cls];
    // Arc gauge
    const container = document.getElementById('freqArc');
    const W=200, H=110, cx=100, cy=100, r=80;
    const minF=49, maxF=51;
    const pct = Math.max(0,Math.min(1,(freq-minF)/(maxF-minF)));
    const startA=Math.PI, endA=0;
    const needleA = startA - pct*(startA-endA);
    let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
    // Background arc
    svg += `<path d="M${cx-r},${cy} A${r},${r} 0 0,1 ${cx+r},${cy}" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="10" stroke-linecap="round"/>`;
    // Colored segments
    const segs = [{f:49,t:49.5,c:'#ff3d3d'},{f:49.5,t:49.85,c:'#ffd700'},{f:49.85,t:50.15,c:'#00e5a0'},{f:50.15,t:50.5,c:'#ffd700'},{f:50.5,t:51,c:'#ff3d3d'}];
    segs.forEach(s => {
        const a1=Math.PI-((s.f-minF)/(maxF-minF))*Math.PI;
        const a2=Math.PI-((s.t-minF)/(maxF-minF))*Math.PI;
        const x1=cx+r*Math.cos(a1),y1=cy-r*Math.sin(a1);
        const x2=cx+r*Math.cos(a2),y2=cy-r*Math.sin(a2);
        svg += `<path d="M${x1},${y1} A${r},${r} 0 0,0 ${x2},${y2}" fill="none" stroke="${s.c}" stroke-width="6" opacity="0.25" stroke-linecap="round"/>`;
    });
    // Needle
    const nx=cx+(r-12)*Math.cos(needleA), ny=cy-(r-12)*Math.sin(needleA);
    svg += `<line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="${col}" stroke-width="2.5" stroke-linecap="round"/>`;
    svg += `<circle cx="${cx}" cy="${cy}" r="4" fill="${col}"/>`;
    // Value text
    svg += `<text x="${cx}" y="${cy-20}" text-anchor="middle" fill="${col}" font-family="JetBrains Mono" font-size="28" font-weight="700" style="text-shadow:0 0 15px ${col}40">${freq.toFixed(2)}</text>`;
    svg += `<text x="${cx}" y="${cy-6}" text-anchor="middle" fill="#90a4ae" font-family="Inter" font-size="11">Hz</text>`;
    // Scale labels
    svg += `<text x="18" y="${cy+14}" fill="#546e7a" font-size="8" font-family="JetBrains Mono">49.0</text>`;
    svg += `<text x="${W-30}" y="${cy+14}" fill="#546e7a" font-size="8" font-family="JetBrains Mono">51.0</text>`;
    svg += `<text x="${cx}" y="12" text-anchor="middle" fill="#546e7a" font-size="8" font-family="JetBrains Mono">50.0</text>`;
    svg += '</svg>';
    container.innerHTML = svg;
    document.getElementById('freqDev').textContent = `Deviation: ${(freq-50).toFixed(3)} Hz | Nominal: 50.00 Hz`;
    // Grid condition
    const gc = document.getElementById('gridCondition');
    const dev = Math.abs(freq-50);
    if(dev<0.15){gc.textContent='NORMAL';gc.className='grid-condition normal';}
    else if(dev<0.3){gc.textContent='CONSERVATIVE OPS';gc.className='grid-condition conservative';}
    else if(dev<0.5){gc.textContent='CONSERVATION ALERT';gc.className='grid-condition alert';}
    else{gc.textContent='EMERGENCY';gc.className='grid-condition emergency';}
}

function freqClass(f) { return Math.abs(f-50)<0.5?'normal':Math.abs(f-50)<1?'warning':'critical'; }

function updateSystemSummary() {
    let gen=0, load=0, lines=0, overloaded=0, totalLines=0;
    for (const obs of Object.values(state.observations)) {
        gen += obs.zone_gen_mw || 0;
        load += obs.zone_load_mw || 0;
        (obs.internal_lines||[]).concat(obs.boundary_lines||[]).forEach(l => {
            totalLines++; if(l.connected) lines++;
            if(l.connected && l.rho > 1) overloaded++;
        });
    }
    document.getElementById('totalGen').textContent = gen.toFixed(1) + ' MW';
    document.getElementById('totalLoad').textContent = load.toFixed(1) + ' MW';
    document.getElementById('netBalance').textContent = (gen-load).toFixed(1) + ' MW';
    document.getElementById('linesConnected').textContent = `${lines} / ${totalLines}`;
    const olEl = document.getElementById('linesOverloaded');
    olEl.textContent = overloaded;
    olEl.style.color = overloaded > 0 ? 'var(--status-critical)' : 'var(--status-normal)';
}

function updateOversight() {
    const o = state.lastOversight;
    if (!o) return;
    const cs = document.getElementById('coordScore');
    cs.textContent = o.coordination_score.toFixed(2);
    cs.style.color = o.coordination_score > 0.7 ? 'var(--status-normal)' : o.coordination_score > 0.4 ? 'var(--status-warning)' : 'var(--status-critical)';
    document.getElementById('conflicts').textContent = o.conflicting_actions_detected;
    document.getElementById('safetyCorrTotal').textContent = state.safetyTotal;
    document.getElementById('selfishActions').textContent = o.selfish_actions_detected;
}

function updateAlarmLog(stepData) {
    if (!stepData) return;
    const logEl = document.getElementById('alarmLog');
    let newAlarms = [];
    const timeStr = `T+${String(state.step).padStart(2,'0')}s`;

    // Check frequency
    const freq = getAvgFreq();
    if (Math.abs(freq - 50) > 0.5) {
        newAlarms.push({t: timeStr, msg: `FREQ DEVIATION: ${freq.toFixed(2)} Hz`, type: Math.abs(freq-50)>1?'crit':'warn'});
    }

    // Check lines and safety
    for (const [aid, obs] of Object.entries(state.observations)) {
        (obs.internal_lines||[]).concat(obs.boundary_lines||[]).forEach(l => {
            if (l.rho > 1.0) newAlarms.push({t: timeStr, msg: `OVERLOAD: Line ${l.id} at ${(l.rho*100).toFixed(0)}%`, type: 'crit'});
            else if (l.rho > 0.9) newAlarms.push({t: timeStr, msg: `CONGESTION: Line ${l.id} at ${(l.rho*100).toFixed(0)}%`, type: 'warn'});
        });
        const sr = stepData.safety_reports?.[aid];
        if (sr && sr.was_corrected) {
            newAlarms.push({t: timeStr, msg: `AGENT ${aid} SAFETY CORRECTED`, type: 'warn'});
        }
    }

    if (state.done && document.getElementById('simStatus').textContent==='BLACKOUT') {
         newAlarms.push({t: timeStr, msg: `SYSTEM COLLAPSE - BLACKOUT`, type: 'crit'});
    }

    if (newAlarms.length > 0) {
        state.alarms = [...newAlarms, ...state.alarms].slice(0, 50); // Keep last 50
        logEl.innerHTML = state.alarms.map(a => `<div class="alarm-entry ${a.type}"><span class="alarm-time">[${a.t}]</span>${a.msg}</div>`).join('');
    }
}

function updateAgentCards(stepData) {
    const container = document.getElementById('agentCards');
    container.innerHTML = '';
    for (let i = 0; i < state.numAgents; i++) {
        const obs = state.observations[String(i)];
        const zi = state.zoneInfo[String(i)] || {};
        const sr = stepData?.safety_reports?.[String(i)];
        const rew = stepData?.rewards?.[String(i)];
        const cumReward = (state.perAgentRewards[i]||[]).reduce((a,b)=>a+b,0);
        const wasCorrected = sr?.was_corrected || false;
        const cardClass = wasCorrected ? 'warning' : 'active';
        const html = `
        <div class="agent-card ${cardClass}">
            <div class="agent-header">
                <div class="agent-name">
                    <span class="agent-dot" style="background:${AGENT_COLORS[i]}"></span>
                    Agent ${i} - ${zi.zone_name||AGENT_NAMES[i]}
                </div>
                <span class="agent-status-badge ${wasCorrected?'corrected':'active'}">${wasCorrected?'Corrected':'Safe'}</span>
            </div>
            <div class="agent-metrics">
                <div class="agent-metric">
                    <div class="label">Step Reward</div>
                    <div class="value" style="color:${(rew?.value||0)>=0?'var(--status-normal)':'var(--status-critical)'}">${(rew?.value||0).toFixed(2)}</div>
                </div>
                <div class="agent-metric">
                    <div class="label">Cumulative</div>
                    <div class="value">${cumReward.toFixed(1)}</div>
                </div>
                <div class="agent-metric">
                    <div class="label">Zone Load</div>
                    <div class="value">${(obs?.zone_load_mw||0).toFixed(0)} MW</div>
                </div>
                <div class="agent-metric">
                    <div class="label">Zone Gen</div>
                    <div class="value">${(obs?.zone_gen_mw||0).toFixed(0)} MW</div>
                </div>
            </div>
            <div class="safety-shield ${wasCorrected?'corrected':'safe'}">
                ${wasCorrected?'&#9888; Safety Corrected':'&#9635; Safety OK'}
                ${sr?.blocked_topology_actions ? ` | ${sr.blocked_topology_actions} blocked` : ''}
            </div>
            <div class="sparkline-container"><svg id="spark${i}"></svg></div>
        </div>`;
        container.innerHTML += html;
    }
    // Draw sparklines
    for (let i = 0; i < state.numAgents; i++) {
        drawSparkline(`spark${i}`, state.perAgentRewards[i]||[], AGENT_COLORS[i]);
    }
}

function updateLeaderboard() {
    const lb = document.getElementById('leaderboard');
    const agents = [];
    for (let i = 0; i < state.numAgents; i++) {
        const cum = (state.perAgentRewards[i]||[]).reduce((a,b)=>a+b,0);
        const zi = state.zoneInfo[String(i)] || {};
        agents.push({id:i, name: zi.zone_name||AGENT_NAMES[i], score: cum});
    }
    agents.sort((a,b) => b.score - a.score);
    lb.innerHTML = agents.map((a,idx) => `
        <li>
            <span class="agent-label">
                <span class="agent-dot" style="background:${AGENT_COLORS[a.id]};width:6px;height:6px;border-radius:50%;display:inline-block;"></span>
                ${['#1','#2','#3'][idx]||'  '} ${a.name}
            </span>
            <span class="score" style="color:${AGENT_COLORS[a.id]}">${a.score.toFixed(1)}</span>
        </li>`).join('');
}

// --- Grid Map (Leaflet) ---
let leafletMap = null;
let mapLayers = { lines: null, nodes: null, badges: null };
let mapFitted = false;

function initLeafletMap() {
    const container = document.getElementById('gridMap');
    if (leafletMap) return;
    
    const isKa = isKarnatakaTask(state.task);
    // Karnataka bounds: tight crop around the state
    const kaBounds = [[11.5, 73.8], [18.5, 79.0]];
    
    const mapOpts = {
        center: isKa ? [14.5, 76.5] : [15, 76],
        zoom: isKa ? 7 : 6,
        zoomControl: true,
        attributionControl: false,
        minZoom: isKa ? 6 : 3,
        maxZoom: 15,
        preferCanvas: true,
    };
    // Lock panning for Karnataka tasks
    if (isKa) {
        mapOpts.maxBounds = L.latLngBounds(kaBounds).pad(0.15);
        mapOpts.maxBoundsViscosity = 1.0;
    }

    leafletMap = L.map(container, mapOpts);
    
    if (isKa) {
        // Real map tiles for Karnataka tasks
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            subdomains: 'abcd',
            maxZoom: 19,
        }).addTo(leafletMap);

        L.control.attribution({position: 'bottomright', prefix: false})
            .addAttribution('© <a href="https://carto.com/">CARTO</a>')
            .addTo(leafletMap);

        leafletMap.fitBounds(kaBounds, { padding: [20, 20] });
    }
    // Procedural grids: no tiles — plain dark background via CSS

    // Layer groups for easy clearing
    mapLayers.lines = L.layerGroup().addTo(leafletMap);
    mapLayers.nodes = L.layerGroup().addTo(leafletMap);
    mapLayers.badges = L.layerGroup().addTo(leafletMap);
    
    // Fix Leaflet size after container is fully rendered
    setTimeout(() => {
        leafletMap.invalidateSize();
        if (isKa) leafletMap.fitBounds(kaBounds, { padding: [20, 20] });
    }, 200);
}

function updateGridMap() {
    if (!leafletMap) initLeafletMap();
    
    // Clear previous layers
    mapLayers.lines.clearLayers();
    mapLayers.nodes.clearLayers();
    mapLayers.badges.clearLayers();

    const typeIcons = {slack:'S',generator:'G',load:'L',battery:'B',solar:'PV',wind:'W'};
    const typeColors = {slack:'#00e5a0',generator:'#f5a623',load:'#e94560',battery:'#4a90d9',solar:'#ffeb3b',wind:'#64ffda'};

    // Collect buses — merge static config with runtime state
    let allBuses = [];
    const taskCfg = state.taskConfigs[state.task];
    const runtimeState = {};
    for (const obs of Object.values(state.observations)) {
        (obs.local_buses||[]).forEach(b => { runtimeState[b.id] = b; });
    }
    if (taskCfg && taskCfg.buses) {
        allBuses = taskCfg.buses.map(b => {
            const rt = runtimeState[b.id];
            return {...b, p_injection: rt ? rt.p_injection : (b.base_p || 0)};
        });
    } else {
        allBuses = Object.values(runtimeState);
    }

    const hasGPS = allBuses.some(b => b.lat !== undefined && b.lon !== undefined);
    
    // For non-GPS tasks, generate fake positions around Karnataka center
    const busPositions = {};
    const zones = [
        {id:0, lat:16.8, lon:76.8, color:AGENT_COLORS[0], label:'Kalaburagi'},
        {id:1, lat:15.2, lon:75.2, color:AGENT_COLORS[1], label:'Hubballi'},
        {id:2, lat:12.8, lon:75.5, color:AGENT_COLORS[2], label:'Mysuru'},
        {id:3, lat:13.2, lon:77.5, color:AGENT_COLORS[3], label:'Bengaluru'},
    ];

    allBuses.forEach((b, idx) => {
        const aid = findAgent(b.id);
        let lat, lon;
        if (hasGPS && b.lat !== undefined && b.lon !== undefined) {
            lat = b.lat;
            lon = b.lon;
        } else {
            // Fallback: spread around zone center
            const zd = zones[aid >= 0 && aid < zones.length ? aid : 0];
            const zBuses = allBuses.filter(bb => findAgent(bb.id) === aid);
            const zi = zBuses.indexOf(b);
            const a = (zi / Math.max(zBuses.length, 1)) * Math.PI * 2;
            lat = zd.lat + Math.cos(a) * 0.3;
            lon = zd.lon + Math.sin(a) * 0.3;
        }
        busPositions[b.id] = {lat, lon, bus: b, agent: aid};
    });

    // Draw transmission lines
    const drawnLines = new Set();
    for (const obs of Object.values(state.observations)) {
        (obs.internal_lines||[]).concat(obs.boundary_lines||[]).forEach(l => {
            if (drawnLines.has(l.id)) return;
            drawnLines.add(l.id);
            const parts = l.id.replace('L_','').split('_');
            const fromId = parseInt(parts[0]);
            const toId = parseInt(parts[1]);
            const from = busPositions[fromId];
            const to = busPositions[toId];
            if (!from || !to) return;

            const lc = !l.connected ? '#4a5568' : l.rho > 1 ? '#ff1744' : l.rho > 0.8 ? '#ff9100' : '#e91e63';
            const w = !l.connected ? 2 : l.rho > 1 ? 6 : l.rho > 0.8 ? 5 : 3.5;

            // Glow layer for overloaded/congested lines
            if (l.connected && l.rho > 0.8) {
                const glow = L.polyline(
                    [[from.lat, from.lon], [to.lat, to.lon]],
                    { color: lc, weight: w + 6, opacity: 0.15, dashArray: null, interactive: false }
                );
                mapLayers.lines.addLayer(glow);
            }

            const polyline = L.polyline(
                [[from.lat, from.lon], [to.lat, to.lon]],
                { color: lc, weight: w, dashArray: l.connected ? '12 6' : '4 6', opacity: 0.95 }
            );
            // Show tooltip with flow info
            const flowStr = l.connected ? `${l.flow.toFixed(0)} MW · ${(l.rho*100).toFixed(0)}% load` : 'Disconnected';
            polyline.bindTooltip(`<b>${l.id}</b><br>${flowStr}`, {
                permanent: false, className: 'leaflet-tooltip-dark', direction: 'center'
            });

            // Permanent label for high-flow lines
            if (l.connected && Math.abs(l.flow) > 10) {
                const midLat = (from.lat + to.lat) / 2;
                const midLon = (from.lon + to.lon) / 2;
                const flowLabel = L.divIcon({
                    className: 'line-flow-label',
                    html: `<span style="color:${lc};text-shadow:0 0 4px #000,0 0 8px #000;font-size:9px;font-family:'JetBrains Mono',monospace;font-weight:600;white-space:nowrap;">${Math.abs(l.flow).toFixed(0)}MW</span>`,
                    iconSize: [40, 12],
                    iconAnchor: [20, 6],
                });
                L.marker([midLat, midLon], { icon: flowLabel, interactive: false }).addTo(mapLayers.lines);
            }

            mapLayers.lines.addLayer(polyline);
        });
    }
    // Ensure lines are visible above tiles
    if (drawnLines.size > 0) {
        mapLayers.lines.eachLayer(l => { if (l.bringToFront) l.bringToFront(); });
    }

    // Draw bus markers
    for (const [bid, pos] of Object.entries(busPositions)) {
        const b = pos.bus;
        const col = AGENT_COLORS[pos.agent] || '#4a5568';
        const fill = typeColors[b.type] || '#666';
        const r = b.type === 'slack' ? 12 : b.type === 'load' ? 7 : 9;
        const inj = (b.p_injection !== undefined ? b.p_injection : 0);
        const busLabel = b.name || `${b.type} ${b.id}`;
        const icon = typeIcons[b.type] || '?';

        // Outer ring (zone color)
        const outerRing = L.circleMarker([pos.lat, pos.lon], {
            radius: r + 4, fillColor: 'transparent', fillOpacity: 0,
            color: col, weight: 1.5, opacity: 0.4
        });
        mapLayers.nodes.addLayer(outerRing);

        // Inner node
        const marker = L.circleMarker([pos.lat, pos.lon], {
            radius: r, fillColor: fill, fillOpacity: 0.9,
            color: col, weight: 1, opacity: 0.6
        });

        // Rich tooltip
        const tooltipHtml = `
            <div style="font-family:'JetBrains Mono',monospace;font-size:11px;min-width:120px;">
                <b style="color:${fill}">${icon}</b> <b>${busLabel}</b><br>
                <span style="color:#888">Type:</span> ${b.type}<br>
                <span style="color:#888">Injection:</span> <b>${inj.toFixed(1)} MW</b><br>
                <span style="color:#888">Zone:</span> ${state.zoneInfo[String(pos.agent)]?.zone_name || 'Agent ' + pos.agent}
            </div>`;
        marker.bindTooltip(tooltipHtml, { className: 'leaflet-tooltip-dark', direction: 'top', offset: [0, -r] });
        mapLayers.nodes.addLayer(marker);

        // Label under node
        const labelIcon = L.divIcon({
            className: 'bus-label-icon',
            html: `<span style="color:${fill};text-shadow:0 0 4px #000;font-size:9px;font-family:'JetBrains Mono',monospace;white-space:nowrap;">${busLabel}</span>`,
            iconSize: [80, 14],
            iconAnchor: [40, -r - 2],
        });
        L.marker([pos.lat, pos.lon], { icon: labelIcon, interactive: false }).addTo(mapLayers.nodes);

        // MW label above node
        const mwIcon = L.divIcon({
            className: 'bus-mw-icon',
            html: `<span style="color:#e0e0e0;text-shadow:0 0 4px #000;font-size:10px;font-weight:700;font-family:'JetBrains Mono',monospace;">${inj.toFixed(0)}</span>`,
            iconSize: [40, 14],
            iconAnchor: [20, r + 16],
        });
        L.marker([pos.lat, pos.lon], { icon: mwIcon, interactive: false }).addTo(mapLayers.nodes);
    }

    // Zone badge overlays
    zones.slice(0, state.numAgents).forEach(z => {
        const zi = state.zoneInfo[String(z.id)] || {};
        const name = zi.zone_name || z.label || AGENT_NAMES[z.id];
        const cum = (state.perAgentRewards[z.id] || []).reduce((a, b) => a + b, 0);
        
        const badgeIcon = L.divIcon({
            className: 'zone-badge-leaflet',
            html: `<div style="background:rgba(10,14,26,0.85);border:1px solid ${z.color};border-radius:6px;padding:4px 10px;text-align:center;white-space:nowrap;">
                <div style="color:${z.color};font-size:11px;font-weight:700;font-family:'JetBrains Mono',monospace;">${name}</div>
                <div style="color:${z.color};font-size:10px;font-family:'JetBrains Mono',monospace;opacity:0.8">${cum.toFixed(1)} pts</div>
            </div>`,
            iconSize: [120, 36],
            iconAnchor: [60, 50],
        });
        L.marker([z.lat, z.lon], { icon: badgeIcon, interactive: false }).addTo(mapLayers.badges);
    });

    // Fit map to bus extent on first data load
    if (!mapFitted && allBuses.length > 0) {
        const lats = allBuses.filter(b => b.lat).map(b => b.lat);
        const lons = allBuses.filter(b => b.lon).map(b => b.lon);
        if (lats.length > 0) {
            leafletMap.fitBounds([
                [Math.min(...lats) - 0.5, Math.min(...lons) - 0.5],
                [Math.max(...lats) + 0.5, Math.max(...lons) + 0.5]
            ]);
            mapFitted = true;
        }
    }
}

function showBusTooltip(e, node) {
    const tt = document.getElementById('busTooltip');
    const zi = state.zoneInfo[node.dataset.agent]||{};
    document.getElementById('ttTitle').textContent = `Bus ${node.dataset.bus} (${node.dataset.type})`;
    document.getElementById('ttType').textContent = node.dataset.type;
    document.getElementById('ttInj').textContent = node.dataset.inj + ' MW';
    document.getElementById('ttZone').textContent = zi.zone_name || 'Zone ' + node.dataset.agent;
    tt.style.left = (e.clientX + 12) + 'px';
    tt.style.top = (e.clientY - 20) + 'px';
    tt.classList.add('visible');
}
function hideBusTooltip() { document.getElementById('busTooltip').classList.remove('visible'); }

function findAgent(busId) {
    for (const [aid, zi] of Object.entries(state.zoneInfo)) {
        if ((zi.bus_ids||[]).includes(busId)) return parseInt(aid);
    }
    return -1;
}

// --- Charts ---
function drawSparkline(id, data, color) {
    const el = document.getElementById(id);
    if (!el || !data.length) return;
    const w = el.clientWidth||120, h = el.clientHeight||22;
    const min = Math.min(...data), max = Math.max(...data);
    const range = max-min || 1;
    const pts = data.slice(-30).map((v,i,a) => `${(i/(a.length-1||1))*w},${h-(((v-min)/range)*h*0.8+h*0.1)}`).join(' ');
    el.innerHTML = `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" opacity="0.8"/>`;
}

function updateCharts() {
    // Reward chart
    drawChart('rewardChart', state.rewardHistory, 'var(--chart-reward)', 'Reward');
    // Frequency chart
    drawChart('freqChart', state.freqHistory, 'var(--chart-supply)', 'Hz', 49, 51);
}

function drawChart(containerId, data, color, label, fixedMin, fixedMax) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const W = el.clientWidth||300, H = el.clientHeight||140;
    if (!data.length) { el.innerHTML = `<svg viewBox="0 0 ${W} ${H}"><text x="${W/2}" y="${H/2}" text-anchor="middle" fill="var(--text-muted)" font-size="11">Waiting for data...</text></svg>`; return; }
    const pad = {t:10,r:10,b:20,l:40};
    const cw = W-pad.l-pad.r, ch = H-pad.t-pad.b;
    const min = fixedMin !== undefined ? fixedMin : Math.min(...data);
    const max = fixedMax !== undefined ? fixedMax : Math.max(...data);
    const range = max-min||1;
    const pts = data.map((v,i) => `${pad.l+(i/(data.length-1||1))*cw},${pad.t+ch-(((v-min)/range)*ch)}`).join(' ');
    let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
    // Grid lines
    for(let i=0;i<=4;i++){const y=pad.t+ch*i/4;const v=(max-((max-min)*i/4)).toFixed(1);svg+=`<line x1="${pad.l}" y1="${y}" x2="${W-pad.r}" y2="${y}" stroke="rgba(255,255,255,0.05)"/><text x="${pad.l-4}" y="${y+3}" text-anchor="end" fill="var(--text-muted)" font-size="8" font-family="JetBrains Mono">${v}</text>`;}
    svg += `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5"/>`;
    // Fill area
    const firstX = pad.l, lastX = pad.l+(data.length-1)/(data.length-1||1)*cw;
    svg += `<polygon points="${pts} ${lastX},${pad.t+ch} ${firstX},${pad.t+ch}" fill="${color}" opacity="0.08"/>`;
    svg += '</svg>';
    el.innerHTML = svg;
    // Gen mix chart
    if (containerId === 'freqChart') updateGenMix();
}

function updateGenMix() {
    const el = document.getElementById('genMixChart');
    if (!el) return;
    const W = el.clientWidth||200, H = el.clientHeight||140;
    let types = {};
    for (const obs of Object.values(state.observations)) {
        (obs.local_buses||[]).forEach(b => {
            if (b.p_injection > 0) types[b.type] = (types[b.type]||0) + b.p_injection;
        });
    }
    const total = Object.values(types).reduce((a,b)=>a+b,0) || 1;
    const colors = {slack:'#00e5a0',generator:'#f5a623',solar:'#ffeb3b',wind:'#64ffda',battery:'#4a90d9'};
    let svg = `<svg viewBox="0 0 ${W} ${H}">`;
    const cx=W/2, cy=H/2-5, r=Math.min(W,H)*0.3;
    let startAngle = -Math.PI/2;
    for (const [type, val] of Object.entries(types)) {
        const pct = val/total;
        const endAngle = startAngle + pct * Math.PI*2;
        const x1=cx+r*Math.cos(startAngle), y1=cy+r*Math.sin(startAngle);
        const x2=cx+r*Math.cos(endAngle), y2=cy+r*Math.sin(endAngle);
        const large = pct > 0.5 ? 1 : 0;
        svg += `<path d="M${cx},${cy} L${x1},${y1} A${r},${r} 0 ${large},1 ${x2},${y2} Z" fill="${colors[type]||'#666'}" opacity="0.8"/>`;
        const mid = (startAngle+endAngle)/2;
        if (pct > 0.08) {
            const lx=cx+(r+14)*Math.cos(mid), ly=cy+(r+14)*Math.sin(mid);
            svg += `<text x="${lx}" y="${ly}" text-anchor="middle" fill="var(--text-secondary)" font-size="8">${type} ${(pct*100).toFixed(0)}%</text>`;
        }
        startAngle = endAngle;
    }
    svg += `<circle cx="${cx}" cy="${cy}" r="${r*0.55}" fill="var(--bg-card)"/>`;
    svg += `<text x="${cx}" y="${cy-2}" text-anchor="middle" fill="var(--text-primary)" font-family="JetBrains Mono" font-size="14" font-weight="700">${total.toFixed(0)}</text>`;
    svg += `<text x="${cx}" y="${cy+10}" text-anchor="middle" fill="var(--text-muted)" font-size="8">MW</text>`;
    svg += '</svg>';
    el.innerHTML = svg;
}

// --- Alerts ---
function showAlert(type, msg) {
    const el = document.getElementById('alertBanner');
    el.className = `alert-banner ${type} visible`;
    document.getElementById('alertText').textContent = msg;
    setTimeout(() => el.classList.remove('visible'), 5000);
}
function dismissAlert() { document.getElementById('alertBanner').classList.remove('visible'); }

// --- Map Controls ---
function zoomMap(factor) { state.mapScale *= factor; updateGridMap(); }
function resetMapView() { state.mapScale = 1; updateGridMap(); }
