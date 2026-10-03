// Mathemation · Аватары, рамки, символы лиг
// Плагин строит в Figma редактируемые векторные компоненты, наборы вариантов
// и кадры-ключи для Smart Animate. Данные вшиты в файл при сборке.

const DATA = /*__DATA__*/null;
const CONCEPTS = /*__CONCEPTS__*/null;

const INK = '#10162A', MUTED = '#6B7590', BG = '#F5F7FE', CARD = '#FFFFFF',
      LINE = '#DCE3F6', PRIMARY = '#4F6BEA';
const TRACK = 'Призма — объёмный градиент и стекло';

let FONT_B = { family: 'Inter', style: 'Semi Bold' };
let FONT_R = { family: 'Inter', style: 'Regular' };

function hexToRgb(h) {
  const n = parseInt(h.slice(1), 16);
  return { r: ((n >> 16) & 255) / 255, g: ((n >> 8) & 255) / 255, b: (n & 255) / 255 };
}
function solid(h, o) { return { type: 'SOLID', color: hexToRgb(h), opacity: o === undefined ? 1 : o }; }

async function ensureFonts() {
  const cand = [
    [{ family: 'Inter', style: 'Semi Bold' }, { family: 'Inter', style: 'Regular' }],
    [{ family: 'Inter', style: 'Bold' }, { family: 'Inter', style: 'Regular' }],
    [{ family: 'Roboto', style: 'Medium' }, { family: 'Roboto', style: 'Regular' }]
  ];
  for (const [b, r] of cand) {
    try {
      await figma.loadFontAsync(b);
      await figma.loadFontAsync(r);
      FONT_B = b; FONT_R = r; return;
    } catch (e) { /* пробуем следующий */ }
  }
  throw new Error('Не удалось загрузить ни один шрифт (Inter / Roboto).');
}

function text(str, size, color, bold, width) {
  const t = figma.createText();
  t.fontName = bold ? FONT_B : FONT_R;
  t.characters = str;
  t.fontSize = size;
  t.lineHeight = { unit: 'PERCENT', value: 140 };
  t.fills = [solid(color)];
  if (width) { t.textAutoResize = 'HEIGHT'; t.resize(width, t.height); }
  return t;
}

function vstack(name, gap, pad, fill, radius) {
  const f = figma.createFrame();
  f.name = name;
  f.layoutMode = 'VERTICAL';
  f.primaryAxisSizingMode = 'AUTO';
  f.counterAxisSizingMode = 'AUTO';
  f.itemSpacing = gap;
  f.paddingTop = f.paddingBottom = f.paddingLeft = f.paddingRight = pad;
  f.fills = fill ? [solid(fill)] : [];
  f.cornerRadius = radius || 0;
  f.clipsContent = false;
  return f;
}

function hstack(name, gap, pad, fill, radius) {
  const f = vstack(name, gap, pad, fill, radius);
  f.layoutMode = 'HORIZONTAL';
  f.counterAxisAlignItems = 'CENTER';
  return f;
}

// SVG → компонент (детей переносим внутрь компонента, лишний фрейм убираем)
function componentFromSvg(svg, name) {
  const node = figma.createNodeFromSvg(svg);
  const c = figma.createComponent();
  c.name = name;
  c.resizeWithoutConstraints(node.width, node.height);
  c.fills = [];
  c.clipsContent = false;
  const kids = node.children.slice();
  for (const k of kids) c.appendChild(k);
  node.remove();
  return c;
}

function frameFromSvg(svg, name) {
  const node = figma.createNodeFromSvg(svg);
  node.name = name;
  node.fills = [];
  node.clipsContent = false;
  return node;
}

// Карточка: элемент + подпись
function card(child, caption, sub) {
  const f = vstack('Карточка · ' + caption, 10, 18, CARD, 20);
  f.counterAxisAlignItems = 'CENTER';
  f.strokes = [solid(LINE)];
  f.strokeWeight = 1;
  f.appendChild(child);
  const t = text(caption, 13, INK, true);
  t.textAlignHorizontal = 'CENTER';
  f.appendChild(t);
  if (sub) {
    const s = text(sub, 11, MUTED, false);
    s.textAlignHorizontal = 'CENTER';
    f.appendChild(s);
  }
  return f;
}

function rows(items, perRow, gap) {
  const wrap = vstack('Сетка', gap, 0, null, 0);
  for (let i = 0; i < items.length; i += perRow) {
    const r = hstack('Ряд', gap, 0, null, 0);
    r.counterAxisAlignItems = 'MIN';
    for (const it of items.slice(i, i + perRow)) r.appendChild(it);
    wrap.appendChild(r);
  }
  return wrap;
}

