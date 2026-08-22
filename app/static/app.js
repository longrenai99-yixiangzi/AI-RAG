const statusElement = document.querySelector("#status");
const healthDetailsElement = document.querySelector("#health-details");
const indexDetailsElement = document.querySelector("#index-details");
const form = document.querySelector("#question-form");
const questionElement = document.querySelector("#question");
const submitElement = document.querySelector("#submit");
const conversation = document.querySelector("#conversation");
const template = document.querySelector("#answer-template");
let questionCount = 0;
const growthPanel = document.querySelector("#growth-panel");
const growthStats = document.querySelector("#growth-stats");
const growthList = document.querySelector("#growth-list");
const candidateView = document.querySelector("#candidate-view");
const documentsPanel = document.querySelector("#documents-panel");
const documentsList = document.querySelector("#documents-list");
const documentQuery = document.querySelector("#document-query");
const filterBoard = document.querySelector("#filter-board");
const filterKnowledgeType = document.querySelector("#filter-knowledge-type");
const filterBuildingType = document.querySelector("#filter-building-type");
const filterProjectStage = document.querySelector("#filter-project-stage");
const fileMode = window.location.protocol === "file:";

if (fileMode) {
  statusElement.textContent = "当前以文件直开方式打开，未连接知识库服务";
  healthDetailsElement.textContent = "请运行“启动知识库.bat”，再访问 http://127.0.0.1:8000；不要直接双击 index.html。";
  indexDetailsElement.textContent = "文件直开模式不能访问 /api/health、/api/status 等后端接口。";
  submitElement.disabled = true;
  document.querySelector("#health").disabled = true;
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[character]);
}

function formatAnswer(value) {
  return escapeHtml(value)
    .replace(/【([^】]+)】/g, "<strong>【$1】</strong>")
    .replace(/\n/g, "<br>");
}

function formatGrowthStatus(status) {
  return ({ OPEN: "待补充", REVIEWING: "审核中", RESOLVED: "已解决", IGNORED: "已忽略" })[status] || status;
}

function displayText(value, fallback = "历史记录（原始文本编码损坏）") {
  const text = String(value ?? "");
  return /\?{3,}|�{2,}/.test(text) ? fallback : text;
}

