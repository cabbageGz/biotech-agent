const state = {
  currentRun: null,
  currentTab: "post",
  selectedTopicIndices: new Set(),
};

const els = {
  clearRuns: document.querySelector("#clearRuns"),
  logout: document.querySelector("#logout"),
  adminLink: document.querySelector("#adminLink"),
  togglePassword: document.querySelector("#togglePassword"),
  passwordPanel: document.querySelector("#passwordPanel"),
  currentPassword: document.querySelector("#currentPassword"),
  newPassword: document.querySelector("#newPassword"),
  changePassword: document.querySelector("#changePassword"),
  passwordMessage: document.querySelector("#passwordMessage"),
  runList: document.querySelector("#runList"),
  runFlow: document.querySelector("#runFlow"),
  autoPublish: document.querySelector("#autoPublish"),
  topicInput: document.querySelector("#topicInput"),
  contentInstruction: document.querySelector("#contentInstruction"),
  formatReference: document.querySelector("#formatReference"),
  maxItems: document.querySelector("#maxItems"),
  maxHotspots: document.querySelector("#maxHotspots"),
  publishCount: document.querySelector("#publishCount"),
  contentWords: document.querySelector("#contentWords"),
  imageSize: document.querySelector("#imageSize"),
  statusPill: document.querySelector("#statusPill"),
  totalItems: document.querySelector("#totalItems"),
  hotspotCount: document.querySelector("#hotspotCount"),
  runId: document.querySelector("#runId"),
  outputView: document.querySelector("#outputView"),
  coverActions: document.querySelector("#coverActions"),
  writingSettings: document.querySelector("#writingSettings"),
  hotspotView: document.querySelector("#hotspotView"),
  newsView: document.querySelector("#newsView"),
  publishView: document.querySelector("#publishView"),
  coverView: document.querySelector("#coverView"),
  toast: document.querySelector("#toast"),
  runOverlay: document.querySelector("#runOverlay"),
  runOverlayStep: document.querySelector("#runOverlayStep"),
  tabs: document.querySelectorAll(".tab"),
};

const AUTO_STEPS = [
  "CEO 正在确定今天做什么内容...",
  "Research Agent 正在抓取近期新闻...",
  "Topic Agent 正在聚类、打分并选择热点...",
  "Content Agent 正在生成发布文案...",
  "Review Agent 正在核对证据和合规风险...",
  "Review Agent 正在按审核建议修正文案...",
  "Image Agent 正在规划图组和提示词...",
  "万相正在生成封面图和内容卡片...",
  "Publish Agent 正在整理发布预览...",
];
let autoStepTimer = null;

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
  els.writingSettings.hidden = true;
  els.hotspotView.hidden = true;
  els.hotspotView.replaceChildren();
  els.newsView.hidden = true;
  els.newsView.replaceChildren();
  els.publishView.hidden = true;
  els.publishView.replaceChildren();
  els.coverView.hidden = true;
  els.outputView.hidden = false;
  els.outputView.textContent = "点击“获取新闻并排序”开始第一轮选题分析。";
}

function renderRuns(runs) {
  els.runList.innerHTML = "";
  if (!runs.length) {
    els.runList.innerHTML = '<div class="run-item"><strong>暂无运行记录</strong><span>生成后会显示在这里</span></div>';
    return;
  }
  for (const run of runs) {
    const row = document.createElement("div");
    row.className = `run-row ${state.currentRun?.run_id === run.run_id ? "active" : ""}`;
    const button = document.createElement("button");
    button.className = "run-item";
    button.type = "button";
    button.innerHTML = `<strong>${escapeHtml(run.run_id)}</strong><span>${escapeHtml(run.target_date || "")} · ${run.research?.hotspots?.length || 0} 个候选主题</span>`;
    button.addEventListener("click", () => selectRun(run.run_id));
    const remove = document.createElement("button");
    remove.className = "run-delete";
    remove.type = "button";
    remove.textContent = "删除";
    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteRun(run.run_id, remove);
    });
    row.append(button, remove);
    els.runList.appendChild(row);
  }
}

async function selectRun(runId) {
  state.currentRun = await api(`/api/runs/${encodeURIComponent(runId)}`);
  renderCurrentRun();
  await loadRuns();
}

