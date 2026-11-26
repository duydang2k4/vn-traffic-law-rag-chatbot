const form = document.querySelector("#ask-form");
const question = document.querySelector("#question");
const submit = form.querySelector("button");
const status = document.querySelector("#status");
const result = document.querySelector("#result");
const heading = document.querySelector("#result-title");
const sources = document.querySelector("#sources");

function element(tag, content, className) {
  const item = document.createElement(tag);
  item.textContent = content;
  if (className) item.className = className;
  return item;
}

function citationLink(citation) {
  try {
    const url = new URL(citation.url);
    if (!["https:", "http:"].includes(url.protocol)) return null;
    const link = element("a", citation.document_number);
    link.href = url.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  } catch {
    return null;
  }
}

function renderResponse(data) {
  heading.textContent = {
    gemini: "Trả lời theo nguồn",
    groq: "Trả lời theo nguồn",
    "ollama-cloud": "Trả lời theo nguồn",
    ollama: "Trả lời theo nguồn",
    extractive: "Trích đoạn phù hợp nhất",
    temporal_review: "Cần đối chiếu thời điểm áp dụng",
    abstain: "Chưa tìm thấy căn cứ phù hợp",
  }[data.mode] ?? "Kết quả tra cứu";
  document.querySelector("#answer").textContent = data.answer;
  document.querySelector("#notice").textContent = [data.fallback, data.notice].filter(Boolean).join(" ");
  sources.replaceChildren();
  if (data.sources.length) sources.append(element("h3", "Nguồn đối chiếu"));
  for (const [index, source] of data.sources.entries()) {
    const details = document.createElement("details");
    details.append(
      element("summary", `[${index + 1}] ${source.label}`),
      element("p", source.excerpt, "excerpt"),
    );
    const list = element("ul", "", "source-links");
    for (const citation of source.citations) {
      const item = document.createElement("li");
      item.append(citationLink(citation) ?? citation.document_number);
      item.append(` · Khối ${citation.blocks.join(", ")}`);
      list.append(item);
    }
    details.append(list);
    sources.append(details);
  }
  result.hidden = false;
}

for (const example of document.querySelectorAll(".example")) {
  example.addEventListener("click", () => {
    question.value = example.lastElementChild.textContent;
    question.focus();
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (submit.disabled) return;
  result.hidden = true;
  status.removeAttribute("data-error");
  const prompt = question.value.trim();
  if (!prompt) {
    status.textContent = "Hãy nhập câu hỏi bạn muốn tra cứu.";
    status.dataset.error = "";
    question.focus();
    return;
  }
  submit.disabled = true;
  status.textContent = "Đang tìm điều khoản và nguồn đối chiếu…";
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: prompt }),
    });
    const data = await response.json();
    if (!response.ok) {
      status.textContent = data.error ?? "Không thể hoàn tất tra cứu.";
      status.dataset.error = "";
      return;
    }
    renderResponse(data);
    status.textContent = "Đã có kết quả tra cứu.";
  } catch {
    status.textContent = "Không kết nối được với máy chủ tra cứu. Hãy thử lại.";
    status.dataset.error = "";
  } finally {
    submit.disabled = false;
  }
});
