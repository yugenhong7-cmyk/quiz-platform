/* AI 智能题库 · 前端应用 */
"use strict";

/* ================= 基础工具 ================= */
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const store = {
  get token() { return localStorage.getItem("qb_token") || ""; },
  set token(v) { v ? localStorage.setItem("qb_token", v) : localStorage.removeItem("qb_token"); },
  get user() { try { return JSON.parse(localStorage.getItem("qb_user") || "null"); } catch { return null; } },
  set user(v) { v ? localStorage.setItem("qb_user", JSON.stringify(v)) : localStorage.removeItem("qb_user"); },
  get theme() { return localStorage.getItem("qb_theme") || "light"; },
  set theme(v) { localStorage.setItem("qb_theme", v); },
};

function toast(msg, type = "info") {
  const wrap = $("#toast-wrap");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), 3600);
}

function showModal(html) {
  const m = $("#modal");
  $("#modal-card").innerHTML = html;
  m.classList.remove("hidden");
  m.onclick = (e) => { if (e.target === m) closeModal(); };
}
function closeModal() { $("#modal").classList.add("hidden"); }

function confirmDialog(msg, onOk) {
  showModal(`<h3 style="margin-top:0">确认操作</h3><p class="text-2">${esc(msg)}</p>
    <div class="row" style="justify-content:flex-end">
      <button class="btn btn-outline" onclick="closeModal()">取消</button>
      <button class="btn btn-danger" id="modal-ok">确认</button>
    </div>`);
  $("#modal-ok").onclick = () => { closeModal(); onOk(); };
}