async function deleteRun(runId, button) {
  if (!window.confirm(`确认删除任务记录「${runId}」？`)) return;
  const oldText = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "删除中...";
  }
  try {
    await api(`/api/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
    if (state.currentRun?.run_id === runId) {
      state.currentRun = null;
      renderEmptyState();
    }
    await loadRuns();
    showToast("任务记录已删除");
  } catch (error) {
    showToast(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText || "删除";
    }
  }
}

async function runFlow() {
  els.runFlow.disabled = true;
  els.statusPill.textContent = "正在抓取、聚类和打分...";
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
    state.currentTab = "hotspots";
    syncTabs();
    renderCurrentRun();
    await loadRuns();
    showToast("已完成热点排序，请选择主题生成文案");
  } catch (error) {
    showToast(error.message);
    els.statusPill.textContent = "生成失败";
  } finally {
    els.runFlow.disabled = false;
  }
}

async function autoPublish() {
  setGlobalBusy(true, AUTO_STEPS[0]);
  let stepIndex = 0;
  autoStepTimer = setInterval(() => {
    stepIndex = Math.min(stepIndex + 1, AUTO_STEPS.length - 1);
    setOverlayStep(AUTO_STEPS[stepIndex]);
  }, 3500);
  try {
    const payload = await api("/api/run/auto-publish", {
      method: "POST",
      body: JSON.stringify({
        topic: els.topicInput.value,
        max_items: Number(els.maxItems.value || 24),
        max_hotspots: Number(els.maxHotspots.value || 6),
        publish_count: Number(els.publishCount.value || 3),
        content_words: Number(els.contentWords.value || 700),
        content_instruction: els.contentInstruction.value,
        format_reference: els.formatReference.value,
        image_size: els.imageSize.value,
        max_images_per_post: 5,
      }),
    });
    state.currentRun = payload;
    state.currentTab = "publish";
    syncTabs();
    renderCurrentRun();
    await loadRuns();
    showToast("发布预览已生成，可以检查并下载发布包");
  } catch (error) {
    showToast(error.message);
    els.statusPill.textContent = "一键生成失败";
  } finally {
    clearInterval(autoStepTimer);
    autoStepTimer = null;
    setGlobalBusy(false);
  }
}

function setGlobalBusy(active, message = "") {
  document.body.classList.toggle("is-running", active);
  els.runOverlay.hidden = !active;
  if (message) setOverlayStep(message);
}

function setOverlayStep(message) {
  els.runOverlayStep.textContent = message;
  els.statusPill.textContent = message;
}

async function clearRuns() {
  await api("/api/runs/clear", { method: "POST", body: "{}" });
  state.currentRun = null;
  renderEmptyState();
  await loadRuns();
  showToast("已删除历史任务记录");
}

async function changePassword() {
  els.passwordMessage.textContent = "";
  els.changePassword.disabled = true;
  try {
    await api("/api/me/password", {
      method: "POST",
      body: JSON.stringify({
        current_password: els.currentPassword.value,
        new_password: els.newPassword.value,
      }),
    });
    els.currentPassword.value = "";
    els.newPassword.value = "";
    els.passwordPanel.hidden = true;
    showToast("密码已更新");
  } catch (error) {
    els.passwordMessage.textContent = error.message;
  } finally {
    els.changePassword.disabled = false;
  }
}

async function generateCoverPrompts(index, button, instructionInput) {
  if (!state.currentRun?.run_id) return;
  const oldText = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "正在生成提示词...";
  }
  try {
    state.currentRun = await api(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/cover-prompts`, {
      method: "POST",
      body: JSON.stringify({
        index,
        image_size: els.imageSize.value,
        image_instruction: instructionInput?.value || "",
      }),
    });
    state.currentTab = "cover";
    syncTabs();
    renderOutput();
    await loadRuns();
    showToast("图片提示词已生成，请选择方案生成图片");
  } catch (error) {
    showToast(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText || "生成图片提示词";
    }
  }
}

async function generateCover(index, promptIndex, button) {
  if (!state.currentRun?.run_id) return;
  const oldText = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "正在生成图片...";
  }
  try {
    state.currentRun = await api(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/cover`, {
      method: "POST",
      body: JSON.stringify({
        index,
        prompt_index: promptIndex,
        image_size: els.imageSize.value,
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
      button.textContent = oldText || "用这个生成图片";
    }
  }
}

async function deleteCoverImage(index, asset, button) {
  if (!state.currentRun?.run_id || !asset) return;
  if (!window.confirm("确认删除这张图片？")) return;
  const oldText = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "正在删除...";
  }
  try {
    state.currentRun = await api(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/cover-image/delete`, {
      method: "POST",
      body: JSON.stringify({ index, asset }),
    });
    renderOutput();
    await loadRuns();
    showToast("图片已删除");
  } catch (error) {
    showToast(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText || "删除";
    }
  }
}

