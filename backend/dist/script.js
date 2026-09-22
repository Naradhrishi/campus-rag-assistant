// const API = "http://localhost:8000";
// As I am using app.frontend() to server static frontend files so there is no need of this API url ..
const API = ""; 

// --- Elements ---
const fileInput = document.getElementById("upload-icon");
const fileList = document.getElementById("file-list");
const fileListHeading = document.getElementById("file-list-heading");
const emptyFileHint = document.getElementById("empty-file-hint");
const chatSection = document.getElementById("request-response-section");
const queryInput = document.getElementById("query-input");
const sendBtn = document.getElementById("send-btn");
const status = document.getElementById("upload-status");
const uploadContainer = document.getElementById("file-upload-container");
const universityNote = document.getElementById("university-mode-note");
const modeButtons = document.querySelectorAll(".mode-btn");
const menuToggleBtn = document.getElementById("menu-toggle-btn");
const sidebar = document.getElementById("sidebar");
const sidebarBackdrop = document.getElementById("sidebar-backdrop");

// --- Session (identifies this browser's personal document set) ---
function getSessionId() {
  let id = localStorage.getItem("rag_session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("rag_session_id", id);
  }
  return id;
}
const sessionId = getSessionId();

// --- State ---
let currentMode = "personal";
const chatHistory = {
  personal: [
    { text: "Hi! Upload a document and ask anything from it.", type: "bot", sources: [] },
  ],
  university: [
    { text: "Hi! Ask me anything about university regulations — attendance, exams, grading, deadlines, and more.", type: "bot", sources: [] },
  ],
};

// --- Mobile sidebar toggle ---
function openSidebar() {
  sidebar.classList.add("open");
  sidebarBackdrop.classList.add("open");
}
function closeSidebar() {
  sidebar.classList.remove("open");
  sidebarBackdrop.classList.remove("open");
}
menuToggleBtn?.addEventListener("click", () => {
  sidebar.classList.contains("open") ? closeSidebar() : openSidebar();
});
sidebarBackdrop?.addEventListener("click", closeSidebar);

// --- Mode switching ---
modeButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.mode === currentMode) return;
    modeButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentMode = btn.dataset.mode;
    applyModeUI();
    renderChat();
    loadFiles();
    if (window.innerWidth <= 768) closeSidebar();
  });
});

function applyModeUI() {
  if (currentMode === "personal") {
    uploadContainer.style.display = "flex";
    universityNote.style.display = "none";
    fileListHeading.textContent = "Your Documents";
    queryInput.placeholder = "Ask your knowledge base...";
  } else {
    uploadContainer.style.display = "none";
    universityNote.style.display = "block";
    fileListHeading.textContent = "Regulation Documents";
    queryInput.placeholder = "Ask about university regulations...";
  }
}

