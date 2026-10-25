// A local stand-in for the claude.ai Dashboard runtime, so page.html runs unchanged
// in a plain browser. It implements the parts page.html uses: dash.data, dash.onData,
// dash.calc and dash.colors, over the CSV files listed in window.DASH_DATASETS.
(() => {
  const datasets = {};   // id -> {status, data, columns, message}
  const calcs = {};      // id -> {inputs, fn}
  const listeners = [];

  const colors = Array.from({ length: 8 }, (_, i) => `var(--dash-series-${i})`);

  function calcResult(id) {
    const c = calcs[id];
    const inputs = c.inputs.map((i) => dash.data(i));
    const waiting = inputs.find((d) => d.status !== 'ok');
    if (waiting) return { status: waiting.status, data: [], message: waiting.message };
    try {
      const data = c.fn(...inputs.map((d) => d.data));
      return { status: 'ok', data, columns: data && data[0] ? Object.keys(data[0]) : [] };
    } catch (e) {
      console.error(`calc ${id} failed`, e);
      return { status: 'error', data: [], message: String(e) };
    }
  }

  const dash = {
    colors,
    data(id) {
      if (id in calcs) return calcResult(id);
      return datasets[id] || { status: 'missing', data: [], message: `no dataset ${id}` };
    },
    onData(fn) {
      listeners.push(fn);
      fn();
    },
    calc(id, spec) {
      calcs[id] = spec;
    },
    refresh(id) {
      load(id);
    },
    params: () => ({}),
    setParams() {},
    resetParams() {},
    setLink() {},
  };
  window.dash = dash;

  function notify() {
    for (const fn of listeners) {
      try { fn(); } catch (e) { console.error(e); }
    }
  }

  async function load(id) {
    const url = window.DASH_DATASETS[id];
    datasets[id] = { status: 'loading', data: [] };
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
      const rows = d3.csvParse(await res.text());
      datasets[id] = { status: 'ok', data: rows, columns: rows.columns };
    } catch (e) {
      datasets[id] = { status: 'error', data: [], message: String(e) };
      console.error(e);
    }
    notify();
  }

  // Put page.html into #dash-root, then run its scripts in order, each in its own scope.
  async function mount() {
    const root = document.getElementById('dash-root');
    const html = await (await fetch('page.html', { cache: 'no-store' })).text();
    const tpl = document.createElement('template');
    tpl.innerHTML = html;
    const scripts = [...tpl.content.querySelectorAll('script')];
    scripts.forEach((s) => s.remove());
    root.appendChild(tpl.content);
    for (const s of scripts) {
      const el = document.createElement('script');
      el.textContent = `(() => {\n${s.textContent}\n})();`;
      document.body.appendChild(el);
    }
  }

  async function showUpdated() {
    const el = document.getElementById('updated');
    try {
      const meta = await (await fetch('data/meta.json', { cache: 'no-store' })).json();
      el.textContent = `Data built ${new Date(meta.updated).toLocaleString()} from results/ · ${meta.models} models`;
    } catch {
      el.textContent = 'No data yet: run `uv run aibench dashboard`';
    }
  }

  function themeToggle() {
    const btn = document.getElementById('theme-toggle');
    const html = document.documentElement;
    let saved = null;
    try { saved = localStorage.getItem('aibench-theme'); } catch {}
    if (saved) html.dataset.theme = saved;
    btn.addEventListener('click', () => {
      const dark = html.dataset.theme
        ? html.dataset.theme === 'dark'
        : matchMedia('(prefers-color-scheme: dark)').matches;
      html.dataset.theme = dark ? 'light' : 'dark';
      try { localStorage.setItem('aibench-theme', html.dataset.theme); } catch {}
    });
  }

  // Charts size themselves from clientWidth, so redraw when the width changes.
  let lastWidth = 0;
  let timer = null;
  window.addEventListener('resize', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const w = document.getElementById('dash-root').clientWidth;
      if (w !== lastWidth) { lastWidth = w; notify(); }
    }, 150);
  });

  themeToggle();
  showUpdated();
  for (const id of Object.keys(window.DASH_DATASETS)) datasets[id] = { status: 'loading', data: [] };
  mount().then(() => {
    lastWidth = document.getElementById('dash-root').clientWidth;
    return Promise.all(Object.keys(window.DASH_DATASETS).map(load));
  });
})();
