// StudyForge frontend logic. No build step — open index.html or serve statically.

const state = {
  kit: null,                 // { id, title, summary, concepts, flashcards, quiz, short_answer }
  qaHistory: [],
  masteryByConceptId: {},    // 'c1' -> 'raw' | 'mastered' | 'reviewing'
  flashIndex: 0,
  quizIndex: 0,
  quizQuestions: [],
  quizCorrectCount: 0,
  quizAnswered: false,
};

window.API_BASE_URL = "https://studyforge-pm3c.onrender.com";

// ---------- Identity: guest UUID + optional login token ----------

function getGuestId() {
  let id = localStorage.getItem("studyforge_guest_id");
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) || `guest-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    localStorage.setItem("studyforge_guest_id", id);
  }
  return id;
}

function getToken() {
  return localStorage.getItem("studyforge_token");
}

function getEmail() {
  return localStorage.getItem("studyforge_email");
}

function setSession(token, email) {
  localStorage.setItem("studyforge_token", token);
  localStorage.setItem("studyforge_email", email);
  renderAuthArea();
}

function clearSession() {
  localStorage.removeItem("studyforge_token");
  localStorage.removeItem("studyforge_email");
  renderAuthArea();
}

function identityHeaders(includeJson) {
  const headers = {};
  if (includeJson) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  else headers["X-Guest-Id"] = getGuestId();
  return headers;
}

// ---------- Element refs ----------

const el = {
  history: document.getElementById("history"),
  historyList: document.getElementById("history-list"),
  historyEmpty: document.getElementById("history-empty"),
  historyBtn: document.getElementById("history-btn"),
  historyClose: document.getElementById("history-close"),
  intake: document.getElementById("intake"),
  loading: document.getElementById("loading"),
  workshop: document.getElementById("workshop"),
  sourceText: document.getElementById("source-text"),
  charCount: document.getElementById("char-count"),
  forgeBtn: document.getElementById("forge-btn"),
  intakeError: document.getElementById("intake-error"),
  loadingLabel: document.getElementById("loading-label"),
  loadingSublabel: document.getElementById("loading-sublabel"),
  fileInput: document.getElementById("file-input"),
  dropzoneLabel: document.getElementById("dropzone-label"),
  kitTitle: document.getElementById("kit-title"),
  restartBtn: document.getElementById("restart-btn"),
  summaryText: document.getElementById("summary-text"),
  conceptTree: document.getElementById("concept-tree"),
  flashQ: document.getElementById("flash-q"),
  flashA: document.getElementById("flash-a"),
  flashcard: document.getElementById("flashcard"),
  flashPosition: document.getElementById("flash-position"),
  flashPrev: document.getElementById("flash-prev"),
  flashNext: document.getElementById("flash-next"),
  quizProgress: document.getElementById("quiz-progress"),
  quizBody: document.getElementById("quiz-body"),
  quizComplete: document.getElementById("quiz-complete"),
  quizScore: document.getElementById("quiz-score"),
  retryWeak: document.getElementById("retry-weak"),
  shortAnswerList: document.getElementById("short-answer-list"),
  askThread: document.getElementById("ask-thread"),
  askForm: document.getElementById("ask-form"),
  askInput: document.getElementById("ask-input"),
  themeSelect: document.getElementById("theme-select"),
  authArea: document.getElementById("auth-area"),
  authModal: document.getElementById("auth-modal"),
  authForm: document.getElementById("auth-form"),
  authEmail: document.getElementById("auth-email"),
  authPassword: document.getElementById("auth-password"),
  authError: document.getElementById("auth-error"),
  authSubmit: document.getElementById("auth-submit"),
  authCancel: document.getElementById("auth-cancel"),
  authModalTitle: document.getElementById("auth-modal-title"),
};

// ---------- Theme ----------

el.themeSelect.value = localStorage.getItem("studyforge_theme") || "forge";
el.themeSelect.addEventListener("change", () => {
  const theme = el.themeSelect.value;
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("studyforge_theme", theme);
});

// ---------- Auth UI ----------

/*function renderAuthArea() {
  const email = getEmail();
  el.authArea.innerHTML = "";
  if (email) {
    const span = document.createElement("span");
    span.textContent = email;
    const logoutBtn = document.createElement("button");
    logoutBtn.className = "btn-ghost";
    logoutBtn.textContent = "Log out";
    logoutBtn.addEventListener("click", clearSession);
    el.authArea.appendChild(span);
    el.authArea.appendChild(logoutBtn);
  } else {
    const loginBtn = document.createElement("button");
    loginBtn.className = "btn-ghost";
    loginBtn.textContent = "Log in";
    loginBtn.addEventListener("click", () => openAuthModal("login"));
    el.authArea.appendChild(loginBtn);
  }
}

let authMode = "login";

function openAuthModal(mode) {
  authMode = mode;
  document.querySelectorAll(".modal-tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.mode === mode);
  });
  el.authModalTitle.textContent = mode === "login" ? "Log in" : "Sign up";
  el.authSubmit.textContent = mode === "login" ? "Log in" : "Sign up";
  el.authError.hidden = true;
  el.authForm.reset();
  el.authModal.hidden = false;
}

document.querySelectorAll(".modal-tab").forEach((tab) => {
  tab.addEventListener("click", () => openAuthModal(tab.dataset.mode));
});

el.authCancel.addEventListener("click", () => (el.authModal.hidden = true));

el.authForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  el.authError.hidden = true;
  const email = el.authEmail.value.trim();
  const password = el.authPassword.value;
  const endpoint = authMode === "login" ? "/api/auth/login" : "/api/auth/signup";

  try {
    const res = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "POST",
      headers: identityHeaders(true),
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Something went wrong.");
    setSession(data.token, data.email);
    el.authModal.hidden = true;
    if (!el.history.hidden) loadHistory();
  } catch (err) {
    el.authError.textContent = err.message;
    el.authError.hidden = false;
  }
});
*/
// ---------- History ----------

el.historyBtn.addEventListener("click", () => {
  setStage("history");
  loadHistory();
});
el.historyClose.addEventListener("click", () => setStage("intake"));

async function loadHistory() {
  el.historyList.innerHTML = "";
  el.historyEmpty.hidden = true;
  try {
    const res = await fetch(`${API_BASE_URL}/api/kits`, { headers: identityHeaders(false) });
    if (!res.ok) throw new Error("Could not load history.");
    const data = await res.json();
    if (!data.kits.length) {
      el.historyEmpty.hidden = false;
      return;
    }
    data.kits.forEach((k) => el.historyList.appendChild(buildHistoryItem(k)));
  } catch (err) {
    el.historyEmpty.textContent = err.message;
    el.historyEmpty.hidden = false;
  }
}

function buildHistoryItem(k) {
  const li = document.createElement("li");
  li.className = "history-item";

  const body = document.createElement("div");
  body.style.flex = "1";
  const date = new Date(k.created_at).toLocaleString();
  body.innerHTML = `
    <p class="history-item-title">${escapeHtml(k.title || "Untitled study kit")}</p>
    <p class="history-item-meta">${date} &middot; ${k.concept_count} concepts</p>
    <p class="history-item-preview">${escapeHtml(k.summary_preview)}${k.summary_preview.length >= 160 ? "\u2026" : ""}</p>
  `;
  body.addEventListener("click", () => openKit(k.id));

  const delBtn = document.createElement("button");
  delBtn.className = "history-delete";
  delBtn.textContent = "Delete";
  delBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!confirm("Delete this study kit? This can't be undone.")) return;
    await fetch(`${API_BASE_URL}/api/kits/${k.id}`, { method: "DELETE", headers: identityHeaders(false) });
    loadHistory();
  });

  li.appendChild(body);
  li.appendChild(delBtn);
  return li;
}

async function openKit(kitId) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/kits/${kitId}`, { headers: identityHeaders(false) });
    if (!res.ok) throw new Error("Could not open that study kit.");
    const data = await res.json();
    state.kit = data.kit;
    state.qaHistory = data.qa_history || [];
    state.masteryByConceptId = {};
    (state.kit.concepts || []).forEach((c) => (state.masteryByConceptId[c.id] = "raw"));
    renderWorkshop();
    setStage("workshop");
  } catch (err) {
    alert(err.message);
  }
}

