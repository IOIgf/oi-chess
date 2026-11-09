function getClientId() {
  let cid = localStorage.getItem('oi_client_id');
  if (!cid) {
    cid = 'c_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem('oi_client_id', cid);
  }
  return cid;
}

const state = {
  clientId: getClientId(),
  playerId: null, roomId: null, nickname: '选手', rating: null,
  selectedBench: null, lastVersion: -1, pollTimer: null,
  cards: {}, traits: {}, cardsLoaded: false, pollErrShown: false,
  halfW: 8, halfH: 4, battleW: 8, battleH: 8,
  round: 1, maxRounds: 10,
  timerInterval: null, prepEndsAt: 0, battleEndsAt: 0, serverOffset: 0,
  merged: false,
  battleEpoch: 0,
  battleTimer: null, introTimer: null,
  activeBattleKey: '',
  chatVersion: -1,
  battleData: null, battleFetching: null,
  unitMap: new Map(),
  prepUnitMap: new Map(),
  cellPx: 30, prepCellPx: 30,
  rafId: null, soloBattle: false,
  curPos: null, nextPos: null, cellMap: {},
  lastFrameIdx: -1,
  currentFrames: [],
  currentEvents: [],
  currentD: null,
  playedEventKeys: new Set(),
  starScale: 1.8, maxStar: 3, lastMergeNoticeId: null, mergeInit: false,
};


// 清晰模式 / 低特效模式；尊重系统减少动态效果设置。
function syncFxMode() {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const mode = localStorage.getItem('oi_fx_mode') || (reduced ? 'low' : 'clear');
  document.documentElement.dataset.fx = mode;
  const b = document.getElementById('fxMode');
  if (b) { b.textContent = mode === 'low' ? 'FX−' : 'FX'; b.setAttribute('aria-pressed', String(mode === 'low')); }
}
function toggleFxMode() {
  localStorage.setItem('oi_fx_mode', document.documentElement.dataset.fx === 'low' ? 'clear' : 'low');
  syncFxMode();
}
window.addEventListener('DOMContentLoaded', syncFxMode);
// 50 张卡 = 50 个唯一技能，标签表覆盖全部技能 id。
// 主主动技能的飘字用 skillId 查表，被动机制的说明写在卡面 desc 里。
const SKILL_LABELS = {
  // 主动技能（server.ACTIVE_SKILLS）
  aoe: '范围冲击', multi: '连击', line: '线性扫描', aoe_debuff: '广搜减速',
  range_aoe: '区间打击', block_aoe: '分块打击', delayed_line: '延迟标记',
  swap_stats: '交换攻守', sort_line: '重排站位', compress_line: '同行压缩',
  pincer: '两端夹击', partition: '高攻分区', divide_conquer: '分治追击',
  sweep: '扫描递增', freeze: '冻结', min_cut: '最小割',
  // 被动机制
  stack_ally: '叠层援护', charge_burst: '蓄力爆发', finish_weak: '收割弱者',
  chain_kill: '连锁斩杀', link_ally: '连锁护盾', crowd_crit: '围攻暴击',
  prime_round: '质数回合', every_n: '模节拍', shift_stats: '移位调参',
  seg_query: '线段树查询', shield_on_low: '低血护盾', grow_range: '迭代增距',
  merge_ally: '归并结伴', thorns: '逆元反刺', sliding_max: '滑窗取极',
  heuristic: '启发选点', mod_cycle: '模周期振荡', expectation: '期望收益',
  cdq: 'CDQ 分治', spfa_stall: 'SPFA 停滞', o2_aura: 'O2 加速光环',
  genetic: '遗传突变', matrix_pow: '矩阵幂', pierce: '穿透',
  prefix_growth: '前缀累涨', lifesteal: '汲取', kmp_next: 'KMP 跃迁',
  mst_link: '最小生成树链', splash: '溅射', multi_match: '多模式匹配',
  scc_mark: '强连通标记', rampage: '背水', lcp_chain: '最长公共前缀',
  splay_rotate: '伸展旋转', fft_butterfly: '蝶形变换', sam_compress: '自动机压缩',
};
function effectKind(skill) {
  if (['aoe_debuff','swap_stats','sort_line','freeze'].includes(skill)) return 'control';
  if (skill === 'delayed_line') return 'delay';
  if (['compress_line','sweep','divide_conquer','min_cut'].includes(skill)) return 'burst';
  if (skill === 'thorns') return 'reflect';
  return 'normal';
}

function toggleTheme() {
  const cur = document.documentElement.dataset.theme || 'light';
  const next = cur === 'light' ? 'dark' : 'light';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('theme', next);
}
(function initTheme() {
  document.documentElement.dataset.theme = localStorage.getItem('theme') || 'light';
})();

function showScreen(id) {
  const cur = document.querySelector('.screen.active');
  if (cur && cur.id === id) return;          // 已经是这个界面就不重放动画
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}
let toastTimer;
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 1800);
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);
}
async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    if (location.protocol === 'file:') throw new Error('请用 http://127.0.0.1:8080 打开');
    throw new Error('无法连接服务器');
  }
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); }
  catch { throw new Error(`服务器返回异常: ${text.slice(0, 80)}`); }
  if (!res.ok) throw new Error(data.error || `请求失败 ${res.status}`);
  return data;
}

function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }
function openHelp() { openModal('helpModal'); }
async function loadCards() {
  if (state.cardsLoaded) return;
  try {
    const d = await api('/api/cards');
    // 服务端下发的是数组，前端按 id 建索引
    const map = {};
    (d.cards || []).forEach(c => { map[c.id] = c; });
    state.cards = map;
    state.traits = d.traits || {};
    state.starScale = d.starScale || 1.8;
    state.maxStar = d.maxStar || 3;
    state.cardsLoaded = true;
  } catch (e) {}
}
async function openCodex() {
  openModal('codexModal');
  const el = document.getElementById('codexList');
  if (el.dataset.loaded === '1') return;
  try {
    await loadCards();
    if (!state.cardsLoaded) throw new Error('卡牌数据加载失败');
    renderCodex(Object.values(state.cards), state.traits);
    el.dataset.loaded = '1';
  } catch (e) {
    el.innerHTML = `<div>加载失败: ${escapeHtml(e.message)}</div>`;
  }
}
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal')) e.target.classList.remove('active');
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape')
    document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active'));
});

function renderCodex(cards, traits) {
  const el = document.getElementById('codexList');
  const byCost = {};
  cards.forEach(c => { (byCost[c.cost] = byCost[c.cost] || []).push(c); });
  const skillCount = new Set(cards.map(c => c.skill)).size;
  let html = `<div class="codex-note">共 ${cards.length} 张卡 · ${skillCount} 种技能 ·
    羁绊：同流派 <b>2 / 4 / 6</b> 张自动激活 —— 攻击 +6% → 生命 +8% → 承伤 -6%</div>`;
  [1, 2, 3, 4, 5].forEach(cost => {
    const list = byCost[cost] || [];
    if (!list.length) return;
    html += `<div class="codex-section">${cost} 费 · ${list.length} 张</div>`;
    list.forEach(c => {
      html += `
        <div class="codex-card">
          <div class="cc-head"><span>${escapeHtml(c.name)}</span><span>${c.cost} 金</span></div>
          <div class="cc-meta">${escapeHtml(c.difficulty)} · ${escapeHtml(traits[c.trait] || c.trait)} · ${c.active ? `主动 · 每次 ${c.skillCost} 精力` : '被动 · 不耗精力'}</div>
          <div class="cc-skill"><span class="cc-skill-name">${escapeHtml(SKILL_LABELS[c.skill] || c.skill)}</span><span class="cc-skill-id">${escapeHtml(c.skill)}</span></div>
          <div class="cc-stats">攻击 ${c.attack} · 生命 ${c.maxHp || c.hp} · 射程 ${c.range} · 购买 精力 ${c.energy} / 理智 ${c.reason}</div>
          <div class="cc-role">${escapeHtml(c.role || '')} · ${escapeHtml(c.position || '')}</div><div class="cc-flavor">${escapeHtml(c.flavor || '')}</div>
          <div class="cc-desc">${escapeHtml(c.desc)}</div><div class="cc-tip">${escapeHtml(c.tip || '')}</div>
        </div>`;
    });
  });
  el.innerHTML = html;
}

