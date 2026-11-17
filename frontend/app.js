let rows = [];
let sortKey = 'score';
let sortDir = -1;

document.getElementById('load-btn').addEventListener('click', () => {
  document.getElementById('file-input').click();
});

document.getElementById('file-input').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  document.getElementById('file-name').textContent = file.name;
  const reader = new FileReader();
  reader.onload = (ev) => {
    try {
      const report = JSON.parse(ev.target.result);
      loadReport(report);
    } catch (err) {
      alert('Could not parse that file as JSON: ' + err.message);
    }
  };
  reader.readAsText(file);
});

function bandColor(score) {
  if (score >= 70) return getComputedStyle(document.documentElement).getPropertyValue('--up');
  if (score >= 40) return getComputedStyle(document.documentElement).getPropertyValue('--mid');
  return getComputedStyle(document.documentElement).getPropertyValue('--down');
}

function bandKey(score) {
  if (score >= 70) return 'strong';
  if (score >= 40) return 'moderate';
  return 'weak';
}

function loadReport(report) {
  const ranked = report.ranked || [];
  const tickerDomains = report.ticker_domains || {};

  rows = ranked.map(r => {
    const qm = r.quant_metrics || {};
    const fu = r.fundamentals || {};
    const flags = (r.flags || []).concat(
      (r.llm_analysis && r.llm_analysis.macro_adversities) || []
    );
    return {
      ticker: r.ticker,
      domains: tickerDomains[r.ticker] || (report.domain ? [report.domain] : []),
      score: r.score,
      price: fu.current_price,
      trend: qm.trend_score,
      sortino: qm.sortino,
      drawdown: qm.max_drawdown,
      flags: flags,
      flagCount: flags.length,
    };
  });

  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('content').style.display = 'block';
  document.getElementById('disclaimer').textContent = report.disclaimer || '';

  populateDomainFilter();
  renderStats();
  render();
}

function populateDomainFilter() {
  const select = document.getElementById('domain-filter');
  select.innerHTML = '<option value="">All domains</option>';
  const domains = new Set();
  rows.forEach(r => r.domains.forEach(d => domains.add(d)));
  [...domains].sort().forEach(d => {
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = d.replace(/_/g, ' ');
    select.appendChild(opt);
  });
}

function renderStats() {
  const strip = document.getElementById('stat-strip');
  const scored = rows.filter(r => typeof r.score === 'number');
  const avg = scored.length ? (scored.reduce((a, r) => a + r.score, 0) / scored.length) : 0;
  const strong = scored.filter(r => r.score >= 70).length;
  const flagged = rows.filter(r => r.flagCount > 0).length;

  strip.innerHTML = `
    <div class="stat"><div class="label">Tickers loaded</div><div class="value num">${rows.length}</div></div>
    <div class="stat"><div class="label">Average score</div><div class="value num">${avg.toFixed(1)}</div></div>
    <div class="stat"><div class="label">Strong (&ge;70)</div><div class="value num" style="color:var(--up)">${strong}</div></div>
    <div class="stat"><div class="label">With risk flags</div><div class="value num" style="color:var(--down)">${flagged}</div></div>
  `;
}

function currentFilters() {
  return {
    domain: document.getElementById('domain-filter').value,
    band: document.getElementById('band-filter').value,
    search: document.getElementById('search').value.trim().toUpperCase(),
  };
}

function render() {
  const { domain, band, search } = currentFilters();
  let filtered = rows.filter(r => {
    if (domain && !r.domains.includes(domain)) return false;
    if (band && bandKey(r.score) !== band) return false;
    if (search && !r.ticker.toUpperCase().includes(search)) return false;
    return true;
  });

  filtered.sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (av == null) return 1;
    if (bv == null) return -1;
    return av > bv ? sortDir : av < bv ? -sortDir : 0;
  });

  const tbody = document.getElementById('table-body');
  tbody.innerHTML = filtered.map(r => {
    const color = bandColor(r.score || 0);
    const priceStr = r.price != null ? '$' + Number(r.price).toFixed(2) : '&mdash;';
    const trendStr = r.trend === 1 ? '&#9650; up' : r.trend === -1 ? '&#9660; down' : '&#8226; flat';
    const sortinoStr = r.sortino != null ? r.sortino.toFixed(2) : '&mdash;';
    const ddStr = r.drawdown != null ? (r.drawdown * 100).toFixed(1) + '%' : '&mdash;';
    const domainTags = r.domains.map(d => `<span class="domain-tag">${d.replace(/_/g, ' ')}</span>`).join('');
    const flagsTitle = r.flags.join(' | ').replace(/"/g, '&quot;');

    return `
      <tr>
        <td class="ticker" style="--band-color:${color}">${r.ticker}</td>
        <td>${domainTags || '&mdash;'}</td>
        <td>
          <div class="score-cell">
            <span class="num">${r.score != null ? r.score.toFixed(1) : '&mdash;'}</span>
            <div class="score-bar"><div style="width:${r.score || 0}%; background:${color};"></div></div>
          </div>
        </td>
        <td class="num">${priceStr}</td>
        <td class="num">${trendStr}</td>
        <td class="num">${sortinoStr}</td>
        <td class="num">${ddStr}</td>
        <td class="flags-cell" title="${flagsTitle}">${r.flagCount ? r.flagCount + ' &mdash; ' + r.flags[0] : '&mdash;'}</td>
      </tr>
    `;
  }).join('');
}