function board(title, subtitle) {
  const b = vstack(title, 28, 56, BG, 32);
  const head = vstack('Заголовок', 6, 0, null, 0);
  head.appendChild(text(title, 30, INK, true));
  if (subtitle) head.appendChild(text(subtitle, 14, MUTED, false, 720));
  b.appendChild(head);
  return b;
}

// Собираем набор вариантов из готовых компонентов
function makeVariantSet(comps, name) {
  try {
    let x = 0;
    for (const c of comps) { c.x = x; c.y = 0; x += c.width + 40; }
    const set = figma.combineAsVariants(comps, figma.currentPage);
    set.name = name;
    set.layoutMode = 'HORIZONTAL';
    set.layoutWrap = 'WRAP';
    set.primaryAxisSizingMode = 'FIXED';
    set.counterAxisSizingMode = 'AUTO';
    set.itemSpacing = 32;
    set.counterAxisSpacing = 32;
    set.paddingTop = set.paddingBottom = set.paddingLeft = set.paddingRight = 32;
    set.resize(1040, set.height);
    set.fills = [solid(CARD)];
    set.strokes = [solid(LINE)];
    set.cornerRadius = 24;
    return set;
  } catch (e) {
    // если объединить не удалось — вернём просто ряд компонентов
    const wrap = rows(comps, 8, 24);
    wrap.name = name;
    return wrap;
  }
}