async function exportPublish(button) {
  if (!state.currentRun?.run_id) return;
  const oldText = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "正在打包...";
  }
  try {
    state.currentRun = await api(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/publish/export`, {
      method: "POST",
      body: "{}",
    });
    renderPublish(state.currentRun);
    const asset = state.currentRun.publish_package?.export_asset;
    if (asset) {
      window.location.href = `/api/runs/${encodeURIComponent(state.currentRun.run_id)}/assets/${encodeURIComponent(asset)}`;
    }
    showToast("发布包已生成");
  } catch (error) {
    showToast(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText || "下载发布包";
    }
  }
}

async function reorderPublish(order, button) {
  if (!state.currentRun?.run_id) return;
  const oldText = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "保存中...";
  }
  try {
    state.currentRun = await api(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/publish/order`, {
      method: "POST",
      body: JSON.stringify({ order }),
    });
    renderPublish(state.currentRun);
    await loadRuns();
  } catch (error) {
    showToast(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText || "调整顺序";
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
  if (state.currentTab === "news") {
    renderNews(run);
    return;
  }
  if (state.currentTab === "publish") {
    renderPublish(run);
    return;
  }
  if (state.currentTab === "post") {
    renderItemPosts(run, files);
    return;
  }
  if (state.currentTab === "review") {
    renderReview(run);
    return;
  }
  els.coverActions.hidden = true;
  els.writingSettings.hidden = true;
  els.hotspotView.hidden = true;
  els.hotspotView.replaceChildren();
  els.newsView.hidden = true;
  els.newsView.replaceChildren();
  els.publishView.hidden = true;
  els.publishView.replaceChildren();
  els.coverView.hidden = true;
  els.coverView.replaceChildren();
  els.outputView.hidden = false;
  const fallback = {
    post: files["xiaohongshu_post.md"],
    research: files["research_report.md"],
  };
  els.outputView.textContent = fallback[state.currentTab] || "暂无内容";
}

function renderItemPosts(run, files) {
  els.outputView.hidden = true;
  els.coverActions.hidden = true;
  els.writingSettings.hidden = true;
  els.newsView.hidden = true;
  els.newsView.replaceChildren();
  els.publishView.hidden = true;
  els.publishView.replaceChildren();
  els.coverView.hidden = true;
  els.coverView.replaceChildren();
  els.hotspotView.hidden = false;
  els.hotspotView.replaceChildren();
  const posts = run.item_posts || [];
  if (!posts.length) {
    els.hotspotView.hidden = true;
    els.outputView.hidden = false;
    els.outputView.textContent = "尚未生成发布文案。请到“热点卡片”勾选主题，再点击生成文案。";
    return;
  }
  for (const [index, post] of posts.entries()) {
    els.hotspotView.appendChild(renderPostCard(post, index, run));
  }
}

function renderPostCard(post, index, run) {
  const card = document.createElement("div");
  card.className = "hotspot-card";
  const sourceIndex = Number(post.source_index ?? index);
  const tools = document.createElement("div");
  tools.className = "post-card-tools";
  const status = document.createElement("span");
  status.className = `review-status ${reviewStatusClass(post.review?.publish_status)}`;
  status.textContent = post.review ? reviewStatusLabel(post.review.publish_status) : "未审核";
  const reviewButton = document.createElement("button");
  reviewButton.className = "secondary small-button";
  reviewButton.type = "button";
  reviewButton.textContent = post.review ? "重新审核" : "审核";
  reviewButton.addEventListener("click", () => reviewPost(sourceIndex, reviewButton));
  const reviseButton = document.createElement("button");
  reviseButton.className = "secondary small-button";
  reviseButton.type = "button";
  reviseButton.textContent = "按建议修正";
  reviseButton.disabled = !post.review;
  reviseButton.addEventListener("click", () => revisePost(sourceIndex, reviseButton));
  tools.append(status, reviewButton, reviseButton);
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
  if (post.revision_notes?.length) {
    detail.appendChild(detailLine("修正记录", post.revision_notes.join(" / ")));
  }
  if (post.review) {
    detail.appendChild(renderReviewSummary(post.review));
  }
  toggle.addEventListener("click", () => {
    detail.hidden = !detail.hidden;
  });
  card.append(tools, toggle, detail);
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
  els.writingSettings.hidden = false;
  els.newsView.hidden = true;
  els.newsView.replaceChildren();
  els.publishView.hidden = true;
  els.publishView.replaceChildren();
  els.coverView.hidden = true;
  els.coverView.replaceChildren();
  els.hotspotView.hidden = false;
  els.hotspotView.replaceChildren();
  const hotspots = run.research?.hotspots || [];
  state.selectedTopicIndices = new Set(
    hotspots.map((item, index) => (item.selected ? index : null)).filter((index) => index !== null),
  );
  if (!hotspots.length) {
    const empty = document.createElement("pre");
    empty.textContent = "当前 run 没有热点条目。";
    els.hotspotView.appendChild(empty);
    return;
  }
  els.hotspotView.appendChild(renderCeoDecision(run));
  els.hotspotView.appendChild(renderTopicActionBar());
  for (const [index, hotspot] of hotspots.entries()) {
    els.hotspotView.appendChild(renderHotspotCard(hotspot, index));
  }
}

function renderCeoDecision(run) {
  const decision = run.ceo_decision || {};
  const panel = document.createElement("section");
  panel.className = "ceo-decision-panel";
  const header = document.createElement("div");
  header.className = "ceo-decision-header";
  const copy = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = "CEO 今日决策";
  const subtitle = document.createElement("span");
  subtitle.textContent = decision.today_content || "基于抓取新闻决定今天做什么内容";
  copy.append(title, subtitle);
  const score = document.createElement("div");
  score.className = "ceo-score";
  score.innerHTML = `<span>总体评分</span><strong>${escapeHtml(decision.overall_score ?? "-")}</strong>`;
  header.append(copy, score);
  panel.appendChild(header);

  const strategy = document.createElement("p");
  strategy.className = "ceo-strategy";
  strategy.textContent = decision.strategy || "优先选择高分、证据充分、适合小红书表达的主题。";
  panel.appendChild(strategy);

  const stats = document.createElement("div");
  stats.className = "ceo-stat-grid";
  stats.append(
    ceoStat("建议生成", `${decision.generate_count ?? 0} 篇`),
    ceoStat("推荐主题", formatIndexList(decision.recommended_indices)),
    ceoStat("可选主题", formatIndexList(decision.optional_indices)),
    ceoStat("人工审核", formatIndexList(decision.manual_review_indices)),
  );
  panel.appendChild(stats);

  if (decision.overall_reason) {
    panel.appendChild(detailLine("CEO理由", decision.overall_reason));
  }
  if (decision.capabilities?.length) {
    panel.appendChild(detailLine("调用能力", decision.capabilities.join(" / ")));
  }
  if (decision.execution_notes?.length) {
    const notes = document.createElement("ul");
    notes.className = "ceo-notes";
    for (const note of decision.execution_notes) {
      const item = document.createElement("li");
      item.textContent = note;
      notes.appendChild(item);
    }
    panel.appendChild(notes);
  }
  return panel;
}

function ceoStat(label, value) {
  const item = document.createElement("div");
  item.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value || "-")}</strong>`;
  return item;
}

function formatIndexList(indices) {
  if (!Array.isArray(indices) || !indices.length) return "-";
  return indices.map((index) => `#${Number(index) + 1}`).join("、");
}