document.querySelectorAll('thead th').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.key;
    if (sortKey === key) sortDir *= -1;
    else { sortKey = key; sortDir = -1; }
    render();
  });
});

['domain-filter', 'band-filter'].forEach(id =>
  document.getElementById(id).addEventListener('change', render)
);
document.getElementById('search').addEventListener('input', render);

// ---------- Backend connection ----------
// API_BASE comes from config.js. If the backend isn't running, the run panel
// stays hidden and you can still load a saved report.json by hand.
// Empty = same server that served this page (normal case). If the page was
// double-clicked open from disk (file://), fall back to the local backend.
let apiBase = (window.STOCK_API_BASE || '').trim();
if (!apiBase && location.protocol === 'file:') apiBase = 'http://127.0.0.1:5000';
const API_BASE = apiBase.replace(/\/+$/, '');

function setStatus(msg, isErr) {
  const el = document.getElementById('run-status');
  el.textContent = msg;
  el.className = isErr ? 'err' : '';
}

async function initBackend() {
  try {
    const res = await fetch(API_BASE + '/api/domains');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const domains = await res.json();
    const grid = document.getElementById('domain-grid');
    grid.innerHTML = Object.keys(domains).map(d =>
      `<label><input type="checkbox" class="domain-cb" value="${d}"> ${d.replace(/_/g, ' ')} <span style="color:var(--muted)">(${domains[d].length})</span></label>`
    ).join('');
    document.getElementById('run-panel').style.display = 'block';
  } catch (e) {
    const hint = document.getElementById('empty-state');
    hint.innerHTML = '<div class="glyph">&#9673;</div><div>Backend not reachable at <span class="num">' + (API_BASE || location.origin) +
      '</span>. Start it with <span class="num">python server.py</span>, or load a saved report.json above.</div>';
    return;
  }

  // Show the last completed report, if the server has one
  try {
    const res = await fetch(API_BASE + '/api/latest');
    if (res.ok) {
      loadReport(await res.json());
      setStatus('Showing the most recent saved report.');
    }
  } catch (e) { /* ignore */ }
}

document.getElementById('select-all').addEventListener('click', () =>
  document.querySelectorAll('.domain-cb').forEach(cb => cb.checked = true));
document.getElementById('select-none').addEventListener('click', () =>
  document.querySelectorAll('.domain-cb').forEach(cb => cb.checked = false));

document.getElementById('run-btn').addEventListener('click', async () => {
  const domains = [...document.querySelectorAll('.domain-cb:checked')].map(cb => cb.value);
  const tickers = document.getElementById('custom-tickers').value
    .split(/[\s,]+/).map(t => t.trim().toUpperCase()).filter(Boolean);
  if (!domains.length && !tickers.length) {
    setStatus('Pick at least one domain or enter a ticker.', true);
    return;
  }

  const btn = document.getElementById('run-btn');
  const bar = document.getElementById('progress');
  const barFill = document.getElementById('progress-bar');
  btn.disabled = true;
  bar.style.display = 'block';
  barFill.style.width = '0%';
  setStatus('Starting...');

  try {
    const start = await fetch(API_BASE + '/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domains, tickers, use_llm: document.getElementById('use-llm').checked }),
    });
    const startData = await start.json();
    if (!start.ok) throw new Error(startData.error || ('HTTP ' + start.status));

    // Poll until the job finishes
    while (true) {
      await new Promise(r => setTimeout(r, 2000));
      const res = await fetch(API_BASE + '/api/jobs/' + startData.job_id);
      const job = await res.json();
      if (!res.ok) throw new Error(job.error || 'lost track of the job');

      const pct = job.total ? Math.round(100 * job.done / job.total) : 0;
      barFill.style.width = pct + '%';
      setStatus(`${job.status === 'queued' ? 'Waiting for another run to finish' : 'Analyzing'}... ${job.done}/${job.total} tickers`);

      if (job.status === 'done') {
        loadReport(job.report);
        const errCount = Object.keys(job.report.errors || {}).length;
        setStatus(`Done. ${job.total - errCount} of ${job.total} tickers analyzed` +
          (errCount ? ` (${errCount} had no usable data: ${Object.keys(job.report.errors).join(', ')})` : '') + '.');
        break;
      }
      if (job.status === 'error') throw new Error(job.error || 'analysis failed');
    }
  } catch (e) {
    setStatus(e instanceof TypeError ? 'Cannot reach the backend at ' + (API_BASE || location.origin) + '. Is server.py running?' : 'Failed: ' + e.message, true);
  } finally {
    btn.disabled = false;
    setTimeout(() => { bar.style.display = 'none'; }, 1500);
  }
});

initBackend();