async function loadProfile() {
  try {
    const d = await api(`/api/profile?clientId=${encodeURIComponent(state.clientId)}`);
    state.rating = d.rating;
    const el = document.getElementById('menuRating');
    if (el) el.textContent = d.rating;
  } catch (e) {}
}

// ============================================================
// 特效
// ============================================================
const FX = (() => {
  function layer() { return document.getElementById('fxLayer'); }
  function cs() { return state.cellPx || 30; }
  const damageLabels = new Map();
  // 棋盘格坐标 → 像素坐标（solo 模式下只有己方半场，y 需要上移）
  function pt(bx, by) {
    const self = state.soloBattle || by >= state.halfH;
    const half = document.getElementById(self ? 'selfHalf' : 'oppHalf');
    if (half && half.clientWidth && half.clientHeight) {
      const y = self ? by - state.halfH : by;
      const grid = half.querySelector('.grid-layer');
      const target = grid && grid.children[Math.floor(y) * state.halfW + Math.floor(bx)];
      const fx = layer();
      if (target && fx) {
        const r = target.getBoundingClientRect(), f = fx.getBoundingClientRect(), fs = getComputedStyle(fx);
        const sx = f.width / Math.max(.001, parseFloat(fs.width));
        const sy = f.height / Math.max(.001, parseFloat(fs.height));
        return {x:(r.x+r.width/2-f.x)/sx, y:(r.y+r.height/2-f.y)/sy};
      }
    }
    const c = cs();
    return {x:(bx+.5)*c, y:((state.soloBattle ? by-state.halfH : by)+.5)*c};
  }
  function spawn(cls, x, y, life) {
    const l = layer();
    if (!l) return null;
    const budget = document.documentElement.dataset.fx === 'low' ? 40 : 128;
    while (l.childElementCount >= budget) l.firstElementChild.remove();
    const el = document.createElement('div');
    el.className = cls;
    el.style.left = x + 'px';
    el.style.top = y + 'px';
    l.appendChild(el);
    if (life) setTimeout(() => el.remove(), life);
    return el;
  }
  function floatNum(cls, text, x, y, life, size) {
    const el = spawn('float-text ' + cls, x, y, life);
    if (!el) return null;
    el.textContent = text;
    if (size) el.style.fontSize = size + 'px';
    return el;
  }
  function jitter(px, py, r) {
    return { x: px + (Math.random() * 2 - 1) * (r || 7), y: py + (Math.random() * 2 - 1) * (r || 7) };
  }
  // 特效尺寸跟随格子大小，避免大屏上小得看不见、小屏上糊成一片
  function sz(mult, lo, hi) {
    return Math.max(lo, Math.min(hi, cs() * mult));
  }
  return {
    pt,
    // 伤害数字：数值越大字号越大，避免小伤害淹没屏幕
    damage(bx, by, v) {
      if (!v) return;
      const key = `${bx},${by}`, now = performance.now();
      const old = damageLabels.get(key);
      if (old && old.el.isConnected && now - old.time < 100) {
        old.value += Math.round(v); old.el.textContent = '−' + old.value; return;
      }
      const q = pt(bx, by);
      const base = sz(0.24, 11, 21);
      const el = floatNum('damage' + (v >= 60 ? ' big' : ''), '−' + Math.round(v), q.x + cs()*.17, q.y - cs()*.22, 720, Math.round(base));
      if (el) damageLabels.set(key, {el, value:Math.round(v), time:now});
      if (damageLabels.size > 100) damageLabels.clear();
    },
    heal(bx, by, v) {
      const p = pt(bx, by);
      p.y -= cs() * 0.26;
      floatNum('heal', '+' + Math.round(v), p.x, p.y, 1000, Math.round(sz(0.28, 12, 24)));
    },
    shield(bx, by, v) {
      const p = pt(bx, by);
      floatNum('shield', '盾 +' + Math.round(v), p.x, p.y - 4, 900, Math.round(sz(0.2, 10, 17)));
      spawn('impact shield-ring', p.x, p.y, 460);
    },
    skill(bx, by, name) {
      const p = pt(bx, by);
      floatNum('skill', name, p.x, p.y - cs() * 0.34, 1200, Math.round(sz(0.21, 10, 18)));
    },
    // 施法：脚下光环扩散
    cast(bx, by, colorIdx) {
      const p = pt(bx, by);
      const el = spawn('cast-ring', p.x, p.y, 520);
      if (!el) return;
      const s = sz(0.55, 18, 56);
      el.style.width = el.style.height = s + 'px';
      el.style.setProperty('--fx-color', `var(--p${colorIdx})`);
    },
    // 命中：爆点
    impact(bx, by, colorIdx, big) {
      const p = pt(bx, by);
      const el = spawn('impact' + (big ? ' big' : ''), p.x, p.y, 440);
      if (!el) return;
      const s = sz(big ? 0.5 : 0.36, 12, 44);
      el.style.width = el.style.height = s + 'px';
      el.style.setProperty('--fx-color', `var(--p${colorIdx})`);
    },
    // 阵亡：碎片环
    death(bx, by, colorIdx) {
      const p = pt(bx, by);
      const el = spawn('death-burst', p.x, p.y, 520);
      if (!el) return;
      const s = sz(0.45, 14, 46);
      el.style.width = el.style.height = s + 'px';
      el.style.setProperty('--fx-color', `var(--p${colorIdx})`);
    },
    zone(e) {
      const seen = new Set();
      const limit = document.documentElement.dataset.fx === 'low' ? 4 : 16;
      for (const cell of (e.targets || [])) {
        const key = `${cell.x},${cell.y}`;
        if (seen.has(key) || seen.size >= limit) continue;
        seen.add(key);
        const p = pt(cell.x, cell.y), el = spawn('fx-cell ' + effectKind(e.name), p.x, p.y, 410);
        if (el) { el.style.width = el.style.height = cs()*.88+'px'; }
      }
    },
    projectile(fromX, fromY, toX, toY, colorIdx, onArrive, kind = 'normal') {
      const a = pt(fromX, fromY), b = pt(toX, toY);
      const dx = b.x - a.x, dy = b.y - a.y, dist = Math.hypot(dx,dy);
      // 命中与权威扣血同步；用短时残影表示路径，不再延后数百毫秒命中。
      const el = spawn('fx-trace ' + kind, a.x, a.y, 220);
      if (el) {
        el.style.width = Math.max(1,dist)+'px';
        el.style.transform = `rotate(${Math.atan2(dy,dx)}rad)`;
        el.style.setProperty('--fx-color', `var(--p${colorIdx})`);
      }
      if (onArrive) onArrive();
    },
  };
})();

// ============================================================
// 棋盘构建
// ============================================================
let prepBuilt = false;
function buildPrepBoard() {
  if (prepBuilt) return;
  const grid = document.getElementById('gridLayerPrep');
  const cells = document.getElementById('cellLayerPrep');
  for (const id of ['gridLayerPrep','cellLayerPrep','unitLayerPrep']) {
    const layer = document.getElementById(id);
    layer.style.gridTemplateColumns = `repeat(${state.halfW}, minmax(0, 1fr))`;
    layer.style.gridTemplateRows = `repeat(${state.halfH}, minmax(0, 1fr))`;
  }
  grid.style.gridTemplateColumns = `repeat(${state.halfW}, 1fr)`;
  grid.style.gridTemplateRows = `repeat(${state.halfH}, 1fr)`;
  for (let y = 0; y < state.halfH; y++) {
    for (let x = 0; x < state.halfW; x++) {
      const g = document.createElement('div');
      g.className = 'grid-cell';
      if (x === state.halfW - 1) g.classList.add('no-right');
      if (y === state.halfH - 1) g.classList.add('no-bottom');
      grid.appendChild(g);
    }
  }
  for (let y = 0; y < state.halfH; y++) {
    for (let x = 0; x < state.halfW; x++) {
      const c = document.createElement('div');
      c.className = 'cell';
      c.style.gridColumn = String(x + 1);
      c.style.gridRow = String(y + 1);
      c.dataset.x = x;
      c.dataset.y = y;
      c.addEventListener('click', () => onPrepCellClick(x, y));
      cells.appendChild(c);
    }
  }
  prepBuilt = true;
}

