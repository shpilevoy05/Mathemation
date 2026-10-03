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
      const error = new Error(data.detail || firstError || "Не удалось выполнить запрос. Попробуй ещё раз.");
      // Код нужен там, где ошибка не равна «неверно»: например, неразобранная
      // запись ответа не должна выглядеть как ошибка решения.
      error.code = data.code || "";
      error.status = response.status;
      throw error;
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
        // Близкие флажки сначала разводим в стороны: левая подпись кончается у
        // своей линии, правая начинается от своей — линии не режут текст.
        // Ряды друг над другом — запасной путь, когда места в стороны нет.
        const clash = placed.find(other => other.row === 0 && !other.split && start < other.end + 8 && other.start < end + 8);
        if (clash && clash.centre < centre && clash.centre - clash.width - 4 >= 0 && centre + width + 4 <= bounds.width) {
          clash.entry.label.classList.remove("is-left"); clash.entry.label.classList.add("is-right");
          entry.label.classList.remove("is-right"); entry.label.classList.add("is-left");
          Object.assign(clash, { start: clash.centre - clash.width - 4, end: clash.centre, split: true });
          placed.push({ row: 0, start: centre, end: centre + width + 4, centre, width, entry, split: true });
          return;
        }
        let row = 0;
        while (placed.some(other => other.row === row && start < other.end + 8 && other.start < end + 8)) row += 1;
        if (row) entry.flag.dataset.row = String(Math.min(row, 2));
        placed.push({ row, start, end, centre, width, entry });
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

  function revealActiveMobileTab() {
    const nav = document.querySelector(".mobile-tabs");
    const active = nav?.querySelector(".mobile-tab.is-active");
    if (!nav || !active || !window.matchMedia("(max-width: 720px)").matches) return;
    requestAnimationFrame(() => {
      const left = active.offsetLeft - (nav.clientWidth - active.offsetWidth) / 2;
      nav.scrollTo({ left: Math.max(0, left), behavior: "auto" });
    });
  }
  revealActiveMobileTab();
  window.addEventListener("resize", revealActiveMobileTab);

  // Дорожка идёт через фактические центры точек: translate у змейки уже учтён
  // getBoundingClientRect. Без JS остаётся прямая пунктирная линия из CSS.
  function initTrackCurves() {
    const tracks = [...document.querySelectorAll(".track-path")];
    if (!tracks.length) return;
    const NS = "http://www.w3.org/2000/svg";
    const curvePath = points => {
      if (points.length < 2) return "";
      return points.slice(1).reduce((path, point, index) => {
        const previous = points[index];
        const halfGap = (point.y - previous.y) / 2;
        return `${path} C ${previous.x} ${previous.y + halfGap}, ${point.x} ${point.y - halfGap}, ${point.x} ${point.y}`;
      }, `M ${points[0].x} ${points[0].y}`);
    };
    const entries = tracks.map(track => {
      const svg = document.createElementNS(NS, "svg");
      svg.setAttribute("class", "track-curve");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("focusable", "false");
      const full = document.createElementNS(NS, "path");
      const done = document.createElementNS(NS, "path");
      done.setAttribute("class", "track-curve-done");
      svg.append(full, done);
      track.prepend(svg);
      return { track, svg, full, done };
    });
    const draw = entry => {
      const bounds = entry.track.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return;
      const rows = [...entry.track.querySelectorAll("[data-track-point]")];
      const nodePoints = rows.map(row => {
        const button = row.querySelector(".track-node-button");
        const rect = button.getBoundingClientRect();
        return { x: rect.left - bounds.left + rect.width / 2, y: rect.top - bounds.top + rect.height / 2 };
      });
      if (!nodePoints.length) return;
      const points = [{ x: nodePoints[0].x, y: 0 }, ...nodePoints];
      const path = curvePath(points);
      if (!path) return;
      entry.svg.setAttribute("viewBox", `0 0 ${bounds.width} ${bounds.height}`);
      entry.full.setAttribute("d", path);
      const current = rows.findIndex(row => row.dataset.state === "current");
      entry.done.setAttribute("d", current >= 0 ? curvePath(points.slice(0, current + 2)) : "");
      entry.track.classList.add("has-curve");
    };
    let frame = 0;
    const drawAll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => entries.forEach(draw));
    };
    drawAll();
    window.addEventListener("resize", drawAll);
    if ("ResizeObserver" in window) {
      const observer = new ResizeObserver(drawAll);
      tracks.forEach(track => observer.observe(track));
    }
    if (document.fonts?.ready) document.fonts.ready.then(drawAll);
  }
  initTrackCurves();

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

  // Фильтры витрины: серия, аватары, рамки, оформление.
  const shopFilters = document.querySelector("[data-shop-filters]");
  if (shopFilters) {
    shopFilters.addEventListener("click", event => {
      const button = event.target.closest("button[data-shop-filter]");
      if (!button) return;
      shopFilters.querySelectorAll("button").forEach(item => item.classList.toggle("is-on", item === button));
      const group = button.dataset.shopFilter;
      document.querySelectorAll("[data-shop-group]").forEach(card => {
        card.hidden = group !== "all" && card.dataset.shopGroup !== group;
      });
    });
  }

  // — Примерка косметики в магазине —
  // Состояние живёт только в этой вкладке: сервер о примерке не знает. Уход со
  // страницы возвращает то, что действительно надето, — отсюда и обещание
  // «только пока ты в магазине».
  const preview = { theme: null, badge: null };
  const badgeNode = () => document.querySelector(".rail-foot .avatar-badge");

  // Аватар и рамка — два слоя значка. На примерке они берутся из спрайта:
  // анимация в этот момент не запускается, зато вещь видно сразу и без
  // запроса к серверу.
  function previewLayer(kind, code) {
    const sprite = document.documentElement.dataset.cosmeticsSprite || "";
    const box = kind === "frame" ? "0 0 160 160" : "0 0 128 128";
    return `<span class="${kind === "frame" ? "frame-art" : "avatar-art"}">`
      + `<svg class="${kind}-${code}" viewBox="${box}" aria-hidden="true">`
      + `<use href="${sprite}#${kind}-${code}"></use></svg></span>`;
  }

  function applyPreview(slot, code, title) {
    const badge = badgeNode();
    if (preview.theme === null) preview.theme = document.documentElement.dataset.theme || "";
    if (badge && preview.badge === null) preview.badge = badge.outerHTML;

    if (slot === "theme") {
      document.documentElement.dataset.theme = code;
    } else if (badge && slot === "frame") {
      badge.querySelector(".frame-art")?.remove();
      badge.insertAdjacentHTML("beforeend", previewLayer("frame", code));
    } else if (badge && slot === "avatar") {
      const shown = badge.querySelector(".avatar-art, .avatar-letter");
      if (shown) shown.outerHTML = previewLayer("avatar", code);
      else badge.insertAdjacentHTML("afterbegin", previewLayer("avatar", code));
    }
    const bar = document.querySelector("[data-preview-bar]");
    if (!bar) return;
    bar.hidden = false;
    bar.querySelector("[data-preview-note]").textContent =
      `Примерка: ${title}. Вещь не куплена и не надета — так она выглядит в кабинете.`;
  }

  function resetPreview() {
    if (preview.theme !== null) {
      if (preview.theme) document.documentElement.dataset.theme = preview.theme;
      else delete document.documentElement.dataset.theme;
    }
    const badge = badgeNode();
    if (badge && preview.badge !== null) badge.outerHTML = preview.badge;
    preview.theme = null;
    preview.badge = null;
    const bar = document.querySelector("[data-preview-bar]");
    if (bar) bar.hidden = true;
  }

  // — Календарь: перенос пункта плана перетаскиванием —
  // Календарь не заводит своё расписание: он двигает сам план, поэтому
  // единственное действие здесь — попросить сервер сменить дату пункта.
  const calendar = document.querySelector("[data-calendar]");
  if (calendar) {
    let dragged = null;
    calendar.addEventListener("dragstart", event => {
      dragged = event.target.closest("[data-plan-item]");
      if (dragged) event.dataTransfer.effectAllowed = "move";
    });
    calendar.addEventListener("dragover", event => {
      if (dragged && event.target.closest("[data-day]")) event.preventDefault();
    });
    calendar.addEventListener("drop", async event => {
      const day = event.target.closest("[data-day]");
      if (!dragged || !day) return;
      event.preventDefault();
      const error = document.querySelector("[data-calendar-error]");
      const item = dragged;
      dragged = null;
      try {
        await apiFetch(`/api/plan/items/${item.dataset.planItem}/move/`, {
          method: "POST",
          body: JSON.stringify({ due_date: day.dataset.day }),
        });
        day.append(item);
        if (error) error.hidden = true;
      } catch (exception) {
        if (error) { error.hidden = false; error.textContent = exception.message; }
      }
    });
  }

  // — Арена: друзья и партии —
  // Ответ, время и очки считает сервер; здесь только показ состояния и таймер,
  // который подсказывает, сколько осталось на вопрос.
  const matchForm = document.querySelector("[data-match-form]");
  // Один сборщик параметров на форму и на очередь подбора: правило партии
  // должно совпадать, иначе в очереди встретятся разные игры.
  const matchPayload = () => {
    const body = {
      mode: matchForm.elements.mode.value,
      seconds_per_question: 90,
      limit_kind: matchForm.elements.limit_kind.value,
      // Сложность бота нужна и очереди: если живого соперника не нашлось,
      // запасной бот должен быть того уровня, который выбрал игрок.
      bot_level: Number(matchForm.elements.bot_level.value),
    };
    if (body.mode !== "speed") {
      body.limit_kind = "questions";
      return body;
    }
    const task = matchForm.elements.ege_task_number.value;
    if (task) body.ege_task_number = Number(task);
    if (body.limit_kind === "time") {
      body.time_limit_seconds = Number(matchForm.elements.time_limit_seconds.value);
    } else {
      body.question_count = Number(matchForm.elements.question_count.value);
    }
    return body;
  };
  if (matchForm) {
    const hints = {
      speed: "Задачи из тренировки. Правило выбираете сами: кто быстрее решит восемь или кто больше решит за отведённое время.",
      quiz: "Вопросы по теории с четырьмя вариантами. Кто первым нажал верный — тот и забрал очки.",
      board: "Пять тем, цены от 100 до 500. Ход по очереди, промах списывает цену клетки. Тридцать секунд на ответ.",
    };
    const opponent = matchForm.elements.opponent;
    const level = matchForm.elements.bot_level;
    const botBlock = matchForm.querySelector("[data-bot-level]");
    const speedBlock = matchForm.querySelector("[data-speed-rules]");
    const timeBlock = matchForm.querySelector("[data-time-limit]");
    const syncOpponent = () => { botBlock.hidden = opponent.value !== "bot"; };
    // Правило партии и прототип — только у нарешивания: теория спрашивается
    // не по номеру задания и не на общее время.
    const countBlock = matchForm.querySelector("[data-question-count]");
    const syncMode = () => {
      const speed = matchForm.elements.mode.value === "speed";
      const onTime = matchForm.elements.limit_kind.value === "time";
      speedBlock.hidden = !speed;
      matchForm.querySelector("[data-task-block]").hidden = !speed;
      timeBlock.hidden = !speed || !onTime;
      countBlock.hidden = !speed || onTime;
      matchForm.querySelector("[data-mode-hint]").textContent = hints[matchForm.elements.mode.value] || "";
    };
    matchForm.elements.mode.addEventListener("change", syncMode);
    matchForm.elements.limit_kind.addEventListener("change", syncMode);
    syncMode();
    opponent.addEventListener("change", syncOpponent);
    // Подписи совпадают с таблицей бота (apps/arena/bot.py): доля ошибок и
    // среднее время на задачу в нарешивании.
    const levelNotes = {
      1: "ошибается в каждой четвёртой задаче, на задачу — около минуты",
      2: "ошибается в 15 % задач, на задачу — около 40 секунд",
      3: "ошибается в 15 % задач, на задачу — около 30 секунд",
      4: "ошибается в каждой десятой задаче, на задачу — около 25 секунд",
      5: "почти не ошибается, на задачу — около 15 секунд",
    };
    level.addEventListener("input", () => {
      matchForm.querySelector("[data-level-output]").textContent = level.value;
      const note = matchForm.querySelector("[data-level-note]");
      if (note) note.textContent = levelNotes[level.value] || "";
    });
    syncOpponent();

    matchForm.addEventListener("submit", async event => {
      event.preventDefault();
      const error = matchForm.querySelector("[data-match-error]");
      const button = matchForm.querySelector("[type=submit]");
      button.disabled = true; error.hidden = true;
      const payload = matchPayload();
      if (opponent.value === "bot") payload.bot_level = Number(level.value);
      else payload.opponent_id = Number(opponent.value);
      try {
        const data = await apiFetch("/api/arena/matches/", { method: "POST", body: JSON.stringify(payload) });
        window.location.assign(`/arena/match/${data.id}/`);
      } catch (exception) {
        error.hidden = false; error.textContent = exception.message; button.disabled = false;
      }
    });
  }

  // — Очередь на случайного соперника —
  // Пары сводит сервер: клиент только встаёт в очередь и спрашивает статус.
  // Через минуту ожидания предлагаем бота своего уровня — ждать вечно скучнее,
  // чем сыграть.
  const queueBox = document.querySelector("[data-queue]");
  if (queueBox && matchForm) {
    const status = queueBox.querySelector("[data-queue-status]");
    const botButton = queueBox.querySelector("[data-queue-bot]");
    let poll = null;
    let waited = 0;

    const payload = () => matchPayload();

    const stop = () => { clearInterval(poll); poll = null; };

    const handle = state => {
      if (state.match_url) {
        stop();
        window.location.assign(state.match_url);
        return;
      }
      queueBox.querySelector("[data-queue-rating]").textContent = state.rating;
      status.textContent = `Ищем соперника… ${waited} с, окно поиска ±${state.search_window}`;
      botButton.hidden = waited < 60;
    };

    document.querySelector("[data-queue-join]")?.addEventListener("click", async () => {
      queueBox.hidden = false;
      waited = 0;
      try {
        handle(await apiFetch("/api/arena/queue/", { method: "POST", body: JSON.stringify(payload()) }));
      } catch (exception) { status.textContent = exception.message; return; }
      stop();
      poll = setInterval(async () => {
        waited += 4;
        try { handle(await apiFetch("/api/arena/queue/")); }
        catch (_) { /* сеть подождёт до следующего тика */ }
      }, 4000);
    });

    queueBox.querySelector("[data-queue-cancel]").addEventListener("click", async () => {
      stop();
      queueBox.hidden = true;
      try { await apiFetch("/api/arena/queue/", { method: "DELETE" }); } catch (_) { /* уже ушли */ }
    });

    botButton.addEventListener("click", async () => {
      stop();
      botButton.disabled = true;
      try {
        const match = await apiFetch("/api/arena/queue/bot/", { method: "POST", body: JSON.stringify(payload()) });
        window.location.assign(`/arena/match/${match.id}/`);
      } catch (exception) { status.textContent = exception.message; botButton.disabled = false; }
    });
  }

  // — Лига: включение и выход —
  // Участие добровольное, поэтому обе кнопки ведут себя одинаково просто:
  // нажали — страница перерисовалась с новым состоянием.
  const leagueSwitch = async (method) => {
    const error = document.querySelector("[data-league-error]");
    if (error) error.hidden = true;
    try {
      await apiFetch("/api/leagues/participation/", { method, body: "{}" });
      window.location.reload();
    } catch (exception) {
      if (error) { error.hidden = false; error.textContent = exception.message; }
    }
  };

  document.querySelector("[data-league-join]")?.addEventListener("click", () => leagueSwitch("POST"));
  document.querySelector("[data-league-leave]")?.addEventListener("click", () => {
    if (window.confirm("Выйти из лиги? Место займёт бот, набранный опыт останется при вас.")) {
      leagueSwitch("DELETE");
    }
  });

  const friendForm = document.querySelector("[data-friend-form]");
  if (friendForm) {
    friendForm.addEventListener("submit", async event => {
      event.preventDefault();
      const error = document.querySelector("[data-friend-error]");
      error.hidden = true;
      try {
        await apiFetch("/api/arena/friends/request/", {
          method: "POST",
          body: JSON.stringify({ username: friendForm.elements.username.value }),
        });
        window.location.reload();
      } catch (exception) { error.hidden = false; error.textContent = exception.message; }
    });
  }

  document.addEventListener("click", async event => {
    const friendAnswer = event.target.closest("[data-friend-answer]");
    if (friendAnswer) {
      friendAnswer.disabled = true;
      try {
        await apiFetch(`/api/arena/friends/${friendAnswer.dataset.friendAnswer}/${friendAnswer.dataset.action}/`, { method: "POST", body: "{}" });
        window.location.reload();
      } catch (exception) { friendAnswer.disabled = false; alert(exception.message); }
    }
    const matchAnswer = event.target.closest("[data-match-answer]");
    if (matchAnswer) {
      matchAnswer.disabled = true;
      try {
        await apiFetch(`/api/arena/matches/${matchAnswer.dataset.matchAnswer}/${matchAnswer.dataset.action}/`, { method: "POST", body: "{}" });
        window.location.reload();
      } catch (exception) { matchAnswer.disabled = false; alert(exception.message); }
    }
  });

  // — Экран партии —
  // Всё состояние приходит одним объектом с сервера: он один знает, чей ход,
  // сколько осталось времени и кто уже забрал вопрос. Клиент только рисует.
  const matchShell = document.querySelector("[data-match]");
  if (matchShell) {
    const matchId = matchShell.dataset.match;
    const mode = matchShell.dataset.mode;
    const stateUrl = `/api/arena/matches/${matchId}/`;
    const totalSeconds = Number(matchShell.dataset.seconds) || 30;

    const questionBlock = matchShell.querySelector("[data-match-question]");
    const quizBlock = matchShell.querySelector("[data-quiz]");
    const boardBlock = matchShell.querySelector("[data-board]");
    const resultBlock = matchShell.querySelector("[data-match-result]");
    const waitingBlock = matchShell.querySelector("[data-match-waiting]");
    const runClock = matchShell.querySelector("[data-run-clock]");

    const lobbyBlock = matchShell.querySelector("[data-lobby]");

    let questionId = Number(questionBlock?.dataset.questionId) || null;
    let askedAt = performance.now();
    let quizId = null;
    let openCellId = null;
    let poll = null;
    let lastTag = null;
    let interval = 0;
    let lobbyTimer = null;
    const bars = new Map();

    // Полоска таймера идёт от значения, присланного сервером: местные часы
    // могут отставать, но правило партии считает всё равно сервер.
    const countdown = (bar, secondsLeft) => {
      if (!bar) return;
      const previous = bars.get(bar);
      if (previous) clearInterval(previous);
      const startedAt = performance.now();
      const left = Math.max(0, Number(secondsLeft) || 0);
      const tick = () => {
        const spent = (performance.now() - startedAt) / 1000;
        const share = Math.max(0, (left - spent) / totalSeconds);
        bar.style.width = `${(Math.min(1, share) * 100).toFixed(1)}%`;
        if (share <= 0) clearInterval(bars.get(bar));
      };
      tick();
      bars.set(bar, setInterval(tick, 200));
    };

    const renderSide = (key, side) => {
      const root = matchShell.querySelector(`[data-side="${key}"]`);
      if (!root || !side) return;
      root.querySelector("[data-side-score]").textContent = side.score ?? 0;
      const note = root.querySelector("[data-side-note]");
      if (note) note.textContent = side.finished ? "закончил" : `ответов: ${side.answered}`;
    };

    const renderSpeed = state => {
      if (!questionBlock) return;
      const verdictBox = matchShell.querySelector("[data-match-verdict]");
      if (state.question) {
        questionId = state.question.id;
        questionBlock.hidden = false;
        matchShell.querySelector("[data-question-title]").textContent = state.question.title;
        matchShell.querySelector("[data-question-statement]").textContent = state.question.statement;
        matchShell.querySelector("[data-question-points]").textContent = `${state.question.points} очков`;
        askedAt = performance.now();
        countdown(matchShell.querySelector("[data-match-timer-bar]"), totalSeconds);
      } else {
        questionBlock.hidden = true;
        if (verdictBox) verdictBox.hidden = true;
      }
      if (runClock && state.limit_kind === "time") {
        runClock.hidden = false;
        matchShell.querySelector("[data-run-left]").textContent = state.seconds_left ?? 0;
      }
    };

    const renderQuiz = state => {
      const quiz = state.quiz;
      if (!quizBlock || !quiz) return;
      quizBlock.hidden = state.status === "finished";
      matchShell.querySelector("[data-quiz-progress]").textContent = `${quiz.played} из ${quiz.total}`;
      const options = matchShell.querySelector("[data-quiz-options]");
      const prompt = matchShell.querySelector("[data-quiz-prompt]");
      const note = matchShell.querySelector("[data-quiz-note]");

      if (!quiz.question) {
        options.replaceChildren();
        prompt.textContent = "Вопрос разыгран. Открываем следующий…";
        return;
      }
      matchShell.querySelector("[data-quiz-topic]").textContent = quiz.question.topic;
      prompt.textContent = quiz.question.prompt;
      if (quizId !== quiz.question.id) {
        quizId = quiz.question.id;
        options.replaceChildren(...quiz.question.options.map((text, index) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "quiz-option";
          button.dataset.quizOption = String(index);
          button.textContent = text;
          return button;
        }));
      }
      options.querySelectorAll("[data-quiz-option]").forEach(button => {
        const index = Number(button.dataset.quizOption);
        button.disabled = quiz.locked;
        button.classList.toggle("is-mine", quiz.my_choice === index);
      });
      if (note) {
        note.textContent = quiz.locked
          ? "Вы уже ответили на этот вопрос — ждём соперника или таймер."
          : "Кто первым нажмёт верный вариант, тот и забрал очки.";
      }
      countdown(matchShell.querySelector("[data-quiz-timer]"), quiz.question.seconds_left);
    };

    // Журнал доски: что разыграно и что отвечал соперник. В «своей игре»
    // ответы не секретны — вопрос общий и уже сыгран.
    const renderBoardLog = rows => {
      const list = matchShell.querySelector("[data-board-log]");
      if (!list) return;
      if (!rows.length) {
        const empty = document.createElement("li");
        empty.innerHTML = '<small class="muted">Пока ничего не разыграно.</small>';
        list.replaceChildren(empty);
        return;
      }
      list.replaceChildren(...rows.map(row => {
        const item = document.createElement("li");
        const price = document.createElement("b");
        price.className = "num";
        price.textContent = row.points;
        const topic = document.createElement("span");
        topic.className = "board-log-topic";
        topic.textContent = row.topic;
        const answers = document.createElement("span");
        answers.className = "board-log-answers";
        if (row.answers.length) {
          row.answers.forEach(answer => {
            const chip = document.createElement("span");
            chip.className = answer.is_correct ? "is-correct" : "is-wrong";
            chip.textContent = `${answer.title}: ${answer.answer || "—"}`;
            answers.append(chip);
          });
        } else {
          const chip = document.createElement("span");
          chip.className = "muted";
          chip.textContent = "никто не ответил";
          answers.append(chip);
        }
        const right = document.createElement("small");
        right.className = "muted";
        right.textContent = `верно: ${row.correct_answer}`;
        item.append(price, topic, answers, right);
        return item;
      }));
    };

    const renderBoard = state => {
      const board = state.board;
      if (!boardBlock || !board) return;
      boardBlock.hidden = false;
      const turnChip = matchShell.querySelector("[data-board-turn]");
      if (turnChip) {
        turnChip.textContent = state.status === "finished"
          ? "Партия окончена"
          : board.turn === "me" ? "Ваш ход" : board.turn ? `Ход: ${board.turn_title}` : "";
      }

      const grid = matchShell.querySelector("[data-board-grid]");
      grid.style.setProperty("--board-columns", board.columns.length);
      // Строк в общей сетке: заголовок темы + самая длинная колонка клеток.
      grid.style.setProperty("--board-rows", 1 + Math.max(0, ...board.columns.map(column => column.cells.length)));
      grid.replaceChildren(...board.columns.map(column => {
        const box = document.createElement("div");
        box.className = "board-column";
        const title = document.createElement("h3");
        title.className = "board-topic";
        title.textContent = column.title;
        box.append(title);
        column.cells.forEach(cell => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = `board-cell is-${cell.state}`;
          button.dataset.cell = String(cell.id);
          button.textContent = cell.points;
          button.disabled = cell.state !== "free" || board.turn !== "me" || Boolean(board.open);
          box.append(button);
        });
        return box;
      }));

      renderBoardLog(board.log || []);
      const openBox = matchShell.querySelector("[data-board-open]");
      const form = matchShell.querySelector("[data-board-form]");
      const wait = matchShell.querySelector("[data-board-wait]");
      if (!board.open) {
        openBox.hidden = true;
        openCellId = null;
        return;
      }
      openBox.hidden = false;
      openCellId = board.open.id;
      matchShell.querySelector("[data-board-topic]").textContent = board.open.topic;
      matchShell.querySelector("[data-board-points]").textContent = `${board.open.points} очков`;
      matchShell.querySelector("[data-board-prompt]").textContent = board.open.prompt;
      matchShell.querySelector("[data-board-hint]").textContent = board.open.hint;
      // Перехват: показываем, кто и чем ошибся — соперник получает клетку
      // вместе с чужим ответом.
      const rebound = matchShell.querySelector("[data-board-rebound]");
      if (rebound) {
        rebound.hidden = !board.open.rebound;
        rebound.textContent = board.open.rebound_note || "";
      }
      form.hidden = !board.open.mine;
      wait.hidden = board.open.mine;
      wait.textContent = `Отвечает ${board.open.answering}.`;
      if (board.open.mine) form.elements.answer.focus();
      countdown(matchShell.querySelector("[data-board-timer]"), board.open.seconds_left);
    };

    // Разбор: что спрашивали, что ответил игрок и как было правильно.
    const renderReview = rows => {
      const list = matchShell.querySelector("[data-review]");
      if (!list || !rows.length) return;
      list.replaceChildren(...rows.map(row => {
        const item = document.createElement("li");
        item.className = row.is_correct ? "is-correct" : "is-wrong";
        const title = document.createElement("strong");
        title.textContent = row.title;
        const statement = document.createElement("span");
        statement.className = "statement";
        statement.textContent = row.statement;
        const line = document.createElement("span");
        line.className = "review-line";
        const mine = document.createElement("span");
        mine.textContent = `Ваш ответ: ${row.my_answer || "—"}`;
        line.append(mine);
        if (!row.is_correct) {
          const right = document.createElement("span");
          right.textContent = `Правильно: ${row.correct_answer}`;
          line.append(right);
        }
        item.append(title, statement, line);
        return item;
      }));
    };

    const renderLobby = state => {
      if (!lobbyBlock) return;
      const lobby = state.lobby;
      lobbyBlock.hidden = !lobby;
      if (!lobby) return;
      lobbyBlock.querySelector("[data-lobby-title]").textContent = lobby.invited
        ? "Ждём согласия соперника"
        : "Ждём соперника за столом";
      const note = lobbyBlock.querySelector("[data-lobby-note]");
      note.textContent = lobby.waiting_for.length
        ? `Не подошли: ${lobby.waiting_for.join(", ")}. Партия начнётся, когда её откроют оба.`
        : "Партия вот-вот начнётся.";
      // Обратный отсчёт тикает на клиенте: сервер молчит, пока в партии нет
      // новостей, и цифра иначе замерла бы.
      const left = lobbyBlock.querySelector("[data-lobby-left]");
      clearInterval(lobbyTimer);
      const until = Date.now() + lobby.seconds_left * 1000;
      const tick = () => {
        const seconds = Math.max(0, Math.round((until - Date.now()) / 1000));
        left.textContent = seconds;
        if (seconds <= 0) clearInterval(lobbyTimer);
      };
      tick();
      lobbyTimer = setInterval(tick, 1000);
      lobbyBlock.querySelector("[data-lobby-cancel]").hidden = !lobby.can_cancel;
      lobbyBlock.querySelector("[data-lobby-accept]").hidden = !lobby.invited || lobby.can_cancel;
    };

    const render = state => {
      renderLobby(state);
      if (state.lobby) {
        // До старта показывать нечего: доска и вопросы закрыты, чтобы никто
        // не начал думать раньше соперника.
        [questionBlock, quizBlock, boardBlock, waitingBlock].forEach(box => {
          if (box) box.hidden = true;
        });
        renderSide("me", state.me);
        renderSide("rival", state.opponent);
        return;
      }
      renderSide("me", state.me);
      renderSide("rival", state.opponent);
      if (mode === "quiz") renderQuiz(state);
      else if (mode === "board") renderBoard(state);
      else renderSpeed(state);

      const playing = Boolean(state.question || state.quiz?.question || state.board?.open);
      if (waitingBlock) {
        waitingBlock.hidden = state.status === "finished"
          || playing
          || mode === "board";
      }

      const exitBox = matchShell.querySelector("[data-match-exit]");
      if (exitBox) exitBox.hidden = state.status !== "active";

      if (state.status !== "finished") return;
      clearInterval(poll);
      bars.forEach(timer => clearInterval(timer));
      if (questionBlock) questionBlock.hidden = true;
      if (quizBlock) quizBlock.hidden = true;
      resultBlock.hidden = false;
      renderReview(state.review || []);
      const rows = matchShell.querySelector("[data-result-rows]");
      rows.replaceChildren(...state.results.map(row => {
        const tr = document.createElement("tr");
        if (row.is_me) tr.className = "is-me";
        [row.title, row.score, row.correct, `${row.seconds} с`].forEach((value, index) => {
          const cell = document.createElement("td");
          if (index) cell.className = "num";
          cell.textContent = value;
          tr.append(cell);
        });
        return tr;
      }));
    };

    // Состояние забирается с ETag: пока номер состояния не изменился, сервер
    // отвечает «304 без новостей» и не собирает ответ целиком. На живой партии
    // так проходит подавляющее большинство опросов.
    const fetchState = async () => {
      const headers = { Accept: "application/json" };
      if (lastTag) headers["If-None-Match"] = lastTag;
      const response = await fetch(stateUrl, {
        credentials: "same-origin", cache: "no-store", headers,
      });
      if (response.status === 304) return null;
      if (!response.ok) return null;
      lastTag = response.headers.get("ETag") || lastTag;
      return response.json();
    };

    // Как часто спрашивать. Реже там, где новостей ждать неоткуда: пока идёт
    // сбор игроков или пока ход соперника, секунда роли не играет.
    const paceFor = state => {
      if (!state) return interval || 2500;
      if (["finished", "declined", "cancelled"].includes(state.status)) return 0;
      if (state.lobby) return 3000;
      return 2500;
    };

    const stopPolling = () => { clearInterval(poll); poll = null; };

    const startPolling = pace => {
      if (interval === pace && poll) return;
      stopPolling();
      interval = pace;
      if (pace > 0) poll = setInterval(refresh, pace);
    };

    async function refresh() {
      try {
        const state = await fetchState();
        if (state) render(state);
        startPolling(paceFor(state));
      } catch (_) { /* сеть подождёт до следующего тика */ }
    }

    // Вкладка в фоне не играет: опрашивать её — чистые потери и на клиенте,
    // и на сервере.
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) { stopPolling(); interval = 0; }
      else refresh();
    });

    const show = (box, text, wrong) => {
      if (!box) return;
      box.hidden = false;
      box.textContent = text;
      if (box.classList.contains("verdict")) {
        box.className = `verdict ${wrong ? "is-wrong" : "is-correct"}`;
      }
    };

    // — Нарешивание —
    const speedForm = matchShell.querySelector("[data-match-answer-form]");
    speedForm?.addEventListener("submit", async event => {
      event.preventDefault();
      const button = speedForm.querySelector("[type=submit]");
      const error = matchShell.querySelector("[data-match-error]");
      const verdict = matchShell.querySelector("[data-match-verdict]");
      button.disabled = true; error.hidden = true;
      try {
        const state = await apiFetch(`/api/arena/matches/${matchId}/answer/`, {
          method: "POST",
          body: JSON.stringify({
            question_id: questionId,
            answer: speedForm.elements.answer.value,
            elapsed_ms: Math.round(performance.now() - askedAt),
          }),
        });
        show(verdict, state.last_answer.is_correct ? "Верно!" : "Мимо.", !state.last_answer.is_correct);
        speedForm.elements.answer.value = "";
        render(state);
        speedForm.elements.answer.focus();
      } catch (exception) {
        error.hidden = false; error.textContent = exception.message;
      } finally { button.disabled = false; }
    });

    // — Квиз —
    matchShell.querySelector("[data-quiz-options]")?.addEventListener("click", async event => {
      const button = event.target.closest("[data-quiz-option]");
      if (!button || button.disabled) return;
      const error = matchShell.querySelector("[data-quiz-error]");
      matchShell.querySelectorAll("[data-quiz-option]").forEach(item => { item.disabled = true; });
      error.hidden = true;
      try {
        const state = await apiFetch(`/api/arena/matches/${matchId}/quiz/`, {
          method: "POST",
          body: JSON.stringify({ question_id: quizId, option: Number(button.dataset.quizOption) }),
        });
        button.classList.add(state.last_answer.is_correct ? "is-correct" : "is-wrong");
        render(state);
      } catch (exception) {
        // Отказ — обычный ход игры: вопрос мог забрать соперник, пока летел
        // запрос. Показываем причину и берём свежее состояние.
        error.hidden = false; error.textContent = exception.message;
        await refresh();
      }
    });

    // — Своя игра —
    matchShell.querySelector("[data-board-grid]")?.addEventListener("click", async event => {
      const cell = event.target.closest("[data-cell]");
      if (!cell || cell.disabled) return;
      cell.disabled = true;
      try {
        render(await apiFetch(`/api/arena/matches/${matchId}/pick/`, {
          method: "POST",
          body: JSON.stringify({ question_id: Number(cell.dataset.cell) }),
        }));
      } catch (exception) {
        show(matchShell.querySelector("[data-board-error]"), exception.message, true);
        await refresh();
      }
    });

    const boardForm = matchShell.querySelector("[data-board-form]");
    boardForm?.addEventListener("submit", async event => {
      event.preventDefault();
      const button = boardForm.querySelector("[type=submit]");
      const error = matchShell.querySelector("[data-board-error]");
      const verdict = matchShell.querySelector("[data-board-verdict]");
      button.disabled = true; error.hidden = true;
      try {
        const state = await apiFetch(`/api/arena/matches/${matchId}/board/`, {
          method: "POST",
          body: JSON.stringify({
            question_id: openCellId,
            answer: boardForm.elements.answer.value,
          }),
        });
        const delta = state.last_answer.points_delta;
        show(verdict, delta >= 0 ? `Верно, +${delta}` : `Мимо, ${delta}`, delta < 0);
        boardForm.elements.answer.value = "";
        render(state);
      } catch (exception) {
        error.hidden = false; error.textContent = exception.message;
        await refresh();
      } finally { button.disabled = false; }
    });

    // Выход из партии. Спрашиваем подтверждение: это поражение, а не пауза.
    matchShell.querySelector("[data-leave-match]")?.addEventListener("click", async event => {
      const button = event.currentTarget;
      if (!window.confirm("Выйти из партии? Победа достанется сопернику.")) return;
      button.disabled = true;
      try {
        const state = await apiFetch(`/api/arena/matches/${matchId}/leave/`, {
          method: "POST", body: "{}",
        });
        lastTag = null;
        render(state);
      } catch (exception) {
        button.disabled = false;
        alert(exception.message);
      }
    });

    // Отмена и принятие вызова прямо с экрана ожидания: игрок пришёл сюда,
    // а не в список партий.
    lobbyBlock?.querySelector("[data-lobby-cancel]")?.addEventListener("click", async () => {
      try {
        render(await apiFetch(`/api/arena/matches/${matchId}/cancel/`, { method: "POST", body: "{}" }));
        window.location.assign("/arena/");
      } catch (exception) {
        show(matchShell.querySelector("[data-lobby-error]"), exception.message, true);
      }
    });

    lobbyBlock?.querySelector("[data-lobby-accept]")?.addEventListener("click", async () => {
      try {
        await apiFetch(`/api/arena/matches/${matchId}/accept/`, { method: "POST", body: "{}" });
        await enter();
      } catch (exception) {
        show(matchShell.querySelector("[data-lobby-error]"), exception.message, true);
      }
    });

    // Вход в партию: пока не зашли оба, она не начинается — ни таймер, ни
    // общий вопрос, ни очередь хода.
    async function enter() {
      try {
        const state = await apiFetch(`/api/arena/matches/${matchId}/join/`, {
          method: "POST", body: "{}",
        });
        lastTag = null;
        render(state);
        startPolling(paceFor(state));
      } catch (_) {
        refresh();
      }
    }
    enter();
  }

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
    const reviewForm = event.target.closest("[data-review-form]");
    if (reviewForm) {
      event.preventDefault();
      const item = reviewForm.closest("[data-review-item]");
      const button = reviewForm.querySelector("[data-review-complete]");
      button.disabled = true;
      try {
        const data = await apiFetch(button.dataset.reviewComplete, {
          method: "POST", body: JSON.stringify({ answer: new FormData(reviewForm).get("answer") })
        });
        const result = item.querySelector("[data-review-result]");
        result.hidden = false; result.className = `verdict ${data.is_correct ? "is-correct" : "is-wrong"}`;
        result.textContent = data.message || (data.is_correct ? "Верно. Повтор зачтён." : "Пока неверно. Ошибка вернётся по новому расписанию.");
        window.lessonFlow?.applyRewards(data.rewards);
      } catch (error) { button.disabled = false; alert(error.message); }
      return;
    }
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

    // Кнопки магазина и домашек — обычные button, поэтому живут в обработчике
    // клика: в submit они не попадают и раньше молча ничего не делали.
    const submitHomework = event.target.closest("[data-submit-homework]");
    if (submitHomework) {
      const card = submitHomework.closest("[data-homework]"), error = card.querySelector("[data-homework-error]");
      submitHomework.disabled = true; if (error) error.hidden = true;
      try { await apiFetch(submitHomework.dataset.submitHomework, { method: "POST", body: "{}" }); const chip = document.createElement("span"); chip.className = "item-type-chip"; chip.textContent = "Сдано"; submitHomework.replaceWith(chip); }
      catch (exception) { if (error) { error.hidden = false; error.textContent = exception.message; } submitHomework.disabled = false; }
    }

    // Примерка: вещь показывается на месте, но нигде не сохраняется. Уход со
    // страницы возвращает то, что действительно надето, — поэтому и «до
    // выхода из магазина».
    const previewButton = event.target.closest("[data-shop-preview]");
    if (previewButton) {
      applyPreview(previewButton.dataset.shopPreview, previewButton.dataset.previewCode,
                   previewButton.closest("[data-shop-item]")?.querySelector("h2")?.textContent || "");
    }
    if (event.target.closest("[data-preview-reset]")) resetPreview();

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
          // Цена ушла вместе с покупкой: платить второй раз не за что.
          const price = row.querySelector("[data-shop-price]");
          if (price) {
            const owned = document.createElement("span");
            owned.className = "price-owned";
            owned.dataset.shopPrice = "";
            owned.textContent = "в инвентаре";
            price.replaceWith(owned);
          }
        } else if (shopButton.dataset.shopAction === "unequip") {
          window.location.reload();
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

    const startDiagnostic = event.target.closest("[data-start-diagnostic]");
    if (startDiagnostic) {
      const error = document.querySelector("[data-diagnostic-error]");
      startDiagnostic.disabled = true; if (error) error.hidden = true;
      try {
        const data = await apiFetch(startDiagnostic.dataset.startDiagnostic, { method: "POST", body: "{}" });
        window.location.assign(`/diagnostics/run/${data.result_id}/`);
      } catch (exception) {
        if (error) { error.hidden = false; error.textContent = exception.message; } else alert(exception.message);
        startDiagnostic.disabled = false;
      }
    }

    const resetLook = event.target.closest("[data-reset-look]");
    if (resetLook) {
      resetLook.disabled = true;
      try { await apiFetch("/api/shop/reset-look/", { method: "POST", body: "{}" }); window.location.reload(); }
      catch (exception) { alert(exception.message); resetLook.disabled = false; }
    }

    // Плеер собирается по клику: ссылка живёт минуты, поэтому запрашивать её
    // при загрузке страницы бессмысленно — к просмотру она уже протухнет.
    const playButton = event.target.closest("[data-video-play]");
    if (playButton) {
      const frame = playButton.closest("[data-video]");
      const note = frame.querySelector("[data-video-note]");
      playButton.disabled = true;
      note.textContent = "Готовим плеер…";
      try {
        const link = await apiFetch(frame.dataset.video);
        if (!link.can_embed) {
          note.replaceChildren();
          const outside = document.createElement("a");
          outside.className = "button"; outside.href = link.url;
          outside.rel = "noopener noreferrer"; outside.target = "_blank";
          outside.textContent = "Открыть видео";
          note.append(outside);
          return;
        }
        const player = document.createElement("iframe");
        player.src = link.url;
        player.title = `Видео: ${frame.dataset.title || "занятие"}`;
        player.loading = "lazy";
        player.allowFullscreen = true;
        // Хостинг проверяет домен по Referer, а общая политика сайта его
        // срезает: для плеера отправляем origin, но не путь.
        player.referrerPolicy = "strict-origin-when-cross-origin";
        frame.replaceChildren(player);
      } catch (error) {
        playButton.disabled = false;
        note.textContent = error.message;
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
    const counter = document.querySelector("[data-task-counter]");
    const bar = document.querySelector("[data-task-progress]");
    // Счётчик задач есть только на занятии. На «Задании дня» карточка задачи
    // одна и счётчика нет: без этой проверки здесь падал весь скрипт страницы,
    // а вместе с ним — отправка ответа и всё, что регистрируется ниже.
    if (!tasks.length || !counter || !bar) return;
    const current = tasks.findIndex(task => !task.classList.contains("is-hidden"));
    const position = current < 0 ? tasks.length : current + 1;
    counter.textContent = `${position} / ${tasks.length}`;
    bar.style.width = `${(position / tasks.length) * 100}%`;
  }
  // «Задание дня»: полоса прогресса и заголовок обновляются на месте — уходить
  // со страницы, чтобы увидеть засчитанный ответ, незачем.
  function markDailySolved(data) {
    if (!data.is_correct) return;
    const bar = document.querySelector("[data-daily-progress]");
    if (!bar) return;
    bar.style.width = "100%";
    const title = document.querySelector("[data-daily-title]");
    if (title) title.textContent = "1 из 1 · задание дня закрыто";
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
    const diagnosticForm = event.target.closest("[data-diagnostic-form]");
    if (diagnosticForm) {
      event.preventDefault();
      const button = diagnosticForm.querySelector("[type=submit]");
      const error = diagnosticForm.querySelector("[data-diagnostic-error]");
      button.disabled = true; error.hidden = true;
      try {
        const answers = {};
        diagnosticForm.querySelectorAll("input[name^=answer_]").forEach(input => {
          answers[input.name.slice(7)] = input.value;
        });
        await apiFetch(`/api/diagnostics/results/${diagnosticForm.dataset.resultId}/submit/`, {
          method: "POST", body: JSON.stringify({ answers }),
        });
        window.location.assign(diagnosticForm.dataset.doneUrl);
      } catch (exception) {
        error.hidden = false; error.textContent = exception.message; button.disabled = false;
      }
    }

    const mockForm = event.target.closest("[data-mock-form]");
    if (mockForm) {
      event.preventDefault();
      if (mockForm.dataset.submitting === "true") return;
      mockForm.dataset.submitting = "true";
      const button = mockForm.querySelector("[type=submit]"), errorOutput = mockForm.querySelector("[data-mock-error]");
      button.disabled = true;
      try {
        if (Date.now() < new Date(document.querySelector("[data-mock-timer]").dataset.deadline).getTime()) {
          await mockForm.waitForUploads?.();
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
      try { const data = await apiFetch(`/api/assignments/${task.dataset.assignmentId}/attempt/`, { method: "POST", body: JSON.stringify({ answer: new FormData(attemptForm).get("answer"), context: attemptForm.dataset.context }) }); verdict.hidden = false; verdict.className = `verdict ${data.is_correct ? "is-correct" : "is-wrong"}`; verdict.textContent = data.is_correct === null ? "Решение отправлено на экспертную проверку." : (data.is_correct ? "Верно! Можно двигаться дальше." : "Пока неверно. Ошибка сохранена для отработки."); const next = task.querySelector("[data-next-task]"); if (next) next.hidden = false; renderProgress(task, data.progress); markDailySolved(data); window.lessonFlow?.applyRewards(data.rewards); }
      catch (error) { verdict.hidden = false; verdict.className = `verdict ${error.code === "answer_not_understood" ? "is-unclear" : "is-wrong"}`; verdict.textContent = error.message; button.disabled = false; }
    }
    const hintForm = event.target.closest("[data-hint-form]");
    if (hintForm) {
      event.preventDefault(); const task = hintForm.closest("[data-task]"), button = hintForm.querySelector("button"), input = hintForm.querySelector("input"), history = task.querySelector("[data-mentor-history]"); button.disabled = true;
      const studentMessage = document.createElement("p"); studentMessage.className = "message message-student"; studentMessage.textContent = input.value; history.append(studentMessage);
      try { const data = await apiFetch(`/api/assignments/${task.dataset.assignmentId}/hint/`, { method: "POST", body: JSON.stringify({ question: input.value, context: "lesson" }) }); const message = document.createElement("p"); message.className = "message message-mentor"; message.textContent = data.hint; history.append(message); input.value = ""; if (data.escalated_to_expert) hintForm.remove(); else button.disabled = false; }
      catch (error) { const message = document.createElement("p"); message.className = "form-error"; message.textContent = error.message; history.append(message); button.disabled = false; }
    }
  });

  // Прогноз: числа доезжают до нового значения, а шкала едет вместе с ними.
  // Мгновенная подстановка выглядела как перезагрузка страницы, а шкала и
  // вовсе оставалась на месте — казалось, что рычаги ни на что не влияют.
  function countTo(node, value) {
    const from = Number(node.textContent) || 0;
    const to = Number(value);
    if (!Number.isFinite(to) || from === to) { node.textContent = value; return; }
    const started = performance.now(), duration = 420;
    const step = now => {
      const progress = Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      node.textContent = Math.round(from + (to - from) * eased);
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function moveGauge(gauge) {
    if (!gauge) return;
    const axis = document.querySelector(".gauge-axis");
    if (!axis) return;
    const set = (selector, styles) => {
      const node = axis.querySelector(selector);
      if (node) Object.assign(node.style, styles);
    };
    set(".gauge-fill", { width: `${gauge.now_percent}%` });
    set(".gauge-now", { left: `${gauge.now_percent}%` });
    set(".gauge-band", { left: `${gauge.band_left_percent}%`, width: `${gauge.band_width_percent}%` });
    set(".gauge-flag:not(.gauge-ceiling)", { left: `${gauge.target_percent}%` });
    if (gauge.ceiling_percent !== null) set(".gauge-ceiling", { left: `${gauge.ceiling_percent}%` });
    // Метка потолка переезжала, а подпись оставалась прежней — и врала.
    if (gauge.ceiling_primary !== null && gauge.ceiling_primary !== undefined) {
      const primary = Number(gauge.ceiling_primary).toFixed(1).replace(".", ",");
      const label = document.querySelector("[data-gauge-ceiling-label]");
      if (label) label.textContent = `потолок ${primary}`;
      const tile = document.querySelector("[data-ceiling-primary]");
      if (tile) tile.textContent = primary;
    }
    const caption = axis.querySelector(".gauge-caption-now");
    if (caption) {
      caption.style.left = `${gauge.now_percent}%`;
      caption.textContent = `сейчас ${Number(gauge.primary).toFixed(1).replace(".", ",")}`;
    }
    layoutGaugeLabels();
  }

  const hours = document.querySelector("[data-forecast-hours]"), date = document.querySelector("[data-forecast-date]");
  if (hours && date) {
    let timer;
    const refresh = () => {
      clearTimeout(timer);
      document.querySelector("[data-hours-output]").textContent = hours.value;
      timer = setTimeout(async () => {
        const error = document.querySelector("[data-forecast-error]");
        try {
          const params = new URLSearchParams({ weekly_hours: hours.value });
          if (date.value) params.set("exam_date", date.value);
          const data = await apiFetch(`/api/forecast/?${params}`);
          countTo(document.querySelector("[data-current-score]"), data.current_score);
          countTo(document.querySelector("[data-ceiling-score]"), data.ceiling_score);
          moveGauge(data.gauge);
          // Почему число перестало расти: время уже не узкое место.
          const limit = document.querySelector("[data-forecast-limit]");
          if (limit) {
            limit.textContent = data.limited_by === "scope"
              ? "При такой нагрузке успеваешь весь материал плана: дальше потолок "
                + "держит не время, а объём программы и текущее освоение тем."
              : `Не успеваешь ${data.unreachable_count} тем — потолок держит время. `
                + "Больше часов в неделю или более поздняя дата поднимут его.";
          }
          // Сколько часов нужно, чтобы успеть всё к выбранной дате: совет
          // зависит от даты, а не от положения ползунка.
          const advice = document.querySelector("[data-forecast-advice]");
          const mark = document.querySelector("[data-lever-mark]");
          const need = data.recommended_hours;
          if (advice) {
            advice.hidden = !need;
            if (need) {
              advice.textContent = need > Number(hours.value)
                ? `Чтобы пройти весь план до экзамена, нужно ${need} ч в неделю. `
                  + `Сейчас выбрано ${hours.value} — часть тем не поместится.`
                : `Чтобы пройти весь план до экзамена, нужно ${need} ч в неделю. `
                  + "Текущей нагрузки хватает.";
            }
          }
          if (mark) {
            mark.hidden = !need;
            if (need) {
              const span = Number(hours.max) - Number(hours.min);
              const place = (Math.min(Math.max(need, Number(hours.min)), Number(hours.max))
                - Number(hours.min)) / span * 100;
              mark.style.left = `${place.toFixed(1)}%`;
              mark.textContent = `нужно ${need} ч`;
            }
          }
          document.querySelector("[data-forecast-applied]")?.setAttribute("hidden", "");
          error.hidden = true;
        } catch (exception) { error.hidden = false; error.textContent = exception.message; }
      }, 250);
    };
    hours.addEventListener("input", refresh); date.addEventListener("change", refresh);

    // Применение сценария: рычаги сами по себе ничего не меняют, но решение
    // «буду заниматься столько» должно доезжать до плана и расписания.
    document.querySelector("[data-forecast-apply]")?.addEventListener("click", async event => {
      const button = event.currentTarget;
      const error = document.querySelector("[data-forecast-error]");
      const applied = document.querySelector("[data-forecast-applied]");
      button.disabled = true; error.hidden = true;
      try {
        const body = { weekly_hours: Number(hours.value) };
        if (date.value) body.exam_date = date.value;
        const data = await apiFetch("/api/forecast/apply/", {
          method: "POST", body: JSON.stringify(body),
        });
        countTo(document.querySelector("[data-current-score]"), data.current_score);
        countTo(document.querySelector("[data-ceiling-score]"), data.ceiling_score);
        if (applied) {
          applied.textContent = `План перестроен: ${data.plan_items} пунктов. `
            + "Расписание уже показывает новый порядок.";
          applied.hidden = false;
        }
      } catch (exception) {
        error.hidden = false; error.textContent = exception.message;
      } finally { button.disabled = false; }
    });
  }

  const draftForm = document.querySelector("[data-mock-form]");
  if (draftForm) {
    const state = JSON.parse(document.getElementById("mock-draft-state").textContent);
    const status = draftForm.querySelector("[data-draft-status]");
    const inputs = [...draftForm.querySelectorAll("input[name^=answer_]")];
    inputs.forEach(input => { input.value = state.answers[input.name.slice(7)] || ""; });
    let revision = state.revision, dirty = false, saving = false, conflicted = false;
    const expired = () => Date.now() >= new Date(document.querySelector("[data-mock-timer]").dataset.deadline).getTime();
    async function saveDraft() {
      if (!dirty || saving || conflicted || expired() || draftForm.dataset.submitting === "true") return;
      saving = true; dirty = false;
      const answers = Object.fromEntries(inputs.map(input => [input.name.slice(7), input.value]));
      status.textContent = "Сохраняем ответы…";
      try {
        const data = await apiFetch(`/api/mocks/results/${draftForm.dataset.resultId}/draft/`, {
          method: "POST", body: JSON.stringify({ answers, revision })
        });
        revision = data.revision;
        status.textContent = "Ответы сохранены";
      } catch (error) {
        dirty = true;
        if (error.message.includes("другой вкладке")) conflicted = true;
        status.textContent = `Ответы не сохранены: ${error.message}`;
      } finally { saving = false; }
      if (dirty && !conflicted) setTimeout(saveDraft, 0);
    }
    inputs.forEach(input => input.addEventListener("input", () => { dirty = true; saveDraft(); }));
    window.addEventListener("online", saveDraft);
    window.addEventListener("beforeunload", event => {
      if (dirty || saving) { event.preventDefault(); event.returnValue = ""; }
    });
    const uploads = new Map(), uploadErrors = new Map();
    draftForm.querySelectorAll("[data-part2-assignment]").forEach(task => {
      const input = task.querySelector("input[type=file]");
      const note = document.createElement("p"); note.setAttribute("role", "status"); task.append(note);
      if (state.uploaded.includes(Number(task.dataset.part2Assignment))) note.textContent = "Решение уже загружено. Можно заменить до завершения пробника.";
      input.addEventListener("change", () => {
        const file = input.files[0]; if (!file) return;
        input.disabled = true; note.textContent = "Загружаем решение…";
        uploadErrors.delete(input);
        const payload = new FormData(); payload.append("assignment", task.dataset.part2Assignment);
        payload.append("mock_result", draftForm.dataset.resultId); payload.append("file", file);
        const pending = apiFetch("/api/expert-reviews/submit/", { method: "POST", body: payload })
          .then(() => { note.textContent = "Решение загружено"; })
          .catch(error => { uploadErrors.set(input, error); note.textContent = `Не загружено: ${error.message}. Выберите файл повторно.`; input.value = ""; })
          .finally(() => { input.disabled = false; uploads.delete(input); });
        uploads.set(input, pending);
      });
    });
    draftForm.waitForUploads = async () => {
      await Promise.all(uploads.values());
      if (uploadErrors.size) throw new Error("Есть незагруженные решения. Повторите выбор файла до завершения пробника.");
    };
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

  // Заливка ползунка до бегунка: в WebKit у трека нет «прогресса», поэтому
  // долю заливки держим в CSS-переменной и обновляем при каждом движении.
  const paintRange = range => {
    const min = Number(range.min || 0), max = Number(range.max || 100);
    const share = max > min ? (Number(range.value) - min) / (max - min) : 0;
    range.style.setProperty("--fill", `${Math.round(share * 1000) / 10}%`);
  };
  document.querySelectorAll("input[type=range]").forEach(paintRange);
  document.addEventListener("input", event => {
    if (event.target.matches?.("input[type=range]")) paintRange(event.target);
  });

  // Небольшие серверные formset-формы Studio: Django по-прежнему валидирует
  // и сохраняет строки, JavaScript лишь добавляет и помечает их на удаление.
  document.querySelectorAll("form[data-formset]").forEach(form => {
    const prefix = form.dataset.formset;
    const total = form.querySelector(`#id_${prefix}-TOTAL_FORMS`);
    const rows = form.querySelector("[data-formset-rows]");
    const template = form.querySelector("[data-formset-template]");
    const add = form.querySelector("[data-formset-add]");
    if (!total || !rows || !template || !add) return;
    add.addEventListener("click", () => {
      const index = Number(total.value);
      const fragment = template.content.cloneNode(true);
      fragment.querySelectorAll("*").forEach(element => {
        [...element.attributes].forEach(attribute => {
          if (attribute.value.includes("__prefix__")) {
            element.setAttribute(attribute.name, attribute.value.replaceAll("__prefix__", index));
          }
        });
      });
      rows.append(fragment);
      total.value = String(index + 1);
    });
    form.addEventListener("click", event => {
      const remove = event.target.closest("[data-formset-remove]");
      if (!remove) return;
      const row = remove.closest("[data-formset-row]");
      const deletion = row?.querySelector('input[name$="-DELETE"]');
      const objectId = row?.querySelector('input[name$="-id"]');
      if (objectId?.value && deletion) {
        deletion.value = "on";
        row.hidden = true;
      } else {
        row?.remove();
      }
    });
  });

  const answerType = document.querySelector("[data-answer-type]");
  const answerSpecField = document.querySelector("[data-answer-spec-field]");
  if (answerType && answerSpecField) {
    const updateAnswerSpec = () => {
      answerSpecField.hidden = !["root_set", "root_families"].includes(answerType.value);
    };
    answerType.addEventListener("change", updateAnswerSpec);
    updateAnswerSpec();
  }
})();