/* ================= API 客户端 ================= */
const API = {
  async request(path, { method = "GET", body, formData } = {}) {
    const headers = {};
    if (store.token) headers["Authorization"] = `Bearer ${store.token}`;
    if (body) headers["Content-Type"] = "application/json";
    const opts = { method, headers };
    if (formData) { opts.body = formData; delete headers["Content-Type"]; }
    else if (body) opts.body = JSON.stringify(body);

    let res;
    try {
      res = await fetch(path, opts);
    } catch (e) {
      throw new Error("网络错误，请检查服务是否运行");
    }
    if (res.status === 401) {
      store.token = ""; store.user = null;
      showAuth();
      throw new Error("登录已失效，请重新登录");
    }
    let data = null;
    const text = await res.text();
    try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
    if (!res.ok) {
      const msg = data.detail || data.message || `请求失败 (${res.status})`;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
  },
  get: (p) => API.request(p),
  post: (p, body) => API.request(p, { method: "POST", body }),
  put: (p, body) => API.request(p, { method: "PUT", body }),
  del: (p) => API.request(p, { method: "DELETE" }),
  upload: (p, formData) => API.request(p, { method: "POST", formData }),
};

/* ================= 主题 ================= */
function applyTheme() {
  document.documentElement.setAttribute("data-theme", store.theme);
  const btn = $("#theme-toggle");
  if (btn) btn.textContent = store.theme === "dark" ? "☀️ 浅色" : "🌙 深色";
}
function toggleTheme() {
  store.theme = store.theme === "dark" ? "light" : "dark";
  applyTheme();
}

/* ================= 桌宠 · 学习小伙伴 ================= */
const Pet = {
  el: null, avatar: null, bubble: null, panel: null,
  hideTimer: null, idleTimer: null, welcomed: false,
  tips: [
    "学累了记得休息一下眼睛哦 👀",
    "错题本里的题在等你复习 📕",
    "连续学习 25 分钟就起来动动吧",
    "今天也要加油学习哦！",
    "遇到不会的题可以点我，找 AI 助教聊聊",
    "收藏的题目记得回头再练一遍",
    "保持节奏，比考前突击更有效",
  ],
  teases: [
    "咕咕～我在陪你学习呢！",
    "转个圈给你打气！✨",
    "别盯着我啦，快去看题（*/∇＼*）",
    "我可是上知天文下知刷题的猫头鹰！",
    "需要提示就点我哦～",
  ],

  init() {
    this.el = $("#pet-widget");
    this.avatar = $("#pet-avatar");
    this.bubble = $("#pet-bubble");
    this.panel = $("#pet-panel");
    try {
      const p = JSON.parse(localStorage.getItem("pet_pos") || "null");
      if (p && Number.isFinite(p.right) && Number.isFinite(p.bottom)) {
        this.el.style.right = p.right + "px";
        this.el.style.bottom = p.bottom + "px";
      }
    } catch (e) { /* 忽略损坏的位置数据 */ }
    this.bindDrag();
    this.bindClick();
    this.bindPanel();
    this.idleTimer = setInterval(() => {
      if (!this.el || this.el.classList.contains("hidden")) return;
      if (!this.bubble.classList.contains("hidden")) return;
      this.say(this.tips[Math.floor(Math.random() * this.tips.length)]);
    }, 75000);
  },

  bindDrag() {
    let startX = 0, startY = 0, startRight = 0, startBottom = 0, dragging = false, moved = false;
    const onDown = (e) => {
      if (e.button != null && e.button !== 0) return;
      dragging = true; moved = false;
      startX = e.clientX; startY = e.clientY;
      startRight = parseFloat(this.el.style.right || getComputedStyle(this.el).right) || 22;
      startBottom = parseFloat(this.el.style.bottom || getComputedStyle(this.el).bottom) || 22;
      this.avatar.classList.add("dragging");
      this.avatar.setPointerCapture && e.pointerId != null && this.avatar.setPointerCapture(e.pointerId);
    };
    const onMove = (e) => {
      if (!dragging) return;
      const dx = startX - e.clientX, dy = startY - e.clientY;
      if (Math.abs(dx) + Math.abs(dy) > 6) moved = true;
      if (!moved) return;
      const r = Math.min(Math.max(startRight + dx, -20), window.innerWidth - 60);
      const b = Math.min(Math.max(startBottom + dy, -20), window.innerHeight - 60);
      this.el.style.right = r + "px";
      this.el.style.bottom = b + "px";
    };
    const onUp = () => {
      if (!dragging) return;
      dragging = false;
      this.avatar.classList.remove("dragging");
      if (moved) {
        localStorage.setItem("pet_pos", JSON.stringify({
          right: parseFloat(this.el.style.right) || 22,
          bottom: parseFloat(this.el.style.bottom) || 22,
        }));
        this._justDragged = true;
        setTimeout(() => { this._justDragged = false; }, 250);
      }
    };
    this.avatar.addEventListener("pointerdown", onDown);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  },

  bindClick() {
    this.avatar.addEventListener("click", () => {
      if (this._justDragged) return;
      const open = this.panel.classList.contains("hidden");
      this.panel.classList.toggle("hidden", !open);
      if (open) this.bubble.classList.add("hidden");
    });
    document.addEventListener("click", (e) => {
      if (!this.el || this.el.classList.contains("hidden")) return;
      if (!this.el.contains(e.target)) this.panel.classList.add("hidden");
    });
  },

  bindPanel() {
    this.panel.querySelectorAll(".pet-action").forEach((btn) => {
      btn.onclick = () => {
        const act = btn.dataset.act;
        this.panel.classList.add("hidden");
        if (act === "chat") {
          const drawer = $("#ai-drawer");
          drawer.classList.remove("hidden");
          window._aiContext = null;
          $("#drawer-messages").innerHTML =
            `<div class="chat-msg assistant">你好！我是你的学习小伙伴 🦉 有什么想问的？可以直接问我知识点、解题思路～</div>`;
        } else if (act === "wrong") {
          location.hash = "#/wrong"; router();
        } else if (act === "stats") {
          location.hash = "#/stats"; router();
        } else if (act === "tease") {
          this.react("spin");
          this.say(this.teases[Math.floor(Math.random() * this.teases.length)]);
        }
      };
    });
  },

  show() {
    this.el && this.el.classList.remove("hidden");
    if (!this.welcomed) {
      this.welcomed = true;
      setTimeout(() => this.say("我是你的学习小伙伴 🦉 答题时我会给你加油！"), 700);
    }
  },
  hide() { this.el && this.el.classList.add("hidden"); },

  say(text, ms = 4600) {
    if (!this.bubble) return;
    this.bubble.textContent = text;
    this.bubble.classList.remove("hidden");
    clearTimeout(this.hideTimer);
    this.hideTimer = setTimeout(() => this.bubble.classList.add("hidden"), ms);
  },

  react(kind) {
    if (!this.avatar) return;
    const cls = kind === "happy" ? "react-happy" : kind === "sad" ? "react-sad" : "react-spin";
    this.avatar.classList.remove("react-happy", "react-sad", "react-spin");
    const img = this.avatar.querySelector("img");
    void (img || this.avatar).offsetWidth; // 重启动画
    this.avatar.classList.add(cls);
    setTimeout(() => this.avatar.classList.remove(cls), 1300);
    if (kind === "happy") {
      const lines = ["答对啦！继续保持 🎉", "太棒了，正确！", "漂亮！又拿下一题 ✨", "答对了，手感不错！"];
      this.say(lines[Math.floor(Math.random() * lines.length)]);
    } else if (kind === "sad") {
      const lines = ["没关系，看看解析再试试 💪", "错题是进步的阶梯，记下来！", "别灰心，这题我陪你搞懂它", "再接再厉，下次一定对！"];
      this.say(lines[Math.floor(Math.random() * lines.length)]);
    }
  },
};
window.Pet = Pet;

/* ================= 认证 ================= */
function showAuth() {
  $("#auth-view").classList.remove("hidden");
  $("#main-view").classList.add("hidden");
  window.Pet && Pet.hide();
}
function showMain() {
  $("#auth-view").classList.add("hidden");
  $("#main-view").classList.remove("hidden");
  window.Pet && Pet.show();
  const u = store.user;
  if (u) {
    $("#user-name").textContent = u.nickname || u.username;
    $("#user-role").textContent = u.role === "admin" ? "管理员" : "用户";
    $("#user-avatar").textContent = (u.nickname || u.username || "U").slice(0, 1).toUpperCase();
  }
}

async function doLogin(username, password) {
  const data = await API.post("/api/auth/login", { username, password });
  store.token = data.access_token;
  store.user = data.user;
  toast(`欢迎回来，${data.user.nickname || data.user.username}`, "success");
  showMain();
  location.hash = "#/dashboard";
  router();
}
async function doRegister(payload) {
  const data = await API.post("/api/auth/register", payload);
  store.token = data.access_token;
  store.user = data.user;
  toast("注册成功", "success");
  showMain();
  location.hash = "#/dashboard";
  router();
}

/* ================= 路由 ================= */
const routes = {
  dashboard: viewDashboard,
  banks: viewBanks,
  bank: viewBankDetail,
  import: viewImport,
  practice: viewPracticeSetup,
  quiz: viewQuiz,
  exam: viewExamSetup,
  "exam-run": viewExamRun,
  result: viewResult,
  wrong: viewWrong,
  ai: viewAI,
  stats: viewStats,
  settings: viewSettings,
};
const titles = {
  dashboard: "工作台", banks: "我的题库", bank: "题库详情", import: "智能导入",
  practice: "开始刷题", quiz: "练习中", exam: "模拟考试", "exam-run": "考试中",
  result: "练习报告", wrong: "错题本", ai: "AI 助教", stats: "学习统计", settings: "系统设置",
};

function parseHash() {
  const h = (location.hash || "#/dashboard").replace(/^#\/?/, "");
  const path = h.split("?")[0]; // 去掉 ?query，否则 #/import?bank=1 会匹配不到路由
  const [name, ...rest] = path.split("/").filter(Boolean);
  return { name: name || "dashboard", params: rest };
}

async function router() {
  if (!store.token) { showAuth(); return; }
  showMain();
  const { name, params } = parseHash();
  const fn = routes[name] || viewDashboard;
  $("#page-title").textContent = titles[name] || "工作台";
  $$(".nav-item").forEach((a) => a.classList.toggle("active",
    a.dataset.route === name || (name === "bank" && a.dataset.route === "banks") ||
    (name === "quiz" && a.dataset.route === "practice") ||
    (name === "import" && a.dataset.route === "banks")));
  $("#topbar-actions").innerHTML = "";
  const container = $("#page-container");
  container.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>加载中…</p></div>`;
  try {
    await fn(container, params);
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>${esc(e.message)}</p>
      <button class="btn btn-primary" onclick="router()">重试</button></div>`;
  }
  window.scrollTo({ top: 0 });
}

/* ================= 图表工具（纯 SVG） ================= */
function lineChart(data, { height = 200, color = "var(--primary)", label = "数值" } = {}) {
  if (!data.length) return `<div class="empty-state small">暂无数据</div>`;
  const w = 680, h = height, pad = { l: 36, r: 12, t: 14, b: 28 };
  const max = Math.max(...data.map((d) => d.value), 1);
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const pts = data.map((d, i) => {
    const x = pad.l + (i / Math.max(data.length - 1, 1)) * iw;
    const y = pad.t + ih - (d.value / max) * ih;
    return [x, y];
  });
  const path = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  const area = path + ` L${pts[pts.length - 1][0].toFixed(1)},${(pad.t + ih).toFixed(1)} L${pad.l},${(pad.t + ih).toFixed(1)} Z`;
  const grid = [0, .25, .5, .75, 1].map((f) => {
    const y = pad.t + ih * (1 - f);
    const v = max * f;
    const label = max < 4 ? (Math.round(v * 10) / 10) : Math.round(v);
    return `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y}" y2="${y}" stroke="var(--border)" stroke-width="1"/>
      <text x="${pad.l - 6}" y="${y + 4}" text-anchor="end" font-size="10" fill="var(--text-3)">${label}</text>`;
  }).join("");
  const labels = data.map((d, i) => {
    if (data.length > 8 && i % Math.ceil(data.length / 8) !== 0) return "";
    const x = pad.l + (i / Math.max(data.length - 1, 1)) * iw;
    return `<text x="${x}" y="${h - 8}" text-anchor="middle" font-size="9.5" fill="var(--text-3)">${esc(d.label)}</text>`;
  }).join("");
  const dots = pts.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="3.2" fill="var(--bg-card)" stroke="${color}" stroke-width="2"><title>${esc(data[i].label)}: ${data[i].value}</title></circle>`).join("");
  return `<svg class="chart-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet">${grid}
    <path d="${area}" fill="${color}" opacity="0.1"/><path d="${path}" fill="none" stroke="${color}" stroke-width="2.5"/>
    ${dots}${labels}</svg>`;
}

function barChart(data, { height = 200, color = "var(--primary)" } = {}) {
  if (!data.length) return `<div class="empty-state small">暂无数据</div>`;
  const w = 680, h = height, pad = { l: 36, r: 12, t: 14, b: 30 };
  const max = Math.max(...data.map((d) => d.value), 1);
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const bw = Math.min(42, (iw / data.length) * 0.62);
  const bars = data.map((d, i) => {
    const x = pad.l + ((i + 0.5) / data.length) * iw - bw / 2;
    const bh = (d.value / max) * ih;
    const y = pad.t + ih - bh;
    return `<rect x="${x}" y="${y}" width="${bw}" height="${Math.max(bh, 2)}" rx="5" fill="${d.color || color}" opacity="0.9">
      <title>${esc(d.label)}: ${d.value}</title></rect>
      <text x="${x + bw / 2}" y="${y - 5}" text-anchor="middle" font-size="10" fill="var(--text-2)">${d.value}</text>
      <text x="${x + bw / 2}" y="${h - 10}" text-anchor="middle" font-size="9.5" fill="var(--text-3)">${esc(String(d.label).slice(0, 6))}</text>`;
  }).join("");
  return `<svg class="chart-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet">
    <line x1="${pad.l}" x2="${w - pad.r}" y1="${pad.t + ih}" y2="${pad.t + ih}" stroke="var(--border)"/>${bars}</svg>`;
}

/* ================= 视图：登录后页面 ================= */

/* ---- 工作台 ---- */
async function viewDashboard(el) {
  const [stats, banks, sessions] = await Promise.all([
    API.get("/api/stats/summary"),
    API.get("/api/banks?scope=all"),
    API.get("/api/practice/sessions?limit=5"),
  ]);
  const inProgress = sessions.find((s) => s.status === "in_progress");
  const trend = (stats.daily_trend || []).map((d) => ({ label: d.date.slice(5), value: d.answered }));
  const weak = (stats.by_knowledge || []).slice(0, 5);

  el.innerHTML = `
    <div class="grid grid-4">
      <div class="stat-card"><div class="stat-label">已完成题目</div><div class="stat-value">${stats.total_answered}</div><div class="stat-sub">正确 ${stats.correct_count} 题</div></div>
      <div class="stat-card"><div class="stat-label">总体正确率</div><div class="stat-value">${stats.accuracy}%</div>
        <div class="progress mt-8"><div class="progress-bar" style="width:${Math.min(stats.accuracy, 100)}%"></div></div></div>
      <div class="stat-card"><div class="stat-label">错题数量</div><div class="stat-value" style="color:var(--danger)">${stats.wrong_count}</div>
        <div class="stat-sub">收藏 ${stats.favorite_count} 题</div></div>
      <div class="stat-card"><div class="stat-label">我的题库</div><div class="stat-value">${stats.total_banks}</div><div class="stat-sub">共 ${stats.total_questions} 道题</div></div>
    </div>

    ${inProgress ? `
    <div class="card mt-16" style="background:linear-gradient(135deg,var(--primary-soft),var(--bg-card))">
      <div class="row-between">
        <div>
          <div class="badge badge-primary">继续上次练习</div>
          <h3 style="margin:8px 0 4px">${esc(inProgress.bank_name)} · ${modeName(inProgress.mode)}</h3>
          <p class="text-2 small" style="margin:0">共 ${inProgress.total_questions} 题 · 开始于 ${fmtTime(inProgress.started_at)}</p>
        </div>
        <button class="btn btn-primary btn-lg" onclick="location.hash='#/quiz/${inProgress.id}'">继续作答 →</button>
      </div>
    </div>` : `
    <div class="card mt-16">
      <div class="row-between">
        <div><h3 style="margin:0 0 4px">开始新的练习 💪</h3><p class="text-2" style="margin:0">选择题库，立即刷题巩固知识</p></div>
        <button class="btn btn-primary btn-lg" onclick="location.hash='#/practice'">去刷题 →</button>
      </div>
    </div>`}

    <div class="grid grid-2 mt-16">
      <div class="card">
        <h3 class="card-title">📈 每日刷题趋势（近 30 天）</h3>
        ${lineChart(trend)}
      </div>
      <div class="card">
        <h3 class="card-title">🎯 薄弱知识点</h3>
        ${weak.length ? weak.map((w) => `
          <div style="margin:10px 0">
            <div class="row-between small"><span class="strong">${esc(w.knowledge_point)}</span><span class="text-2">${w.accuracy}%（${w.correct}/${w.answered}）</span></div>
            <div class="progress mt-8"><div class="progress-bar" style="width:${w.accuracy}%;background:${w.accuracy < 60 ? "var(--danger)" : w.accuracy < 80 ? "var(--warning)" : "var(--success)"}"></div></div>
          </div>`).join("") : `<div class="empty-state"><p>暂无数据，先去刷几道题吧</p></div>`}
      </div>
    </div>

    <div class="card mt-16">
      <div class="row-between"><h3 class="card-title" style="margin:0">🗃️ 我的题库</h3>
        <a href="#/banks" class="btn btn-outline btn-sm">查看全部</a></div>
      <div class="grid grid-3 mt-16">
        ${banks.slice(0, 6).map(bankCard).join("") || `<div class="empty-state"><div class="empty-icon">📭</div><p>还没有题库</p>
          <button class="btn btn-primary" onclick="location.hash='#/banks'">创建题库</button></div>`}
      </div>
    </div>

    <div class="card mt-16">
      <h3 class="card-title">⏱️ 最近练习</h3>
      ${stats.recent_sessions.length ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>题库</th><th>模式</th><th>题量</th><th>正确</th><th>得分</th><th>时间</th><th></th></tr></thead>
        <tbody>${stats.recent_sessions.map((s) => `<tr>
          <td class="strong">${esc(s.bank_name)}</td>
          <td><span class="badge">${modeName(s.mode)}</span></td>
          <td>${s.total}</td><td>${s.correct}</td>
          <td>${s.score != null ? s.score + "分" : "-"}</td>
          <td class="text-3 small">${fmtTime(s.started_at)}</td>
          <td><button class="btn btn-ghost btn-sm" onclick="location.hash='#/result/${s.id}'">查看</button></td>
        </tr>`).join("")}</tbody></table></div>` : `<div class="empty-state"><p>暂无练习记录</p></div>`}
    </div>`;
}

function bankCard(b) {
  return `<div class="card" style="cursor:pointer" onclick="location.hash='#/bank/${b.id}'">
    <div class="row-between">
      <div style="font-size:30px">${esc(b.cover || "📖")}</div>
      <span class="badge ${b.visibility === "private" ? "" : "badge-info"}">${b.visibility === "private" ? "私有" : b.visibility === "shared" ? "共享" : "公开"}</span>
    </div>
    <h3 style="margin:10px 0 4px;font-size:15.5px">${esc(b.name)}</h3>
    <p class="text-3 small" style="margin:0 0 10px;height:32px;overflow:hidden">${esc(b.description || b.category || "")}</p>
    <div class="row-between small text-2"><span>${b.question_count} 题</span><span>${b.progress?.percent || 0}% 已练</span></div>
    <div class="progress mt-8"><div class="progress-bar" style="width:${b.progress?.percent || 0}%"></div></div>
  </div>`;
}

/* ---- 题库中心 ---- */
async function viewBanks(el) {
  const banks = await API.get("/api/banks?scope=all");
  window._banksCache = banks;
  el.innerHTML = `
    <div class="row-between mb-8">
      <div class="row" style="flex:1">
        <input id="bank-search" placeholder="搜索题库名称 / 简介…" style="max-width:280px" />
        <select id="bank-scope" style="max-width:130px">
          <option value="all">全部</option><option value="mine">我创建的</option>
          <option value="shared">共享给我的</option><option value="public">公开</option>
        </select>
      </div>
      <div class="row">
        <button class="btn btn-outline" onclick="location.hash='#/import'">📥 批量导入</button>
        <button class="btn btn-primary" id="new-bank-btn">＋ 新建题库</button>
      </div>
    </div>
    <div class="grid grid-3" id="banks-grid"></div>`;

  const render = (list) => {
    $("#banks-grid").innerHTML = list.length
      ? list.map(bankCard).join("")
      : `<div class="empty-state"><div class="empty-icon">🗃️</div><p>没有找到题库</p></div>`;
  };
  render(banks);

  $("#bank-search").oninput = (e) => {
    const kw = e.target.value.toLowerCase();
    render(banks.filter((b) => (b.name + (b.description || "")).toLowerCase().includes(kw)));
  };
  $("#bank-scope").onchange = async (e) => {
    const list = await API.get(`/api/banks?scope=${e.target.value}`);
    window._banksCache = list;
    render(list);
  };
  $("#new-bank-btn").onclick = () => showBankForm();

  $("#topbar-actions").innerHTML = `<button class="btn btn-primary" onclick="document.getElementById('new-bank-btn').click()">＋ 新建题库</button>`;
}

function showBankForm(bank = null) {
  const cats = ["计算机", "操作系统", "计算机网络", "数据结构", "人工智能", "数学", "英语", "考研", "公务员", "自定义"];
  const covers = ["📖", "💻", "🖥️", "🌐", "🌲", "🤖", "📐", "🔤", "📚", "🏛️", "🧠", "⚙️"];
  showModal(`
    <h3 style="margin-top:0">${bank ? "编辑题库" : "新建题库"}</h3>
    <label>名称 *<input id="bf-name" value="${esc(bank?.name || "")}" placeholder="如：操作系统" /></label>
    <label class="mt-8">简介<textarea id="bf-desc" placeholder="简要描述题库内容…">${esc(bank?.description || "")}</textarea></label>
    <div class="form-inline mt-8">
      <label>分类<select id="bf-cat">${cats.map((c) => `<option ${bank?.category === c ? "selected" : ""}>${c}</option>`).join("")}</select></label>
      <label>可见性<select id="bf-vis">
        <option value="private" ${bank?.visibility === "private" ? "selected" : ""}>私有</option>
        <option value="shared" ${bank?.visibility === "shared" ? "selected" : ""}>共享</option>
        <option value="public" ${bank?.visibility === "public" ? "selected" : ""}>公开</option>
      </select></label>
    </div>
    <label class="mt-8">封面图标
      <div class="row">${covers.map((c) => `<button type="button" class="chip cover-pick ${(bank?.cover || "📖") === c ? "active" : ""}" data-c="${c}" style="font-size:18px">${c}</button>`).join("")}</div>
    </label>
    <div class="row mt-16" style="justify-content:flex-end">
      <button class="btn btn-outline" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" id="bf-save">保存</button>
    </div>`);
  let cover = bank?.cover || "📖";
  $$(".cover-pick").forEach((b) => b.onclick = () => {
    $$(".cover-pick").forEach((x) => x.classList.remove("active"));
    b.classList.add("active"); cover = b.dataset.c;
  });
  $("#bf-save").onclick = async () => {
    const name = $("#bf-name").value.trim();
    if (!name) return toast("请输入题库名称", "error");
    const payload = {
      name, description: $("#bf-desc").value, category: $("#bf-cat").value,
      cover, visibility: $("#bf-vis").value,
    };
    try {
      if (bank) await API.put(`/api/banks/${bank.id}`, payload);
      else await API.post("/api/banks", payload);
      closeModal();
      toast(bank ? "题库已更新" : "题库创建成功", "success");
      router();
    } catch (e) { toast(e.message, "error"); }
  };
}

/* ---- 题库详情 ---- */
async function viewBankDetail(el, params) {
  const bankId = params[0];
  const [bank, chapters] = await Promise.all([
    API.get(`/api/banks/${bankId}`),
    API.get(`/api/banks/${bankId}/chapters`),
  ]);
  window._bankCache = { bank, chapters };
  let curType = "", curChapter = "", curPage = 1, curKw = "";

  el.innerHTML = `
    <div class="card">
      <div class="row-between">
        <div class="row">
          <div style="font-size:38px">${esc(bank.cover || "📖")}</div>
          <div>
            <h2 style="margin:0">${esc(bank.name)}</h2>
            <p class="text-2" style="margin:2px 0 0">${esc(bank.description || "暂无简介")}</p>
            <div class="row mt-8">
              <span class="badge badge-primary">${esc(bank.category)}</span>
              <span class="badge">${bank.question_count} 题</span>
              <span class="badge ${bank.is_owner ? "badge-success" : "badge-info"}">${bank.is_owner ? "我创建的" : "共享题库"}</span>
              <span class="badge">已练 ${bank.progress?.percent || 0}%</span>
            </div>
          </div>
        </div>
        <div class="col">
          <button class="btn btn-primary" onclick="startPractice(${bank.id},'sequential')">▶ 开始练习</button>
          <div class="row">
            <button class="btn btn-outline btn-sm" onclick="location.hash='#/import?bank=${bank.id}'">📥 导入</button>
            <button class="btn btn-outline btn-sm" onclick="showBankForm(window._banksCache?.find(b=>b.id==${bank.id}) || ${JSON.stringify(bank).replace(/"/g, "&quot;")})">✏️ 编辑</button>
            ${bank.is_owner ? `<button class="btn btn-outline btn-sm" onclick="showShareModal(${bank.id})">👥 共享</button>
            <button class="btn btn-danger btn-sm" onclick="deleteBank(${bank.id})">删除</button>` : ""}
          </div>
        </div>
      </div>
    </div>

    <div class="row mt-16">
      <input id="q-search" placeholder="搜索题干 / 解析…" style="max-width:220px" />
      <select id="q-type" style="max-width:130px">
        <option value="">全部题型</option>
        <option value="single">单选题</option><option value="multiple">多选题</option>
        <option value="truefalse">判断题</option><option value="blank">填空题</option>
        <option value="shortanswer">简答题</option><option value="calculation">计算题</option>
        <option value="unknown">未识别</option>
      </select>
      <select id="q-chapter" style="max-width:150px">
        <option value="">全部章节</option>
        ${chapters.map((c) => `<option value="${c.id}">${esc(c.name)} (${c.question_count})</option>`).join("")}
      </select>
      <div class="spacer"></div>
      ${bank.is_owner ? `
        <button class="btn btn-outline btn-sm" onclick="addQuestionManually(${bank.id})">＋ 手动添加</button>
        <button class="btn btn-outline btn-sm" id="batch-btn">批量操作</button>
        <button class="btn btn-outline btn-sm" id="chapter-btn">章节管理</button>` : ""}
      <button class="btn btn-primary btn-sm" onclick="startPractice(${bank.id},'sequential')">开始练习</button>
    </div>

    <div class="card mt-16">
      <div id="q-list"><div class="loading-state"><div class="spinner"></div></div></div>
    </div>`;

  async function loadQuestions() {
    const qs = new URLSearchParams({ bank_id: bankId, page: curPage, page_size: 15 });
    if (curType) qs.set("qtype", curType);
    if (curChapter) qs.set("chapter_id", curChapter);
    if (curKw) qs.set("keyword", curKw);
    const data = await API.get(`/api/banks/${bankId}/questions?${qs}`);
    $("#q-list").innerHTML = data.total === 0
      ? `<div class="empty-state"><div class="empty-icon">📝</div><p>还没有题目</p>
         <button class="btn btn-primary" onclick="location.hash='#/import?bank=${bankId}'">批量导入题目</button></div>`
      : `<div class="table-wrap"><table class="table">
        <thead><tr><th style="width:36px"><input type="checkbox" id="q-all" /></th><th>题干</th><th>题型</th><th>难度</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>${data.items.map((q) => `<tr>
          <td><input type="checkbox" class="q-check" value="${q.id}" /></td>
          <td><div style="max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(q.stem)}</div>
            ${(q.knowledge_points || []).length ? `<div class="q-meta">${q.knowledge_points.map((k) => `<span class="badge">${esc(k)}</span>`).join("")}</div>` : ""}</td>
          <td><span class="badge badge-primary">${typeName(q.qtype)}</span></td>
          <td>${"⭐".repeat(q.difficulty)}</td>
          <td>${q.review_status === "confirmed" ? `<span class="badge badge-success">已确认</span>` : `<span class="badge badge-warning">待确认</span>`}
            ${q.is_draft ? `<span class="badge badge-info">草稿</span>` : ""}</td>
          <td class="actions">
            <button class="btn btn-ghost btn-sm" onclick="showQuestionDetail(${q.id})">查看</button>
            ${bank.is_owner ? `<button class="btn btn-ghost btn-sm" onclick="editQuestion(${q.id})">编辑</button>
            <button class="btn btn-ghost btn-sm" onclick="deleteQuestion(${q.id},${bankId})">删除</button>` : ""}
          </td>
        </tr>`).join("")}</tbody></table>
        <div class="pagination">
          <button class="btn btn-outline btn-sm" ${curPage <= 1 ? "disabled" : ""} id="q-prev">上一页</button>
          <span class="text-2 small">第 ${data.page} / ${Math.max(1, Math.ceil(data.total / data.page_size))} 页 · 共 ${data.total} 题</span>
          <button class="btn btn-outline btn-sm" ${curPage >= Math.ceil(data.total / data.page_size) ? "disabled" : ""} id="q-next">下一页</button>
        </div></div>`;

    $("#q-all") && ($("#q-all").onchange = (e) => $$(".q-check").forEach((c) => (c.checked = e.target.checked)));
    $("#q-prev") && ($("#q-prev").onclick = () => { curPage--; loadQuestions(); });
    $("#q-next") && ($("#q-next").onclick = () => { curPage++; loadQuestions(); });
  }

  $("#q-search").oninput = (e) => { curKw = e.target.value; curPage = 1; loadQuestions(); };
  $("#q-type").onchange = (e) => { curType = e.target.value; curPage = 1; loadQuestions(); };
  $("#q-chapter").onchange = (e) => { curChapter = e.target.value; curPage = 1; loadQuestions(); };
  $("#batch-btn") && ($("#batch-btn").onclick = () => showBatchModal(bankId, chapters, loadQuestions));
  $("#chapter-btn") && ($("#chapter-btn").onclick = () => showChapterModal(bankId));
  await loadQuestions();
}

async function showQuestionDetail(qid) {
  const q = await API.get(`/api/questions/${qid}`);
  showModal(`
    <div class="row-between"><h3 style="margin:0">题目详情</h3>
      <button class="btn btn-ghost btn-sm" onclick="closeModal()">✕</button></div>
    <div class="q-meta mt-8">
      <span class="badge badge-primary">${typeName(q.qtype)}</span>
      <span class="badge">${"⭐".repeat(q.difficulty)}</span>
      ${(q.knowledge_points || []).map((k) => `<span class="badge badge-info">${esc(k)}</span>`).join("")}
    </div>
    <div class="q-stem">${esc(q.stem)}</div>
    ${q.options?.length ? q.options.map((o) => `<div class="option-item ${o.is_correct ? "correct" : ""}">
      <div class="option-label">${esc(o.label)}</div><div class="option-text">${esc(o.content)}</div>
      ${o.is_correct ? `<span class="badge badge-success">正确答案</span>` : ""}</div>`).join("") : ""}
    <div class="card mt-8" style="background:var(--bg-hover)">
      <div class="small strong">标准答案</div>
      <div class="mt-8">${esc(JSON.stringify(q.answer))}</div>
      ${q.explanation ? `<div class="small strong mt-8">解析</div><div class="text-2 mt-8">${esc(q.explanation)}</div>` : ""}
    </div>
    <div class="small text-3 mt-8">原始文本：${esc(q.raw_text || "（无）")}</div>`);
}

function showBatchModal(bankId, chapters, reload) {
  showModal(`
    <h3 style="margin-top:0">批量操作</h3>
    <p class="text-2 small">先在题目列表勾选题目，再选择操作。</p>
    <div class="col">
      <button class="btn btn-outline" onclick="batchOp(${bankId},'delete',null,null)">🗑️ 删除选中题目</button>
      <button class="btn btn-outline" onclick="batchOp(${bankId},'dedup',null,null)">🧹 全库去重</button>
      <div class="form-inline">
        <label>移动到章节<select id="batch-chapter">
          ${chapters.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}
        </select></label>
        <button class="btn btn-outline" onclick="batchOp(${bankId},'set_chapter',document.getElementById('batch-chapter').value,null)">移动</button>
      </div>
      <div class="form-inline">
        <label>设置难度<select id="batch-diff"><option value="1">⭐ 简单</option><option value="2">⭐⭐ 中等</option><option value="3">⭐⭐⭐ 困难</option></select></label>
        <button class="btn btn-outline" onclick="batchOp(${bankId},'set_difficulty',null,document.getElementById('batch-diff').value)">设置</button>
      </div>
    </div>`);
}

window.batchOp = async (bankId, action, chapterId, difficulty) => {
  const ids = $$(".q-check:checked").map((c) => +c.value);
  if (action !== "dedup" && !ids.length) return toast("请先勾选题目", "error");
  if (action === "delete") {
    confirmDialog(`确定删除选中的 ${ids.length} 道题吗？`, async () => {
      await doBatch(bankId, { ids, action });
    });
  } else {
    await doBatch(bankId, { ids, action, chapter_id: chapterId ? +chapterId : null, difficulty: difficulty ? +difficulty : null });
  }
};
async function doBatch(bankId, payload) {
  try {
    const r = await API.post(`/api/banks/${bankId}/questions/batch`, payload);
    toast(r.message || "操作成功", "success");
    closeModal();
    router();
  } catch (e) { toast(e.message, "error"); }
}

function showChapterModal(bankId) {
  const chapters = window._bankCache?.chapters || [];
  showModal(`
    <h3 style="margin-top:0">章节管理</h3>
    <div id="ch-list">${chapters.map((c) => `
      <div class="row-between" style="padding:8px 0;border-bottom:1px solid var(--border)">
        <div><span class="strong">${esc(c.name)}</span> <span class="text-3 small">${c.question_count} 题</span></div>
        <button class="btn btn-ghost btn-sm" onclick="deleteChapter(${c.id},${bankId})">删除</button>
      </div>`).join("") || `<p class="text-2">暂无章节</p>`}</div>
    <div class="form-inline mt-16">
      <label>新章节名<input id="ch-name" placeholder="如：第一章 操作系统概述" /></label>
      <button class="btn btn-primary" id="ch-add">添加</button>
    </div>`);
  $("#ch-add").onclick = async () => {
    const name = $("#ch-name").value.trim();
    if (!name) return toast("请输入章节名", "error");
    try {
      await API.post(`/api/banks/${bankId}/chapters`, { name });
      toast("章节已添加", "success");
      closeModal(); router();
    } catch (e) { toast(e.message, "error"); }
  };
}
window.deleteChapter = (id, bankId) => confirmDialog("删除章节后题目会变为未分章，确定？", async () => {
  await API.del(`/api/banks/chapters/${id}`); closeModal(); toast("已删除", "success"); router();
});

function showShareModal(bankId) {
  showModal(`
    <h3 style="margin-top:0">共享题库</h3>
    <p class="text-2 small">共享后对方可以用该题库独立刷题，学习记录互不覆盖。</p>
    <div class="form-inline">
      <label>用户名<input id="share-user" placeholder="输入对方用户名" /></label>
      <label>权限<select id="share-edit"><option value="false">只读</option><option value="true">可编辑</option></select></label>
      <button class="btn btn-primary" id="share-btn">共享</button>
    </div>
    <div class="mt-16" id="share-list"><div class="spinner" style="width:20px;height:20px"></div></div>`);
  const loadShares = async () => {
    const list = await API.get(`/api/banks/${bankId}/shares`);
    $("#share-list").innerHTML = list.length
      ? list.map((s) => `<div class="row-between" style="padding:6px 0;border-bottom:1px solid var(--border)">
          <span>${esc(s.username)} ${s.can_edit ? '<span class="badge badge-primary">可编辑</span>' : '<span class="badge">只读</span>'}</span>
          <button class="btn btn-ghost btn-sm" onclick="removeShare(${bankId},${s.user_id})">移除</button></div>`).join("")
      : `<p class="text-2 small">尚未共享给任何人</p>`;
  };
  loadShares();
  $("#share-btn").onclick = async () => {
    try {
      await API.post(`/api/banks/${bankId}/share`, {
        username: $("#share-user").value.trim(),
        can_edit: $("#share-edit").value === "true",
      });
      toast("共享成功", "success"); loadShares();
    } catch (e) { toast(e.message, "error"); }
  };
}
window.removeShare = async (bid, uid) => { await API.del(`/api/banks/${bid}/share/${uid}`); toast("已移除", "success"); showShareModal(bid); };
window.deleteBank = (id) => confirmDialog("删除题库将同时删除其中所有题目和练习记录，确定删除？", async () => {
  await API.del(`/api/banks/${id}`); toast("题库已删除", "success"); location.hash = "#/banks"; router();
});

/* ---- 题目手动编辑 ---- */
function questionFormHTML(q = null) {
  const qtype = q?.qtype || "single";
  return `
    <label>题型<select id="qf-type">
      ${[["single", "单选题"], ["multiple", "多选题"], ["truefalse", "判断题"], ["blank", "填空题"], ["shortanswer", "简答题"], ["calculation", "计算题"]]
        .map(([v, n]) => `<option value="${v}" ${qtype === v ? "selected" : ""}>${n}</option>`).join("")}
    </select></label>
    <label class="mt-8">题干 *<textarea id="qf-stem">${esc(q?.stem || "")}</textarea></label>
    <div id="qf-options-wrap" class="mt-8"></div>
    <label class="mt-8">答案 *<input id="qf-answer" value="${esc(
      q?.answer != null ? (Array.isArray(q.answer) ? q.answer.join(",") : String(q.answer)) : ""
    )}" placeholder="单选填 B；多选填 A,B；判断填 正确/错误；填空用逗号分隔" /></label>
    <label class="mt-8">解析<textarea id="qf-exp">${esc(q?.explanation || "")}</textarea></label>
    <div class="form-inline mt-8">
      <label>难度<select id="qf-diff">
        <option value="1" ${q?.difficulty === 1 ? "selected" : ""}>简单</option>
        <option value="2" ${(!q || q.difficulty === 2) ? "selected" : ""}>中等</option>
        <option value="3" ${q?.difficulty === 3 ? "selected" : ""}>困难</option>
      </select></label>
      <label>知识点（逗号分隔）<input id="qf-kp" value="${esc((q?.knowledge_points || []).join(","))}" /></label>
    </div>`;
}

function renderQfOptions(q = null) {
  const type = $("#qf-type").value;
  const wrap = $("#qf-options-wrap");
  if (type === "single" || type === "multiple") {
    const opts = q?.options?.length ? q.options : [
      { label: "A", content: "" }, { label: "B", content: "" }, { label: "C", content: "" }, { label: "D", content: "" },
    ];
    wrap.innerHTML = `<div class="small strong mb-8">选项（正确答案请在下方"答案"中填选项字母）</div>
      ${opts.map((o, i) => `<div class="form-inline" style="margin-bottom:6px">
        <label style="flex:0 0 40px">${esc(o.label)}</label>
        <input class="qf-opt" data-label="${esc(o.label)}" value="${esc(o.content)}" placeholder="选项内容" />
      </div>`).join("")}
      <button type="button" class="btn btn-ghost btn-sm" id="qf-add-opt">＋ 添加选项</button>`;
    $("#qf-add-opt").onclick = () => {
      const inputs = $$(".qf-opt");
      const label = String.fromCharCode(65 + inputs.length);
      const div = document.createElement("div");
      div.className = "form-inline"; div.style.marginBottom = "6px";
      div.innerHTML = `<label style="flex:0 0 40px">${label}</label><input class="qf-opt" data-label="${label}" placeholder="选项内容" />`;
      wrap.insertBefore(div, $("#qf-add-opt"));
    };
  } else if (type === "truefalse") {
    wrap.innerHTML = `<div class="small text-2">判断题：在"答案"中填「正确」或「错误」</div>`;
  } else if (type === "blank") {
    wrap.innerHTML = `<div class="small text-2">填空题：题干中用 ____ 表示空位；多个答案用逗号分隔；同一空的等价答案用 | 分隔</div>`;
  } else {
    wrap.innerHTML = `<div class="small text-2">主观题：在"答案"中填写参考答案 / 评分要点</div>`;
  }
}

window.addQuestionManually = (bankId) => {
  showModal(`<h3 style="margin-top:0">手动添加题目</h3>
    ${questionFormHTML()}
    <div class="row mt-16" style="justify-content:flex-end">
      <button class="btn btn-outline" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" id="qf-save">保存题目</button>
    </div>`);
  renderQfOptions();
  $("#qf-type").onchange = () => renderQfOptions();
  $("#qf-save").onclick = async () => {
    const payload = collectQuestionForm();
    if (!payload) return;
    try {
      await API.post(`/api/banks/${bankId}/questions`, payload);
      closeModal(); toast("题目已添加", "success"); router();
    } catch (e) { toast(e.message, "error"); }
  };
};

window.editQuestion = async (qid) => {
  const q = await API.get(`/api/questions/${qid}`);
  showModal(`<h3 style="margin-top:0">编辑题目</h3>
    ${questionFormHTML(q)}
    <div class="row mt-16" style="justify-content:flex-end">
      <button class="btn btn-outline" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" id="qf-save">保存修改</button>
    </div>`);
  renderQfOptions(q);
  $("#qf-type").onchange = () => renderQfOptions(q);
  $("#qf-save").onclick = async () => {
    const payload = collectQuestionForm();
    if (!payload) return;
    try {
      await API.put(`/api/questions/${qid}`, payload);
      closeModal(); toast("已保存", "success"); router();
    } catch (e) { toast(e.message, "error"); }
  };
};

function collectQuestionForm() {
  const qtype = $("#qf-type").value;
  const stem = $("#qf-stem").value.trim();
  if (!stem) { toast("请填写题干", "error"); return null; }
  const options = [];
  if (qtype === "single" || qtype === "multiple") {
    $$(".qf-opt").forEach((inp) => {
      if (inp.value.trim()) options.push({ label: inp.dataset.label, content: inp.value.trim(), is_correct: false });
    });
    if (options.length < 2) { toast("至少需要 2 个选项", "error"); return null; }
  }
  let answer = $("#qf-answer").value.trim();
  if (qtype === "multiple") answer = answer.split(/[,，、\s]+/).filter(Boolean).map((s) => s.toUpperCase());
  else if (qtype === "truefalse") answer = ["正确", "对", "true", "1", "√"].includes(answer.toLowerCase()) || answer === "正确";
  else if (qtype === "blank") answer = answer.split(/[,，;；]+/).map((s) => s.trim()).filter(Boolean);
  return {
    qtype, stem, options, answer,
    explanation: $("#qf-exp").value,
    difficulty: +$("#qf-diff").value,
    knowledge_points: $("#qf-kp").value.split(/[,，、]+/).map((s) => s.trim()).filter(Boolean),
    raw_text: stem,
    review_status: "confirmed",
  };
}

window.deleteQuestion = (id, bankId) => confirmDialog("确定删除这道题吗？", async () => {
  await API.del(`/api/questions/${id}`); toast("已删除", "success"); router();
});

/* ---- 智能导入 ---- */
async function viewImport(el, params) {
  const bankIdParam = params[0] || new URLSearchParams(location.hash.split("?")[1] || "").get("bank") || "";
  const banks = await API.get("/api/banks?scope=mine");
  el.innerHTML = `
    <div class="grid grid-2">
      <div class="card" id="imp-input-card">
        <h3 class="card-title">📥 输入题目</h3>
        <label>目标题库 *<select id="imp-bank">
          <option value="">请选择题库</option>
          ${banks.map((b) => `<option value="${b.id}" ${String(b.id) === String(bankIdParam) ? "selected" : ""}>${esc(b.name)}（${b.question_count} 题）</option>`).join("")}
        </select></label>
        <div class="panel-tabs mt-8">
          <button class="panel-tab active" data-mode="text">粘贴文本</button>
          <button class="panel-tab" data-mode="file">上传文件</button>
        </div>
        <div id="imp-text-wrap">
          <label>原始文本（支持几十上百道题）
            <textarea id="imp-text" style="min-height:300px" placeholder="1. 题目内容？&#10;A. 选项A&#10;B. 选项B&#10;C. 选项C&#10;D. 选项D&#10;答案：B&#10;&#10;2. 下一题…"></textarea>
          </label>
        </div>
        <div id="imp-file-wrap" class="hidden">
          <div class="drop-zone" id="imp-dropzone">
            <div class="drop-ico">📄</div>
            <p class="strong" style="margin:6px 0 2px">拖拽文件到此处，或点击选择文件</p>
            <p class="small text-3" style="margin:0">支持 TXT / CSV / Excel(.xlsx) / Word(.docx) / PDF</p>
            <input type="file" id="imp-file" accept=".txt,.csv,.xlsx,.docx,.pdf" hidden />
            <div id="imp-file-name" class="small mt-8"></div>
          </div>
          <p class="small text-3">Excel/CSV 支持列：题干、A/B/C/D、答案、解析、题型。扫描版 PDF 需先 OCR。</p>
        </div>
        <label class="mt-8 row" style="flex-direction:row;align-items:center;gap:8px">
          <input type="checkbox" id="imp-use-ai" style="width:auto" />
          <span class="small">格式混乱时使用 AI 辅助整理（未配置 API Key 时自动跳过）</span>
        </label>
        <button class="btn btn-primary btn-lg mt-8 full" id="imp-parse">🔍 开始识别</button>
      </div>
      <div class="card">
        <div class="row-between">
          <h3 class="card-title" style="margin:0">📋 识别结果</h3>
          <div class="row" id="imp-stats"></div>
        </div>
        <div id="imp-result" class="mt-16">
          <div class="empty-state"><div class="empty-icon">🔍</div><p>粘贴文本或上传文件后点击「开始识别」</p>
            <p class="small text-3">系统会自动拆分题目、识别题型、提取答案与解析</p></div>
        </div>
      </div>
    </div>`;

  $$(".panel-tab").forEach((t) => t.onclick = () => {
    $$(".panel-tab").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $("#imp-text-wrap").classList.toggle("hidden", t.dataset.mode !== "text");
    $("#imp-file-wrap").classList.toggle("hidden", t.dataset.mode !== "file");
  });

  /* 文件拖拽 / 点击选择 */
  const dropzone = $("#imp-dropzone");
  const fileInput = $("#imp-file");
  const fileNameEl = $("#imp-file-name");
  const showFileName = () => {
    const f = fileInput.files[0];
    fileNameEl.innerHTML = f
      ? `<span class="badge badge-success">已选择</span> <span class="strong">${esc(f.name)}</span> <span class="text-3">(${(f.size / 1024).toFixed(1)} KB)</span>`
      : "";
  };
  dropzone.onclick = () => fileInput.click();
  fileInput.onchange = showFileName;
  ["dragenter", "dragover"].forEach((ev) => dropzone.addEventListener(ev, (e) => {
    e.preventDefault(); e.stopPropagation();
    dropzone.classList.add("dragover");
  }));
  ["dragleave", "drop"].forEach((ev) => dropzone.addEventListener(ev, (e) => {
    e.preventDefault(); e.stopPropagation();
    dropzone.classList.remove("dragover");
  }));
  dropzone.addEventListener("drop", (e) => {
    const f = e.dataTransfer?.files?.[0];
    if (!f) return;
    const dt = new DataTransfer();
    dt.items.add(f);
    fileInput.files = dt.files;
    showFileName();
  });

  /* 整卡拖拽：拖到输入卡片任意位置自动切到上传模式 */
  const inputCard = $("#imp-input-card");
  const switchToFileTab = () => {
    $$(".panel-tab").forEach((x) => x.classList.toggle("active", x.dataset.mode === "file"));
    $("#imp-text-wrap").classList.add("hidden");
    $("#imp-file-wrap").classList.remove("hidden");
  };
  inputCard.addEventListener("dragover", (e) => {
    if (e.dataTransfer?.types?.includes("Files")) { e.preventDefault(); switchToFileTab(); }
  });
  inputCard.addEventListener("drop", (e) => {
    if (!e.dataTransfer?.files?.length) return;
    e.preventDefault(); e.stopPropagation();
    switchToFileTab();
    const dt = new DataTransfer();
    dt.items.add(e.dataTransfer.files[0]);
    fileInput.files = dt.files;
    showFileName();
  });

  $("#imp-parse").onclick = async () => {
    const bankId = +$("#imp-bank").value;
    if (!bankId) return toast("请先选择目标题库", "error");
    const useAi = $("#imp-use-ai").checked;
    const btn = $("#imp-parse");
    btn.disabled = true; btn.textContent = "识别中…";
    try {
      let data;
      const fileMode = !$("#imp-file-wrap").classList.contains("hidden");
      if (fileMode) {
        const file = $("#imp-file").files[0];
        if (!file) return toast("请选择文件", "error");
        const fd = new FormData();
        fd.append("file", file);
        data = await API.upload(`/api/import/file?bank_id=${bankId}&use_ai=${useAi}`, fd);
      } else {
        const text = $("#imp-text").value;
        if (!text.trim()) return toast("请粘贴题目文本", "error");
        data = await API.post("/api/import/parse", { raw_text: text, bank_id: bankId, use_ai: useAi });
      }
      renderImportResult(data, bankId);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      btn.disabled = false; btn.textContent = "🔍 开始识别";
    }
  };
}

function renderImportResult(data, bankId) {
  $("#imp-stats").innerHTML = `
    <span class="badge badge-primary">共 ${data.total}</span>
    <span class="badge badge-success">识别 ${data.recognized}</span>
    <span class="badge badge-warning">待确认 ${data.need_review}</span>
    <span class="badge">重复 ${data.duplicate}</span>
    <span class="badge badge-danger">失败 ${data.failed}</span>
    ${data.used_ai ? '<span class="badge badge-info">已用 AI</span>' : ""}
    ${data.ai_placeholder ? '<span class="badge badge-warning">AI 未配置</span>' : ""}`;

  const items = data.questions.map((q, idx) => `
    <div class="parse-item status-${q.status}" data-idx="${idx}">
      <div class="parse-head">
        <span class="strong">#${q.index}</span>
        <span class="badge badge-primary">${typeName(q.qtype)}</span>
        <span class="badge ${q.status === "ok" ? "badge-success" : q.status === "duplicate" ? "" : q.status === "failed" ? "badge-danger" : "badge-warning"}">
          ${q.status === "ok" ? "识别成功" : q.status === "need_review" ? "需人工确认" : q.status === "duplicate" ? "疑似重复" : "识别失败"}
        </span>
        <span class="small text-3">置信度 ${(q.confidence * 100).toFixed(0)}%</span>
        <div class="spacer"></div>
        <button class="btn btn-ghost btn-sm" onclick="editParsedQuestion(${idx})">编辑</button>
      </div>
      <div class="mt-8" style="font-weight:550">${esc(q.stem)}</div>
      ${(q.options || []).length ? `<div class="small text-2 mt-8">${q.options.map((o) => `${o.label}. ${esc(o.content)}`).join("　")}</div>` : ""}
      <div class="small mt-8"><span class="text-3">答案：</span><span class="strong">${esc(JSON.stringify(q.answer))}</span>
        ${q.explanation ? `<span class="text-3">　解析：</span><span class="text-2">${esc(q.explanation.slice(0, 80))}</span>` : ""}</div>
      ${q.uncertain_fields?.length ? `<div class="small text-3 mt-8">不确定字段：${q.uncertain_fields.join("、")}</div>` : ""}
      ${q.error ? `<div class="small" style="color:var(--danger)">${esc(q.error)}</div>` : ""}
    </div>`).join("");

  $("#imp-result").innerHTML = `
    <div class="row-between mb-8">
      <div class="row">
        <label class="row" style="flex-direction:row;gap:6px;align-items:center">
          <input type="checkbox" id="imp-skip-dup" checked style="width:auto" /><span class="small">跳过重复</span></label>
        <label class="row" style="flex-direction:row;gap:6px;align-items:center">
          <input type="checkbox" id="imp-inc-unknown" style="width:auto" /><span class="small">包含未识别题型</span></label>
      </div>
      <div class="row">
        <button class="btn btn-outline btn-sm" id="imp-edit-all">逐题检查</button>
        <button class="btn btn-success" id="imp-confirm">✅ 确认导入</button>
      </div>
    </div>
    <div style="max-height:520px;overflow-y:auto">${items}</div>`;

  window._parsedQuestions = data.questions;
  window._importBankId = bankId;
  window._importTaskId = data.task_id;

  $("#imp-confirm").onclick = async () => {
    const skipDup = $("#imp-skip-dup").checked;
    const incUnknown = $("#imp-inc-unknown").checked;
    const btn = $("#imp-confirm");
    btn.disabled = true; btn.textContent = "导入中…";
    try {
      const r = await API.post("/api/import/confirm", {
        task_id: window._importTaskId,
        bank_id: bankId,
        questions: window._parsedQuestions,
        skip_duplicates: skipDup,
        include_unknown: incUnknown,
      });
      toast(`导入完成：成功 ${r.imported} 题，跳过重复 ${r.skipped_duplicate}，无效 ${r.skipped_invalid}`, "success");
      location.hash = `#/bank/${bankId}`;
      router();
    } catch (e) {
      toast(e.message, "error");
      btn.disabled = false; btn.textContent = "✅ 确认导入";
    }
  };
}

window.editParsedQuestion = (idx) => {
  const q = window._parsedQuestions[idx];
  showModal(`<h3 style="margin-top:0">编辑识别结果 #${q.index}</h3>
    <label>题型<select id="ep-type">
      ${["single", "multiple", "truefalse", "blank", "shortanswer", "calculation", "unknown"]
        .map((t) => `<option value="${t}" ${q.qtype === t ? "selected" : ""}>${typeName(t)}</option>`).join("")}
    </select></label>
    <label class="mt-8">题干<textarea id="ep-stem">${esc(q.stem)}</textarea></label>
    <label class="mt-8">选项（每行一个，格式：A. 内容）<textarea id="ep-opts" style="min-height:100px">${esc((q.options || []).map((o) => `${o.label}. ${o.content}`).join("\n"))}</textarea></label>
    <label class="mt-8">答案<input id="ep-ans" value="${esc(Array.isArray(q.answer) ? q.answer.join(",") : String(q.answer ?? ""))}" /></label>
    <label class="mt-8">解析<textarea id="ep-exp">${esc(q.explanation)}</textarea></label>
    <div class="row mt-16" style="justify-content:flex-end">
      <button class="btn btn-outline" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" id="ep-save">保存</button>
    </div>`);
  $("#ep-save").onclick = () => {
    q.qtype = $("#ep-type").value;
    q.stem = $("#ep-stem").value.trim();
    q.options = $("#ep-opts").value.split("\n").map((l) => {
      const m = l.match(/^\s*([A-Ha-h1-8])\s*[.、．)）:：]\s*(.+)$/);
      return m ? { label: m[1].toUpperCase(), content: m[2].trim(), is_correct: false } : null;
    }).filter(Boolean);
    const ansRaw = $("#ep-ans").value.trim();
    q.answer = q.qtype === "multiple" ? ansRaw.split(/[,，、\s]+/).filter(Boolean).map((s) => s.toUpperCase())
      : q.qtype === "blank" ? ansRaw.split(/[,，;；]+/).map((s) => s.trim()).filter(Boolean)
      : q.qtype === "truefalse" ? ["正确", "对", "true", "1"].includes(ansRaw.toLowerCase())
      : ansRaw;
    q.explanation = $("#ep-exp").value;
    q.status = q.stem && q.answer !== "" && q.answer !== null && (!Array.isArray(q.answer) || q.answer.length) ? "ok" : "need_review";
    closeModal();
    renderImportResult({
      total: window._parsedQuestions.length,
      recognized: window._parsedQuestions.filter((x) => x.status === "ok").length,
      need_review: window._parsedQuestions.filter((x) => x.status === "need_review").length,
      duplicate: window._parsedQuestions.filter((x) => x.status === "duplicate").length,
      failed: window._parsedQuestions.filter((x) => x.status === "failed").length,
      questions: window._parsedQuestions,
      task_id: window._importTaskId,
    }, window._importBankId);
    toast("已更新", "success");
  };
};

/* ---- 刷题设置 ---- */
async function viewPracticeSetup(el) {
  const [banks, wrong, favs] = await Promise.all([
    API.get("/api/banks?scope=all"),
    API.get("/api/practice/wrong?limit=1"),
    API.get("/api/practice/favorites"),
  ]);
  el.innerHTML = `
    <div class="card">
      <h3 class="card-title">✍️ 选择练习模式</h3>
      <div class="grid grid-4">
        ${[
          ["sequential", "📖", "顺序练习", "从头按题库顺序做题（需手动选择）"],
          ["random", "🎲", "随机练习", "随机抽取指定数量题目"],
          ["chapter", "📑", "章节练习", "按章节/知识点专项突破"],
          ["specialized", "🎯", "专项练习", "只练某种题型"],
          ["wrong_retry", "📕", "错题重练", `错题本 ${wrong.total || 0} 题`],
          ["favorite", "⭐", "收藏练习", `已收藏 ${favs.total || 0} 题`],
          ["exam", "📝", "模拟考试", "限时考试 · 交卷出分"],
        ].map(([mode, ico, name, desc]) => `
          <div class="card mode-card" data-mode="${mode}" style="cursor:pointer;text-align:center">
            <div style="font-size:30px">${ico}</div>
            <div class="strong mt-8">${name}</div>
            <div class="small text-3">${desc}</div>
          </div>`).join("")}
      </div>
    </div>
    <div class="card mt-16" id="practice-config">
      <h3 class="card-title">⚙️ 练习配置</h3>
      <div class="form-inline">
        <label>选择题库 *<select id="pc-bank">
          <option value="">请选择</option>
          ${banks.map((b) => `<option value="${b.id}">${esc(b.name)}（${b.question_count} 题）</option>`).join("")}
        </select></label>
        <label>题目数量<input id="pc-count" type="number" value="10" min="1" max="200" /></label>
        <label>选题策略<select id="pc-selection">
          <option value="smart" selected>智能优先（未做 → 错题 → 已掌握）</option>
          <option value="from_start">从头开始（按题库原始顺序）</option>
        </select></label>
        <label>提交后显示答案<select id="pc-show">
          <option value="immediate">立即显示</option>
          <option value="after_submit">练习结束后显示</option>
        </select></label>
      </div>
      <div class="form-inline mt-8">
        <label>限定章节（章节练习用）<select id="pc-chapter"><option value="">不限</option></select></label>
        <label>限定题型（专项/筛选）<select id="pc-qtype"><option value="">全部</option>
          <option value="single">单选</option><option value="multiple">多选</option>
          <option value="truefalse">判断</option><option value="blank">填空</option>
          <option value="shortanswer">简答</option><option value="calculation">计算</option>
        </select></label>
      </div>
      <button class="btn btn-primary btn-lg mt-16" id="pc-start">🚀 开始练习</button>
    </div>`;

  let mode = "sequential";
  const selEl = $("#pc-selection");
  $$(".mode-card").forEach((c) => c.onclick = () => {
    $$(".mode-card").forEach((x) => x.style.borderColor = "var(--border)");
    c.style.borderColor = "var(--primary)";
    mode = c.dataset.mode;
    // 「顺序练习」= 从头开始（显式选择）；其余模式默认智能优先
    if (selEl) selEl.value = (mode === "sequential") ? "from_start" : "smart";
    if (mode === "exam") { location.hash = "#/exam"; return; }
  });

  $("#pc-bank").onchange = async (e) => {
    const bid = e.target.value;
    const sel = $("#pc-chapter");
    sel.innerHTML = `<option value="">不限</option>`;
    if (bid) {
      const chs = await API.get(`/api/banks/${bid}/chapters`);
      chs.forEach((c) => sel.insertAdjacentHTML("beforeend", `<option value="${c.id}">${esc(c.name)}</option>`));
    }
  };
  $("#pc-start").onclick = () => {
    const bankId = +$("#pc-bank").value;
    if (!bankId) return toast("请选择题库", "error");
    startPractice(bankId, mode, {
      count: +$("#pc-count").value || 10,
      qtype: $("#pc-qtype").value,
      chapterId: $("#pc-chapter").value ? +$("#pc-chapter").value : null,
      show: $("#pc-show").value,
      selection: $("#pc-selection") ? $("#pc-selection").value : "smart",
    });
  };
}

window.startPractice = async (bankId, mode, opts = {}) => {
  try {
    const payload = {
      bank_id: bankId,
      mode,
      count: opts.count || 10,
      show_answer_mode: opts.show || "immediate",
      qtypes: opts.qtype ? [opts.qtype] : [],
      chapter_id: opts.chapterId || null,
      // 默认智能优先（未做/错题）；从头开始需用户主动选择 from_start
      selection: opts.selection || "smart",
    };
    const s = await API.post("/api/practice/sessions", payload);
    location.hash = `#/quiz/${s.id}`;
    if (parseHash().name === "quiz") router();
  } catch (e) { toast(e.message, "error"); }
};

/* ---- 刷题页 ---- */
async function viewQuiz(el, params) {
  const sessionId = params[0];
  const data = await API.get(`/api/practice/sessions/${sessionId}/questions`);
  const session = data.session;
  const questions = data.questions;
  if (!questions.length) {
    el.innerHTML = `<div class="empty-state"><div class="empty-icon">😶</div><p>试卷为空</p>
      <a class="btn btn-primary" href="#/practice">返回</a></div>`;
    return;
  }
  let idx = 0;
  const answers = {};
  Object.assign(answers, session.answers_map || {});
  const marked = new Set();
  let startTime = Date.now();
  let submitted = session.status === "submitted";

  el.innerHTML = `
    <div class="row-between mb-8">
      <div class="row">
        <a class="btn btn-ghost btn-sm" href="#/practice">← 返回</a>
        <h3 style="margin:0">${esc(session.bank_name)}</h3>
        <span class="badge badge-primary">${modeName(session.mode)}</span>
        <span class="badge">进度 <span id="quiz-progress">1</span>/${questions.length}</span>
      </div>
      <div class="row">
        <div class="timer" id="quiz-timer">00:00</div>
        <button class="btn btn-outline btn-sm" id="quiz-ai-btn">🤖 AI 助教</button>
        <button class="btn btn-outline btn-sm" id="quiz-card-btn">📋 答题卡</button>
        <button class="btn btn-primary btn-sm" id="quiz-submit-btn">提交练习</button>
      </div>
    </div>
    <div class="progress mb-8"><div class="progress-bar" id="quiz-bar" style="width:5%"></div></div>
    <div class="grid" style="grid-template-columns: 1fr 280px">
      <div class="card" id="quiz-main"></div>
      <div>
        <div class="card">
          <h3 class="card-title" style="margin-bottom:8px">📋 答题卡</h3>
          <div class="answer-card-grid" id="answer-card"></div>
          <div class="small text-3 mt-8">
            <span class="badge badge-primary">已答</span> <span class="badge">未答</span> <span class="badge" style="box-shadow:inset 0 -3px 0 var(--warning)">标记</span>
          </div>
        </div>
        <div class="card mt-8">
          <h3 class="card-title" style="margin-bottom:8px">题目操作</h3>
          <button class="btn btn-outline full mt-8" id="quiz-mark">⭐ 标记本题</button>
          <button class="btn btn-outline full mt-8" id="quiz-fav">📌 收藏本题</button>
          <button class="btn btn-outline full mt-8" id="quiz-hint">💡 AI 提示（不给答案）</button>
          <button class="btn btn-outline full mt-8" id="quiz-explain">🔍 AI 解析</button>
        </div>
      </div>
    </div>`;

  const timerEl = $("#quiz-timer");
  const tick = () => {
    if (submitted) return;
    const secs = Math.floor((Date.now() - startTime) / 1000);
    const mm = String(Math.floor(secs / 60)).padStart(2, "0");
    const ss = String(secs % 60).padStart(2, "0");
    timerEl.textContent = `${mm}:${ss}`;
  };
  const timerId = setInterval(tick, 1000);

  function renderCard() {
    $("#answer-card").innerHTML = questions.map((q, i) => {
      const cls = [i === idx ? "current" : "", answers[q.id] != null && answers[q.id] !== "" ? "answered" : "",
        marked.has(q.id) ? "marked" : ""].join(" ");
      return `<div class="answer-card-item ${cls}" onclick="window._quizGo(${i})">${i + 1}</div>`;
    }).join("");
    $("#quiz-progress").textContent = idx + 1;
    $("#quiz-bar").style.width = `${((idx + 1) / questions.length) * 100}%`;
  }

  function renderQuestion() {
    const q = questions[idx];
    const ans = answers[q.id];
    let body = `
      <div class="q-meta">
        <span class="badge badge-primary">${typeName(q.qtype)}</span>
        <span class="badge">${"⭐".repeat(q.difficulty || 2)}</span>
        ${(q.knowledge_points || []).map((k) => `<span class="badge badge-info">${esc(k)}</span>`).join("")}
      </div>
      <div class="q-stem">${idx + 1}. ${esc(q.stem)}</div>`;

    if (q.qtype === "single" || q.qtype === "multiple") {
      body += (q.options || []).map((o) => {
        const selected = q.qtype === "single" ? ans === o.label : (Array.isArray(ans) && ans.includes(o.label));
        return `<div class="option-item ${selected ? "selected" : ""}" data-label="${o.label}">
          <div class="option-label">${o.label}</div>
          <div class="option-text">${esc(o.content)}</div>
        </div>`;
      }).join("");
    } else if (q.qtype === "truefalse") {
      body += [["true", "✅ 正确"], ["false", "❌ 错误"]].map(([v, n]) => `
        <div class="option-item ${(ans === v || ans === (v === "true")) ? "selected" : ""}" data-tf="${v}">
          <div class="option-label">${v === "true" ? "✓" : "✗"}</div>
          <div class="option-text">${n}</div>
        </div>`).join("");
    } else if (q.qtype === "blank") {
      body += `<label>你的答案（多个空用逗号分隔）
        <textarea id="quiz-blank-input" placeholder="填入答案…">${esc(Array.isArray(ans) ? ans.join(",") : ans || "")}</textarea></label>
        <button class="btn btn-primary mt-8" id="quiz-blank-save">保存答案</button>`;
    } else {
      body += `<label>你的作答
        <textarea id="quiz-text-input" style="min-height:120px" placeholder="输入你的答案…">${esc(ans || "")}</textarea></label>
        <button class="btn btn-primary mt-8" id="quiz-text-save">保存答案</button>`;
    }

    if (submitted || (session.show_answer_mode === "immediate" && answers[q.id + "_result"])) {
      const r = answers[q.id + "_result"];
      if (r) body += `
        <div class="card mt-16" style="background:${r.is_correct ? "var(--success-soft)" : "var(--danger-soft)"}">
          <div class="row-between">
            <strong>${r.is_correct ? "✅ 回答正确" : r.is_correct === false ? "❌ 回答错误" : "⏳ 待评分"}</strong>
            ${r.ai_graded ? '<span class="badge badge-warning">AI 辅助评分 · 非绝对判定</span>' : ""}
          </div>
          <div class="mt-8 small">标准答案：<strong>${esc(JSON.stringify(r.correct_answer))}</strong></div>
          ${r.grade_note ? `<div class="small mt-8 text-2">${esc(r.grade_note)}</div>` : ""}
          ${r.explanation ? `<div class="small mt-8"><strong>解析：</strong>${esc(r.explanation)}</div>` : ""}
        </div>`;
    }

    body += `<div class="row mt-16">
      <button class="btn btn-outline" id="quiz-prev" ${idx === 0 ? "disabled" : ""}>← 上一题</button>
      <div class="spacer"></div>
      <button class="btn btn-outline" id="quiz-next" ${idx === questions.length - 1 ? "disabled" : ""}>下一题 →</button>
      <button class="btn btn-primary" id="quiz-answer-btn">提交本题答案</button>
    </div>`;

    $("#quiz-main").innerHTML = body;

    // 事件绑定
    $$("#quiz-main .option-item[data-label]").forEach((opt) => opt.onclick = () => {
      const label = opt.dataset.label;
      if (q.qtype === "single") {
        answers[q.id] = label;
      } else {
        const cur = Array.isArray(answers[q.id]) ? [...answers[q.id]] : [];
        const i = cur.indexOf(label);
        if (i >= 0) cur.splice(i, 1); else cur.push(label);
        answers[q.id] = cur.sort();
      }
      renderQuestion(); renderCard();
    });
    $$("#quiz-main .option-item[data-tf]").forEach((opt) => opt.onclick = () => {
      answers[q.id] = opt.dataset.tf;
      renderQuestion(); renderCard();
    });
    $("#quiz-blank-save") && ($("#quiz-blank-save").onclick = () => {
      answers[q.id] = $("#quiz-blank-input").value.split(/[,，;；]+/).map((s) => s.trim()).filter(Boolean);
      renderCard(); toast("答案已保存", "success");
    });
    $("#quiz-text-save") && ($("#quiz-text-save").onclick = () => {
      answers[q.id] = $("#quiz-text-input").value;
      renderCard(); toast("答案已保存", "success");
    });
    $("#quiz-prev").onclick = () => { if (idx > 0) { idx--; renderQuestion(); renderCard(); } };
    $("#quiz-next").onclick = () => { if (idx < questions.length - 1) { idx++; renderQuestion(); renderCard(); } };
    $("#quiz-answer-btn").onclick = () => submitCurrentAnswer(q);
    renderCard();
  }

  async function submitCurrentAnswer(q) {
    const ans = answers[q.id];
    if (ans == null || ans === "" || (Array.isArray(ans) && !ans.length)) return toast("请先作答", "error");
    try {
      const r = await API.post(`/api/practice/sessions/${sessionId}/answer`, {
        question_id: q.id, answer: ans, time_spent: Math.floor((Date.now() - startTime) / 1000),
      });
      if (session.show_answer_mode === "immediate") {
        answers[q.id + "_result"] = r;
        renderQuestion();
      }
      toast(r.is_correct === true ? "✅ 回答正确" : r.is_correct === false ? "❌ 回答错误" : "已提交", r.is_correct ? "success" : "info");
      window.Pet && Pet.react(r.is_correct === true ? "happy" : r.is_correct === false ? "sad" : "info");
    } catch (e) { toast(e.message, "error"); }
  }

  window._quizGo = (i) => { idx = i; renderQuestion(); };

  $("#quiz-card-btn").onclick = () => {
    // 移动端展开答题卡（已常驻桌面侧栏）
    document.querySelector("#answer-card")?.scrollIntoView({ behavior: "smooth" });
  };
  $("#quiz-mark").onclick = () => {
    const qid = questions[idx].id;
    marked.has(qid) ? marked.delete(qid) : marked.add(qid);
    renderCard();
    toast(marked.has(qid) ? "已标记" : "已取消标记");
  };
  $("#quiz-fav").onclick = async () => {
    try {
      await API.post("/api/practice/favorites", { question_id: questions[idx].id });
      toast("已收藏", "success");
    } catch (e) { toast(e.message, "error"); }
  };
  $("#quiz-hint").onclick = () => openAIForQuestion(questions[idx], "hint");
  $("#quiz-explain").onclick = () => openAIForQuestion(questions[idx], "explain");
  $("#quiz-ai-btn").onclick = () => openAIForQuestion(questions[idx], "chat");
  $("#quiz-submit-btn").onclick = () => {
    confirmDialog("确定提交本次练习吗？提交后将显示成绩。", async () => {
      submitted = true;
      clearInterval(timerId);
      try {
        await API.post(`/api/practice/sessions/${sessionId}/submit`, { answers: [] });
        location.hash = `#/result/${sessionId}`;
        router();
      } catch (e) { toast(e.message, "error"); }
    });
  };

  renderQuestion();

  // 快捷键
  el.onkeydown = (e) => {
    if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
    if (e.key === "ArrowLeft" && idx > 0) { idx--; renderQuestion(); }
    if (e.key === "ArrowRight" && idx < questions.length - 1) { idx++; renderQuestion(); }
    if (["1", "2", "3", "4", "5", "6"].includes(e.key)) {
      const q = questions[idx];
      const opt = (q.options || [])[+e.key - 1];
      if (opt && (q.qtype === "single" || q.qtype === "multiple")) {
        if (q.qtype === "single") answers[q.id] = opt.label;
        else {
          const cur = Array.isArray(answers[q.id]) ? [...answers[q.id]] : [];
          const i = cur.indexOf(opt.label);
          if (i >= 0) cur.splice(i, 1); else cur.push(opt.label);
          answers[q.id] = cur.sort();
        }
        renderQuestion();
      }
    }
  };
}

/* ---- AI 抽屉 ---- */
function openAIForQuestion(q, mode) {
  const drawer = $("#ai-drawer");
  drawer.classList.remove("hidden");
  const box = $("#drawer-messages");
  box.innerHTML = `<div class="chat-msg assistant">正在为你准备关于「${esc(q.stem.slice(0, 30))}…」的解答…</div>`;
  window._aiContext = q;

  const run = async () => {
    try {
      if (mode === "hint") {
        const r = await API.post(`/api/ai/hint?question_id=${q.id}`);
        box.innerHTML = `<div class="chat-msg assistant ${r.is_placeholder ? "placeholder" : ""}">${esc(r.content)}</div>`;
      } else if (mode === "explain") {
        const r = await API.post(`/api/ai/explain?question_id=${q.id}`);
        box.innerHTML = `<div class="chat-msg assistant ${r.is_placeholder ? "placeholder" : ""}">${esc(r.content)}</div>`;
      } else {
        box.innerHTML = `<div class="chat-msg assistant">你好！我是本题的 AI 助教，可以问我「为什么 B 是正确的」「举个例子」等问题。</div>`;
      }
    } catch (e) {
      box.innerHTML = `<div class="chat-msg assistant placeholder">AI 服务异常：${esc(e.message)}</div>`;
    }
  };
  run();
}

/* ---- 考试 ---- */
async function viewExamSetup(el) {
  const banks = await API.get("/api/banks?scope=all");
  el.innerHTML = `
    <div class="card">
      <h3 class="card-title">📝 模拟考试设置</h3>
      <p class="text-2">自动生成试卷，考试期间不显示答案，交卷后统一评分与解析。</p>
      <div class="form-inline">
        <label>选择题库 *<select id="ex-bank">
          <option value="">请选择</option>
          ${banks.map((b) => `<option value="${b.id}">${esc(b.name)}（${b.question_count} 题）</option>`).join("")}
        </select></label>
        <label>题目数量<input id="ex-count" type="number" value="20" min="1" max="100" /></label>
        <label>考试时长（分钟）<input id="ex-time" type="number" value="30" min="1" max="240" /></label>
      </div>
      <div class="form-inline mt-8">
        <label>包含题型（可多选）
          <div class="row mt-8">
            ${[["single", "单选"], ["multiple", "多选"], ["truefalse", "判断"], ["blank", "填空"], ["shortanswer", "简答"], ["calculation", "计算"]]
              .map(([v, n]) => `<label class="row" style="flex-direction:row;align-items:center;gap:4px">
                <input type="checkbox" class="ex-type" value="${v}" checked style="width:auto" />${n}</label>`).join("")}
          </div>
        </label>
      </div>
      <button class="btn btn-primary btn-lg mt-16" id="ex-start">🚀 生成试卷并开始考试</button>
    </div>
    <div class="card mt-16">
      <h3 class="card-title">📌 考试须知</h3>
      <ul class="text-2">
        <li>考试过程中不会显示正确答案与解析。</li>
        <li>计时结束后需手动交卷，超时未交卷会自动保存作答。</li>
        <li>交卷后立即出分，错题自动进入错题本。</li>
        <li>支持单选、多选、判断、填空、简答（AI 辅助评分标注）。</li>
      </ul>
    </div>`;
  $("#ex-start").onclick = () => {
    const bankId = +$("#ex-bank").value;
    if (!bankId) return toast("请选择题库", "error");
    const qtypes = $$(".ex-type:checked").map((c) => c.value);
    startPractice(bankId, "exam", {
      count: +$("#ex-count").value || 20,
      show: "after_submit",
      qtype: qtypes.length === 1 ? qtypes[0] : "",
      duration: (+$("#ex-time").value || 30) * 60,
    });
  };
}

async function viewExamRun(el, params) {
  // 复用 quiz 视图
  await viewQuiz(el, params);
}

/* ---- 练习报告 ---- */
async function viewResult(el, params) {
  const data = await API.get(`/api/practice/sessions/${params[0]}/result`);
  const { session, summary, details } = data;
  const typeStats = {};
  details.forEach((d) => {
    const t = typeStats[d.qtype] || { total: 0, correct: 0 };
    t.total++; if (d.is_correct) t.correct++;
    typeStats[d.qtype] = t;
  });

  // 桌宠对成绩的反应
  if (window.Pet) {
    if (summary.accuracy >= 80) { Pet.react("happy"); Pet.say(`考得不错！正确率 ${summary.accuracy}% 🎉`); }
    else if (summary.accuracy < 60) { Pet.react("sad"); Pet.say(`正确率 ${summary.accuracy}%，去错题本巩固一下 💪`); }
    else Pet.say(`正确率 ${summary.accuracy}%，继续加油！`);
  }

  el.innerHTML = `
    <div class="card center" style="background:linear-gradient(135deg,var(--primary-soft),var(--bg-card))">
      <div class="text-2">${esc(session.bank_name)} · ${modeName(session.mode)}</div>
      <div class="stat-value" style="font-size:52px;margin:12px 0">${summary.score ?? 0}<span style="font-size:20px">分</span></div>
      <div class="row" style="justify-content:center">
        <span class="badge badge-success">正确 ${summary.correct}</span>
        <span class="badge badge-danger">错误 ${summary.wrong}</span>
        <span class="badge">已答 ${summary.answered}/${summary.total}</span>
        <span class="badge badge-primary">正确率 ${summary.accuracy}%</span>
      </div>
      <div class="row mt-16" style="justify-content:center">
        <a class="btn btn-outline" href="#/practice">再来一组</a>
        <button class="btn btn-primary" onclick="location.hash='#/wrong'">去错题本复习</button>
      </div>
    </div>

    <div class="card mt-16">
      <h3 class="card-title">📊 题型表现</h3>
      ${barChart(Object.entries(typeStats).map(([t, v]) => ({
        label: typeName(t), value: Math.round(v.correct / v.total * 100),
        color: v.correct / v.total >= 0.8 ? "var(--success)" : v.correct / v.total >= 0.6 ? "var(--warning)" : "var(--danger)",
      })), { height: 180 })}
      <div class="legend">${Object.entries(typeStats).map(([t, v]) => `
        <div class="legend-item"><span class="legend-dot" style="background:var(--primary)"></span>${typeName(t)}：${v.correct}/${v.total}</div>`).join("")}</div>
    </div>

    <div class="card mt-16">
      <h3 class="card-title">📝 答题明细</h3>
      ${details.map((d, i) => `
        <div class="parse-item ${d.is_correct ? "status-ok" : d.is_correct === false ? "status-failed" : ""}" style="margin-bottom:12px">
          <div class="parse-head">
            <span class="strong">#${i + 1}</span>
            <span class="badge badge-primary">${typeName(d.qtype)}</span>
            ${d.is_correct === true ? '<span class="badge badge-success">正确</span>' :
              d.is_correct === false ? '<span class="badge badge-danger">错误</span>' : '<span class="badge badge-warning">待评分</span>'}
            ${d.is_ai_graded ? '<span class="badge badge-warning">AI 辅助评分 · 非绝对判定</span>' : ""}
          </div>
          <div class="mt-8 strong">${esc(d.stem)}</div>
          ${(d.options || []).length ? `<div class="small text-2 mt-8">${d.options.map((o) =>
            `${o.label}. ${esc(o.content)}${o.is_correct ? " ✓" : ""}`).join("　")}</div>` : ""}
          <div class="small mt-8">
            <span class="text-3">你的答案：</span><span class="strong">${esc(JSON.stringify(d.user_answer))}</span>
            <span class="text-3">　标准答案：</span><span class="strong" style="color:var(--success)">${esc(JSON.stringify(d.answer))}</span>
          </div>
          ${d.ai_grade_note ? `<div class="small mt-8 text-2">${esc(d.ai_grade_note)}</div>` : ""}
          ${d.explanation ? `<div class="small mt-8"><span class="text-3">解析：</span>${esc(d.explanation)}</div>` : ""}
        </div>`).join("")}
    </div>`;
}

/* ---- 错题本 ---- */
async function viewWrong(el) {
  const [data, banks] = await Promise.all([
    API.get("/api/practice/wrong?limit=200"),
    API.get("/api/banks?scope=all"),
  ]);
  el.innerHTML = `
    <div class="row mb-8">
      <select id="w-bank" style="max-width:170px"><option value="">全部题库</option>
        ${banks.map((b) => `<option value="${b.id}">${esc(b.name)}</option>`).join("")}</select>
      <select id="w-mastery" style="max-width:140px">
        <option value="">全部掌握度</option>
        <option value="not_mastered">尚未掌握</option><option value="need_review">需要复习</option>
        <option value="basically">基本掌握</option><option value="mastered">已掌握</option>
      </select>
      <select id="w-sort" style="max-width:150px">
        <option value="wrong_count">按错误次数</option>
        <option value="last_wrong_at">按最近出错</option>
        <option value="next_review_at">按复习计划</option>
      </select>
      <div class="spacer"></div>
      <button class="btn btn-outline" id="w-analyze">🤖 AI 错题分析</button>
      <button class="btn btn-primary" id="w-practice">📕 错题重练</button>
    </div>
    <div class="card">
      <div id="w-list"></div>
    </div>
    <div class="card mt-16 hidden" id="w-analysis"></div>`;

  async function load() {
    const qs = new URLSearchParams({ limit: 200 });
    if ($("#w-bank").value) qs.set("bank_id", $("#w-bank").value);
    if ($("#w-mastery").value) qs.set("mastery", $("#w-mastery").value);
    qs.set("sort", $("#w-sort").value);
    const d = await API.get(`/api/practice/wrong?${qs}`);
    $("#w-list").innerHTML = d.total === 0
      ? `<div class="empty-state"><div class="empty-icon">🎉</div><p>太棒了，没有错题！</p></div>`
      : `<div class="table-wrap"><table class="table">
        <thead><tr><th>题干</th><th>题型</th><th>错误次数</th><th>连对</th><th>掌握度</th><th>下次复习</th><th>操作</th></tr></thead>
        <tbody>${d.items.map((w) => `<tr>
          <td><div style="max-width:380px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(w.stem)}</div>
            ${(w.knowledge_points || []).slice(0, 3).map((k) => `<span class="badge">${esc(k)}</span>`).join(" ")}</td>
          <td><span class="badge badge-primary">${typeName(w.qtype)}</span></td>
          <td><strong style="color:var(--danger)">${w.wrong_count}</strong> 次</td>
          <td>${w.streak ? `<strong style="color:var(--success)">${w.streak}</strong> 次` : '<span class="text-2">—</span>'}</td>
          <td>
            <select onchange="updateMastery(${w.id}, this.value)" style="width:auto;padding:4px 8px">
              ${[["not_mastered", "尚未掌握"], ["need_review", "需要复习"], ["basically", "基本掌握"], ["mastered", "已掌握"]]
                .map(([v, n]) => `<option value="${v}" ${w.mastery === v ? "selected" : ""}>${n}</option>`).join("")}
            </select>
          </td>
          <td class="small text-2">${(w.next_review_at || "").slice(0, 10)}</td>
          <td class="actions">
            <button class="btn btn-ghost btn-sm" onclick="showQuestionDetail(${w.question_id})">查看</button>
            <button class="btn btn-ghost btn-sm" onclick="removeWrong(${w.id})">移出</button>
          </td>
        </tr>`).join("")}</tbody></table></div>`;
  }
  ["w-bank", "w-mastery", "w-sort"].forEach((id) => $(`#${id}`).onchange = load);
  $("#w-practice").onclick = () => {
    const bankId = +$("#w-bank").value;
    if (!bankId) return toast("请先选择题库", "error");
    startPractice(bankId, "wrong_retry", { count: 20 });
  };
  $("#w-analyze").onclick = async () => {
    const box = $("#w-analysis");
    box.classList.remove("hidden");
    box.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>AI 正在分析错题…</p></div>`;
    try {
      const r = await API.post(`/api/ai/analyze-wrong${$("#w-bank").value ? `?bank_id=${$("#w-bank").value}` : ""}`);
      box.innerHTML = `<h3 class="card-title">🤖 错题分析 ${r.is_placeholder ? '<span class="badge badge-warning">本地统计 · 非 AI</span>' : '<span class="badge badge-success">AI 生成</span>'}</h3>
        <div style="white-space:pre-wrap;line-height:1.8">${esc(r.content)}</div>`;
    } catch (e) {
      box.innerHTML = `<p style="color:var(--danger)">${esc(e.message)}</p>`;
    }
  };
  await load();
}

window.updateMastery = async (id, mastery) => {
  try {
    await API.put(`/api/practice/wrong/${id}`, { mastery });
    toast("已更新掌握度", "success");
  } catch (e) { toast(e.message, "error"); }
};
window.removeWrong = (id) => confirmDialog("确定将该题移出错题本？", async () => {
  await API.del(`/api/practice/wrong/${id}`); toast("已移出", "success"); router();
});

/* ---- AI 助教 ---- */
async function viewAI(el) {
  const [convs, banks] = await Promise.all([
    API.get("/api/ai/conversations"),
    API.get("/api/banks?scope=all"),
  ]);
  el.innerHTML = `
    <div class="grid" style="grid-template-columns: 250px 1fr">
      <div class="card">
        <div class="row-between"><h3 class="card-title" style="margin:0">对话历史</h3>
          <button class="btn btn-ghost btn-sm" id="ai-new">＋ 新对话</button></div>
        <div class="mt-8" id="ai-convs">
          ${convs.map((c) => `<div class="row-between conv-item" data-id="${c.id}" style="padding:8px;border-radius:8px;cursor:pointer">
            <div class="small" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(c.title)}</div>
            <button class="btn btn-ghost btn-sm" onclick="deleteConv(${c.id})">✕</button>
          </div>`).join("") || `<p class="small text-3">暂无历史对话</p>`}
        </div>
      </div>
      <div class="card chat-page">
        <div class="row-between mb-8">
          <h3 class="card-title" style="margin:0">🤖 AI 学习助教</h3>
          <select id="ai-context-type" style="width:auto">
            <option value="general">通用问答</option>
            <option value="knowledge">指定知识点</option>
          </select>
        </div>
        <div class="form-inline mb-8" id="ai-context-row">
          <input id="ai-knowledge" placeholder="输入知识点（可选）：如 进程与线程" />
          <select id="ai-bank"><option value="">关联题库（可选）</option>
            ${banks.map((b) => `<option value="${b.id}">${esc(b.name)}</option>`).join("")}</select>
        </div>
        <div class="chat-page-body" id="ai-messages"></div>
        <div class="quick-prompts">
          <button class="chip">帮我复习「进程与线程」</button>
          <button class="chip">出 3 道计算机网络基础题考考我</button>
          <button class="chip">用通俗的话解释死锁</button>
        </div>
        <form class="chat-input-row" id="ai-form">
          <input id="ai-input" placeholder="输入你的问题…" autocomplete="off" />
          <button class="btn btn-primary" type="submit">发送</button>
        </form>
      </div>
    </div>`;

  let convId = null;
  const box = $("#ai-messages");

  async function loadConv(id) {
    convId = id;
    const msgs = await API.get(`/api/ai/conversations/${id}/messages`);
    box.innerHTML = msgs.map((m) =>
      `<div class="chat-msg ${m.role} ${m.is_placeholder ? "placeholder" : ""}">${esc(m.content)}</div>`).join("");
    box.scrollTop = box.scrollHeight;
    $$(".conv-item").forEach((c) => c.style.background = +c.dataset.id === id ? "var(--primary-soft)" : "");
  }

  async function send(text) {
    if (!text.trim()) return;
    box.insertAdjacentHTML("beforeend", `<div class="chat-msg user">${esc(text)}</div>`);
    box.insertAdjacentHTML("beforeend", `<div class="chat-msg assistant" id="ai-pending"><div class="spinner" style="width:18px;height:18px"></div> 正在思考…</div>`);
    box.scrollTop = box.scrollHeight;
    try {
      const ctx = {};
      const kp = $("#ai-knowledge").value.trim();
      const bank = $("#ai-bank").value;
      if (kp) ctx.knowledge_point = kp;
      if (bank) ctx.bank_id = +bank;
      const r = await API.post("/api/ai/chat", {
        message: text,
        conversation_id: convId,
        context_type: $("#ai-context-type").value,
        context_ref: ctx,
      });
      convId = r.conversation_id;
      $("#ai-pending").outerHTML = `<div class="chat-msg assistant ${r.is_placeholder ? "placeholder" : ""}">${esc(r.reply)}</div>`;
      box.scrollTop = box.scrollHeight;
    } catch (e) {
      $("#ai-pending").outerHTML = `<div class="chat-msg assistant placeholder">请求失败：${esc(e.message)}</div>`;
    }
  }

  $("#ai-form").onsubmit = (e) => {
    e.preventDefault();
    const v = $("#ai-input").value;
    $("#ai-input").value = "";
    send(v);
  };
  $$(".quick-prompts .chip").forEach((c) => c.onclick = () => send(c.textContent));
  $("#ai-new").onclick = () => { convId = null; box.innerHTML = `<div class="chat-msg assistant">你好！我是 AI 学习助教，可以问我任何学习问题。</div>`; };
  $$(".conv-item").forEach((c) => c.onclick = (e) => {
    if (e.target.tagName !== "BUTTON") loadConv(+c.dataset.id);
  });
  box.innerHTML = `<div class="chat-msg assistant">你好！我是 AI 学习助教 🤖\n可以问我：概念解释、题目讲解、出题练习、复习规划等。\n\n${store.user?.role !== "admin" ? "提示：AI 功能需管理员在系统设置中配置 API Key。" : ""}</div>`;
}

window.deleteConv = async (id) => {
  await API.del(`/api/ai/conversations/${id}`);
  toast("已删除对话", "success"); router();
};

/* ---- 学习统计 ---- */
async function viewStats(el) {
  const stats = await API.get("/api/stats/summary");
  const trend = (stats.daily_trend || []).map((d) => ({ label: d.date.slice(5), value: d.answered }));
  const accuracyTrend = (stats.daily_trend || []).filter((d) => d.answered > 0)
    .map((d) => ({ label: d.date.slice(5), value: Math.round(d.correct / d.answered * 100) }));
  const typeData = Object.entries(stats.by_type || {}).map(([t, v]) => ({
    label: typeName(t), value: v.answered, color: "var(--primary)",
  }));

  el.innerHTML = `
    <div class="grid grid-4">
      <div class="stat-card"><div class="stat-label">总作答</div><div class="stat-value">${stats.total_answered}</div></div>
      <div class="stat-card"><div class="stat-label">总正确率</div><div class="stat-value">${stats.accuracy}%</div></div>
      <div class="stat-card"><div class="stat-label">错题</div><div class="stat-value" style="color:var(--danger)">${stats.wrong_count}</div></div>
      <div class="stat-card"><div class="stat-label">收藏</div><div class="stat-value">${stats.favorite_count}</div></div>
    </div>
    <div class="grid grid-2 mt-16">
      <div class="card"><h3 class="card-title">📈 每日刷题量</h3>${lineChart(trend)}</div>
      <div class="card"><h3 class="card-title">🎯 每日正确率变化</h3>${lineChart(accuracyTrend, { color: "var(--success)" })}</div>
    </div>
    <div class="grid grid-2 mt-16">
      <div class="card"><h3 class="card-title">📊 题型作答分布</h3>${barChart(typeData)}</div>
      <div class="card">
        <h3 class="card-title">🧠 知识点掌握</h3>
        ${stats.by_knowledge.length ? stats.by_knowledge.slice(0, 8).map((w) => `
          <div style="margin:9px 0">
            <div class="row-between small"><span>${esc(w.knowledge_point)}</span><span class="text-2">${w.accuracy}%</span></div>
            <div class="progress mt-8"><div class="progress-bar" style="width:${w.accuracy}%;background:${w.accuracy < 60 ? "var(--danger)" : w.accuracy < 80 ? "var(--warning)" : "var(--success)"}"></div></div>
          </div>`).join("") : `<div class="empty-state"><p>暂无数据</p></div>`}
      </div>
    </div>
    <div class="card mt-16">
      <h3 class="card-title">📕 错题掌握情况</h3>
      ${barChart(Object.entries(stats.wrong_by_mastery || {}).map(([m, v]) => ({
        label: masteryName(m), value: v,
        color: m === "mastered" ? "var(--success)" : m === "not_mastered" ? "var(--danger)" : "var(--warning)",
      })))}
    </div>`;
}

/* ---- 系统设置 ---- */
async function viewSettings(el) {
  const user = store.user;
  let aiConfig = null;
  if (user.role === "admin") {
    try { aiConfig = await API.get("/api/settings/ai"); } catch { aiConfig = null; }
  }
  el.innerHTML = `
    <div class="grid grid-2">
      <div class="card">
        <h3 class="card-title">👤 个人账户</h3>
        <label>用户名<input value="${esc(user.username)}" disabled /></label>
        <label class="mt-8">昵称<input id="set-nick" value="${esc(user.nickname || "")}" /></label>
        <label class="mt-8">邮箱<input id="set-email" value="${esc(user.email || "")}" /></label>
        <label class="mt-8">新密码（不修改请留空）<input id="set-pwd" type="password" placeholder="••••••" /></label>
        <button class="btn btn-primary mt-16" id="set-save">保存资料</button>
        <p class="small text-3 mt-8">最近登录：${user.last_login_at ? fmtTime(user.last_login_at) : "—"}</p>
      </div>
      <div class="card">
        <h3 class="card-title">🔐 登录记录（已保存到数据库）</h3>
        <div id="login-records"><p class="text-3 small">加载中…</p></div>
      </div>
      <div class="card">
        <h3 class="card-title">🎨 外观</h3>
        <div class="row">
          <button class="btn btn-outline" onclick="document.documentElement.setAttribute('data-theme','light');localStorage.setItem('qb_theme','light');applyTheme()">☀️ 浅色模式</button>
          <button class="btn btn-outline" onclick="document.documentElement.setAttribute('data-theme','dark');localStorage.setItem('qb_theme','dark');applyTheme()">🌙 深色模式</button>
        </div>
        <p class="small text-3 mt-16">主题偏好保存在本地浏览器中。</p>
        ${user.role === "admin" ? `
        <h3 class="card-title mt-16">👥 用户管理</h3>
        <button class="btn btn-outline" id="load-users">加载用户列表</button>
        <div id="user-list" class="mt-8"></div>` : ""}
      </div>
    </div>

    ${user.role === "admin" ? `
    <div class="card mt-16">
      <h3 class="card-title">🤖 AI 服务配置（服务端保存）</h3>
      <p class="text-2 small">支持 OpenAI 兼容接口。未配置 API Key 时 AI 功能返回开发占位内容，不影响刷题。</p>
      <div class="form-inline">
        <label>API 地址<input id="ai-base" value="${esc(aiConfig?.api_base || "https://api.openai.com/v1")}" /></label>
        <label>模型名称<input id="ai-model" value="${esc(aiConfig?.model || "gpt-4o-mini")}" /></label>
      </div>
      <div class="form-inline mt-8">
        <label>API Key ${aiConfig?.api_key_set ? `<span class="small text-3">（已保存 ${esc(aiConfig.api_key_masked)}，留空保持不变）</span>` : ""}
          <input id="ai-key" type="password" placeholder="sk-..." /></label>
        <label>超时（秒）<input id="ai-timeout" type="number" value="${aiConfig?.timeout || 60}" /></label>
        <label>最大输出<input id="ai-tokens" type="number" value="${aiConfig?.max_tokens || 2048}" /></label>
      </div>
      <div class="row mt-16">
        <button class="btn btn-primary" id="ai-save">保存配置</button>
        <button class="btn btn-outline" id="ai-test">🔌 测试连接</button>
      </div>
      <div id="ai-test-result" class="mt-8"></div>
    </div>` : ""}

    <div class="card mt-16">
      <h3 class="card-title">📦 数据说明</h3>
      <ul class="text-2 small">
        <li>数据存储于服务端数据库（默认 SQLite，文件 <code>quiz_platform.db</code>）。</li>
        <li>API Key 安全保存在服务端，不会下发到浏览器。</li>
        <li>题库支持导出：可在题库详情中查看/复制题目原文。</li>
        <li>如需 PostgreSQL：设置环境变量 <code>DATABASE_URL</code> 后重启服务。</li>
      </ul>
    </div>`;

  $("#set-save").onclick = async () => {
    try {
      const payload = { nickname: $("#set-nick").value, email: $("#set-email").value || null };
      if ($("#set-pwd").value) payload.password = $("#set-pwd").value;
      const u = await API.put("/api/auth/me", payload);
      store.user = u;
      showMain();
      toast("资料已保存", "success");
    } catch (e) { toast(e.message, "error"); }
  };

  // 登录记录（数据来自数据库 login_records 表）
  (async () => {
    try {
      const rows = await API.get("/api/auth/login-records?limit=10");
      const box = $("#login-records");
      if (!box) return;
      if (!rows.length) { box.innerHTML = `<p class="text-3 small">暂无登录记录</p>`; return; }
      const evName = { login: "登录", register: "注册", failed: "登录失败" };
      box.innerHTML = `<div class="table-wrap"><table class="table">
        <thead><tr><th>时间</th><th>事件</th><th>IP</th></tr></thead>
        <tbody>${rows.map((r) => `<tr>
          <td class="small">${fmtTime(r.created_at)}</td>
          <td><span class="badge ${r.event === "failed" ? "badge-danger" : "badge-success"}">${evName[r.event] || r.event}</span></td>
          <td class="small text-3">${esc(r.ip || "-")}</td>
        </tr>`).join("")}</tbody></table></div>`;
    } catch {
      const box = $("#login-records");
      if (box) box.innerHTML = `<p class="text-3 small">登录记录加载失败</p>`;
    }
  })();

  $("#load-users") && ($("#load-users").onclick = async () => {
    const users = await API.get("/api/auth/users");
    $("#user-list").innerHTML = `<div class="table-wrap"><table class="table">
      <thead><tr><th>ID</th><th>用户名</th><th>角色</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>${users.map((u) => `<tr>
        <td>${u.id}</td><td>${esc(u.username)}</td>
        <td><span class="badge ${u.role === "admin" ? "badge-primary" : ""}">${u.role}</span></td>
        <td>${u.is_active ? '<span class="badge badge-success">正常</span>' : '<span class="badge badge-danger">禁用</span>'}</td>
        <td class="actions">
          <button class="btn btn-ghost btn-sm" onclick="toggleUser(${u.id})">${u.is_active ? "禁用" : "启用"}</button>
          <button class="btn btn-ghost btn-sm" onclick="setUserRole(${u.id},'${u.role === "admin" ? "user" : "admin"}')">${u.role === "admin" ? "降为用户" : "设为管理员"}</button>
        </td></tr>`).join("")}</tbody></table></div>`;
  });

  $("#ai-save") && ($("#ai-save").onclick = async () => {
    try {
      await API.put("/api/settings/ai", {
        api_base: $("#ai-base").value,
        model: $("#ai-model").value,
        api_key: $("#ai-key").value,
        timeout: +$("#ai-timeout").value || 60,
        max_tokens: +$("#ai-tokens").value || 2048,
      });
      toast("AI 配置已保存（API Key 安全存储在服务端）", "success");
    } catch (e) { toast(e.message, "error"); }
  });

  $("#ai-test") && ($("#ai-test").onclick = async () => {
    const box = $("#ai-test-result");
    box.innerHTML = `<div class="spinner" style="width:20px;height:20px"></div>`;
    try {
      const r = await API.post("/api/settings/ai/test");
      box.innerHTML = `<div class="badge ${r.ok ? "badge-success" : "badge-warning"}">${r.ok ? "连接成功" : "连接失败"}</div>
        <div class="small mt-8 text-2">${esc(r.message)}${r.reply ? " · " + esc(r.reply) : ""}</div>`;
    } catch (e) {
      box.innerHTML = `<div class="badge badge-danger">测试失败</div><div class="small mt-8">${esc(e.message)}</div>`;
    }
  });
}

window.toggleUser = async (id) => {
  try { await API.put(`/api/auth/users/${id}/toggle`); toast("已更新", "success"); $("#load-users").click(); }
  catch (e) { toast(e.message, "error"); }
};
window.setUserRole = async (id, role) => {
  try { await API.put(`/api/auth/users/${id}/role?role=${role}`); toast("已更新", "success"); $("#load-users").click(); }
  catch (e) { toast(e.message, "error"); }
};

/* ================= 工具函数 ================= */
function typeName(t) {
  return { single: "单选题", multiple: "多选题", truefalse: "判断题", blank: "填空题",
    shortanswer: "简答题", calculation: "计算题", unknown: "未识别" }[t] || t || "未知";
}
function modeName(m) {
  return { sequential: "顺序练习", random: "随机练习", chapter: "章节练习", topic: "知识点练习",
    specialized: "专项练习", exam: "模拟考试", wrong_retry: "错题重练", favorite: "收藏练习" }[m] || m;
}
function masteryName(m) {
  return { not_mastered: "尚未掌握", need_review: "需要复习", basically: "基本掌握", mastered: "已掌握" }[m] || m;
}
function fmtTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/* ================= 启动 ================= */
document.addEventListener("DOMContentLoaded", () => {
  applyTheme();
  $("#theme-toggle").onclick = toggleTheme;

  // 认证表单
  $$(".auth-tab").forEach((t) => t.onclick = () => {
    $$(".auth-tab").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $("#login-form").classList.toggle("hidden", t.dataset.tab !== "login");
    $("#register-form").classList.toggle("hidden", t.dataset.tab !== "register");
  });
  $("#login-form").onsubmit = async (e) => {
    e.preventDefault();
    try { await doLogin($("#login-username").value.trim(), $("#login-password").value); }
    catch (err) { toast(err.message, "error"); }
  };
  $("#register-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await doRegister({
        username: $("#reg-username").value.trim(),
        nickname: $("#reg-nickname").value.trim() || undefined,
        email: $("#reg-email").value.trim() || undefined,
        password: $("#reg-password").value,
      });
    } catch (err) { toast(err.message, "error"); }
  };
  $("#logout-btn").onclick = () => {
    store.token = ""; store.user = null;
    showAuth();
    toast("已退出登录");
  };

  // 移动端菜单
  $("#menu-toggle").onclick = () => {
    $("#sidebar").classList.add("open");
    $("#sidebar-mask").classList.add("show");
  };
  $("#sidebar-mask").onclick = () => {
    $("#sidebar").classList.remove("open");
    $("#sidebar-mask").classList.remove("show");
  };
  $$(".nav-item").forEach((a) => a.onclick = () => {
    $("#sidebar").classList.remove("open");
    $("#sidebar-mask").classList.remove("show");
  });

  // AI 抽屉
  $("#close-drawer").onclick = () => $("#ai-drawer").classList.add("hidden");
  $("#drawer-chat-form").onsubmit = async (e) => {
    e.preventDefault();
    const input = $("#drawer-chat-input");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    const box = $("#drawer-messages");
    box.insertAdjacentHTML("beforeend", `<div class="chat-msg user">${esc(text)}</div>`);
    const q = window._aiContext;
    box.insertAdjacentHTML("beforeend", `<div class="chat-msg assistant" id="drawer-pending">思考中…</div>`);
    try {
      const r = await API.post("/api/ai/chat", {
        message: text,
        context_type: q ? "question" : "general",
        context_ref: q ? { question_id: q.id } : {},
      });
      $("#drawer-pending").outerHTML = `<div class="chat-msg assistant ${r.is_placeholder ? "placeholder" : ""}">${esc(r.reply)}</div>`;
    } catch (err) {
      $("#drawer-pending").outerHTML = `<div class="chat-msg assistant placeholder">${esc(err.message)}</div>`;
    }
    box.scrollTop = box.scrollHeight;
  };
  $$("#drawer-messages + * .chip, .quick-prompts .chip").forEach((c) => {
    if (c.closest(".drawer-foot")) {
      c.onclick = () => {
        $("#drawer-chat-input").value = c.dataset.q || c.textContent;
        $("#drawer-chat-form").dispatchEvent(new Event("submit"));
      };
    }
  });

  window.closeModal = closeModal;

  Pet.init();
  window.addEventListener("hashchange", router);
  if (store.token) { router(); } else { showAuth(); }
});