async function build(opts) {
  await ensureFonts();

  const page = figma.createPage();
  page.name = 'Mathemation · аватары, рамки, лиги';
  figma.currentPage = page;
  page.backgrounds = [solid('#EDF0F9')];

  const root = vstack('Mathemation · визуальный набор', 48, 64, '#EDF0F9', 0);
  root.x = 0; root.y = 0;

  const title = vstack('Титул', 10, 0, null, 0);
  title.appendChild(text('Аватары, рамки и символы лиг', 44, INK, true));
  title.appendChild(text('Трек «' + TRACK + '». Все элементы — живые векторы: ' +
    'цвета, формы и обводки редактируются прямо здесь.', 15, MUTED, false, 820));
  root.appendChild(title);

  const D = DATA;

  if (opts.set) {
    // ── Аватары ────────────────────────────────────────────────────────
    const avComps = D.avatars.map(function (it) { return componentFromSvg(it.s, 'Аватар=' + it.n); });
    const avSet = makeVariantSet(avComps, 'Аватар');
    const bAv = board('Аватары', '16 аватаров, 128×128, компонент с одним свойством «Аватар»');
    bAv.appendChild(avSet);
    bAv.appendChild(rows(D.avatars.map(function (it, i) {
      const inst = avComps[i].createInstance(); inst.resize(96, 96);
      return card(inst, it.n, it.c);
    }), 8, 20));
    root.appendChild(bAv);

    // ── Рамки ──────────────────────────────────────────────────────────
    const frComps = D.frames.map(function (it) { return componentFromSvg(it.s, 'Рамка=' + it.n); });
    const frSet = makeVariantSet(frComps, 'Рамка');
    const bFr = board('Рамки', '14 рамок, 160×160, отверстие под аватар Ø104 в центре. ' +
      'Рамка — отдельный слой поверх аватара, поэтому сочетается с любым из 16.');
    bFr.appendChild(frSet);
    const avForFrame = D.avatars.filter(function (a) { return a.k === 'pi'; })[0];
    bFr.appendChild(rows(D.frames.map(function (it, i) {
      const box = figma.createFrame();
      box.name = 'Композиция · ' + it.n;
      box.resize(160, 160); box.fills = []; box.clipsContent = false;
      const av = frameFromSvg(avForFrame.s, 'Аватар (пример)');
      av.x = 28; av.y = 28; av.resize(104, 104);
      box.appendChild(av);
      const dec = frComps[i].createInstance(); dec.x = 0; dec.y = 0;
      box.appendChild(dec);
      return card(box, it.n, it.c);
    }), 7, 20));
    root.appendChild(bFr);

    // ── Лиги ───────────────────────────────────────────────────────────
    const lgComps = D.leagues.map(function (it) {
      return componentFromSvg(it.s, 'Лига=' + it.l + ', Место=' + it.p);
    });
    const lgSet = makeVariantSet(lgComps, 'Знак лиги');
    const bLg = board('Символы лиг', 'Четыре лиги × базовый знак и три места. ' +
      'Место читается металлом пластины и жетоном с номером — глиф лиги остаётся в её цвете.');
    bLg.appendChild(lgSet);
    bLg.appendChild(rows(D.leagues.map(function (it, i) {
      const inst = lgComps[i].createInstance(); inst.resize(88, 88);
      return card(inst, it.l, it.p === '—' ? 'базовый знак' : it.p + ' место');
    }), 8, 20));
    root.appendChild(bLg);
  }

  // ── Варианты знаков лиг (для выбора) ─────────────────────────────────
  if (opts.variants) {
    const bV = board('Варианты знаков лиг', 'Слева — форма пластины для Альфы и Сигмы, ' +
      'справа — начертание греческих символов. Выберите по одному из каждого ряда.');
    const plates = vstack('Пластины', 14, 0, null, 0);
    plates.appendChild(text('Форма пластины', 18, INK, true));
    plates.appendChild(rows(D.plates.map(function (it) {
      const n = frameFromSvg(it.s, it.l + ' · ' + it.n); n.resize(96, 96);
      return card(n, it.n, it.l);
    }), 4, 20));
    bV.appendChild(plates);

    const gl = vstack('Начертание', 14, 0, null, 0);
    gl.appendChild(text('Начертание символов', 18, INK, true));
    const seen = {};
    for (const it of D.glyphs) {
      if (!seen[it.v]) { seen[it.v] = { n: it.n, items: [] }; }
      seen[it.v].items.push(it);
    }
    for (const v in seen) {
      const rowFrame = vstack('Вариант · ' + seen[v].n, 10, 18, CARD, 20);
      rowFrame.strokes = [solid(LINE)];
      rowFrame.appendChild(text(seen[v].n, 15, INK, true));
      const strip = hstack('Буквы', 16, 0, null, 0);
      for (const it of seen[v].items) {
        const n = frameFromSvg(it.s, it.l); n.resize(84, 84);
        strip.appendChild(n);
      }
      rowFrame.appendChild(strip);
      gl.appendChild(rowFrame);
    }
    bV.appendChild(gl);
    root.appendChild(bV);
  }

  // ── Анимации ─────────────────────────────────────────────────────────
  if (opts.anim) {
    const bAn = board('Кадры анимаций',
      'Каждая строка — три кадра одного концепта. Между кадрами проставлен переход ' +
      'Smart Animate: нажмите Present, чтобы увидеть движение. Тайминги и кривые — в подписи.');
    for (const c of CONCEPTS) {
      const kf = D.anim.filter(function (a) { return a.cid === c.id; });
      if (!kf.length) continue;
      const row = vstack('Концепт · ' + c.ru, 12, 20, CARD, 20);
      row.strokes = [solid(LINE)];
      row.appendChild(text(c.ru, 16, INK, true));
      row.appendChild(text(c.idea, 12, MUTED, false, 760));
      const meta = hstack('Параметры', 16, 0, null, 0);
      meta.appendChild(text('длительность: ' + c.dur, 11, PRIMARY, true));
      meta.appendChild(text('кривая: ' + c.ease, 11, PRIMARY, true));
      meta.appendChild(text('повтор: ' + c.loop, 11, PRIMARY, true));
      row.appendChild(meta);
      const strip = hstack('Кадры', 24, 0, null, 0);
      const made = [];
      for (const k of kf) {
        const holder = figma.createFrame();
        holder.name = k.n; holder.resize(180, 180);
        holder.fills = [solid(BG)]; holder.cornerRadius = 16; holder.clipsContent = true;
        const art = frameFromSvg(k.s, 'Кадр');
        art.x = (180 - art.width) / 2; art.y = (180 - art.height) / 2;
        holder.appendChild(art);
        strip.appendChild(holder); made.push(holder);
      }
      try {
        for (let i = 0; i < made.length; i++) {
          const next = made[(i + 1) % made.length];
          made[i].reactions = [{
            trigger: { type: 'AFTER_TIMEOUT', timeout: 0.15 },
            action: {
              type: 'NODE', destinationId: next.id, navigation: 'NAVIGATE',
              transition: { type: 'SMART_ANIMATE', easing: { type: 'EASE_IN_AND_OUT' }, duration: 0.8 },
              preserveScrollPosition: false
            }
          }];
        }
      } catch (e) { /* прототип не обязателен */ }
      row.appendChild(strip);
      bAn.appendChild(row);
    }
    root.appendChild(bAn);
  }

  figma.currentPage.appendChild(root);
  figma.viewport.scrollAndZoomIntoView([root]);
  return root;
}

figma.showUI(__html__, { width: 380, height: 480, themeColors: true });

figma.ui.onmessage = async function (msg) {
  if (msg.type !== 'build') return;
  try {
    figma.ui.postMessage({ type: 'status', text: 'Собираю…' });
    await build(msg.opts);
    figma.ui.postMessage({ type: 'done' });
    figma.notify('Готово — макет собран на новой странице');
  } catch (e) {
    figma.ui.postMessage({ type: 'error', text: String(e && e.message ? e.message : e) });
    figma.notify('Ошибка: ' + e, { error: true });
  }
};
