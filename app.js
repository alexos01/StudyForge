// StudyForge frontend logic. No build step — open index.html or serve statically.

const state = {
  sourceText: "",
  kit: null,               // { title, summary, concepts, flashcards, quiz }
  masteryByConceptId: {},  // 'c1' -> 'raw' | 'mastered' | 'reviewing'
  flashIndex: 0,
  quizIndex: 0,
  quizQuestions: [],
  quizCorrectCount: 0,
  quizAnswered: false,
};

window.API_BASE_URL = "https://studyforge-pm3c.onrender.com";

const loadingMessages = [
  "Heating the material\u2026",
  "Extracting the core concepts\u2026",
  "Hammering out flashcards\u2026",
  "Tempering the quiz\u2026",
];

// ---------- Element refs ----------

const el = {
  intake: document.getElementById("intake"),
  loading: document.getElementById("loading"),
  workshop: document.getElementById("workshop"),
  sourceText: document.getElementById("source-text"),
  charCount: document.getElementById("char-count"),
  forgeBtn: document.getElementById("forge-btn"),
  intakeError: document.getElementById("intake-error"),
  loadingLabel: document.getElementById("loading-label"),
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
};

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
    state.sourceText = text;
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
  cycleLoadingMessages();

  try {
    let response;
    if (file) {
      const formData = new FormData();
      formData.append("file", file);
      response = await fetch(`${API_BASE_URL}/api/process-file`, {
        method: "POST",
        body: formData,
      });
    } else {
      response = await fetch(`${API_BASE_URL}/api/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      state.sourceText = text;
    }

    if (!response.ok) {
      const errBody = await response.json().catch(() => ({}));
      throw new Error(errBody.detail || `Request failed (${response.status})`);
    }

    const kit = await response.json();
    state.kit = kit;
    state.masteryByConceptId = {};
    (kit.concepts || []).forEach((c) => (state.masteryByConceptId[c.id] = "raw"));

    renderWorkshop();
    setStage("workshop");
  } catch (err) {
    setStage("intake");
    showIntakeError(err.message || "Something went wrong forging the study kit. Check the backend is running.");
  }
}

let loadingInterval;
function cycleLoadingMessages() {
  let i = 0;
  el.loadingLabel.textContent = loadingMessages[0];
  clearInterval(loadingInterval);
  loadingInterval = setInterval(() => {
    i = (i + 1) % loadingMessages.length;
    el.loadingLabel.textContent = loadingMessages[i];
  }, 1600);
}

function setStage(stage) {
  el.intake.hidden = stage !== "intake";
  el.loading.hidden = stage !== "loading";
  el.workshop.hidden = stage !== "workshop";
  if (stage !== "loading") clearInterval(loadingInterval);
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
  (byParent["root"] || []).forEach((c) => {
    el.conceptTree.appendChild(buildConceptNode(c, byParent));
  });
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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_text: state.sourceText,
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

// ---------- Helpers ----------

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

function cssEscape(str) {
  return String(str).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}