function renderTopicActionBar() {
  const bar = document.createElement("div");
  bar.className = "topic-action-bar";
  const copy = document.createElement("div");
  copy.innerHTML = "<strong>选题排序</strong><span>先调整上方文案设置，再勾选主题调用 DeepSeek 生成发布文案。</span>";
  const button = document.createElement("button");
  button.className = "primary";
  button.type = "button";
  button.textContent = "生成所选文案";
  button.addEventListener("click", () => generateSelectedPosts(button));
  bar.append(copy, button);
  return bar;
}

function renderNews(run) {
  els.outputView.hidden = true;
  els.coverActions.hidden = true;
  els.writingSettings.hidden = true;
  els.hotspotView.hidden = true;
  els.hotspotView.replaceChildren();
  els.coverView.hidden = true;
  els.coverView.replaceChildren();
  els.publishView.hidden = true;
  els.publishView.replaceChildren();
  els.newsView.hidden = false;
  els.newsView.replaceChildren();
  const items = run.research?.source_items || [];
  if (!items.length) {
    const empty = document.createElement("pre");
    empty.textContent = "当前 run 没有可展示的原始新闻清单。";
    els.newsView.appendChild(empty);
    return;
  }
  const header = document.createElement("div");
  header.className = "news-list-header";
  header.innerHTML = `<strong>原始新闻清单</strong><span>${items.length} 条，供核对主题聚类和打分依据。</span>`;
  els.newsView.appendChild(header);
  for (const [index, item] of items.entries()) {
    const card = document.createElement("article");
    card.className = "news-card";
    const title = document.createElement("h3");
    title.textContent = `${index + 1}. ${item.title || "未命名新闻"}`;
    const meta = document.createElement("p");
    meta.className = "news-meta";
    meta.textContent = `${item.source || "未知来源"} · ${item.published || "未知时间"}`;
    const summary = document.createElement("p");
    summary.textContent = item.summary || "";
    card.append(title, meta, summary);
    if (item.url) {
      const link = document.createElement("a");
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "打开来源";
      card.appendChild(link);
    }
    els.newsView.appendChild(card);
  }
}

