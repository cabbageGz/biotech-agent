const state = {
  currentRun: null,
  currentTab: "post",
};

const els = {
  refreshRuns: document.querySelector("#refreshRuns"),
  clearRuns: document.querySelector("#clearRuns"),
  runList: document.querySelector("#runList"),
  runFlow: document.querySelector("#runFlow"),
  generateCover: document.querySelector("#generateCover"),
  topicInput: document.querySelector("#topicInput"),
  maxItems: document.querySelector("#maxItems"),
  maxHotspots: document.querySelector("#maxHotspots"),
  statusPill: document.querySelector("#statusPill"),
  totalItems: document.querySelector("#totalItems"),
  hotspotCount: document.querySelector("#hotspotCount"),
  runId: document.querySelector("#runId"),
  outputView: document.querySelector("#outputView"),
  coverActions: document.querySelector("#coverActions"),
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

async function generateCover() {
  if (!state.currentRun?.run_id) return;
  els.generateCover.disabled = true;
  els.generateCover.textContent = "正在生成封面...";
  try {
    state.currentRun = await api(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/cover`, {
      method: "POST",
      body: "{}",
    });
    state.currentTab = "cover";
    syncTabs();
    renderOutput();
    await loadRuns();
    showToast("封面图已生成");
  } catch (error) {
    showToast(error.message);
  } finally {
    els.generateCover.disabled = false;
    els.generateCover.textContent = "根据正文生成封面";
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
  els.coverActions.hidden = true;
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

function renderCover(run, files) {
  els.outputView.hidden = true;
  els.coverActions.hidden = false;
  els.coverView.hidden = false;
  els.coverView.replaceChildren();
  const cover = run.cover || {};
  const hasLocal = cover.local_path && !cover.error;
  if (hasLocal) {
    const image = document.createElement("img");
    image.src = `/api/runs/${encodeURIComponent(run.run_id)}/assets/cover.png?ts=${Date.now()}`;
    image.alt = "小红书封面图";
    els.coverView.appendChild(image);
  }
  const detail = document.createElement("pre");
  detail.textContent = [
    cover.error ? `封面生成状态：${cover.error}` : hasLocal ? "封面生成状态：已生成" : "封面生成状态：尚未生成",
    "",
    "封面 Prompt：",
    files["cover_prompt.md"] || cover.prompt || "暂无封面 prompt",
  ].join("\n");
  els.coverView.appendChild(detail);
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
els.refreshRuns.addEventListener("click", loadRuns);
els.clearRuns.addEventListener("click", clearRuns);
els.generateCover.addEventListener("click", generateCover);
for (const button of els.tabs) {
  button.addEventListener("click", () => setTab(button.dataset.tab));
}

loadRuns().catch((error) => showToast(error.message));
