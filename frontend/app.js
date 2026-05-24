const state = {
  currentRun: null,
  currentTab: "post",
};

const els = {
  clearRuns: document.querySelector("#clearRuns"),
  logout: document.querySelector("#logout"),
  adminLink: document.querySelector("#adminLink"),
  runList: document.querySelector("#runList"),
  runFlow: document.querySelector("#runFlow"),
  topicInput: document.querySelector("#topicInput"),
  contentInstruction: document.querySelector("#contentInstruction"),
  formatReference: document.querySelector("#formatReference"),
  maxItems: document.querySelector("#maxItems"),
  maxHotspots: document.querySelector("#maxHotspots"),
  contentWords: document.querySelector("#contentWords"),
  imageSize: document.querySelector("#imageSize"),
  imageInstruction: document.querySelector("#imageInstruction"),
  statusPill: document.querySelector("#statusPill"),
  totalItems: document.querySelector("#totalItems"),
  hotspotCount: document.querySelector("#hotspotCount"),
  runId: document.querySelector("#runId"),
  outputView: document.querySelector("#outputView"),
  coverActions: document.querySelector("#coverActions"),
  hotspotView: document.querySelector("#hotspotView"),
  coverView: document.querySelector("#coverView"),
  toast: document.querySelector("#toast"),
  tabs: document.querySelectorAll(".tab"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "请求失败");
  return payload;
}

async function loadMe() {
  const payload = await api("/api/me");
  els.statusPill.textContent = `${payload.user.username} · Ready`;
  els.adminLink.hidden = payload.user.role !== "admin";
}

async function loadRuns() {
  const payload = await api("/api/runs");
  renderRuns(payload.runs || []);
  if (!state.currentRun && payload.runs?.length) {
    await selectRun(payload.runs[0].run_id);
  } else if (!payload.runs?.length) {
    state.currentRun = null;
    renderEmptyState();
  }
}

function renderEmptyState() {
  els.statusPill.textContent = "Ready";
  els.totalItems.textContent = "-";
  els.hotspotCount.textContent = "-";
  els.runId.textContent = "-";
  els.coverActions.hidden = true;
  els.hotspotView.hidden = true;
  els.hotspotView.replaceChildren();
  els.coverView.hidden = true;
  els.outputView.hidden = false;
  els.outputView.textContent = "点击“获取新闻并生成”开始第一轮内容生产。";
}

function renderRuns(runs) {
  els.runList.innerHTML = "";
  if (!runs.length) {
    els.runList.innerHTML = '<div class="run-item"><strong>暂无运行记录</strong><span>生成后会显示在这里</span></div>';
    return;
  }
  for (const run of runs) {
    const button = document.createElement("button");
    button.className = `run-item ${state.currentRun?.run_id === run.run_id ? "active" : ""}`;
    button.type = "button";
    button.innerHTML = `<strong>${escapeHtml(run.run_id)}</strong><span>${escapeHtml(run.target_date || "")} · ${run.research?.hotspots?.length || 0} 条热点</span>`;
    button.addEventListener("click", () => selectRun(run.run_id));
    els.runList.appendChild(button);
  }
}

async function selectRun(runId) {
  state.currentRun = await api(`/api/runs/${encodeURIComponent(runId)}`);
  renderCurrentRun();
  await loadRuns();
}

async function runFlow() {
  els.runFlow.disabled = true;
  els.statusPill.textContent = "正在抓取和生成...";
  try {
    const payload = await api("/api/run", {
      method: "POST",
      body: JSON.stringify({
        topic: els.topicInput.value,
        max_items: Number(els.maxItems.value || 24),
        max_hotspots: Number(els.maxHotspots.value || 6),
        content_words: Number(els.contentWords.value || 700),
        content_instruction: els.contentInstruction.value,
        format_reference: els.formatReference.value,
      }),
    });
    state.currentRun = payload;
    renderCurrentRun();
    await loadRuns();
    showToast("已生成今日小红书热点文案");
  } catch (error) {
    showToast(error.message);
    els.statusPill.textContent = "生成失败";
  } finally {
    els.runFlow.disabled = false;
  }
}

async function clearRuns() {
  await api("/api/runs/clear", { method: "POST", body: "{}" });
  state.currentRun = null;
  renderEmptyState();
  await loadRuns();
  showToast("已删除历史任务记录");
}