function renderPublish(run) {
  els.outputView.hidden = true;
  els.coverActions.hidden = true;
  els.writingSettings.hidden = true;
  els.hotspotView.hidden = true;
  els.hotspotView.replaceChildren();
  els.newsView.hidden = true;
  els.newsView.replaceChildren();
  els.coverView.hidden = true;
  els.coverView.replaceChildren();
  els.publishView.hidden = false;
  els.publishView.replaceChildren();

  const generatedSources = new Set((run.item_posts || []).map((post, index) => Number(post.source_index ?? index)));
  const covers = (run.item_covers || []).filter((item) => generatedSources.has(Number(item.source_index ?? item.index)));
  const coversBySource = new Map(covers.map((cover) => [Number(cover.source_index ?? cover.index), cover]));
  const posts = sortedPublishPosts(run).map((post, index) => {
    const sourceIndex = Number(post.source_index ?? index);
    const cover = coversBySource.get(sourceIndex) || {};
    return {
      source_index: sourceIndex,
      title: post.title || cover.title || `发布内容 ${index + 1}`,
      body: post.body || "",
      hashtags: post.hashtags || [],
      images: (cover.images || []).filter((image) => image.asset),
    };
  });

  const header = document.createElement("div");
  header.className = "publish-header";
  const copy = document.createElement("div");
  copy.innerHTML = `<strong>发布预览</strong><span>${posts.length} 条已生成文案，可检查标题、正文和多张图片。</span>`;
  const download = document.createElement("button");
  download.className = "primary";
  download.type = "button";
  download.textContent = "下载发布包";
  download.disabled = posts.length === 0;
  download.addEventListener("click", () => exportPublish(download));
  header.append(copy, download);
  els.publishView.appendChild(header);

  if (!posts.length) {
    const empty = document.createElement("pre");
    empty.textContent = "还没有可预览的发布内容。请先在“热点卡片”生成文案，并在“封面图”生成图片。";
    els.publishView.appendChild(empty);
    return;
  }
  for (const [index, post] of posts.entries()) {
    const card = document.createElement("article");
    card.className = "publish-card";
    const tools = document.createElement("div");
    tools.className = "publish-order-tools";
    const up = document.createElement("button");
    up.className = "secondary small-button";
    up.type = "button";
    up.textContent = "上移";
    up.disabled = index === 0;
    up.addEventListener("click", () => movePublishPost(posts, index, -1, up));
    const down = document.createElement("button");
    down.className = "secondary small-button";
    down.type = "button";
    down.textContent = "下移";
    down.disabled = index === posts.length - 1;
    down.addEventListener("click", () => movePublishPost(posts, index, 1, down));
    tools.append(up, down);
    const title = document.createElement("h3");
    title.textContent = `${index + 1}. ${post.title}`;
    const body = document.createElement("pre");
    body.textContent = post.body;
    const tags = document.createElement("p");
    tags.textContent = (post.hashtags || []).join(" ");
    const gallery = document.createElement("div");
    gallery.className = "publish-gallery";
    for (const image of post.images) {
      const img = document.createElement("img");
      img.src = `/api/runs/${encodeURIComponent(run.run_id)}/assets/${encodeURIComponent(image.asset)}?ts=${Date.now()}`;
      img.alt = post.title;
      gallery.appendChild(img);
    }
    if (!post.images.length) {
      const missing = document.createElement("p");
      missing.className = "muted-copy";
      missing.textContent = "尚未生成图片";
      gallery.appendChild(missing);
    }
    card.append(tools, title, body, tags, gallery);
    els.publishView.appendChild(card);
  }
}

function sortedPublishPosts(run) {
  const posts = (run.item_posts || []).filter((post) => post && typeof post === "object");
  const order = Array.isArray(run.publish_order) ? run.publish_order.map(Number) : [];
  if (!order.length) return posts;
  const rank = new Map(order.map((sourceIndex, index) => [sourceIndex, index]));
  return posts
    .map((post, index) => ({ post, index, sourceIndex: Number(post.source_index ?? index) }))
    .sort((a, b) => (rank.get(a.sourceIndex) ?? order.length + a.index) - (rank.get(b.sourceIndex) ?? order.length + b.index))
    .map((item) => item.post);
}

function movePublishPost(posts, index, direction, button) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= posts.length) return;
  const next = [...posts];
  [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
  reorderPublish(next.map((post) => Number(post.source_index)), button);
}

function renderReview(run) {
  els.outputView.hidden = true;
  els.coverActions.hidden = true;
  els.writingSettings.hidden = true;
  els.hotspotView.hidden = false;
  els.hotspotView.replaceChildren();
  els.newsView.hidden = true;
  els.newsView.replaceChildren();
  els.coverView.hidden = true;
  els.coverView.replaceChildren();
  els.publishView.hidden = true;
  els.publishView.replaceChildren();
  const posts = run.item_posts || [];
  if (!posts.length) {
    const empty = document.createElement("pre");
    empty.textContent = "还没有可审核的发布文案。请先在“热点卡片”生成文案。";
    els.hotspotView.appendChild(empty);
    return;
  }
  const header = document.createElement("div");
  header.className = "topic-action-bar";
  const copy = document.createElement("div");
  copy.innerHTML = "<strong>Review / Evidence</strong><span>对照源新闻检查来源、夸大、疗效承诺、投资建议，并给出置信评分和修改点。</span>";
  header.appendChild(copy);
  els.hotspotView.appendChild(header);
  for (const [index, post] of posts.entries()) {
    els.hotspotView.appendChild(renderReviewCard(run, post, index));
  }
}