let halvesBuilt = false;
function buildBattleHalves() {
  if (halvesBuilt) return;
  for (const id of ['gridLayerOpp', 'gridLayerSelf']) {
    const grid = document.getElementById(id);
    grid.style.gridTemplateColumns = `repeat(${state.halfW}, 1fr)`;
    grid.style.gridTemplateRows = `repeat(${state.halfH}, 1fr)`;
    for (let y = 0; y < state.halfH; y++) {
      for (let x = 0; x < state.halfW; x++) {
        const g = document.createElement('div');
        g.className = 'grid-cell';
        if (x === state.halfW - 1) g.classList.add('no-right');
        if (y === state.halfH - 1) g.classList.add('no-bottom');
        grid.appendChild(g);
      }
    }
  }
  halvesBuilt = true;
}

function fitBoard() {
  const wrap = document.getElementById('boardWrap');
  if (!wrap) return;
  const rect = wrap.getBoundingClientRect();

  const prep = document.getElementById('prepBoard');
  if (prep && !prep.classList.contains('hidden')) {
    // clientWidth/Height 为未受浏览器缩放影响的 CSS 像素；扣除容器内边距和棋盘边框。
    const ws = getComputedStyle(wrap), ps = getComputedStyle(prep);
    const availableW = wrap.clientWidth - parseFloat(ws.paddingLeft) - parseFloat(ws.paddingRight);
    const availableH = wrap.clientHeight - parseFloat(ws.paddingTop) - parseFloat(ws.paddingBottom);
    const borderX = parseFloat(ps.borderLeftWidth) + parseFloat(ps.borderRightWidth);
    const borderY = parseFloat(ps.borderTopWidth) + parseFloat(ps.borderBottomWidth);
    const cell = Math.max(1, Math.min((availableW - borderX) / state.halfW, (availableH - borderY) / state.halfH));
    prep.style.width = (cell * state.halfW + borderX) + 'px';
    prep.style.height = (cell * state.halfH + borderY) + 'px';
    prep.style.setProperty('--cell-size', cell + 'px');
    state.prepCellPx = cell;
  }

  const battle = document.getElementById('battleBoard');
  if (battle && !battle.classList.contains('hidden')) {
    const ws = getComputedStyle(wrap);
    const availableW = wrap.clientWidth - parseFloat(ws.paddingLeft) - parseFloat(ws.paddingRight);
    const availableH = wrap.clientHeight - parseFloat(ws.paddingTop) - parseFloat(ws.paddingBottom);
    const solo = battle.classList.contains('solo');
    const halfCount = solo ? 1 : 2;
    const sample = document.getElementById('selfHalf'), hs = getComputedStyle(sample);
    const borderX = parseFloat(hs.borderLeftWidth) + parseFloat(hs.borderRightWidth);
    const borderY = parseFloat(hs.borderTopWidth) + parseFloat(hs.borderBottomWidth);
    // Count any real row gap: board-wrap has overflow:hidden, so a gap that is
    // not subtracted here clips both halves (worst on half-height windows).
    const rowGap = solo ? 0 : (parseFloat(getComputedStyle(battle).rowGap) || 0);
    const cell = Math.max(1, Math.min((availableW - borderX) / state.halfW,
      (availableH - rowGap - halfCount * borderY) / (halfCount * state.halfH)));
    state.cellPx = cell;
    for (const half of battle.querySelectorAll('.half-board')) {
      half.style.width = (cell * state.halfW + borderX) + 'px';
      half.style.height = (cell * state.halfH + borderY) + 'px';
      half.style.setProperty('--cell-size', cell + 'px');
    }
    // 尺寸变化后立即重排一次，避免等下一帧才归位
    for (const [uid, el] of state.unitMap) {
      const u = state.curPos && state.curPos.get(uid);
      if (u) setBattleUnitPos(el, u.x, u.y);
    }
  }
}
let resizeTimer;
function scheduleFit() {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(fitBoard, 30);
}
window.addEventListener('resize', scheduleFit);
window.addEventListener('orientationchange', scheduleFit);

// ============================================================
// 主菜单 / 房间
// ============================================================
async function createRoom() {
  const name = (document.getElementById('nickname').value || '选手').trim().slice(0, 12);
  try {
    const d = await api('/api/rooms', 'POST', { clientId: state.clientId, name });
    state.playerId = d.playerId;
    state.roomId = d.roomId;
    state.lastMergeNoticeId = null;
    state.mergeInit = false;
    state.nickname = name;
    saveIdentity();
    if (d.rejoined) toast('已回到原房间');
    showScreen('lobby');
    startPolling();
  } catch (e) { toast(e.message); }
}
async function showRoomList() {
  try {
    const d = await api('/api/rooms');
    const el = document.getElementById('roomList');
    // 只列出还能加入的房间（已开局/已结束的房间加入会直接报“游戏已开始”）
    const open = d.rooms.filter(r => r.state === 'waiting' && r.players < (r.max || 8));
    if (!open.length) {
      el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--muted);font-size:12px">暂无可加入的房间</div>';
    } else {
      el.innerHTML = open.map(r => `
        <div class="room-item" onclick="joinRoom('${r.id}')">
          <div><div>${escapeHtml(r.host)}</div><div class="room-id">${r.id}</div></div>
          <div>${r.players}/${r.max || 8}</div>
        </div>`).join('');
    }
    el.classList.toggle('hidden');
  } catch (e) { toast(e.message); }
}
async function joinRoom(roomId) {
  const name = (document.getElementById('nickname').value || '选手').trim().slice(0, 12);
  try {
    const d = await api('/api/join', 'POST', { clientId: state.clientId, roomId, name });
    state.playerId = d.playerId;
    state.roomId = d.roomId;
    state.lastMergeNoticeId = null;
    state.mergeInit = false;
    state.nickname = name;
    saveIdentity();
    if (d.rejoined) toast('已回到原房间');
    showScreen('lobby');
    startPolling();
  } catch (e) { toast(e.message); }
}
async function rejoin() {
  try {
    const d = await api('/api/rejoin', 'POST', { clientId: state.clientId });
    state.playerId = d.playerId;
    state.roomId = d.roomId;
    state.lastMergeNoticeId = null;
    state.mergeInit = false;
    showScreen('lobby');
    startPolling();
  } catch (e) {
    toast('原房间已不存在');
    clearIdentity();
  }
}
function saveIdentity() {
  localStorage.setItem('oi_room_id', state.roomId);
  localStorage.setItem('oi_nickname', state.nickname);
}
function clearIdentity() {
  localStorage.removeItem('oi_room_id');
  localStorage.removeItem('oi_nickname');
}
function loadIdentity() {
  state.roomId = localStorage.getItem('oi_room_id');
  state.nickname = localStorage.getItem('oi_nickname') || '选手';
  const el = document.getElementById('nickname');
  if (el) el.value = state.nickname;
}

async function doAction(action, data = {}) {
  try {
    await api('/api/action', 'POST', { playerId: state.playerId, action, ...data });
    return true;
  } catch (e) {
    toast(e.message);
    if (e.message.includes('不在房间')) resetToMenu();
    return false;
  }
}
async function startGame() { await doAction('start'); }
async function buyCard(i) { await doAction('buy', { index: i }); }
async function refreshShop() { await doAction('refresh'); }
async function toggleReady() { await doAction('ready'); }
async function placeCard(x, y) {
  if (state.selectedBench === null) return;
  const ok = await doAction('place', { benchIndex: state.selectedBench, x, y });
  if (ok) state.selectedBench = null;   // 放失败（格子被占等）时保留选中状态
  if (currentState) renderBench(getMe());
}
async function retrieveCard(x, y) { await doAction('retrieve', { x, y }); }
function selectBench(i) {
  state.selectedBench = (state.selectedBench === i) ? null : i;
  if (currentState) renderBench(getMe());
}
function onPrepCellClick(x, y) {
  const me = getMe();
  if (!me) return;
  if (state.selectedBench !== null) { placeCard(x, y); return; }
  if (me.board[`${x},${y}`]) { retrieveCard(x, y); }
}