// ---------- Input tabs (paste vs file) ----------

document.querySelectorAll(".input-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".input-tab").forEach((t) => {
      t.classList.remove("active");
      t.setAttribute("aria-selected", "false");
    });
    tab.classList.add("active");
    tab.setAttribute("aria-selected", "true");
    const target = tab.dataset.tab;
    document.querySelectorAll(".input-panel").forEach((p) => {
      p.hidden = p.dataset.panel !== target;
    });
  });
});

el.sourceText.addEventListener("input", () => {
  el.charCount.textContent = `${el.sourceText.value.length} characters`;
});

let uploadedFile = null;
el.fileInput.addEventListener("change", () => {
  const file = el.fileInput.files[0];
  if (file) {
    uploadedFile = file;
    el.dropzoneLabel.textContent = file.name;
  }
});

// ---------- Forge (submit) ----------

el.forgeBtn.addEventListener("click", async () => {
  el.intakeError.hidden = true;
  const pasteActive = document.querySelector('.input-tab[data-tab="paste"]').classList.contains("active");

  if (pasteActive) {
    const text = el.sourceText.value.trim();
    if (text.length < 40) {
      showIntakeError("Paste at least a few sentences of material — enough for StudyForge to work with.");
      return;
    }
    await runPipeline({ text });
  } else {
    if (!uploadedFile) {
      showIntakeError("Choose a .txt or .pdf file first.");
      return;
    }
    await runPipeline({ file: uploadedFile });
  }
});