function renderReviewCard(run, post, index) {
  const card = document.createElement("article");
  card.className = "review-card";
  const sourceIndex = Number(post.source_index ?? index);
  const hotspot = (run.research?.hotspots || [])[sourceIndex] || {};
  const header = document.createElement("div");
  header.className = "review-card-header";
  const titleWrap = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = `${index + 1}. ${post.title || "未命名文案"}`;
  const meta = document.createElement("p");
  meta.textContent = `${hotspot.source || "未知来源"} · ${hotspot.published || "未知时间"}`;
  titleWrap.append(title, meta);
  const actions = document.createElement("div");
  actions.className = "review-actions";
  const status = document.createElement("span");
  status.className = `review-status ${reviewStatusClass(post.review?.publish_status)}`;
  status.textContent = post.review ? reviewStatusLabel(post.review.publish_status) : "未审核";
  const reviewButton = document.createElement("button");
  reviewButton.className = "primary";
  reviewButton.type = "button";
  reviewButton.textContent = post.review ? "重新审核" : "开始审核";
  reviewButton.addEventListener("click", () => reviewPost(sourceIndex, reviewButton));
  const reviseButton = document.createElement("button");
  reviseButton.className = "secondary";
  reviseButton.type = "button";
  reviseButton.textContent = "按建议修正";
  reviseButton.disabled = !post.review;
  reviseButton.addEventListener("click", () => revisePost(sourceIndex, reviseButton));
  actions.append(status, reviewButton, reviseButton);
  header.append(titleWrap, actions);
  card.appendChild(header);

  if (post.review) {
    card.appendChild(renderReviewSummary(post.review));
    card.appendChild(renderReviewIssues(post.review));
    card.appendChild(renderEvidenceList(post.review.evidence_used || hotspot.evidence || []));
  } else {
    const empty = document.createElement("p");
    empty.className = "muted-copy";
    empty.textContent = "尚未审核。点击“开始审核”后会调用 DeepSeek 对照源新闻进行判断。";
    card.appendChild(empty);
  }
  return card;
}

function renderReviewSummary(review) {
  const wrapper = document.createElement("div");
  wrapper.className = "review-summary";
  wrapper.append(
    reviewMetric("来源置信", review.source_confidence),
    reviewMetric("总体置信", review.overall_confidence),
    reviewMetric("夸大风险", review.exaggeration_risk),
    reviewMetric("疗效风险", review.efficacy_promise_risk),
    reviewMetric("投资风险", review.investment_advice_risk),
  );
  const summary = document.createElement("p");
  summary.textContent = review.summary || "";
  wrapper.appendChild(summary);
  return wrapper;
}

function reviewMetric(label, value) {
  const item = document.createElement("div");
  item.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? 0)}</strong>`;
  return item;
}

function renderReviewIssues(review) {
  const box = document.createElement("div");
  box.className = "review-issues";
  const issues = review.issues || [];
  const heading = document.createElement("strong");
  heading.textContent = issues.length ? "审核问题与修改点" : "审核问题与修改点：暂无明显问题";
  box.appendChild(heading);
  for (const issue of issues) {
    const item = document.createElement("div");
    item.className = "review-issue";
    item.innerHTML = `<b>${escapeHtml(issue.severity || "-")} · ${escapeHtml(issue.category || "-")}</b>`;
    item.appendChild(detailLine("发现", issue.finding || ""));
    item.appendChild(detailLine("证据", issue.evidence || ""));
    item.appendChild(detailLine("建议", issue.suggestion || ""));
    box.appendChild(item);
  }
  if (review.revision_suggestions?.length) {
    const list = document.createElement("ul");
    for (const suggestion of review.revision_suggestions) {
      const item = document.createElement("li");
      item.textContent = suggestion;
      list.appendChild(item);
    }
    box.appendChild(list);
  }
  return box;
}

function renderEvidenceList(items) {
  const box = document.createElement("div");
  box.className = "evidence-list";
  const heading = document.createElement("strong");
  heading.textContent = "Evidence";
  box.appendChild(heading);
  if (!items.length) {
    const empty = document.createElement("p");
    empty.textContent = "暂无可追溯证据。";
    box.appendChild(empty);
    return box;
  }
  for (const item of items) {
    const row = document.createElement("p");
    const link = item.url ? document.createElement("a") : null;
    if (link) {
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = item.title || item.url;
      row.append(`${item.source || "未知来源"} · ${item.published || "未知时间"}｜`, link);
    } else {
      row.textContent = `${item.source || "未知来源"} · ${item.published || "未知时间"}｜${item.title || "-"}`;
    }
    box.appendChild(row);
  }
  return box;
}

async function reviewPost(sourceIndex, button) {
  if (!state.currentRun?.run_id) return;
  const oldText = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "审核中...";
  }
  try {
    state.currentRun = await api(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/review`, {
      method: "POST",
      body: JSON.stringify({ source_index: sourceIndex }),
    });
    state.currentTab = "review";
    syncTabs();
    renderOutput();
    await loadRuns();
    showToast("审核完成");
  } catch (error) {
    showToast(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText || "审核";
    }
  }
}

