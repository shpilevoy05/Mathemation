(function () {
  "use strict";

  function getCookie(name) {
    return document.cookie.split(";").map(v => v.trim()).find(v => v.startsWith(name + "="))?.slice(name.length + 1) || "";
  }


  function renderProgress(task, progress) {
    if (!Array.isArray(progress) || !progress.length) return;
    const output = task.querySelector("[data-answer-progress]");
    if (!output) return;
    output.hidden = false;
    output.replaceChildren(...progress.map(node => {
      const line = document.createElement("p");
      const done = node.completed_plan_items || [];
      const planNote = done.length ? ` · пункт плана закрыт` : "";
      line.textContent = `${node.node}: освоение ${node.mastery}% · решено ${node.solved} из ${node.total}${planNote}`;
      return line;
    }));
  }

  async function apiFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(options.method || "GET")) headers.set("X-CSRFToken", decodeURIComponent(getCookie("csrftoken")));
    const response = await fetch(url, { credentials: "same-origin", ...options, headers });
    let data = null;
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok) {
      const firstError = Object.values(data).flat().find(value => typeof value === "string");
      throw new Error(data.detail || firstError || "Не удалось выполнить запрос. Попробуй ещё раз.");
    }
    return data;
  }
  window.apiFetch = apiFetch;

  function openInitialDialog() {
    const dialog = document.querySelector("dialog[data-auto-open]");
    if (dialog && !dialog.open) dialog.showModal();
  }
  openInitialDialog();

  // Подписи шкалы прогноза: при низком или максимальном балле «сейчас»,
  // «цель» и «потолок» сходятся в одну точку. Разводим их по рядам и
  // прижимаем к краю, чтобы ничего не наезжало и не выходило за карточку.
  function layoutGaugeLabels() {
    document.querySelectorAll(".gauge-axis").forEach(axis => {
      const bounds = axis.getBoundingClientRect();
      if (!bounds.width) return;
      const flags = [...axis.querySelectorAll(".gauge-flag")]
        .map(flag => ({ flag, label: flag.querySelector("span"), left: parseFloat(flag.style.left) || 0 }))
        .sort((a, b) => a.left - b.left);
      const placed = [];
      flags.forEach(entry => {
        entry.label.classList.remove("is-left", "is-right");
        entry.flag.removeAttribute("data-row");
        const width = entry.label.getBoundingClientRect().width;
        const centre = bounds.width * entry.left / 100;
        if (centre - width / 2 < 0) entry.label.classList.add("is-left");
        else if (centre + width / 2 > bounds.width) entry.label.classList.add("is-right");
        const start = Math.max(0, Math.min(bounds.width - width, centre - width / 2));
        const end = start + width;
        let row = 0;
        while (placed.some(other => other.row === row && start < other.end + 8 && other.start < end + 8)) row += 1;
        if (row) entry.flag.dataset.row = String(Math.min(row, 2));
        placed.push({ row, start, end });
      });

      const caption = axis.querySelector(".gauge-caption-now");
      if (caption) {
        caption.classList.remove("is-left", "is-right");
        const width = caption.getBoundingClientRect().width;
        const centre = bounds.width * (parseFloat(caption.style.left) || 0) / 100;
        if (centre - width / 2 < 0) caption.classList.add("is-left");
        else if (centre + width / 2 > bounds.width) caption.classList.add("is-right");
      }
    });
  }
  layoutGaugeLabels();
  window.addEventListener("resize", layoutGaugeLabels);

  // Граф карты навыков: координаты приходят с сервера, здесь только отрисовка
  // и подсветка цепочки пререквизитов выбранной темы.
  function renderKnowledgeGraph() {
    const wrap = document.querySelector("[data-graph]"), payload = document.getElementById("graph-data");
    if (!wrap || !payload) return;
    const data = JSON.parse(payload.textContent), svg = wrap.querySelector("svg");
    const NS = "http://www.w3.org/2000/svg", RADIUS = 27, CIRCUMFERENCE = 2 * Math.PI * RADIUS;
    const el = (name, attrs) => {
      const node = document.createElementNS(NS, name);
      Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
      return node;
    };
    const byId = new Map(data.nodes.map(node => [node.id, node]));
    const parents = new Map(data.nodes.map(node => [node.id, []]));
    data.edges.forEach(edge => parents.get(edge.to).push(edge.from));

    const hulls = el("g", {}), edges = el("g", {}), nodes = el("g", {});
    data.clusters.forEach(cluster => {
      hulls.appendChild(el("rect", { class: "cluster-hull", x: cluster.x, y: cluster.y, width: cluster.w, height: cluster.h, rx: 26 }));
      const label = el("text", { class: "cluster-label", x: cluster.x + 20, y: cluster.y + 28 });
      label.textContent = cluster.title;
      hulls.appendChild(label);
    });
    data.edges.forEach(edge => {
      const from = byId.get(edge.from), to = byId.get(edge.to);
      const dx = to.x - from.x, dy = to.y - from.y, length = Math.hypot(dx, dy) || 1;
      const ux = dx / length, uy = dy / length;
      const start = { x: from.x + ux * RADIUS, y: from.y + uy * RADIUS };
      const end = { x: to.x - ux * RADIUS, y: to.y - uy * RADIUS };
      const control = { x: (start.x + end.x) / 2 - uy * 16, y: (start.y + end.y) / 2 + ux * 16 };
      edges.appendChild(el("path", {
        class: `edge ${edge.met ? "met" : "blocked"}`, "data-from": edge.from, "data-to": edge.to,
        d: `M${start.x},${start.y} Q${control.x},${control.y} ${end.x},${end.y}`
      }));
    });
    data.nodes.forEach(node => {
      const group = el("g", {
        class: "gnode", "data-id": node.id, "data-state": node.state, tabindex: "0", role: "button",
        "aria-label": `${node.title}, ${node.state_label}, освоение ${node.mastery} процентов`
      });
      group.appendChild(el("circle", { class: "halo", cx: node.x, cy: node.y, r: RADIUS }));
      if (node.mastery > 0) {
        group.appendChild(el("circle", {
          class: "ring", cx: node.x, cy: node.y, r: RADIUS,
          "stroke-dasharray": `${(CIRCUMFERENCE * node.mastery / 100).toFixed(1)} ${CIRCUMFERENCE.toFixed(1)}`,
          transform: `rotate(-90 ${node.x} ${node.y})`
        }));
      }
      const percent = el("text", { class: "pct", x: node.x, y: node.y + 4 });
      percent.textContent = node.state === "locked" ? "—" : `${node.mastery}%`;
      group.appendChild(percent);
      // Длинные названия рвём по словам: одной строкой они наезжают на
      // соседние темы и на рёбра.
      const name = el("text", { class: "name", x: node.x, y: node.y + RADIUS + 18 });
      const lines = [];
      node.title.split(" ").forEach(word => {
        const last = lines[lines.length - 1];
        if (last && (last + " " + word).length <= 18) lines[lines.length - 1] = last + " " + word;
        else lines.push(word);
      });
      (lines.length > 2 ? [lines[0], lines.slice(1).join(" ")] : lines).forEach((line, index) => {
        const span = el("tspan", { x: node.x, dy: index ? "1.15em" : "0" });
        span.textContent = index === 1 && line.length > 20 ? line.slice(0, 19) + "…" : line;
        name.appendChild(span);
      });
      group.appendChild(name);
      nodes.appendChild(group);
    });
    svg.replaceChildren(hulls, edges, nodes);

    const inspector = document.querySelector("[data-graph-inspector]");
    const parts = inspector && {
      title: inspector.querySelector("[data-ins-title]"), state: inspector.querySelector("[data-ins-state]"),
      why: inspector.querySelector("[data-ins-why]"), bar: inspector.querySelector("[data-ins-bar]"),
      task: inspector.querySelector("[data-ins-task]"), link: inspector.querySelector("[data-ins-link]")
    };
    const describe = node => {
      if (node.state === "locked") {
        const blocker = parents.get(node.id).map(id => byId.get(id)).find(dep => dep.mastery < 70);
        if (blocker) return `Тема закрыта: не хватает освоения в теме «${blocker.title}» — сейчас ${blocker.mastery} %.`;
        return "Тема закрыта пререквизитом.";
      }
      if (node.state === "decayed") return "Тема остыла без повторов. Возврат быстрее, чем изучение заново.";
      if (node.state === "available") return "Пререквизиты закрыты — тему можно брать в план.";
      if (node.state === "mastered") return "Тема освоена. Контрольный повтор запланирован автоматически.";
      return "Тема в работе: порог освоения — 70 %.";
    };
    const STATE_CHIP = {
      mastered: "success-soft", in_progress: "chip-progress", available: "chip-progress",
      decayed: "warning-soft", locked: "chip-locked"
    };
    const show = node => {
      if (!parts) return;
      parts.title.textContent = node.title;
      parts.state.textContent = node.state_label;
      parts.state.className = `chip chip-status ${STATE_CHIP[node.state] || ""}`;
      parts.why.textContent = describe(node);
      parts.bar.style.width = `${Math.max(node.mastery, 2)}%`;
      parts.task.textContent = `Освоение ${node.mastery} %`;
      parts.link.href = node.url;
    };
    const chain = (id, seen = new Set()) => {
      if (seen.has(id)) return seen;
      seen.add(id);
      parents.get(id).forEach(parent => chain(parent, seen));
      return seen;
    };
    let picked = null;
    const highlight = id => {
      const lit = id ? chain(id) : null;
      wrap.classList.toggle("is-picked", Boolean(lit));
      nodes.querySelectorAll(".gnode").forEach(group => {
        group.classList.toggle("is-lit", Boolean(lit && lit.has(Number(group.dataset.id))));
      });
      edges.querySelectorAll(".edge").forEach(edge => {
        edge.classList.toggle("is-lit", Boolean(lit && lit.has(Number(edge.dataset.from)) && lit.has(Number(edge.dataset.to))));
      });
    };
    const groupFrom = event => event.target.closest && event.target.closest(".gnode");
    const toggle = group => {
      const id = Number(group.dataset.id);
      picked = picked === id ? null : id;
      show(byId.get(id));
      highlight(picked);
    };
    svg.addEventListener("mouseover", event => { const group = groupFrom(event); if (group) show(byId.get(Number(group.dataset.id))); });
    svg.addEventListener("focusin", event => { const group = groupFrom(event); if (group) show(byId.get(Number(group.dataset.id))); });
    svg.addEventListener("click", event => { const group = groupFrom(event); if (group) toggle(group); });
    svg.addEventListener("keydown", event => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const group = groupFrom(event);
      if (!group) return;
      event.preventDefault();
      toggle(group);
    });
  }
  renderKnowledgeGraph();

  const viewSwitch = document.querySelector("[data-view-switch]");
  if (viewSwitch) {
    viewSwitch.addEventListener("click", event => {
      const button = event.target.closest("button[data-view]");
      if (!button) return;
      viewSwitch.querySelectorAll("button").forEach(item => {
        const on = item === button;
        item.classList.toggle("is-on", on);
        item.setAttribute("aria-pressed", String(on));
      });
      document.querySelectorAll("[data-view-panel]").forEach(panel => {
        panel.hidden = panel.dataset.viewPanel !== button.dataset.view;
      });
    });
  }

  // Повторная загрузка решения после «вернули на доработку».
  document.addEventListener("submit", async event => {
    const form = event.target.closest("[data-resubmit-form]");
    if (!form) return;
    event.preventDefault();
    const button = form.querySelector("button"), error = form.querySelector("[data-resubmit-error]");
    const file = form.querySelector("input[type=file]").files[0];
    if (!file) return;
    button.disabled = true; error.hidden = true;
    try {
      const payload = new FormData();
      payload.append("assignment", form.dataset.assignment);
      payload.append("file", file);
      await apiFetch("/api/expert-reviews/submit/", { method: "POST", body: payload });
      window.location.reload();
    } catch (exception) {
      error.hidden = false; error.textContent = exception.message; button.disabled = false;
    }
  });

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
        window.lessonFlow?.applyRewards(data.rewards);
      } catch (error) { item.querySelectorAll("button").forEach(button => button.disabled = false); alert(error.message); }
    }

    // Кнопки магазина и домашек — обычные button, поэтому живут в обработчике
    // клика: в submit они не попадают и раньше молча ничего не делали.
    const submitHomework = event.target.closest("[data-submit-homework]");
    if (submitHomework) {
      const card = submitHomework.closest("[data-homework]"), error = card.querySelector("[data-homework-error]");
      submitHomework.disabled = true; if (error) error.hidden = true;
      try { await apiFetch(submitHomework.dataset.submitHomework, { method: "POST", body: "{}" }); const chip = document.createElement("span"); chip.className = "item-type-chip"; chip.textContent = "Сдано"; submitHomework.replaceWith(chip); }
      catch (exception) { if (error) { error.hidden = false; error.textContent = exception.message; } submitHomework.disabled = false; }
    }

    const shopButton = event.target.closest("[data-shop-action]");
    if (shopButton) {
      const row = shopButton.closest("[data-shop-item]");
      const error = row.closest("section")?.querySelector("[data-shop-error]") || document.querySelector("[data-shop-error]");
      shopButton.disabled = true; if (error) error.hidden = true;
      try {
        const data = await apiFetch(shopButton.dataset.shopUrl, { method: "POST", body: "{}" });
        document.querySelectorAll("[data-shop-balance]").forEach(node => {
          if (typeof data.balance === "number") node.textContent = data.balance;
        });
        if (data.consumable) {
          const note = document.createElement("span"); note.className = "boost-chip";
          note.textContent = data.effect === "streak_freeze"
            ? `Куплено · заморозок: ${data.streak_freezes}`
            : `Куплено · опыт +${data.boost_percent} %`;
          row.querySelector("[data-shop-note]")?.remove();
          note.dataset.shopNote = "";
          row.querySelector(".shop-actions").append(note);
          shopButton.disabled = false;
        } else if (shopButton.dataset.shopAction === "buy") {
          row.classList.add("is-owned");
          shopButton.dataset.shopAction = "equip";
          shopButton.dataset.shopUrl = shopButton.dataset.shopUrl.replace("/buy/", "/equip/");
          shopButton.textContent = "Надеть";
          shopButton.disabled = false;
        } else {
          document.querySelectorAll("[data-shop-item] [data-shop-state]").forEach(node => { if (node.textContent === "Надето") node.remove(); });
          const state = document.createElement("span"); state.className = "quest-check"; state.dataset.shopState = ""; state.textContent = "Надето";
          shopButton.replaceWith(state);
          // Тема, аватар и рамка меняют весь кабинет — показываем это сразу.
          if (row.dataset.shopSlot === "theme" || row.dataset.shopSlot === "avatar" || row.dataset.shopSlot === "frame") {
            window.location.reload();
          }
        }
      } catch (exception) {
        if (error) { error.hidden = false; error.textContent = exception.message; }
        else alert(exception.message);
        shopButton.disabled = false;
      }
    }

    const nextButton = event.target.closest("[data-next-task]");
    if (nextButton) showNextTask(nextButton.closest("[data-task]"));
  });

  // Занятие как три этапа: материал → задачи → отработка. Между этапами
  // показываем, что именно принесла работа: рост освоения, XP и сигмы.
  function initLessonFlow() {
    const shell = document.querySelector("[data-lesson]");
    if (!shell) return;
    const STAGES = ["material", "tasks", "review"];
    const TITLES = { tasks: "Дальше — задачи", review: "Дальше — отработка", done: "Занятие пройдено" };
    const PRAISE = [
      "Тема разобрана, задачи решены, ошибки вернулись в работу.",
      "Так и растёт балл: понял, отработал, закрепил.",
      "Сильный заход. Освоение темы поднялось — дорожка уже это учла.",
    ];
    const layer = shell.querySelector("[data-reward-layer]");
    const outro = shell.querySelector("[data-lesson-outro]");
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const startMastery = Number(shell.dataset.mastery) || 0;
    const session = { xp: 0, coins: 0, mastery: startMastery };
    let pending = null;

    const meter = name => shell.querySelector(`[data-meter-${name}]`);
    const bump = element => {
      if (!element || reduceMotion) return;
      element.classList.remove("is-bumped");
      void element.offsetWidth;
      element.classList.add("is-bumped");
    };
    const countTo = (element, value, suffix = "") => {
      if (!element) return;
      const from = parseFloat(element.textContent.replace(",", ".")) || 0;
      if (reduceMotion || from === value) { element.textContent = `${value}${suffix}`; return; }
      const started = performance.now(), duration = 600;
      const step = now => {
        const share = Math.min((now - started) / duration, 1);
        const current = from + (value - from) * share;
        element.textContent = `${Number.isInteger(value) ? Math.round(current) : current.toFixed(1)}${suffix}`;
        if (share < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };

    function applyRewards(rewards) {
      if (!rewards) return;
      if (rewards.xp) {
        session.xp += rewards.xp;
        countTo(meter("xp"), Number(shell.dataset.startXp) + session.xp);
        bump(meter("xp"));
      }
      if (rewards.coins) {
        session.coins += rewards.coins;
        countTo(meter("coins"), Number(shell.dataset.startCoins) + session.coins);
        bump(meter("coins"));
      }
      const nodeGain = (rewards.mastery || []).find(row => String(row.node_id) === shell.dataset.nodeId);
      if (nodeGain) {
        session.mastery = nodeGain.to;
        countTo(meter("mastery"), nodeGain.to, "%");
        bump(meter("mastery"));
      }
      pending = {
        xp: (pending?.xp || 0) + (rewards.xp || 0),
        coins: (pending?.coins || 0) + (rewards.coins || 0),
        masteryFrom: pending?.masteryFrom ?? (nodeGain ? nodeGain.from : null),
        masteryTo: nodeGain ? nodeGain.to : pending?.masteryTo ?? null,
      };
    }

    function showStage(key) {
      shell.dataset.stage = key;
      shell.querySelectorAll("[data-stage-panel]").forEach(panel => {
        panel.hidden = panel.dataset.stagePanel !== key;
      });
      outro.hidden = key !== "done";
      shell.querySelectorAll(".step").forEach(step => {
        const index = STAGES.indexOf(step.dataset.step), position = STAGES.indexOf(key);
        step.classList.toggle("is-current", key !== "done" && index === position);
        if (key === "done" || index < position) step.classList.add("is-done");
        step.setAttribute("aria-current", index === position && key !== "done" ? "step" : "false");
      });
      const done = shell.querySelectorAll(".step.is-done").length;
      const fill = shell.querySelector("[data-stepper-fill]");
      if (fill) fill.style.width = `${Math.min(done / (STAGES.length - 1), 1) * 100}%`;
      shell.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    }

    function celebrate(nextStage) {
      const rewards = pending || {};
      pending = null;
      layer.querySelector("[data-reward-kicker]").textContent =
        nextStage === "done" ? "Занятие завершено" : "Этап пройден";
      layer.querySelector("[data-reward-title]").textContent = TITLES[nextStage] || TITLES.done;

      const masteryRow = layer.querySelector("[data-reward-mastery]");
      const hasMastery = rewards.masteryTo != null && rewards.masteryFrom != null;
      masteryRow.hidden = !hasMastery;
      if (hasMastery) {
        layer.querySelector("[data-reward-mastery-from]").textContent = rewards.masteryFrom;
        layer.querySelector("[data-reward-mastery-to]").textContent = rewards.masteryTo;
        const bar = layer.querySelector("[data-reward-mastery-bar]");
        bar.style.width = `${rewards.masteryFrom}%`;
        setTimeout(() => { bar.style.width = `${rewards.masteryTo}%`; }, 60);
      }
      const xpRow = layer.querySelector("[data-reward-xp-row]");
      xpRow.hidden = !rewards.xp;
      if (rewards.xp) layer.querySelector("[data-reward-xp]").textContent = `+${rewards.xp}`;
      const coinsRow = layer.querySelector("[data-reward-coins-row]");
      coinsRow.hidden = !rewards.coins;
      if (rewards.coins) layer.querySelector("[data-reward-coins]").textContent = `+${rewards.coins}`;

      layer.hidden = false;
      layer.querySelector("[data-reward-continue]").onclick = () => {
        layer.hidden = true;
        if (nextStage === "done") finishLesson(); else showStage(nextStage);
      };
    }

    function finishLesson() {
      const praise = PRAISE[Math.min(Math.floor(session.xp / 10), PRAISE.length - 1)];
      const gain = Math.round((session.mastery - startMastery) * 10) / 10;
      outro.querySelector("[data-outro-praise]").textContent =
        gain > 0 ? `${praise} Освоение темы выросло на ${gain} п. п.` : praise;
      // Итог показывает движение, а не только конечную точку: «54% → 61%»
      // говорит о работе больше, чем одно число.
      outro.querySelector("[data-outro-mastery-from]").textContent = startMastery;
      outro.querySelector("[data-outro-mastery]").textContent = session.mastery;
      const bar = outro.querySelector("[data-outro-mastery-bar]");
      bar.style.width = `${startMastery}%`;
      setTimeout(() => { bar.style.width = `${session.mastery}%`; }, 80);
      outro.querySelector("[data-outro-xp]").textContent = `+${session.xp}`;
      outro.querySelector("[data-outro-coins]").textContent = `+${session.coins}`;
      showStage("done");
    }

    shell.addEventListener("click", async event => {
      const jump = event.target.closest("[data-step-jump]");
      if (jump) { showStage(jump.dataset.stepJump); return; }

      const material = event.target.closest("[data-finish-material]");
      if (material) {
        material.disabled = true;
        try {
          const data = await apiFetch(`/api/lessons/${shell.dataset.nodeId}/stages/`, { method: "POST", body: "{}" });
          const step = shell.querySelector('[data-step="material"]');
          step.classList.add("is-done");
          const caption = data.stages.find(stage => stage.key === "material")?.caption;
          if (caption) step.querySelector("[data-step-caption]").textContent = caption;
        } catch (error) { alert(error.message); }
        material.disabled = false;
        celebrate("tasks");
        return;
      }

      const goto = event.target.closest("[data-goto-stage]");
      if (goto) { celebrate(goto.dataset.gotoStage); return; }

      const finish = event.target.closest("[data-finish-lesson]");
      if (finish) celebrate("done");
    });

    window.lessonFlow = { applyRewards, celebrate, showStage };
    showStage(shell.dataset.stage);
  }
  initLessonFlow();

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
    if (tasks[index + 1]) {
      tasks[index + 1].classList.remove("is-hidden");
      updateTaskProgress();
      window.scrollTo({ top: document.querySelector("#tasks")?.offsetTop - 90, behavior: "smooth" });
      return;
    }
    // Задачи кончились: показываем итог этапа и уводим на отработку.
    updateTaskProgress();
    document.querySelector("[data-lesson-complete]")?.classList.remove("is-hidden");
    if (window.lessonFlow) window.lessonFlow.celebrate("review");
  }
  updateTaskProgress();

  document.addEventListener("submit", async event => {
    const targetScoreForm = event.target.closest("[data-target-score-form]");
    if (targetScoreForm) {
      event.preventDefault();
      const button = targetScoreForm.querySelector("button"), input = targetScoreForm.querySelector("input"), error = targetScoreForm.querySelector("[data-target-score-error]"), success = targetScoreForm.querySelector("[data-target-score-success]");
      button.disabled = true; error.hidden = true; success.hidden = true;
      try {
        const data = await apiFetch("/api/me/target/", { method: "POST", body: JSON.stringify({ target_score: Number(input.value) }) });
        document.querySelector("[data-target-score-current]").textContent = data.target_score;
        document.querySelector("[data-target-trajectory]").textContent = data.trajectory.title;
        document.querySelector("[data-current-score]").textContent = data.forecast.current_score;
        document.querySelector("[data-ceiling-score]").textContent = data.forecast.ceiling_score;
        success.textContent = data.trajectory_changed ? `Цель изменена. План перестроен под траекторию ${data.trajectory.title}.` : `Цель изменена. Траектория ${data.trajectory.title} сохранена, план не перестраивался.`;
        success.hidden = false;
      } catch (exception) { error.textContent = exception.message; error.hidden = false; }
      finally { button.disabled = false; }
    }
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
      try { const data = await apiFetch(`/api/assignments/${task.dataset.assignmentId}/attempt/`, { method: "POST", body: JSON.stringify({ answer: new FormData(attemptForm).get("answer"), context: attemptForm.dataset.context }) }); verdict.hidden = false; verdict.className = `verdict ${data.is_correct ? "is-correct" : "is-wrong"}`; verdict.textContent = data.is_correct === null ? "Решение отправлено на экспертную проверку." : (data.is_correct ? "Верно! Можно двигаться дальше." : "Пока неверно. Ошибка сохранена для отработки."); task.querySelector("[data-next-task]").hidden = false; renderProgress(task, data.progress); window.lessonFlow?.applyRewards(data.rewards); }
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