function showIntakeError(msg) {
  el.intakeError.textContent = msg;
  el.intakeError.hidden = false;
}

async function runPipeline({ text, file }) {
  setStage("loading");
  el.loadingLabel.textContent = "Starting up\u2026";
  el.loadingSublabel.textContent = "Longer material runs in several passes so nothing gets skipped.";

  try {
    let startRes;
    if (file) {
      const formData = new FormData();
      formData.append("file", file);
      startRes = await fetch(`${API_BASE_URL}/api/process-file`, {
        method: "POST",
        headers: identityHeaders(false),
        body: formData,
      });
    } else {
      startRes = await fetch(`${API_BASE_URL}/api/process`, {
        method: "POST",
        headers: identityHeaders(true),
        body: JSON.stringify({ text }),
      });
    }

    if (!startRes.ok) {
      const errBody = await startRes.json().catch(() => ({}));
      throw new Error(errBody.detail || `Request failed (${startRes.status})`);
    }

    const { job_id } = await startRes.json();
    const kit = await pollJob(job_id);

    state.kit = kit;
    state.qaHistory = [];
    state.masteryByConceptId = {};
    (kit.concepts || []).forEach((c) => (state.masteryByConceptId[c.id] = "raw"));

    renderWorkshop();
    setStage("workshop");
  } catch (err) {
    setStage("intake");
    showIntakeError(err.message || "Something went wrong forging the study kit. Check the backend is running.");
  }
}