function confirmExit() {
  const inGame = currentState && (currentState.state === 'prep' || currentState.state === 'battle');
  const me = currentState && currentState.players[currentState.viewerId];
  if (me && me.dead) {
    // 已出局，直接离开
    doExit();
    return;
  }
  const msg = inGame ? '确定退出对局吗？\n将扣除 30 Rating，且本局无法恢复。' : '确定离开吗？';
  if (!confirm(msg)) return;
  doExit();
}
async function doExit() {
  try {
    await api('/api/action', 'POST', { playerId: state.playerId, action: 'leave' });
  } catch (e) {}
  resetToMenu();
}
function resetToMenu() {
  clearIdentity();
  stopPolling();
  stopBattlePlayback();
  clearTimeout(state.introTimer);
  state.introTimer = null;
  state.playerId = null;
  state.roomId = null;
  state.lastVersion = -1;
  state.selectedBench = null;
  state.merged = false;
  state.lastMergeNoticeId = null;
  state.mergeInit = false;
  state.playedEventKeys.clear();
  state.activeBattleKey = '';
  state.chatVersion = -1;
  state.battleData = null;
  state.battleFetching = null;
  state.unitMap.clear();
  state.prepUnitMap.clear();
  state.curPos = state.nextPos = null;
  state.soloBattle = false;
  state.currentFrames = [];
  state.currentEvents = [];
  state.lastFrameIdx = -1;
  state.currentD = null;
  stopTimer();
  ['fxLayer', 'unitLayerPrep', 'unitLayerOpp', 'unitLayerSelf',
   'lobbyChatMessages', 'gameChatMessages'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '';
  });
  const byeBadge = document.getElementById('byeBadge');
  if (byeBadge) byeBadge.classList.add('hidden');
  hideEndBanner();
  showScreen('menu');
  loadProfile();
  checkRejoinButton();
}
async function leaveRoom() {
  if (!confirm('确定离开房间吗？')) return;
  doExit();
}

function startPolling() {
  stopPolling();
  state.pollErrShown = false;
  state.pollTimer = setInterval(poll, 300);
  poll();
}
function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}
async function poll() {
  if (!state.playerId) return;
  try {
    const d = await api(`/api/state?playerId=${encodeURIComponent(state.playerId)}`
      + `&haveChat=${state.chatVersion}&since=${state.lastVersion}`);
    state.pollErrShown = false;
    if (d.chat) {
      state.chatVersion = d.chatVersion;
      renderChat(d.chat, d.viewerId);
    }
    // Nothing changed server-side: refresh the countdown but skip the full
    // render / battle fetch. The thin response carries no players snapshot.
    if (d.minimal) {
      updateTimerFromState(d);
      return;
    }
    // 战斗帧拉取成功后需要强制重渲染，否则战斗画面会一直空白
    const gotBattle = await ensureBattleData(d);
    if (d.version !== state.lastVersion || gotBattle) {
      state.lastVersion = d.version;
      render(d);
    } else {
      updateTimerFromState(d);
    }
  } catch (e) {
    if (!state.pollErrShown) {
      state.pollErrShown = true;
      if (e.message.includes('not in room') || e.message.includes('不在')) {
        toast('房间已结束');
        resetToMenu();
      } else {
        toast(e.message);
      }
    }
  }
}

// 战斗帧序列体积大，只在开战时单独拉一次，避免每 300ms 重复传输
// 返回值：是否拿到了新的战斗数据（用于强制触发 render）
async function ensureBattleData(d) {
  if (!d || d.state !== 'battle' || !d.battleKey) return false;
  if (state.battleData && state.battleData.battleKey === d.battleKey) return false;
  if (state.battleFetching === d.battleKey) return false;
  state.battleFetching = d.battleKey;
  try {
    const b = await api(`/api/battle?playerId=${encodeURIComponent(state.playerId)}`);
    if (b && b.battleKey === d.battleKey) {
      state.battleData = b;
      return true;
    }
  } catch (e) {
    // 下一轮 poll 会重试
  } finally {
    state.battleFetching = null;
  }
  return false;
}

// 聊天增量渲染：用最后一条消息的 id 作为锚点，避免每次全量重建 DOM
function renderChat(chat, viewerId) {
  ['lobbyChatMessages', 'gameChatMessages'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const lastId = el.dataset.lastId || '';
    let startIdx = chat.findIndex(m => m.id === lastId);
    if (startIdx < 0) {
      // 锚点已不在（首次渲染 / 聊天被裁剪）→ 全量重建
      el.innerHTML = '';
      startIdx = 0;
    } else {
      startIdx += 1;
    }
    for (let i = startIdx; i < chat.length; i++) {
      const m = chat[i];
      const div = document.createElement('div');
      div.className = 'chat-msg';
      if (m.system) {
        div.classList.add('system');
        div.textContent = m.text;
      } else {
        if (m.senderId === viewerId) div.classList.add('self');
        div.innerHTML = `<span class="chat-name">${escapeHtml(m.sender)}</span>${escapeHtml(m.text)}`;
      }
      el.appendChild(div);
    }
    if (chat.length) el.dataset.lastId = chat[chat.length - 1].id;
    el.scrollTop = el.scrollHeight;
  });
}
async function sendChat(where) {
  const inputId = where === 'lobby' ? 'lobbyChatInput' : 'gameChatInput';
  const el = document.getElementById(inputId);
  if (!el) return;
  const text = el.value.trim();
  if (!text) return;
  el.value = '';
  try {
    await api('/api/chat', 'POST', { playerId: state.playerId, text });
  } catch (e) {
    toast(e.message);
  }
}

// ============================================================
// 倒计时
// ============================================================
function updateTimerFromState(d) {
  if (d.serverNow) state.serverOffset = d.serverNow * 1000 - Date.now();
  if (d.state === 'prep' && d.prepEndsAt) {
    state.prepEndsAt = d.prepEndsAt * 1000;
    state.battleEndsAt = 0;
    ensureTimer();
  } else if (d.state === 'battle' && d.battleEndsAt) {
    state.battleEndsAt = d.battleEndsAt * 1000;
    if (d.battleStartedAt) state.battleStartedAt = d.battleStartedAt * 1000;
    ensureTimer();
  } else {
    stopTimer();
    const el = document.getElementById('timerVal');
    if (el) el.textContent = '—';
  }
}
function ensureTimer() {
  if (state.timerInterval) return;
  state.timerInterval = setInterval(tickTimer, 200);
  tickTimer();
}
function stopTimer() {
  if (state.timerInterval) {
    clearInterval(state.timerInterval);
    state.timerInterval = null;
  }
}
function tickTimer() {
  const el = document.getElementById('timerVal');
  if (!el) return;
  const now = Date.now() + state.serverOffset;
  let target = 0;
  if (state.prepEndsAt > 0 && now < state.prepEndsAt) target = state.prepEndsAt;
  else if (state.battleEndsAt > 0 && now < state.battleEndsAt) target = state.battleEndsAt;
  if (target === 0) { el.textContent = '—'; return; }
  el.textContent = Math.max(0, Math.ceil((target - now) / 1000));
}

// ============================================================
// 渲染主入口
// ============================================================
let currentState = null;
function getMe() {
  if (!currentState) return null;
  return currentState.players[currentState.viewerId];
}

function render(d) {
  currentState = d;
  state.currentD = d;
  if (!state.cardsLoaded) loadCards();
  state.halfW = d.halfW || 8;
  state.halfH = d.halfH || 4;
  state.battleW = d.battleW || 8;
  state.battleH = d.battleH || 8;
  state.round = d.round || 1;
  state.maxRounds = d.maxRounds || 10;

  if (d.state === 'waiting') {
    hideEndBanner();
    showScreen('lobby');
    renderLobby(d);
    stopTimer();
    stopBattlePlayback();
    return;
  }

  showScreen('game');
  updateTimerFromState(d);

  const me = d.players[d.viewerId];
  if (!state.mergeInit) {
    state.mergeInit = true;
    state.lastMergeNoticeId = me && me.mergeNotice ? me.mergeNotice.id : null;
  } else if (me && me.mergeNotice && me.mergeNotice.id !== state.lastMergeNoticeId) {
    state.lastMergeNoticeId = me.mergeNotice.id;
    const merged = state.cards[me.mergeNotice.card];
    const name = merged ? merged.name : me.mergeNotice.card;
    toast(`${name} ${'★'.repeat(me.mergeNotice.star)} 合成`);
    state.selectedBench = null;
  }
  renderGame(d);
  if ((me && me.dead) || d.state === 'ended') {
    showEndBanner(d);
  } else {
    hideEndBanner();
  }
}