async function revisePost(sourceIndex, button) {
  if (!state.currentRun?.run_id) return;
  const oldText = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "修正中...";
  }
  try {
    state.currentRun = await api(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/revise`, {
      method: "POST",
      body: JSON.stringify({ source_index: sourceIndex }),
    });
    state.currentTab = "post";
    syncTabs();
    renderOutput();
    await loadRuns();
    showToast("已按审核建议修正文案");
  } catch (error) {
    showToast(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText || "按建议修正";
    }
  }
}

function reviewStatusLabel(status) {
  return { pass: "通过", revise: "建议修正", block: "暂不发布" }[status] || "未审核";
}

function reviewStatusClass(status) {
  return { pass: "status-pass", revise: "status-revise", block: "status-block" }[status] || "status-pending";
}

function renderHotspotCard(hotspot, index) {
  const card = document.createElement("div");
  card.className = "hotspot-card";
  const selector = document.createElement("label");
  selector.className = "topic-selector";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = Boolean(hotspot.selected);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) state.selectedTopicIndices.add(index);
    else state.selectedTopicIndices.delete(index);
  });
  const score = document.createElement("strong");
  score.textContent = `${hotspot.total_score ?? 0} 分`;
  const selectorText = document.createElement("span");
  selectorText.textContent = "选择生成文案";
  selector.append(checkbox, score, selectorText);
  const badges = document.createElement("div");
  badges.className = "topic-badges";
  const ceoDecision = hotspot.ceo_decision || "";
  if (ceoDecision) {
    badges.appendChild(topicBadge(`CEO：${ceoDecisionLabel(ceoDecision)}`, `decision-${ceoDecision}`));
  }
  if (hotspot.ceo_score) {
    badges.appendChild(topicBadge(`CEO ${hotspot.ceo_score}分`, "decision-score"));
  }
  if (hotspot.human_review_required) {
    badges.appendChild(topicBadge("需人工审核", "decision-review"));
  }
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
  detail.appendChild(renderScoreGrid(hotspot));
  detail.appendChild(detailLine("CEO意见", hotspot.ceo_reason || ""));
  detail.appendChild(detailLine("CEO建议做法", hotspot.ceo_content_angle || ""));
  detail.appendChild(detailLine("CEO调用能力", (hotspot.ceo_capabilities || []).join(" / ")));
  detail.appendChild(detailLine("人工审核", hotspot.human_review_required ? hotspot.review_reason || "建议人工复核。" : "否"));
  detail.appendChild(detailLine("打分理由", hotspot.score_reason || hotspot.why_it_matters || ""));
  detail.appendChild(detailLine("合规提醒", hotspot.compliance_note || ""));
  detail.appendChild(detailLine("为什么重要", hotspot.why_it_matters || ""));
  detail.appendChild(detailLine("标签", (hotspot.tags || []).join(" / ")));
  detail.appendChild(detailLine("来源", `${hotspot.source || "未知"} · ${hotspot.published || "未知时间"}`));
  for (const evidence of hotspot.evidence || []) {
    detail.appendChild(detailLine("证据新闻", `${evidence.source || "未知"}｜${evidence.title || ""}`));
  }
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
  const generateOne = document.createElement("button");
  generateOne.className = "secondary topic-generate-one";
  generateOne.type = "button";
  generateOne.textContent = "生成这条文案";
  generateOne.addEventListener("click", () => generatePosts([index], generateOne));
  const header = document.createElement("div");
  header.className = "topic-card-tools";
  const leftTools = document.createElement("div");
  leftTools.className = "topic-card-left";
  leftTools.append(selector, badges);
  header.append(leftTools, generateOne);
  card.append(header, toggle, detail);
  return card;
}

function topicBadge(label, className) {
  const badge = document.createElement("span");
  badge.className = `topic-badge ${className}`;
  badge.textContent = label;
  return badge;
}

function ceoDecisionLabel(value) {
  return { do: "推荐做", optional: "可选", skip: "暂不做" }[value] || value;
}

function renderScoreGrid(hotspot) {
  const grid = document.createElement("div");
  grid.className = "score-grid";
  const labels = hotspot.score_labels || {};
  const scores = hotspot.scores || {};
  for (const [key, value] of Object.entries(scores)) {
    const item = document.createElement("div");
    item.innerHTML = `<span>${escapeHtml(labels[key] || key)}</span><strong>${escapeHtml(value)}</strong>`;
    grid.appendChild(item);
  }
  return grid;
}

async function generateSelectedPosts(button) {
  const indices = [...state.selectedTopicIndices];
  if (!indices.length) {
    showToast("请先勾选至少一个热点主题");
    return;
  }
  await generatePosts(indices, button);
}

async function generatePosts(indices, button) {
  if (!state.currentRun?.run_id) return;
  const oldText = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "正在生成...";
  }
  try {
    state.currentRun = await api(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/posts`, {
      method: "POST",
      body: JSON.stringify({
        indices,
        content_words: Number(els.contentWords.value || state.currentRun.content_options?.content_words || 700),
        content_instruction: els.contentInstruction.value || state.currentRun.content_options?.content_instruction || "",
        format_reference: els.formatReference.value || state.currentRun.content_options?.format_reference || "",
      }),
    });
    state.currentTab = "post";
    syncTabs();
    renderOutput();
    await loadRuns();
    showToast("所选主题文案已生成");
  } catch (error) {
    showToast(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText || "生成文案";
    }
  }
}