function pollJob(jobId) {
  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`);
        if (!res.ok) throw new Error("Lost track of that job.");
        const job = await res.json();
        el.loadingLabel.textContent = job.label || "Working\u2026";

        if (job.done) {
          clearInterval(interval);
          if (job.error) reject(new Error(job.error));
          else resolve(job.result);
        }
      } catch (err) {
        clearInterval(interval);
        reject(err);
      }
    }, 900);
  });
}

function setStage(stage) {
  el.intake.hidden = stage !== "intake";
  el.loading.hidden = stage !== "loading";
  el.workshop.hidden = stage !== "workshop";
  el.history.hidden = stage !== "history";
}

el.restartBtn.addEventListener("click", () => {
  state.kit = null;
  state.masteryByConceptId = {};
  el.sourceText.value = "";
  el.charCount.textContent = "0 characters";
  uploadedFile = null;
  el.dropzoneLabel.textContent = "Drop a .txt or .pdf file, or click to browse";
  setStage("intake");
});

// ---------- Workshop tabs ----------

document.querySelectorAll(".ws-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".ws-tab").forEach((t) => {
      t.classList.remove("active");
      t.setAttribute("aria-selected", "false");
    });
    tab.classList.add("active");
    tab.setAttribute("aria-selected", "true");
    document.querySelectorAll(".ws-panel").forEach((p) => {
      p.hidden = p.id !== tab.dataset.target;
    });
  });
});

// ---------- Render: workshop root ----------

function renderWorkshop() {
  const kit = state.kit;
  el.kitTitle.textContent = kit.title || "Your study kit";
  el.summaryText.textContent = kit.summary || "";

  renderConceptTree();
  state.flashIndex = 0;
  renderFlashcard();

  state.quizQuestions = kit.quiz || [];
  state.quizIndex = 0;
  state.quizCorrectCount = 0;
  el.quizComplete.hidden = true;
  renderQuizQuestion();

  renderShortAnswerList();
  renderAskThread();

  // Reset to the first tab each time a kit is opened.
  document.querySelectorAll(".ws-tab").forEach((t, i) => {
    t.classList.toggle("active", i === 0);
    t.setAttribute("aria-selected", i === 0 ? "true" : "false");
  });
  document.querySelectorAll(".ws-panel").forEach((p, i) => (p.hidden = i !== 0));
}

// ---------- Concept map ----------

function renderConceptTree() {
  const concepts = state.kit.concepts || [];
  const byParent = {};
  concepts.forEach((c) => {
    const key = c.parent_id || "root";
    (byParent[key] = byParent[key] || []).push(c);
  });

  el.conceptTree.innerHTML = "";
  (byParent["root"] || []).forEach((c) => el.conceptTree.appendChild(buildConceptNode(c, byParent)));
}

function buildConceptNode(concept, byParent) {
  const li = document.createElement("li");
  const node = document.createElement("div");
  node.className = "concept-node";
  node.dataset.conceptId = concept.id;

  const gauge = document.createElement("span");
  gauge.className = "gauge";
  applyGaugeClass(gauge, state.masteryByConceptId[concept.id]);

  const body = document.createElement("div");
  body.className = "concept-node-body";
  body.innerHTML = `<p class="concept-node-title">${escapeHtml(concept.title)}</p>
                     <p class="concept-node-desc">${escapeHtml(concept.description)}</p>`;

  node.appendChild(gauge);
  node.appendChild(body);
  li.appendChild(node);

  const children = byParent[concept.id];
  if (children && children.length) {
    const ul = document.createElement("ul");
    children.forEach((child) => ul.appendChild(buildConceptNode(child, byParent)));
    li.appendChild(ul);
  }
  return li;
}

function applyGaugeClass(gaugeEl, mastery) {
  gaugeEl.classList.remove("mastered", "steel");
  if (mastery === "mastered") gaugeEl.classList.add("mastered");
  else if (mastery === "reviewing") gaugeEl.classList.add("steel");
}

function refreshGauge(conceptId) {
  const node = el.conceptTree.querySelector(`[data-concept-id="${cssEscape(conceptId)}"] .gauge`);
  if (node) applyGaugeClass(node, state.masteryByConceptId[conceptId]);
}

// ---------- Flashcards ----------

function renderFlashcard() {
  const cards = state.kit.flashcards || [];
  if (!cards.length) {
    el.flashQ.textContent = "No flashcards were generated for this material.";
    el.flashA.textContent = "";
    el.flashPosition.textContent = "";
    return;
  }
  const card = cards[state.flashIndex];
  el.flashcard.classList.remove("flipped");
  el.flashQ.textContent = card.question;
  el.flashA.textContent = card.answer;
  el.flashPosition.textContent = `${state.flashIndex + 1} / ${cards.length}`;
}

el.flashcard.addEventListener("click", () => el.flashcard.classList.toggle("flipped"));
el.flashcard.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    el.flashcard.classList.toggle("flipped");
  }
});

el.flashPrev.addEventListener("click", () => {
  const cards = state.kit.flashcards || [];
  if (!cards.length) return;
  state.flashIndex = (state.flashIndex - 1 + cards.length) % cards.length;
  renderFlashcard();
});

el.flashNext.addEventListener("click", () => {
  const cards = state.kit.flashcards || [];
  if (!cards.length) return;
  state.flashIndex = (state.flashIndex + 1) % cards.length;
  renderFlashcard();
});

// ---------- Quiz ----------

function renderQuizQuestion() {
  const questions = state.quizQuestions;
  el.quizComplete.hidden = true;
  el.quizBody.hidden = false;

  if (!questions.length) {
    el.quizBody.innerHTML = `<p class="panel-hint">No quiz questions were generated for this material.</p>`;
    return;
  }

  if (state.quizIndex >= questions.length) {
    finishQuiz();
    return;
  }

  const q = questions[state.quizIndex];
  const concept = (state.kit.concepts || []).find((c) => c.id === q.concept_id);
  state.quizAnswered = false;

  el.quizProgress.textContent = `Question ${state.quizIndex + 1} of ${questions.length}`;

  const wrap = document.createElement("div");
  wrap.className = "quiz-question";

  const conceptLabel = document.createElement("p");
  conceptLabel.className = "quiz-question-concept";
  conceptLabel.textContent = concept ? concept.title : "Concept check";
  wrap.appendChild(conceptLabel);

  const questionText = document.createElement("p");
  questionText.className = "quiz-question-text";
  questionText.textContent = q.question;
  wrap.appendChild(questionText);

  q.options.forEach((option, idx) => {
    const btn = document.createElement("button");
    btn.className = "quiz-option";
    btn.textContent = option;
    btn.addEventListener("click", () => handleQuizAnswer(idx, q, concept, wrap));
    wrap.appendChild(btn);
  });

  el.quizBody.innerHTML = "";
  el.quizBody.appendChild(wrap);
}

async function handleQuizAnswer(selectedIdx, question, concept, wrapEl) {
  if (state.quizAnswered) return;
  state.quizAnswered = true;

  const options = wrapEl.querySelectorAll(".quiz-option");
  const isCorrect = selectedIdx === question.correct_index;

  options.forEach((btn, idx) => {
    btn.disabled = true;
    if (idx === question.correct_index) btn.classList.add("correct");
    if (idx === selectedIdx && !isCorrect) btn.classList.add("incorrect");
  });

  if (isCorrect) {
    state.quizCorrectCount += 1;
    if (concept) {
      state.masteryByConceptId[concept.id] = "mastered";
      refreshGauge(concept.id);
    }
    appendQuizNextControl(wrapEl);
    return;
  }

  if (concept) {
    state.masteryByConceptId[concept.id] = "reviewing";
    refreshGauge(concept.id);
  }

  const feedback = document.createElement("div");
  feedback.className = "quiz-feedback";
  feedback.innerHTML = `<p class="quiz-feedback-loading">Forging a targeted explanation\u2026</p>`;
  wrapEl.appendChild(feedback);

  try {
    const res = await fetch(`${API_BASE_URL}/api/explain`, {
      method: "POST",
      headers: identityHeaders(true),
      body: JSON.stringify({
        kit_id: state.kit.id,
        concept_id: concept ? concept.id : null,
        concept_title: concept ? concept.title : "",
        concept_description: concept ? concept.description : "",
        question: question.question,
        student_answer: question.options[selectedIdx],
        correct_answer: question.options[question.correct_index],
      }),
    });
    if (!res.ok) throw new Error("explain request failed");
    const data = await res.json();
    feedback.innerHTML = `
      <h3>Let's rebuild this one</h3>
      <p>${escapeHtml(data.explanation || "")}</p>
      ${data.analogy ? `<p class="analogy">${escapeHtml(data.analogy)}</p>` : ""}
    `;
  } catch (err) {
    feedback.innerHTML = `<p class="quiz-feedback-loading">Couldn't reach the explanation service. Check your backend is running.</p>`;
  }

  appendQuizNextControl(wrapEl);
}

