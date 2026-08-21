const statusElement = document.querySelector("#status");
const form = document.querySelector("#question-form");
const questionElement = document.querySelector("#question");
const submitElement = document.querySelector("#submit");
const conversation = document.querySelector("#conversation");
const template = document.querySelector("#answer-template");

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

async function refreshHealth() {
  statusElement.textContent = "正在检查服务状态…";
  try {
    const results = await Promise.all([
      fetch("/api/health").then((response) => response.json()),
      fetch("/api/status").then((response) => response.json()),
    ]);
    const health = results[0];
    const status = results[1];
    const label = health.status === "ok" ? "服务就绪" : "服务部分不可用";
    statusElement.textContent =
      label + " · 索引 " + status.index.documents + " 个文件 / " +
      status.index.chunks + " 个切片" +
      (status.embedding_device ? " · " + status.embedding_device.toUpperCase() : "");
    statusElement.classList.toggle("error", health.status !== "ok");
  } catch {
    statusElement.textContent = "无法连接本地服务。请确认服务已启动。";
    statusElement.classList.add("error");
  }
}

function showAnswer(data) {
  const node = template.content.cloneNode(true);
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
  conversation.appendChild(node);
  conversation.lastElementChild.scrollIntoView({ behavior: "smooth", block: "start" });
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
    showAnswer(body);
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

document.querySelector("#health").addEventListener("click", refreshHealth);
refreshHealth();