async function generateCover(index, button, instructionInput) {
  if (!state.currentRun?.run_id) return;
  if (button) {
    button.disabled = true;
    button.textContent = "正在生成...";
  }
  try {
    state.currentRun = await api(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/cover`, {
      method: "POST",
      body: JSON.stringify({
        index,
        image_size: els.imageSize.value,
        image_instruction: [els.imageInstruction.value, instructionInput?.value || ""].filter(Boolean).join("\n"),
      }),
    });
    state.currentTab = "cover";
    syncTabs();
    renderOutput();
    await loadRuns();
    showToast("这条配图已生成");
  } catch (error) {
    showToast(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "生成这条图片";
    }
  }
}

function renderCurrentRun() {
  const run = state.currentRun;
  if (!run) return;
  els.statusPill.textContent = "已生成";
  els.totalItems.textContent = run.research?.total_items ?? "-";
  els.hotspotCount.textContent = run.research?.hotspots?.length ?? "-";
  els.runId.textContent = run.run_id || "-";
  renderOutput();
}

function renderOutput() {
  const run = state.currentRun;
  if (!run) return;
  const files = run.file_contents || {};
  if (state.currentTab === "cover") {
    renderCover(run, files);
    return;
  }
  if (state.currentTab === "hotspots") {
    renderHotspots(run);
    return;
  }
  if (state.currentTab === "post") {
    renderItemPosts(run, files);
    return;
  }
  els.coverActions.hidden = true;
  els.hotspotView.hidden = true;
  els.hotspotView.replaceChildren();
  els.coverView.hidden = true;
  els.coverView.replaceChildren();
  els.outputView.hidden = false;
  const fallback = {
    post: files["xiaohongshu_post.md"],
    research: files["research_report.md"],
    brief: files["ceo_brief.md"],
    json: JSON.stringify(run, null, 2),
  };
  els.outputView.textContent = fallback[state.currentTab] || "暂无内容";
}

function renderItemPosts(run, files) {
  els.outputView.hidden = true;
  els.coverActions.hidden = true;
  els.coverView.hidden = true;
  els.coverView.replaceChildren();
  els.hotspotView.hidden = false;
  els.hotspotView.replaceChildren();
  const posts = run.item_posts || [];
  if (!posts.length) {
    els.hotspotView.hidden = true;
    els.outputView.hidden = false;
    els.outputView.textContent = files["xiaohongshu_post.md"] || "暂无发布文案。";
    return;
  }
  for (const [index, post] of posts.entries()) {
    els.hotspotView.appendChild(renderPostCard(post, index));
  }
}

function renderPostCard(post, index) {
  const card = document.createElement("div");
  card.className = "hotspot-card";
  const toggle = document.createElement("button");
  toggle.type = "button";
  const title = document.createElement("h3");
  title.textContent = `${index + 1}. ${post.title || "未命名文案"}`;
  const summary = document.createElement("p");
  summary.textContent = post.hook || (post.body || "").slice(0, 90);
  toggle.append(title, summary);
  const detail = document.createElement("div");
  detail.className = "hotspot-detail";
  detail.hidden = index !== 0;
  detail.appendChild(detailBlock("正文", post.body || ""));
  detail.appendChild(detailLine("标签", (post.hashtags || []).join(" ")));
  detail.appendChild(detailLine("发布备注", (post.publish_notes || []).join(" / ")));
  toggle.addEventListener("click", () => {
    detail.hidden = !detail.hidden;
  });
  card.append(toggle, detail);
  return card;
}

function detailBlock(label, value) {
  const wrapper = document.createElement("div");
  const heading = document.createElement("p");
  heading.textContent = `${label}：`;
  const pre = document.createElement("pre");
  pre.textContent = value || "-";
  wrapper.append(heading, pre);
  return wrapper;
}

function renderHotspots(run) {
  els.outputView.hidden = true;
  els.coverActions.hidden = true;
  els.coverView.hidden = true;
  els.coverView.replaceChildren();
  els.hotspotView.hidden = false;
  els.hotspotView.replaceChildren();
  const hotspots = run.research?.hotspots || [];
  if (!hotspots.length) {
    const empty = document.createElement("pre");
    empty.textContent = "当前 run 没有热点条目。";
    els.hotspotView.appendChild(empty);
    return;
  }
  for (const [index, hotspot] of hotspots.entries()) {
    els.hotspotView.appendChild(renderHotspotCard(hotspot, index));
  }
}

function renderHotspotCard(hotspot, index) {
  const card = document.createElement("div");
  card.className = "hotspot-card";
  const toggle = document.createElement("button");
  toggle.type = "button";
  const title = document.createElement("h3");
  title.textContent = `${index + 1}. ${hotspot.title || "未命名热点"}`;
  const summary = document.createElement("p");
  summary.textContent = hotspot.summary || "";
  toggle.append(title, summary);
  const detail = document.createElement("div");
  detail.className = "hotspot-detail";
  detail.hidden = true;
  detail.appendChild(detailLine("为什么重要", hotspot.why_it_matters || ""));
  detail.appendChild(detailLine("标签", (hotspot.tags || []).join(" / ")));
  detail.appendChild(detailLine("来源", `${hotspot.source || "未知"} · ${hotspot.published || "未知时间"}`));
  if (hotspot.url) {
    const link = document.createElement("a");
    link.href = hotspot.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = hotspot.url;
    const line = document.createElement("p");
    line.append("链接：", link);
    detail.appendChild(line);
  }
  toggle.addEventListener("click", () => {
    detail.hidden = !detail.hidden;
  });
  card.append(toggle, detail);
  return card;
}

function detailLine(label, value) {
  const line = document.createElement("p");
  line.textContent = `${label}：${value || "-"}`;
  return line;
}

function renderCover(run, files) {
  els.outputView.hidden = true;
  els.coverActions.hidden = false;
  els.hotspotView.hidden = true;
  els.hotspotView.replaceChildren();
  els.coverView.hidden = false;
  els.coverView.replaceChildren();
  const itemCovers = run.item_covers || [];
  if (!itemCovers.length) {
    const empty = document.createElement("pre");
    empty.textContent = "当前 run 没有可生成配图的正文条目。";
    els.coverView.appendChild(empty);
    return;
  }
  for (const item of itemCovers) {
    els.coverView.appendChild(renderCoverItem(run, item));
  }
}

function renderCoverItem(run, item) {
  const card = document.createElement("div");
  card.className = "cover-item";

  const header = document.createElement("div");
  header.className = "cover-item-header";
  const title = document.createElement("h3");
  title.textContent = `${Number(item.index) + 1}. ${item.title || "未命名热点"}`;
  const button = document.createElement("button");
  button.className = "primary";
  button.type = "button";
  button.textContent = item.asset ? "重新生成" : "生成这条图片";
  const instruction = document.createElement("textarea");
  instruction.className = "wide-textarea";
  instruction.rows = 2;
  instruction.placeholder = "可选：单独给这张图的要求，例如突出机制、不放曲线、白底、只保留标题和标签等";
  button.addEventListener("click", () => generateCover(Number(item.index), button, instruction));
  header.append(title, button);
  card.appendChild(header);
  card.appendChild(instruction);

  if (item.summary) {
    const details = document.createElement("details");
    const label = document.createElement("summary");
    label.textContent = "查看对应正文";
    const summary = document.createElement("p");
    summary.textContent = item.summary;
    details.append(label, summary);
    card.appendChild(details);
  }
  if (item.asset && !item.error) {
    const image = document.createElement("img");
    image.src = `/api/runs/${encodeURIComponent(run.run_id)}/assets/${encodeURIComponent(item.asset)}?ts=${Date.now()}`;
    image.alt = item.title || "正文配图";
    card.appendChild(image);
  }
  const detail = document.createElement("pre");
  detail.textContent = [
    item.error ? `生成状态：${item.error}` : item.asset ? "生成状态：已生成" : "生成状态：尚未生成",
    "",
    "图片 Prompt：",
    item.prompt || "点击按钮后会根据这条正文生成 prompt",
  ].join("\n");
  card.appendChild(detail);
  return card;
}

function setTab(tab) {
  state.currentTab = tab;
  syncTabs();
  renderOutput();
}

function syncTabs() {
  for (const button of els.tabs) {
    button.classList.toggle("active", button.dataset.tab === state.currentTab);
  }
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  setTimeout(() => els.toast.classList.remove("show"), 2200);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

els.runFlow.addEventListener("click", runFlow);
els.clearRuns.addEventListener("click", clearRuns);
els.logout.addEventListener("click", async () => {
  await api("/api/logout", { method: "POST", body: "{}" });
  window.location.href = "/login.html";
});
for (const button of els.tabs) {
  button.addEventListener("click", () => setTab(button.dataset.tab));
}

loadMe().then(loadRuns).catch((error) => {
  if (String(error.message).includes("Unauthorized")) window.location.href = "/login.html";
  else showToast(error.message);
});