function appendQuizNextControl(wrapEl) {
  const btn = document.createElement("button");
  btn.className = "btn-primary quiz-next-btn";
  const questions = state.quizQuestions;
  btn.textContent = state.quizIndex + 1 >= questions.length ? "See results" : "Next question";
  btn.addEventListener("click", () => {
    state.quizIndex += 1;
    renderQuizQuestion();
  });
  wrapEl.appendChild(btn);
}

function finishQuiz() {
  el.quizBody.hidden = true;
  el.quizComplete.hidden = false;
  const total = state.quizQuestions.length;
  el.quizScore.textContent = `${state.quizCorrectCount} / ${total} correct on the first try.`;
}

el.retryWeak.addEventListener("click", () => {
  const weakConceptIds = Object.keys(state.masteryByConceptId).filter(
    (id) => state.masteryByConceptId[id] !== "mastered"
  );
  const weakQuestions = (state.kit.quiz || []).filter((q) => weakConceptIds.includes(q.concept_id));

  if (!weakQuestions.length) {
    el.quizScore.textContent = "Every concept is mastered. Nothing left to retry.";
    return;
  }

  state.quizQuestions = weakQuestions;
  state.quizIndex = 0;
  state.quizCorrectCount = 0;
  el.quizComplete.hidden = true;
  renderQuizQuestion();
});

// ---------- Short answer ----------