function colorDot(c) {
  return `<span class="color-dot" style="background:var(--p${c})"></span>`;
}
function renderLobby(d) {
  document.getElementById('roomIdLabel').textContent = d.roomId;
  const list = document.getElementById('playerList');
  const arr = Object.values(d.players);
  list.innerHTML = arr.map(p => `
    <div class="player-item">
      <span>${colorDot(p.color)}${escapeHtml(p.name)}</span>
      ${p.id === d.host ? '<span class="host-tag">房主</span>' : ''}
    </div>`).join('');
  const btn = document.getElementById('startBtn');
  if (d.viewerId === d.host) {
    btn.style.display = 'block';
    const n = arr.filter(p => !p.dead).length;
    if (n < 2) {
      btn.disabled = true;
      btn.textContent = '至少 2 人';
    } else {
      btn.disabled = false;
      btn.textContent = '开始游戏';
    }
  } else {
    btn.style.display = 'none';
  }
}

// 羁绊：按流派统计场上棋子，达到 2/4/6 档自动激活对应增益。
// 服务端 bond_status 已算好档位与生效效果，前端只负责展示。
function renderBonds(bonds) {
  const el = document.getElementById('bondList');
  if (!el) return;
  if (!bonds || !bonds.length) {
    el.classList.add('hidden');
    el.innerHTML = '';
    return;
  }
  el.classList.remove('hidden');
  const rows = bonds.map(b => {
    const active = b.tier > 0;
    const next = b.next
      ? `<span class="bond-next">还差 ${b.next - b.count}</span>`
      : '<span class="bond-next bond-max">已满</span>';
    const eff = b.effects && b.effects.length
      ? `<div class="bond-eff">${b.effects.map(escapeHtml).join(' · ')}</div>`
      : '<div class="bond-eff bond-none">未激活</div>';
    const dots = Array.from({ length: 3 }, (_, i) =>
      `<span class="bond-dot${i < b.tier ? ' on' : ''}"></span>`).join('');
    return `<div class="bond${active ? ' on' : ''}">
      <span class="bond-name">${escapeHtml(b.name)}</span>
      <span class="bond-count">${b.count}</span>${next}
      <span class="bond-dots">${dots}</span>${eff}
    </div>`;
  }).join('');
  el.innerHTML = `<div class="bonds-title">羁绊</div>${rows}`;
}

function renderGame(d) {
  const me = d.players[d.viewerId];
  if (!me) return;

  document.getElementById('mindVal').textContent = me.mind;
  document.getElementById('mindBar').style.width = Math.min(100, me.mind) + '%';
  document.getElementById('reasonVal').textContent = me.reason;
  document.getElementById('reasonBar').style.width = me.reason + '%';
  document.getElementById('energyVal').textContent = me.energy;
  document.getElementById('energyBar').style.width = me.energy + '%';
  document.getElementById('roundVal').textContent = `${d.round}/${d.maxRounds}`;
  document.getElementById('goldVal').textContent = me.gold;
  document.getElementById('hpVal').textContent = me.hp;
  const isPrep = d.state === 'prep';
  const refreshBtn = document.getElementById('refreshBtn');
  if (refreshBtn) {
    const refreshCost = me.shopRefreshCost || 0;
    refreshBtn.textContent = refreshCost > 0 ? `刷新 ${refreshCost} 金` : '刷新 免费';
    refreshBtn.disabled = me.dead || !isPrep || me.gold < refreshCost;
  }
  const phaseMap = { prep: '准备', battle: '战斗', ended: '结束' };
  let phase = me.dead ? '出局' : (phaseMap[d.state] || d.state);
  if (!me.dead && me.crashed) phase += '·崩溃';
  document.getElementById('phaseVal').textContent = phase;
  renderOpponents(d, me);
  renderBonds(d.bonds);

  const byeBadge = document.getElementById('byeBadge');

  // 出局玩家不再渲染棋盘
  if (me.dead) {
    stopBattlePlayback();
    document.getElementById('prepBoard').classList.add('hidden');
    document.getElementById('battleBoard').classList.add('hidden');
    document.getElementById('battleBanner').classList.add('hidden');
    if (byeBadge) byeBadge.classList.add('hidden');
    const fxLayer = document.getElementById('fxLayer');
    if (fxLayer) fxLayer.innerHTML = '';
    const rb0 = document.getElementById('readyBtn');
    rb0.disabled = true;
    rb0.textContent = '已出局';
    rb0.classList.remove('ready');
    renderShop(me, false);
    renderBench(me);
    return;
  }

  if (d.state === 'prep') {
    stopBattlePlayback();
    document.getElementById('prepBoard').classList.remove('hidden');
    document.getElementById('battleBoard').classList.add('hidden');
    document.getElementById('battleBanner').classList.add('hidden');
    if (byeBadge) byeBadge.classList.add('hidden');
    buildPrepBoard();
    fitBoard();                              // 先量尺寸，回合切换时首帧即正确
    requestAnimationFrame(() => requestAnimationFrame(fitBoard));
    renderPrepUnits(me);

    state.merged = false;
    state.soloBattle = false;
    state.activeBattleKey = '';
    state.playedEventKeys.clear();
    state.unitMap.clear();
    state.curPos = state.nextPos = null;
    state.cellMap = {};
    state.currentFrames = [];
    state.currentEvents = [];
    state.lastFrameIdx = -1;
    const fxLayer = document.getElementById('fxLayer');
    if (fxLayer) fxLayer.innerHTML = '';
    const bb = document.getElementById('battleBoard');
    if (bb) { bb.classList.remove('merged'); bb.classList.remove('solo'); }
  } else if (d.state === 'battle') {
    document.getElementById('prepBoard').classList.add('hidden');
    document.getElementById('battleBoard').classList.remove('hidden');
    buildBattleHalves();
    fitBoard();                              // 先量尺寸，首帧坐标才准确
    requestAnimationFrame(() => requestAnimationFrame(fitBoard));

    // 战斗棋盘从一开始就处于合并状态，保证弹道坐标与视觉一致
    const bb = document.getElementById('battleBoard');
    bb.classList.add('merged');

    const b = (state.battleData && state.battleData.battleKey === d.battleKey)
      ? state.battleData : null;
    if (b && state.activeBattleKey !== d.battleKey) {
      stopBattlePlayback();
      state.activeBattleKey = d.battleKey;
      state.playedEventKeys.clear();
      state.unitMap.clear();
      state.lastFrameIdx = -1;
      state.currentFrames = b.frames || [];
      state.currentEvents = b.events || [];
      state.battleEpoch = b.battleStartedAt
        ? b.battleStartedAt * 1000
        : (Date.now() + state.serverOffset);

      const isBye = !!b.viewerBye || !b.opponentId;
      state.soloBattle = isBye;
      if (isBye) {
        bb.classList.add('solo');
        state.merged = true;
        if (byeBadge) byeBadge.classList.remove('hidden');
        document.getElementById('battleBanner').classList.add('hidden');
      } else {
        bb.classList.remove('solo');
        if (byeBadge) byeBadge.classList.add('hidden');
      }

      initBattleUnits(d, me, b);
      // 一开战就按服务端时间轴回放，不再延迟 4 秒（否则会丢掉开场帧）
      startBattlePlayback();
      if (!isBye) triggerBattleIntro(d, me);
    }
  }

  const rb = document.getElementById('readyBtn');
  rb.disabled = !isPrep;
  rb.textContent = me.ready ? '已准备' : '准备';
  rb.classList.toggle('ready', me.ready);
  renderShop(me, isPrep);
  renderBench(me);
}

function renderOpponents(d, me) {
  const el = document.getElementById('opponents');
  if (!el) return;
  el.innerHTML = Object.values(d.players).map(p => {
    const isSelf = p.id === me.id;
    const isOpp = d.opponentId === p.id;
    const dead = p.dead ? 'dead' : '';
    const tags = [];
    if (p.crashed && !p.dead) tags.push('崩溃');
    if (p.level) tags.push('Lv' + p.level);
    const info = p.dead ? '出局' : `AC ${p.hp} · ${p.gold} 金`;
    return `<div class="opp ${isSelf ? 'self' : ''} ${isOpp ? 'opponent' : ''} ${dead}"
      title="${tags.join(' ')}">
      <span>${colorDot(p.color)}${escapeHtml(p.name)}${tags.length ? ` <span class="opp-tag">${tags.join('·')}</span>` : ''}</span>
      <span>${info}</span>
    </div>`;
  }).join('');
}