// --- File list --- FIXED FOR app.frontend() ---
async function loadFiles() {
  try {
    const params = new URLSearchParams();
    params.set("mode", currentMode);
    if (currentMode === "personal") params.set("session_id", sessionId);
    
    const url = `${API}/files?${params.toString()}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    
    fileList.innerHTML = "";

    if (!data.files || data.files.length === 0) {
      emptyFileHint.style.display = "block";
      // remove old delete all button if exists
      document.getElementById("delete-all-btn")?.remove();
      return;
    }
    emptyFileHint.style.display = "none";
    
    data.files.forEach((f) => {
      const li = document.createElement("li");
      li.style.display = "flex";
      li.style.justifyContent = "space-between";
      li.style.alignItems = "center";
      
      const safeName = escapeHtml(f);
      const safeJsName = f.replace(/'/g, "\\'").replace(/"/g, '&quot;');
      
      if (currentMode === "personal") {
        li.innerHTML = `<span><i class="fa-solid fa-file-lines"></i> ${safeName}</span>
                        <button onclick="deleteFile('${safeJsName}')" style="background:#ff4444;color:white;border:none;padding:3px 8px;border-radius:4px;cursor:pointer;">🗑️ Delete</button>`;
      } else {
        // University mode - NO delete button
        li.innerHTML = `<span><i class="fa-solid fa-file-lines"></i> ${safeName}</span>`;
      }
      fileList.appendChild(li);
    });

    // Only in personal mode
    if (currentMode === "personal") {
      document.getElementById("delete-all-btn")?.remove();
      const delAll = document.createElement("button");
      delAll.id = "delete-all-btn";
      delAll.textContent = "Delete All Files";
      delAll.style = "margin-top:10px;background:#d32f2f;color:white;padding:6px 12px;border:none;cursor:pointer;width:100%;";
      delAll.onclick = deleteAllFiles;
      fileList.parentElement.appendChild(delAll);
    } else {
      document.getElementById("delete-all-btn")?.remove();
    }

  } catch (err) {
    console.error("Failed to load files:", err);
  }
}

async function deleteFile(filename) {
  if (!confirm(`Delete ${filename}?`)) return;
  await fetch(`${API}/files?mode=personal&session_id=${sessionId}&filename=${encodeURIComponent(filename)}`, { method: "DELETE" });
  loadFiles();
}

async function deleteAllFiles() {
  if (!confirm("Delete ALL your personal documents?")) return;
  await fetch(`${API}/session/${sessionId}`, { method: "DELETE" });
  loadFiles();
}

// --- Upload (personal mode only) ---
fileInput?.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  status.textContent = "Uploading & embedding...";
  const form = new FormData();
  form.append("file", file);
  form.append("session_id", sessionId);

  try {
    const res = await fetch(`${API}/upload`, { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    status.textContent = data.message || "Uploaded!";
    await loadFiles();
  } catch (err) {
    status.textContent = "Upload failed. Is the backend running?";
    console.error(err);
  } finally {
    fileInput.value = "";
    setTimeout(() => (status.textContent = ""), 4000);
  }
});

// --- Chat rendering ---
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderChat() {
  chatSection.innerHTML = "";
  chatHistory[currentMode].forEach((msg) => {
    const div = document.createElement("div");
    div.className = `message ${msg.type}`;
    div.innerHTML = escapeHtml(msg.text).replace(/\n/g, "<br>");
    if (msg.sources && msg.sources.length) {
      div.innerHTML += `<div class="source">Sources: ${msg.sources.map(escapeHtml).join(", ")}</div>`;
    }
    chatSection.appendChild(div);
  });
  chatSection.scrollTop = chatSection.scrollHeight;
}

function addMessage(text, type, sources = []) {
  chatHistory[currentMode].push({ text, type, sources });
  renderChat();
}

// --- Ask ---
async function ask() {
  const q = queryInput.value.trim();
  if (!q) return;

  addMessage(q, "user");
  queryInput.value = "";
  queryInput.disabled = true;
  sendBtn.disabled = true;

  chatHistory[currentMode].push({ text: "Thinking...", type: "bot thinking", sources: [] });
  renderChat();

  try {
    const res = await fetch(`${API}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: q,
        mode: currentMode,
        session_id: currentMode === "personal" ? sessionId : null,
      }),
    });
    const data = await res.json();
    chatHistory[currentMode].pop(); // remove "Thinking..."

    if (!res.ok) {
      addMessage(data.detail || "Something went wrong.", "bot");
    } else {
      addMessage(data.answer, "bot", data.sources || []);
    }
  } catch (err) {
    chatHistory[currentMode].pop();
    addMessage("Couldn't reach the server. Is the backend running?", "bot");
    console.error(err);
  } finally {
    queryInput.disabled = false;
    sendBtn.disabled = false;
    queryInput.focus();
  }
}

sendBtn?.addEventListener("click", ask);
queryInput?.addEventListener("keypress", (e) => {
  if (e.key === "Enter") ask();
});

// --- Init ---
applyModeUI();
renderChat();
loadFiles();