function renderShortAnswerList() {
  const items = state.kit.short_answer || [];
  el.shortAnswerList.innerHTML = "";

  if (!items.length) {
    el.shortAnswerList.innerHTML = `<p class="panel-hint">No short-answer questions were generated for this material.</p>`;
    return;
  }

  items.forEach((item, idx) => {
    const wrap = document.createElement("div");
    wrap.className = "short-answer-item";

    const q = document.createElement("p");
    q.className = "short-answer-question";
    q.textContent = `${idx + 1}. ${item.question}`;
    wrap.appendChild(q);

    const textarea = document.createElement("textarea");
    textarea.placeholder = "Write your answer in your own words\u2026";
    wrap.appendChild(textarea);

    const submitBtn = document.createElement("button");
    submitBtn.className = "btn-primary short-answer-submit";
    submitBtn.textContent = "Check my answer";
    wrap.appendChild(submitBtn);

    const feedback = document.createElement("div");
    feedback.className = "short-answer-feedback";
    feedback.hidden = true;
    wrap.appendChild(feedback);

    submitBtn.addEventListener("click", async () => {
      const answer = textarea.value.trim();
      if (!answer) return;
      submitBtn.disabled = true;
      submitBtn.textContent = "Checking\u2026";

      try {
        const res = await fetch(`${API_BASE_URL}/api/kits/${state.kit.id}/grade-short-answer`, {
          method: "POST",
          headers: identityHeaders(true),
          body: JSON.stringify({ question_index: idx, student_answer: answer }),
        });
        if (!res.ok) throw new Error("Grading failed.");
        const data = await res.json();

        const verdictClass =
          data.verdict === "correct" ? "verdict-correct" : data.verdict === "partial" ? "verdict-partial" : "verdict-incorrect";
        const verdictLabel = data.verdict === "correct" ? "Correct" : data.verdict === "partial" ? "Partially correct" : "Needs work";

        feedback.innerHTML = `<span class="verdict-badge ${verdictClass}">${verdictLabel}</span><p>${escapeHtml(data.feedback || "")}</p>`;
        feedback.hidden = false;

        if (item.concept_id) {
          state.masteryByConceptId[item.concept_id] = data.verdict === "correct" ? "mastered" : "reviewing";
          refreshGauge(item.concept_id);
        }
      } catch (err) {
        feedback.innerHTML = `<p>Couldn't grade that answer. Check your backend is running.</p>`;
        feedback.hidden = false;
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Check my answer";
      }
    });

    el.shortAnswerList.appendChild(wrap);
  });
}

// ---------- Ask tab ----------

function renderAskThread() {
  el.askThread.innerHTML = "";
  state.qaHistory.forEach((qa) => appendAskExchange(qa.question, qa.answer));
}

function appendAskExchange(question, answer) {
  const item = document.createElement("div");
  item.className = "ask-item";
  const q = document.createElement("div");
  q.className = "ask-question";
  q.textContent = question;
  const a = document.createElement("div");
  a.className = "ask-answer";
  a.textContent = answer;
  item.appendChild(q);
  item.appendChild(a);
  el.askThread.appendChild(item);
  el.askThread.scrollTop = el.askThread.scrollHeight;
  return a;
}

el.askForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = el.askInput.value.trim();
  if (!question || !state.kit) return;
  el.askInput.value = "";
  el.askInput.disabled = true;

  const answerEl = appendAskExchange(question, "");
  answerEl.classList.add("ask-loading");
  answerEl.textContent = "Thinking\u2026";

  try {
    const res = await fetch(`${API_BASE_URL}/api/kits/${state.kit.id}/ask`, {
      method: "POST",
      headers: identityHeaders(true),
      body: JSON.stringify({ question }),
    });
    if (!res.ok) throw new Error("Could not get an answer.");
    const data = await res.json();
    answerEl.classList.remove("ask-loading");
    answerEl.textContent = data.answer;
    state.qaHistory.push({ question, answer: data.answer });
  } catch (err) {
    answerEl.classList.remove("ask-loading");
    answerEl.textContent = "Couldn't reach the server for an answer. Check your backend is running.";
  } finally {
    el.askInput.disabled = false;
    el.askInput.focus();
  }
});

// ---------- Helpers ----------

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

function cssEscape(str) {
  return String(str).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

// ---------- Init ----------

renderAuthArea();