function renderPrepUnits(me) {
  const layer = document.getElementById('unitLayerPrep');
  if (!layer) return;
  const alive = new Set();
  const occupied = new Set();

  for (const [key, info] of Object.entries(me.board)) {
    const [x, y] = key.split(',').map(Number);
    const card = state.cards[info.card];
    if (!card) continue;
    const star = starOf(info);
    const maxHp = starMaxHp(card, star);
    const hp = Math.min(Math.floor(info.hp ?? maxHp), maxHp);
    if (hp <= 0) continue;
    occupied.add(key);

    let el = state.prepUnitMap.get(key);
    if (!el) {
      el = document.createElement('div');
      el.className = 'unit self spawn';
      el.style.width = '100%';
      el.style.height = '100%';
      layer.appendChild(el);
      state.prepUnitMap.set(key, el);
    }
    alive.add(key);
    el.dataset.star = star;
    el.style.setProperty('--owner-color', `var(--p${me.color})`);
    // 背景、点击层、棋子层共用相同 CSS Grid 行列；可见边框也直接落在格线上。
    el.style.gridColumn = String(x + 1);
    el.style.gridRow = String(y + 1);
    el.style.left = el.style.top = '0';
    el.style.transform = 'none';
    el._tf = null;

    // 只有卡面/血量/星级变化时才重绘内部，避免每次轮询把动画重置掉
    const sig = `${info.card}|${hp}|${maxHp}|${star}`;
    if (el.dataset.sig !== sig) {
      el.dataset.sig = sig;
      const stars = starText(star);
      el.innerHTML = `
        <div class="unit-inner" title="${escapeHtml((stars ? stars + ' ' : '') + card.name)}">
          <div class="unit-stars">${stars}</div>
          <div class="unit-body">
            <div class="unit-name">${escapeHtml(card.name)}</div>
            <div class="unit-stat">${hp}/${maxHp}</div>
            <div class="unit-bar"><i class="hp-fill"></i></div>
          </div>
        </div>`;
      const fill = el.querySelector('.hp-fill');
      if (fill) fill.style.transform = 'scaleX(' + Math.max(0, Math.min(1, hp / maxHp)).toFixed(3) + ')';
      el.classList.toggle('low', hp / Math.max(1, maxHp) <= 0.3);
    }
  }

  for (const [key, el] of Array.from(state.prepUnitMap.entries())) {
    if (alive.has(key)) continue;
    state.prepUnitMap.delete(key);
    el.classList.add('dying');
    setTimeout(() => el.remove(), 420);
  }

  // 选中备战席卡时，空格子提示可放置
  const cells = document.getElementById('cellLayerPrep');
  if (cells) {
    for (const c of cells.children) {
      c.classList.toggle('occupied', occupied.has(`${c.dataset.x},${c.dataset.y}`));
    }
  }
}

// ============================================================
// 战斗：帧驱动
// ============================================================
// 服务端按真实事件时间记录状态；前端在相邻权威帧之间做位置插值
// （transform，不触发重排），血条/状态只在帧边界更新一次。

function halfY(u, isSelf) {
  return isSelf ? u.y - state.halfH : u.y;
}

function setBattleUnitPos(el, x, y) {
  el.style.left = (x * 100 / state.halfW) + '%';
  el.style.top = (y * 100 / state.halfH) + '%';
  el.style.transform = 'none';
  el._tf = null;
}

function setUnitPos(el, px, py) {
  const t = 'translate3d(' + px.toFixed(2) + 'px,' + py.toFixed(2) + 'px,0)';
  if (el._tf !== t) { el._tf = t; el.style.transform = t; }
}

function initBattleUnits(d, me, b) {
  const oppLayer = document.getElementById('unitLayerOpp');
  const selfLayer = document.getElementById('unitLayerSelf');
  oppLayer.innerHTML = '';
  selfLayer.innerHTML = '';
  state.unitMap.clear();

  const frames = (b && b.frames) || [];
  if (!frames.length) return;
  const first = frames[0];

  for (const u of first.units) {
    const isSelf = u.owner === me.id;
    const el = createUnitEl(u, d, isSelf);
    if (!el) continue;
    (isSelf ? selfLayer : oppLayer).appendChild(el);
    state.unitMap.set(u.uid, el);
    const delay = state.unitMap.size * 24;
    el.classList.add('spawn');           // 开场：错峰落下
    el.style.setProperty('--delay', delay + 'ms');
    setTimeout(() => el.classList.remove('spawn'), 340 + delay);
  }
  state.lastFrameIdx = 0;
  state.curPos = new Map();
  state.nextPos = new Map();
}

function starOf(u) {
  return Math.max(1, Math.min(state.maxStar || 3, (u && u.star) || 1));
}
function starMaxHp(card, star) {
  const base = card.maxHp || card.hp;
  return Math.floor(base * Math.pow(state.starScale || 1.8, star - 1));
}
function starText(star) {
  return star > 1 ? '★'.repeat(star) : '';
}
function copyCount(me, cid, star) {
  let n = 0;
  for (const info of Object.values((me && me.board) || {})) {
    if (info.card === cid && starOf(info) === star) n++;
  }
  for (const info of ((me && me.bench) || [])) {
    if (info.card === cid && starOf(info) === star) n++;
  }
  return n;
}

function unitStatText(u) {
  const shield = u.shield || 0;
  return `${u.hp}/${u.maxHp}` + (shield > 0 ? ` +${shield}` : '');
}

function createUnitEl(u, d, isSelf) {
  const me = getMe();
  if (!me) return null;
  if (isSelf === undefined) isSelf = u.owner === me.id;
  const card = state.cards[u.card];
  const player = d.players[u.owner];
  const colorIdx = player ? player.color : 7;
  const star = starOf(u);

  const el = document.createElement('div');
  el.className = 'unit' + (isSelf ? ' self' : '');
  el.dataset.uid = u.uid;
  el.dataset.self = isSelf ? '1' : '0';
  el.dataset.star = star;
  el.dataset.maxhp = u.maxHp;
  el.dataset.hp = u.hp;
  el.dataset.shield = u.shield || 0;
  el.dataset.owner = u.owner;
  el.dataset.card = u.card;
  el.style.setProperty('--owner-color', `var(--p${colorIdx})`);
  el.innerHTML = `
    <div class="unit-inner" title="${escapeHtml(card ? card.name : '')}">
      <div class="unit-stars">${starText(star)}</div>
      <div class="unit-body">
        <div class="unit-name">${escapeHtml(card ? card.name : '?')}</div>
        <div class="unit-stat">${unitStatText(u)}</div>
        <div class="unit-tags"></div><div class="unit-bar"><i class="hp-fill"></i><i class="shield-fill"></i></div><div class="unit-ready"><i></i></div>
      </div>
    </div>`;

  el.style.width = (100 / state.halfW) + '%';
  el.style.height = (100 / state.halfH) + '%';
  const cs = state.cellPx || 30;
  setBattleUnitPos(el, u.x, halfY(u, isSelf));
  applyUnitState(el, u, null, true);
  return el;
}