function detailLine(label, value) {
  const line = document.createElement("p");
  line.textContent = `${label}：${value || "-"}`;
  return line;
}

function renderCover(run, files) {
  els.outputView.hidden = true;
  els.coverActions.hidden = false;
  els.writingSettings.hidden = true;
  els.hotspotView.hidden = true;
  els.hotspotView.replaceChildren();
  els.newsView.hidden = true;
  els.newsView.replaceChildren();
  els.publishView.hidden = true;
  els.publishView.replaceChildren();
  els.coverView.hidden = false;
  els.coverView.replaceChildren();
  const generatedSources = new Set((run.item_posts || []).map((post, index) => Number(post.source_index ?? index)));
  const itemCovers = (run.item_covers || []).filter((item) => generatedSources.has(Number(item.source_index ?? item.index)));
  if (!itemCovers.length) {
    const empty = document.createElement("pre");
    empty.textContent = "当前 run 还没有已生成发布文案的热点。请先在“热点卡片”中选择主题生成文案。";
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
  button.textContent = item.prompt_options?.length ? "重新生成提示词" : "生成图片提示词";
  const instruction = document.createElement("textarea");
  instruction.className = "wide-textarea";
  instruction.rows = 2;
  instruction.placeholder = "可选：单独给这张图的要求，例如突出机制、不放曲线、白底、只保留标题和标签等";
  button.addEventListener("click", () => generateCoverPrompts(Number(item.index), button, instruction));
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
  const images = (item.images || []).filter((image) => image.asset && !image.error);
  if (images.length) {
    const gallery = document.createElement("div");
    gallery.className = "cover-gallery";
    for (const imageItem of images) {
      const figure = document.createElement("figure");
      const image = document.createElement("img");
      image.src = `/api/runs/${encodeURIComponent(run.run_id)}/assets/${encodeURIComponent(imageItem.asset)}?ts=${Date.now()}`;
      image.alt = item.title || "正文配图";
      const remove = document.createElement("button");
      remove.className = "secondary danger-link";
      remove.type = "button";
      remove.textContent = "删除图片";
      remove.addEventListener("click", () => deleteCoverImage(Number(item.index), imageItem.asset, remove));
      const caption = document.createElement("figcaption");
      caption.textContent = `方案 ${Number(imageItem.prompt_index || 0) + 1} · ${imageItem.size || ""}`;
      figure.append(image, caption, remove);
      gallery.appendChild(figure);
    }
    card.appendChild(gallery);
  }
  if (item.prompt_options?.length) {
    const options = document.createElement("div");
    options.className = "prompt-options";
    const heading = document.createElement("strong");
    const plan = item.image_plan || {};
    heading.textContent = `Image Agent 图组提示词${plan.recommended_count ? `：推荐 ${plan.recommended_count} 张` : ""}`;
    options.appendChild(heading);
    if (plan.strategy) {
      const planText = document.createElement("p");
      planText.className = "muted-copy";
      planText.textContent = plan.strategy;
      options.appendChild(planText);
    }
    for (const [promptIndex, option] of item.prompt_options.slice(0, 5).entries()) {
      const details = document.createElement("details");
      details.className = "prompt-option";
      details.open = promptIndex === 0 && !item.asset;
      const summary = document.createElement("summary");
      summary.textContent = `${option.sequence || promptIndex + 1}. ${imageRoleLabel(option.image_role)} · ${option.title || "图片方案"} · ${option.style || "视觉风格"} · ${option.score || 0}分`;
      const imageButton = document.createElement("button");
      imageButton.className = "primary prompt-image-button";
      imageButton.type = "button";
      imageButton.textContent = `生成这张${imageRoleLabel(option.image_role)}`;
      imageButton.addEventListener("click", (event) => {
        event.preventDefault();
        generateCover(Number(item.index), promptIndex, imageButton);
      });
      const pre = document.createElement("pre");
      pre.textContent = option.prompt || "";
      details.append(summary, imageButton, pre);
      options.appendChild(details);
    }
    card.appendChild(options);
  }
  const detail = document.createElement("pre");
  detail.textContent = [
    item.error ? `生成状态：${item.error}` : images.length ? `生成状态：已生成 ${images.length} 张图片` : "生成状态：尚未生成图片",
    "",
    "图片 Prompt：",
    item.prompt || "请先点击“生成图片提示词”，再选择一个方案生成图片",
  ].join("\n");
  card.appendChild(detail);
  return card;
}

function imageRoleLabel(role) {
  return role === "content_card" ? "内容卡片" : "封面图";
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
els.autoPublish.addEventListener("click", autoPublish);
els.clearRuns.addEventListener("click", clearRuns);
els.togglePassword.addEventListener("click", () => {
  els.passwordPanel.hidden = !els.passwordPanel.hidden;
});
els.changePassword.addEventListener("click", changePassword);
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
