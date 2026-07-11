(function () {
  "use strict";

  function getCookie(name) {
    return document.cookie.split(";").map(v => v.trim()).find(v => v.startsWith(name + "="))?.slice(name.length + 1) || "";
  }

  async function apiFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(options.method || "GET")) headers.set("X-CSRFToken", decodeURIComponent(getCookie("csrftoken")));
    const response = await fetch(url, { credentials: "same-origin", ...options, headers });
    let data = null;
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok) throw new Error(data.detail || "Не удалось выполнить запрос. Попробуй ещё раз.");
    return data;
  }
  window.apiFetch = apiFetch;

  function openInitialDialog() {
    const dialog = document.querySelector("dialog[data-auto-open]");
    if (dialog && !dialog.open) dialog.showModal();
  }
  openInitialDialog();

  document.addEventListener("click", async event => {
    const startMockButton = event.target.closest("[data-start-mock]");
    if (startMockButton) {
      startMockButton.disabled = true;
      try {
        const data = await apiFetch(startMockButton.dataset.startMock, { method: "POST", body: "{}" });
        window.location.assign(`/mocks/run/${data.result_id}/`);
      } catch (error) { startMockButton.disabled = false; alert(error.message); }
    }

    const aiLogButton = event.target.closest("[data-parent-ai-log]");
    if (aiLogButton) {
      const dialog = document.getElementById("parent-ai-log"), content = dialog.querySelector("[data-parent-ai-content]");
      dialog.showModal(); content.textContent = "Загрузка…";
      try {
        const sessions = await apiFetch(aiLogButton.dataset.parentAiLog);
        content.replaceChildren();
        if (!sessions.length) content.textContent = "Переписки пока нет.";
        sessions.forEach(session => {
          const button = document.createElement("button");
          button.type = "button"; button.className = "dialog-card ai-session-button";
          button.dataset.aiSession = `${aiLogButton.dataset.parentAiLog}?session=${session.id}`;
          button.textContent = `${session.assignment} · подсказок: ${session.hints_used}`;
          content.append(button);
        });
      } catch (error) { content.textContent = error.message; }
    }

    const sessionButton = event.target.closest("[data-ai-session]");
    if (sessionButton) {
      const content = document.querySelector("[data-parent-ai-content]");
      try {
        const session = await apiFetch(sessionButton.dataset.aiSession);
        content.replaceChildren();
        const title = document.createElement("h3"); title.textContent = session.assignment; content.append(title);
        session.messages.forEach(item => { const message = document.createElement("p"); message.className = `message ${item.role === "student" ? "message-student" : "message-mentor"}`; message.textContent = item.text; content.append(message); });
      } catch (error) { content.textContent = error.message; }
    }
    const openButton = event.target.closest("[data-open-dialog]");
    if (openButton) document.getElementById(openButton.dataset.openDialog)?.showModal();
    const closeButton = event.target.closest("[data-close-dialog]");
    if (closeButton) closeButton.closest("dialog")?.close();

    const ackButton = event.target.closest("[data-ack-dialog]");
    if (ackButton) {
      const dialog = ackButton.closest("dialog");
      ackButton.disabled = true;
      try {
        await Promise.all([...dialog.querySelectorAll("[data-ack-url]")].map(item => apiFetch(item.dataset.ackUrl, { method: "POST", body: "{}" })));
        dialog.close();
        document.getElementById("week-plan-dialog")?.showModal();
      } catch (error) {
        const output = dialog.querySelector("[data-dialog-error]"); output.hidden = false; output.textContent = error.message; ackButton.disabled = false;
      }
    }

    const planButton = event.target.closest("[data-complete-plan]");
    if (planButton) {
      planButton.disabled = true;
      try { await apiFetch(planButton.dataset.completePlan, { method: "POST", body: "{}" }); planButton.closest("[data-plan-item]").classList.add("is-done"); planButton.remove(); }
      catch (error) { planButton.disabled = false; alert(error.message); }
    }

    const reviewButton = event.target.closest("[data-review-complete]");
    if (reviewButton) {
      const item = reviewButton.closest("[data-review-item]");
      item.querySelectorAll("button").forEach(button => button.disabled = true);
      try {
        const data = await apiFetch(reviewButton.dataset.reviewComplete, { method: "POST", body: JSON.stringify({ success: reviewButton.dataset.success === "true" }) });
        const result = item.querySelector("[data-review-result]"); result.hidden = false; result.classList.add(reviewButton.dataset.success === "true" ? "is-correct" : "is-wrong"); result.textContent = data.message || (reviewButton.dataset.success === "true" ? "Повтор зачтён." : "Ошибка вернётся по новому расписанию.");
      } catch (error) { item.querySelectorAll("button").forEach(button => button.disabled = false); alert(error.message); }
    }

    const nextButton = event.target.closest("[data-next-task]");
    if (nextButton) showNextTask(nextButton.closest("[data-task]"));
  });

  function updateTaskProgress() {
    const tasks = [...document.querySelectorAll("[data-task]")];
    if (!tasks.length) return;
    const current = tasks.findIndex(task => !task.classList.contains("is-hidden"));
    const position = current < 0 ? tasks.length : current + 1;
    document.querySelector("[data-task-counter]").textContent = `${position} / ${tasks.length}`;
    document.querySelector("[data-task-progress]").style.width = `${(position / tasks.length) * 100}%`;
  }
  function showNextTask(current) {
    const tasks = [...document.querySelectorAll("[data-task]")], index = tasks.indexOf(current);
    current.classList.add("is-hidden");
    if (tasks[index + 1]) tasks[index + 1].classList.remove("is-hidden"); else document.querySelector("[data-lesson-complete]")?.classList.remove("is-hidden");
    updateTaskProgress(); window.scrollTo({ top: document.querySelector("#tasks")?.offsetTop - 90, behavior: "smooth" });
  }
  updateTaskProgress();

  document.addEventListener("submit", async event => {
    const mockForm = event.target.closest("[data-mock-form]");
    if (mockForm) {
      event.preventDefault();
      if (mockForm.dataset.submitting === "true") return;
      mockForm.dataset.submitting = "true";
      const button = mockForm.querySelector("[type=submit]"), errorOutput = mockForm.querySelector("[data-mock-error]");
      button.disabled = true;
      try {
        for (const task of mockForm.querySelectorAll("[data-part2-assignment]")) {
          const file = task.querySelector("input[type=file]").files[0];
          if (!file) continue;
          const payload = new FormData(); payload.append("assignment", task.dataset.part2Assignment); payload.append("mock_result", mockForm.dataset.resultId); payload.append("file", file);
          await apiFetch("/api/expert-reviews/submit/", { method: "POST", body: payload });
        }
        const answers = {};
        mockForm.querySelectorAll("input[name^=answer_]").forEach(input => { answers[input.name.slice(7)] = input.value; });
        await apiFetch(`/api/mocks/results/${mockForm.dataset.resultId}/submit/`, { method: "POST", body: JSON.stringify({ answers }) });
        window.location.assign(mockForm.dataset.resultUrl);
      } catch (error) { errorOutput.hidden = false; errorOutput.textContent = error.message; button.disabled = false; mockForm.dataset.submitting = "false"; }
    }
    const attemptForm = event.target.closest("[data-attempt-form]");
    if (attemptForm) {
      event.preventDefault(); const task = attemptForm.closest("[data-task]"), button = attemptForm.querySelector("button"), verdict = task.querySelector("[data-verdict]"); button.disabled = true;
      try { const data = await apiFetch(`/api/assignments/${task.dataset.assignmentId}/attempt/`, { method: "POST", body: JSON.stringify({ answer: new FormData(attemptForm).get("answer"), context: attemptForm.dataset.context }) }); verdict.hidden = false; verdict.className = `verdict ${data.is_correct ? "is-correct" : "is-wrong"}`; verdict.textContent = data.is_correct === null ? "Решение отправлено на экспертную проверку." : (data.is_correct ? "Верно! Можно двигаться дальше." : "Пока неверно. Ошибка сохранена для отработки."); task.querySelector("[data-next-task]").hidden = false; }
      catch (error) { verdict.hidden = false; verdict.className = "verdict is-wrong"; verdict.textContent = error.message; button.disabled = false; }
    }
    const hintForm = event.target.closest("[data-hint-form]");
    if (hintForm) {
      event.preventDefault(); const task = hintForm.closest("[data-task]"), button = hintForm.querySelector("button"), input = hintForm.querySelector("input"), history = task.querySelector("[data-mentor-history]"); button.disabled = true;
      const studentMessage = document.createElement("p"); studentMessage.className = "message message-student"; studentMessage.textContent = input.value; history.append(studentMessage);
      try { const data = await apiFetch(`/api/assignments/${task.dataset.assignmentId}/hint/`, { method: "POST", body: JSON.stringify({ question: input.value, context: "lesson" }) }); const message = document.createElement("p"); message.className = "message message-mentor"; message.textContent = data.hint; history.append(message); input.value = ""; if (data.escalated_to_expert) hintForm.remove(); else button.disabled = false; }
      catch (error) { const message = document.createElement("p"); message.className = "form-error"; message.textContent = error.message; history.append(message); button.disabled = false; }
    }
  });

  const hours = document.querySelector("[data-forecast-hours]"), date = document.querySelector("[data-forecast-date]");
  if (hours && date) {
    let timer;
    const refresh = () => { clearTimeout(timer); document.querySelector("[data-hours-output]").textContent = hours.value; timer = setTimeout(async () => { const error = document.querySelector("[data-forecast-error]"); try { const params = new URLSearchParams({ weekly_hours: hours.value }); if (date.value) params.set("exam_date", date.value); const data = await apiFetch(`/api/forecast/?${params}`); document.querySelector("[data-current-score]").textContent = data.current_score; document.querySelector("[data-ceiling-score]").textContent = data.ceiling_score; error.hidden = true; } catch (exception) { error.hidden = false; error.textContent = exception.message; } }, 250); };
    hours.addEventListener("input", refresh); date.addEventListener("change", refresh);
  }

  const mockTimer = document.querySelector("[data-mock-timer]");
  if (mockTimer) {
    const deadline = new Date(mockTimer.dataset.deadline).getTime();
    let timerId;
    const tick = () => {
      const remaining = Math.max(0, deadline - Date.now());
      const totalSeconds = Math.floor(remaining / 1000), hoursLeft = Math.floor(totalSeconds / 3600), minutes = Math.floor(totalSeconds % 3600 / 60), seconds = totalSeconds % 60;
      mockTimer.textContent = `${String(hoursLeft).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
      if (remaining <= 0) { clearInterval(timerId); document.querySelector("[data-mock-form]")?.requestSubmit(); }
    };
    tick(); timerId = setInterval(tick, 1000);
  }
})();