// 血量/护盾/减速的视觉状态
function applyUnitState(el, u, prev, silent) {
  const shield = u.shield || 0;
  const oldHp = prev ? prev.hp : null;
  const pct = Math.max(0, Math.min(1, u.hp / Math.max(1, u.maxHp)));

  el.dataset.hp = u.hp;
  el.dataset.shield = shield;
  el.dataset.cx = u.x;
  el.dataset.cy = u.y;

  const statEl = el.querySelector('.unit-stat');
  const txt = unitStatText(u);
  if (statEl && statEl.textContent !== txt) statEl.textContent = txt;

  const bar = el.querySelector('.hp-fill');
  if (bar) bar.style.transform = 'scaleX(' + pct.toFixed(3) + ')';
  const sfill = el.querySelector('.shield-fill');
  if (sfill) {
    const sp = Math.min(1, shield / Math.max(1, u.maxHp));
    // 护盾条贴右端覆盖在血条同一轨道上（transform-origin: right）
    sfill.style.transform = 'scaleX(' + sp.toFixed(3) + ')';
  }
  el.classList.toggle('low', pct <= 0.3);
  el.classList.toggle('mid', pct > 0.3 && pct <= 0.6);
  el.classList.toggle('shielded', shield > 0);
  el.classList.toggle('slowed', !!u.slowed);
  el.classList.toggle('hasted', (u.haste || 1) > 1);
  el.classList.toggle('stalled', !!u.stalled);
  el.classList.toggle('aura-source', u.card === 'o2');
  el.classList.toggle('delayed-mark', (u.delayedDamage || 0) > 0);
  const tags = [];
  if (u.stalled) tags.push('卡 ' + Number(u.stallLeft || 0).toFixed(1));
  else if ((u.haste || 1) > 1) tags.push('速×' + u.haste);
  if (u.slowed) tags.push('慢');
  if ((u.delayedDamage || 0) > 0) tags.push('延');
  if (u.swapped) tags.push('换');
  if (u.phase) tags.push(u.phase);
  if (u.stacks) tags.push('层' + u.stacks);
  if (u.kills && u.card === 'genetic') tags.push('进化' + u.kills);
  const tagEl = el.querySelector('.unit-tags');
  if (tagEl) tagEl.textContent = tags.slice(0,2).join(' · ');
  const ready = el.querySelector('.unit-ready i');
  if (ready) ready.style.transform = 'scaleX(' + (u.attackProgress || 0).toFixed(4) + ')';
  const stars = starText(starOf(u));
  el.querySelector('.unit-inner').title = `${stars ? stars + ' ' : ''}${state.cards[u.card]?.name || u.card} · 攻 ${u.atk ?? '?'} · 射程 ${u.range ?? '?'}${tags.length ? ' · '+tags.join(' / ') : ''}`;


  if (silent) return;
  if (oldHp === null) return;
  const isSelf = el.dataset.self === '1';
  const relY = halfY(u, isSelf);
  if (u.hp < oldHp) {
    FX.damage(u.x, u.y, oldHp - u.hp);
    flashHit(el);
  } else if (u.hp > oldHp) {
    FX.heal(u.x, u.y, u.hp - oldHp);
    flashHeal(el);
  }
}

function retrigger(el, cls) {
  el.classList.remove(cls);
  void el.offsetWidth;
  el.classList.add(cls);
}

function flashHit(el) {
  const body = el.querySelector('.unit-body');
  if (body) retrigger(body, 'hit');
  el.classList.add('hurt');
  setTimeout(() => el.classList.remove('hurt'), 190);
}

function flashHeal(el) {
  const inner = el.querySelector('.unit-inner');
  if (!inner) return;
  retrigger(inner, 'healed');
}

// 攻击前倾：朝目标方向顶一下
function lungeTo(el, fromX, fromY, toX, toY) {
  const inner = el.querySelector('.unit-inner');
  if (!inner) return;
  el.style.setProperty('--lx', Math.sign(toX - fromX) || 0);
  el.style.setProperty('--ly', Math.sign(toY - fromY) || 0);
  retrigger(inner, 'attacking');
}

function killUnit(el, last) {
  if (el._dying) return;
  el._dying = true;
  el.classList.remove('spawn');
  el.classList.add('dying');
  const isSelf = el.dataset.self === '1';
  const owner = el.dataset.owner;
  const d = state.currentD;
  const colorIdx = d && d.players[owner] ? d.players[owner].color : 7;
  if (last) FX.death(last.x, last.y, colorIdx);
  setTimeout(() => el.remove(), 420);
}

// ---- 回放主循环 --------------------------------------------------------
function startBattlePlayback() {
  stopBattlePlayback();
  const frames = state.currentFrames;
  if (!frames.length) return;
  state.lastFrameIdx = -1;
  paintBattle();
  state.rafId = requestAnimationFrame(function loop() {
    paintBattle();
    state.rafId = requestAnimationFrame(loop);
  });
}

function stopBattlePlayback() {
  if (state.rafId) {
    cancelAnimationFrame(state.rafId);
    state.rafId = null;
  }
}

function paintBattle() {
  const d = state.currentD;
  const frames = state.currentFrames;
  if (!d || !frames.length) return;

  const elapsed = (Date.now() + state.serverOffset - state.battleEpoch) / 1000;
  let idx = 0;
  for (let i = frames.length - 1; i >= 0; i--) {
    if (frames[i].t <= elapsed) { idx = i; break; }
  }

  if (idx !== state.lastFrameIdx) {
    const prev = state.lastFrameIdx >= 0 ? frames[state.lastFrameIdx] : null;
    state.lastFrameIdx = idx;
    applyFrame(frames[idx], prev, d);
  }
  // 特效按自身事件时间播放，不再等待下一张状态帧。
  playEventsUpTo(d, elapsed);

  // 位置插值：使用相邻权威帧的真实时间间隔，抹平离散移动
  const cur = state.curPos, nxt = state.nextPos;
  if (!cur || !nxt || !cur.size) return;
  const cs = state.cellPx || 30;
  const f = frames[idx];
  const nf = frames[idx + 1];
  let frac = 0;
  if (nf) {
    const span = Math.max(0.001, nf.t - f.t);
    frac = Math.min(1, Math.max(0, (elapsed - f.t) / span));
  }
  for (const [uid, p] of cur) {
    const el = state.unitMap.get(uid);
    if (!el || el._dying) continue;
    const n = nxt.get(uid);
    let x = p.x, y = p.y;
    if (n) {
      x = p.x + (n.x - p.x) * frac;
      y = p.y + (n.y - p.y) * frac;
    }
    setBattleUnitPos(el, x, y);
  }
}

function applyFrame(frame, prevFrame, d) {
  const me = getMe();
  if (!me) return;

  const prevMap = {};
  if (prevFrame) for (const u of prevFrame.units) prevMap[u.uid] = u;

  const frameMap = {};
  for (const u of frame.units) frameMap[u.uid] = u;

  // 位置缓存（本帧 / 下一帧），供 rAF 插值
  state.curPos = new Map(frame.units.map(u => [u.uid, { x: u.x, y: halfY(u, u.owner === me.id) }]));
  const nf = state.currentFrames[state.lastFrameIdx + 1];
  state.nextPos = new Map((nf ? nf.units : []).map(u => [u.uid, { x: u.x, y: halfY(u, u.owner === me.id) }]));
  // 站位索引：事件里只有格子坐标，用它反查是哪个棋子
  state.cellMap = {};
  for (const u of frame.units) state.cellMap[`${u.x},${u.y}`] = u.uid;

  for (const uid of Array.from(state.unitMap.keys())) {
    if (!(uid in frameMap)) {
      const el = state.unitMap.get(uid);
      state.unitMap.delete(uid);
      if (el) killUnit(el, prevMap[uid]);
    }
  }

  for (const u of frame.units) {
    let el = state.unitMap.get(u.uid);
    if (!el) {
      const isSelf = u.owner === me.id;
      el = createUnitEl(u, d, isSelf);
      if (!el) continue;
      const layer = document.getElementById(isSelf ? 'unitLayerSelf' : 'unitLayerOpp');
      layer.appendChild(el);
      state.unitMap.set(u.uid, el);
      continue;
    }
    applyUnitState(el, u, prevMap[u.uid] || null);
  }
}

function playEventsUpTo(d, elapsed) {
  const events = state.currentEvents || [];
  const me = getMe();
  if (!me) return;
  const cmap = state.cellMap || {};

  for (const [eventIndex, e] of events.entries()) {
    if (e.t > elapsed) continue;
    const key = `${eventIndex}|${e.t}|${e.type}|${e.name || ''}|${e.fromX ?? ''},${e.fromY ?? ''}`
      + `->${e.toX ?? ''},${e.toY ?? ''}|${e.thorns ? 'T' : ''}`;
    if (state.playedEventKeys.has(key)) continue;
    state.playedEventKeys.add(key);
    // 页面卡顿导致积压时不补播动画，只补状态
    if (elapsed - e.t > 0.6) continue;

    const isMe = e.owner === me.id;
    const colorIdx = isMe ? me.color : (d.players[e.owner] ? d.players[e.owner].color : 7);

    if (e.type === 'attack') {
      const fromUid = e.sourceUid || cmap[`${e.fromX},${e.fromY}`];
      const atkEl = fromUid ? state.unitMap.get(fromUid) : null;
      if (atkEl && !e.thorns) lungeTo(atkEl, e.fromX, e.fromY, e.toX, e.toY);
      const big = (e.dmg || 0) >= 40;
      FX.projectile(e.fromX, e.fromY, e.toX, e.toY, colorIdx,
        () => FX.impact(e.toX, e.toY, colorIdx, big), effectKind(e.skillId));
    } else if (e.type === 'skill') {
      const uid = e.sourceUid || cmap[`${e.x},${e.y}`];
      const caster = uid ? state.unitMap.get(uid) : null;
      if (caster) retrigger(caster.querySelector('.unit-inner'), 'casting');
      FX.cast(e.x, e.y, colorIdx);
      FX.zone(e);
      if (document.documentElement.dataset.fx !== 'low') FX.skill(e.x, e.y, SKILL_LABELS[e.name] || '施法');
      // 卡名已经画在棋子上，再叠一层文字只会糊在一起；用脚下光环表达「这个棋子在放技能」

    } else if (e.type === 'shield') {
      FX.shield(e.x, e.y, e.dmg || 0);
    } else if (e.type === 'heal') {
      FX.heal(e.x, e.y, e.dmg || 0);
    }
  }
}

