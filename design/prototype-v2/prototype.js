(() => {
  const page = document.body.dataset.page || "overview";
  const titles = {
    overview: ["设计总览", "AtlasMind 企业知识平台"],
    chat: ["企业知识助手", "年度销售制度有哪些变化？"],
    data: ["企业知识库", "数据接入"],
    graph: ["企业知识库", "知识图谱"],
    rag: ["检索治理", "RAG 策略"],
    runs: ["运营中心", "Agent 运行"],
    approvals: ["运营中心", "高风险审批"],
    evaluations: ["质量中心", "评估与发布门禁"],
    governance: ["系统治理", "权限与审计"],
    states: ["设计规范", "系统状态"],
  };
  const nav = [
    ["chat", "01-chat.html", "message-square", "智能问答", ""],
    ["data", "02-data-sources.html", "database", "数据接入", ""],
    ["graph", "08-knowledge-graph.html", "network", "知识图谱", ""],
    ["rag", "11-rag-strategies.html", "sliders", "RAG 策略", ""],
    ["runs", "13-run-center.html", "activity", "运行中心", ""],
    ["approvals", "15-approval-center.html", "shield", "审批中心", "2"],
    ["evaluations", "17-evaluation-center.html", "flask", "质量评估", ""],
    ["governance", "19-access-audit.html", "lock", "权限与审计", ""],
  ];
  const paths = {
    "message-square": '<path d="M5 5h14v11H9l-4 4V5Z"/><path d="M8 9h8M8 12h5"/>',
    database: '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
    network: '<circle cx="6" cy="7" r="3"/><circle cx="18" cy="7" r="3"/><circle cx="12" cy="18" r="3"/><path d="m8.5 8.5 2 6m5-6-2 6M9 7h6"/>',
    sliders: '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="7" cy="18" r="2"/>',
    activity: '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
    shield: '<path d="M12 3 5 6v5c0 4.6 2.8 8.1 7 10 4.2-1.9 7-5.4 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-4"/>',
    flask: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M8 15h8"/>',
    lock: '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    plus: '<path d="M12 5v14M5 12h14"/>', search: '<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/>',
    file: '<path d="M6 3h8l4 4v14H6Z"/><path d="M14 3v5h4M9 13h6M9 17h6"/>',
    upload: '<path d="M12 16V4m0 0L7 9m5-5 5 5M5 18v3h14v-3"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>', chevron: '<path d="m9 6 6 6-6 6"/>',
    check: '<path d="m5 12 4 4L19 6"/>', alert: '<path d="M12 4 3 20h18L12 4Z"/><path d="M12 9v5m0 3h.01"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  };
  const icon = (name) => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`;
  const current = ["data", "graph", "rag", "runs", "approvals", "evaluations", "governance"].find((key) => page.startsWith(key)) || (page === "chat" ? "chat" : "");
  const content = document.getElementById("page-content")?.innerHTML || "";
  const overlay = document.getElementById("overlay-content")?.innerHTML || "";
  const overlayType = document.body.dataset.overlay;
  const top = titles[current || page] || titles.overview;
  const primary = nav.slice(0, 4).map(([key, href, ico, label, badge]) => `<a href="${href}" class="${current === key ? "active" : ""}">${icon(ico)}<span>${label}</span>${badge ? `<span class="nav-badge">${badge}</span>` : ""}</a>`).join("");
  const ops = nav.slice(4).map(([key, href, ico, label, badge]) => `<a href="${href}" class="${current === key ? "active" : ""}">${icon(ico)}<span>${label}</span>${badge ? `<span class="nav-badge">${badge}</span>` : ""}</a>`).join("");
  document.body.innerHTML = `<div class="prototype">
    <aside class="sidebar">
      <a class="brand" href="00-overview.html"><span class="brand-mark">A</span><span>AtlasMind</span></a>
      <a class="new-chat" href="01-chat.html">${icon("plus")}<span>开启新对话</span><kbd>⌘ K</kbd></a>
      <div class="nav-label">工作台</div><nav class="nav">${primary}</nav>
      <div class="nav-separator"></div><div class="nav-label">运营与治理</div><nav class="nav">${ops}</nav>
      <div class="nav-separator"></div><div class="nav-label history-label">最近对话</div>
      <div class="history"><a class="active" href="01-chat.html">年度销售制度有哪些变化？</a><a href="01-chat.html">梳理客户数据安全规范</a><a href="01-chat.html">项目 Atlas 的交付流程</a><a href="01-chat.html">报销审批需要哪些材料？</a></div>
      <div class="profile"><span class="avatar">Z</span><div><strong>Zoe</strong><span>知识库管理员</span></div></div>
    </aside>
    <main class="main"><header class="topbar"><div><small>${top[0]}</small><h1>${top[1]}</h1></div><div class="top-actions"><span class="knowledge-chip"><span class="dot"></span>企业知识库</span></div></header>${content}</main>
  </div>`;
  if (overlay) {
    document.body.insertAdjacentHTML("beforeend", overlayType === "drawer" ? `<div class="drawer-wrap"><aside class="drawer">${overlay}</aside></div>` : `<div class="overlay"><section class="modal ${document.body.dataset.modalWidth === "wide" ? "wide" : ""}">${overlay}</section></div>`);
  }
  document.querySelectorAll("[data-icon]").forEach((node) => { node.outerHTML = icon(node.getAttribute("data-icon")); });
})();