async function fetchJson(url, timeoutMs = 7000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Error(`${url} ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function loadGrowth() {
  try {
    const data = await fetch("/api/growth", { cache: "no-store" }).then((response) => response.json());
    growthStats.innerHTML = Object.entries(data.stats || {})
      .map(([status, count]) => `<span class="growth-stat">${escapeHtml(formatGrowthStatus(status))}: ${escapeHtml(String(count))}</span>`)
      .join("") || '<span class="status">暂无知识缺口</span>';
    growthList.innerHTML = (data.gaps || []).map((gap) => {
      const candidate = gap.candidate_id
        ? `<button class="candidate-button secondary" data-candidate="${escapeHtml(gap.candidate_id)}">查看候选</button>
           <button class="draft-button secondary" title="只生成待审批草稿，不写回正式知识" data-candidate="${escapeHtml(gap.candidate_id)}">生成待审批草稿</button>`
        : "";
      return `<article class="growth-item">
        <div><strong>${escapeHtml(displayText(gap.latest_query, "历史问题（原始文本编码损坏，请重新提问）"))}</strong>
        <p>${escapeHtml(displayText(gap.reason || "证据不足"))} · 频次 ${escapeHtml(String(gap.frequency || 1))}</p>
        <small>${escapeHtml(formatGrowthStatus(gap.status))}</small></div>
        <div class="growth-actions">${candidate}
        <button class="status-button" data-gap="${escapeHtml(gap.gap_id)}" data-status="REVIEWING">审核中</button>
        <button class="status-button secondary" data-gap="${escapeHtml(gap.gap_id)}" data-status="RESOLVED">解决</button></div>
      </article>`;
    }).join("") || '<p class="status">尚未发现知识缺口。提问后，证据不足的问题会自动出现在这里。</p>';
    growthList.querySelectorAll(".status-button").forEach((button) => {
      button.addEventListener("click", async () => {
        await fetch(`/api/growth/gaps/${button.dataset.gap}/status`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: button.dataset.status }),
        });
        await loadGrowth();
      });
    });
    growthList.querySelectorAll(".candidate-button").forEach((button) => {
      button.addEventListener("click", async () => {
        const result = await fetch(`/api/growth/candidates/${button.dataset.candidate}`).then((response) => response.json());
        candidateView.hidden = false;
        candidateView.textContent = result.content || "候选文件不存在。";
      });
    });
    growthList.querySelectorAll(".draft-button").forEach((button) => {
      button.addEventListener("click", async () => {
        const response = await fetch(`/api/growth/candidates/${button.dataset.candidate}/formal-draft`, { method: "POST" });
        const result = await response.json();
        candidateView.hidden = false;
        candidateView.textContent = response.ok
          ? `已生成待审批草稿：${result.path}\n\n正式写回仍被禁止。`
          : (result.detail || "草稿生成失败。");
        await loadGrowth();
      });
    });
  } catch (error) {
    growthList.innerHTML = `<p class="error">知识生长读取失败：${escapeHtml(error.message)}</p>`;
  }
}

async function loadDocuments() {
  try {
    const params = new URLSearchParams({
      query: documentQuery.value.trim(),
      board: filterBoard.value,
      knowledge_type: filterKnowledgeType.value,
      building_type: filterBuildingType.value,
      project_stage: filterProjectStage.value,
    });
    const data = await fetch(`/api/documents?${params.toString()}`, { cache: "no-store" }).then((response) => response.json());
    const groups = new Map();
    for (const item of data.items || []) {
      const metadata = item.metadata || {};
      const group = `${metadata.board || "待核实板块"} / ${metadata.knowledge_type || "待核实类型"}`;
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group).push(item);
    }
    documentsList.innerHTML = [...groups.entries()].map(([group, items]) => `<section class="document-group"><h3>${escapeHtml(group)} <small>(${items.length})</small></h3>${items.map((item) => {
      const metadata = item.metadata || {};
      const tags = [metadata.board, metadata.knowledge_type, metadata.building_type, metadata.project_stage]
        .filter(Boolean).map((value) => `<span>${escapeHtml(String(value))}</span>`).join("");
      return `<article class="document-item">
        <div><strong>${escapeHtml(item.file_name)}</strong><p>${escapeHtml(item.source_path)}</p></div>
        <div class="document-meta"><span>${escapeHtml(item.file_type)}</span><span>解析: ${escapeHtml(item.parse_status)}</span>
        <span>索引: ${escapeHtml(item.index_status)}</span><span>OCR: ${item.needs_ocr ? "待处理" : "否"}</span><div>${tags}</div></div>
      </article>`;
    }).join("")}</section>`).join("") || '<p class="status">当前没有符合筛选条件的索引文件。</p>';
  } catch (error) {
    documentsList.innerHTML = `<p class="error">知识管理读取失败：${escapeHtml(error.message)}</p>`;
  }
}

function showMode(mode) {
  const growth = mode === "growth";
  const documents = mode === "documents";
  growthPanel.hidden = !growth;
  documentsPanel.hidden = !documents;
  conversation.hidden = growth || documents;
  form.hidden = growth || documents;
  document.querySelector("#growth-nav").classList.toggle("secondary", !growth);
  document.querySelector("#documents-nav").classList.toggle("secondary", !documents);
  document.querySelector("#qa-nav").classList.toggle("secondary", growth || documents);
  if (growth) loadGrowth();
  if (documents) loadDocuments();
}

async function refreshHealth(probeLlm = false) {
  statusElement.textContent = "正在检查服务状态…";
  const results = await Promise.allSettled([
    fetchJson(`/api/health${probeLlm ? "?probe_llm=true" : ""}`, probeLlm ? 8000 : 3000),
    fetchJson("/api/status", 3000),
  ]);
  const healthResult = results[0];
  const statusResult = results[1];
  const health = healthResult.status === "fulfilled" ? healthResult.value : null;
  const status = statusResult.status === "fulfilled" ? statusResult.value : null;
  if (!health && !status) {
    statusElement.textContent = "无法连接本地服务。请确认服务已启动。";
    statusElement.classList.add("error");
    return;
  }
  if (status) {
    const label = health?.status === "ok" ? "服务就绪" : "服务可用（部分状态待确认）";
    statusElement.textContent =
      label + " · 索引 " + status.index.documents + " 个文件 / " +
      status.index.chunks + " 个切片" +
      (status.embedding_device ? " · " + status.embedding_device.toUpperCase() : "") +
      " · OCR待处理 " + (status.index.ocr_pending ?? 0) +
      " · 实体 " + (status.index.entities ?? 0) +
      " / 事实 " + (status.index.facts ?? 0);
    const types = Object.entries(status.index.file_types || {})
      .map(([type, count]) => type + " " + count)
      .join(" · ");
    indexDetailsElement.textContent = "文件类型: " + (types || "暂无") +
      " · OCR Provider: " + (status.ocr_provider || "disabled");
  }
  if (health) {
    const availability = (value) => value === true ? "可用" : value === false ? "不可用" : "未探测";
    healthDetailsElement.textContent =
      "LLM: " + availability(health.llm) +
      " · Embedding: " + availability(health.embedding) +
      " · Reranker文件: " + (health.reranker_model_available ? "可用" : "缺失") +
      " · Reranker运行: " + availability(health.reranker) +
      " · Qdrant: " + availability(health.vector_db) +
      (health.llm_probe ? " · LLM探测: " + health.llm_probe : "");
    statusElement.classList.toggle("error", health.status === "degraded" && !status);
  } else {
    healthDetailsElement.textContent = "网络状态探测超时，但索引状态仍可用；点击“重新检查”可再次探测。";
    statusElement.classList.remove("error");
  }
}

function showAnswer(data, question) {
  questionCount += 1;
  const node = template.content.cloneNode(true);
  node.querySelector(".question-number").textContent = "#" + questionCount;
  node.querySelector(".answer-number").textContent = "#" + questionCount;
  node.querySelector(".question-text").textContent = question;
  node.querySelector(".answer-body").innerHTML = formatAnswer(data.answer);
  node.querySelector(".meta").textContent =
    (data.elapsed_ms ?? 0) + " ms · " +
    (data.citation_valid ? "引用已校验" : "引用未通过校验");
  const citations = node.querySelector(".citation-list");
  for (const citation of data.citations ?? []) {
    const card = document.createElement("div");
    card.className = "citation";
    card.innerHTML =
      "<strong>[" + escapeHtml(citation.id) + "] " + escapeHtml(citation.file_name) + "</strong>" +
      "<span>" + escapeHtml(citation.heading_path || "未识别章节") +
      (citation.location ? " · " + escapeHtml(citation.location) : "") + "</span>" +
      "<span>" + escapeHtml(citation.excerpt) + "</span>";
    citations.appendChild(card);
  }
  const debug = node.querySelector(".retrieval-debug");
  debug.textContent = JSON.stringify(data.retrieval ?? {}, null, 2);
  conversation.appendChild(node);
  conversation.lastElementChild.scrollIntoView({ behavior: "smooth", block: "start" });
  loadGrowth();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionElement.value.trim();
  if (!question) return;
  submitElement.disabled = true;
  submitElement.textContent = "检索并回答中…";
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "请求失败");
    showAnswer(body, question);
    questionElement.value = "";
  } catch (error) {
    const warning = document.createElement("p");
    warning.className = "error";
    warning.textContent = "提问失败：" + error.message;
    conversation.appendChild(warning);
  } finally {
    submitElement.disabled = false;
    submitElement.textContent = "提问";
  }
});

document.querySelector("#health").addEventListener("click", () => refreshHealth(true));
document.querySelector("#qa-nav").addEventListener("click", () => showMode("qa"));
document.querySelector("#growth-nav").addEventListener("click", () => showMode("growth"));
document.querySelector("#growth-refresh").addEventListener("click", loadGrowth);
document.querySelector("#documents-nav").addEventListener("click", () => showMode("documents"));
document.querySelector("#documents-refresh").addEventListener("click", loadDocuments);
documentQuery.addEventListener("keydown", (event) => { if (event.key === "Enter") loadDocuments(); });
[filterBoard, filterKnowledgeType, filterBuildingType, filterProjectStage].forEach((select) => {
  select.addEventListener("change", loadDocuments);
});
if (!fileMode) refreshHealth();