// ============================================================
// 战斗流程
// ============================================================
function triggerBattleIntro(d, me) {
  const banner = document.getElementById('battleBanner');
  const oppName = d.opponentId && d.players[d.opponentId] ? d.players[d.opponentId].name : '（无对手）';
  document.getElementById('bannerOpp').textContent = oppName;
  document.getElementById('bannerMe').textContent = me.name;
  banner.classList.remove('hidden');
  banner.style.animation = 'none';
  void banner.offsetWidth;
  banner.style.animation = '';

  clearTimeout(state.introTimer);
  state.introTimer = setTimeout(() => {
    banner.classList.add('hidden');
  }, 2900);
}

function renderShop(me, enabled) {
  const list = document.getElementById('shopList');
  list.innerHTML = me.shop.map((cid, i) => {
    const c = state.cards[cid];
    if (!c) return '';
    const n1 = copyCount(me, cid, 1);
    const n2 = copyCount(me, cid, 2);
    const dis = !enabled || me.gold < c.cost || me.energy < c.energy
      || me.reason < c.reason || (me.bench.length >= 10 && n1 < 2);
    const copyLabel = n2 > 0 ? `2★ ${n2}/3` : (n1 > 0 ? `${n1}/3` : '');
    return `
      <div class="shop-card ${dis ? 'disabled' : ''}" onclick="${dis ? '' : `buyCard(${i})`}">
        <div class="card-name"><span>${escapeHtml(c.name)}</span><span class="card-cost">${c.cost} 金</span>${copyLabel ? `<span class="shop-copy ${n1 >= 2 || n2 >= 2 ? 'hot' : ''}">${copyLabel}</span>` : ''}</div>
        <div class="card-trait"><span class="ct-extra">${c.difficulty} · ${state.traits[c.trait] || ''} · </span>射程${c.range} · ${c.active ? '主动 ' + c.skillCost + '精力' : '被动'}</div>
        <div class="card-stats">攻 ${c.attack} · 血 ${c.maxHp || c.hp}</div><div class="card-role" title="${escapeHtml(c.tip || '')}">${escapeHtml(c.role || '')} · ${escapeHtml(c.position || '')}</div>
        <div class="card-flavor">${escapeHtml(c.flavor || '')}</div>
        <div class="card-desc">${escapeHtml(c.desc)}</div>
      </div>`;
  }).join('');
}

function renderBench(me) {
  const list = document.getElementById('benchList');
  if (!list || !me) return;
  if (state.selectedBench !== null && state.selectedBench >= me.bench.length) {
    state.selectedBench = null;
  }
  const pb = document.getElementById('prepBoard');
  if (pb) pb.classList.toggle('placing', state.selectedBench !== null);
  list.innerHTML = me.bench.map((item, i) => {
    const c = state.cards[item.card];
    if (!c) return '';
    const sel = state.selectedBench === i ? 'selected' : '';
    const star = starOf(item);
    const maxHp = starMaxHp(c, star);
    const hp = Math.min(Math.floor(item.hp ?? maxHp), maxHp);
    const stars = starText(star);
    return `<div class="bench-card ${sel}" onclick="selectBench(${i})">${escapeHtml(c.name)}${stars ? `<span class="bench-star">${stars}</span>` : ''} <span style="opacity:.6">${hp}/${maxHp}</span></div>`;
  }).join('');
}

function showEndBanner(d) {
  const banner = document.getElementById('endBanner');
  const title = document.getElementById('endTitle');
  const sub = document.getElementById('endSub');
  if (!banner) return;
  const me = d.players[d.viewerId];

  if (me && me.dead) {
    title.textContent = '出局';
    sub.textContent = '-20 Rating';
  } else if (d.winner === d.viewerId) {
    title.textContent = '胜利';
    const gold = me ? me.gold : 0;
    const g = Math.max(1, Math.floor(gold / 3));
    sub.textContent = `金币 ${gold} · Rating +${g}`;
  } else if (d.state === 'ended') {
    title.textContent = '结束';
    sub.textContent = '';
  } else {
    banner.classList.add('hidden');
    return;
  }
  banner.classList.remove('hidden');
}
function hideEndBanner() {
  const b = document.getElementById('endBanner');
  if (b) b.classList.add('hidden');
}

async function checkRejoinButton() {
  const btn = document.getElementById('rejoinBtn');
  const rid = localStorage.getItem('oi_room_id');
  if (!rid) {
    btn.style.display = 'none';
    return;
  }
  try {
    await api('/api/rejoin', 'POST', { clientId: state.clientId });
    btn.style.display = 'block';
  } catch {
    clearIdentity();
    btn.style.display = 'none';
  }
}

// ============================================================
// 启动前检查更新（静默：离线 / 超时 / 限流都不影响进入游戏）
// 本地版本取自 index.html 的 <meta name="oi-chess-release">，
// 与 check_update.py、版本清单.json 共用同一个真相源。
// ============================================================
const UPDATE_API = 'https://api.github.com/repos/IOIgf/oi-chess/releases/latest';

function versionKey(tag) {
  const m = /^v?(\d+)\.(\d+)\.(\d+)/.exec(tag || '');
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : [0, 0, 0];
}
function releaseIsNewer(local, remote) {
  const a = versionKey(local), b = versionKey(remote);
  for (let i = 0; i < 3; i++) { if (b[i] !== a[i]) return b[i] > a[i]; }
  return false;
}
async function checkUpdate() {
  const meta = document.querySelector('meta[name="oi-chess-release"]');
  const local = meta ? meta.content : '';
  // 离线预览页只注入 body，不含该 meta：直接跳过，不发网络请求。
  if (!local) return;
  try {
    if (sessionStorage.getItem('oiUpdateChecked')) return;
    sessionStorage.setItem('oiUpdateChecked', '1');
  } catch (e) { /* 隐私模式下 storage 不可用时仍检查一次 */ }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 4000);
  try {
    const res = await fetch(UPDATE_API, {
      signal: ctrl.signal, headers: { Accept: 'application/vnd.github+json' }
    });
    if (!res.ok) return;
    const d = await res.json();
    if (!d || !d.tag_name || !releaseIsNewer(local, d.tag_name)) return;
    const assets = Array.isArray(d.assets) ? d.assets : [];
    const dl = (assets[0] && assets[0].browser_download_url) || d.html_url;
    const banner = document.getElementById('updateBanner');
    if (!banner) return;
    banner.innerHTML =
      '发现新版本 <b>' + escapeHtml(d.tag_name) + '</b>（当前 ' + escapeHtml(local) + '）'
      + '<div class="update-links">'
      + (d.html_url ? '<a href="' + escapeHtml(d.html_url) + '" target="_blank" rel="noopener">查看更新</a>' : '')
      + (dl ? '<a href="' + escapeHtml(dl) + '" target="_blank" rel="noopener">下载</a>' : '')
      + '</div>'
      + '<button type="button" aria-label="关闭" onclick="dismissUpdate()">×</button>';
    banner.classList.remove('hidden');
  } catch (e) {
    // 静默跳过：检查更新绝不能阻塞游戏
  } finally {
    clearTimeout(timer);
  }
}
function dismissUpdate() {
  const b = document.getElementById('updateBanner');
  if (b) b.classList.add('hidden');
}
checkUpdate();

(async function boot() {
  loadIdentity();
  await Promise.all([loadProfile(), loadCards()]);
  await checkRejoinButton();
  const rid = localStorage.getItem('oi_room_id');
  if (rid) {
    try {
      const d = await api('/api/rejoin', 'POST', { clientId: state.clientId });
      state.playerId = d.playerId;
      state.roomId = d.roomId;
      showScreen('lobby');
      startPolling();
    } catch {
      clearIdentity();
    }
  }
})();