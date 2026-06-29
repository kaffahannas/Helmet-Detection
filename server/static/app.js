'use strict';

const N_CAMS = 3;
let currentCam = 0;
let detailPollTimer = null;

// ─── Clock ────────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  document.getElementById('clock').textContent =
    now.toLocaleDateString('id-ID') + '  ' +
    now.toLocaleTimeString('id-ID', { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

// ─── View switching ───────────────────────────────────────────────────────────
function showGrid() {
  document.getElementById('detailView').classList.add('hidden');
  document.getElementById('gridView').classList.remove('hidden');

  // Stop per-camera detail polling
  if (detailPollTimer) { clearInterval(detailPollTimer); detailPollTimer = null; }

  // Resume grid streams (force-reload any that errored)
  for (let i = 0; i < N_CAMS; i++) {
    const img = document.getElementById(`gridFeed${i}`);
    if (!img.complete || img.naturalWidth === 0) {
      img.src = `/stream/${i}?t=${Date.now()}`;
    }
  }
}

function showDetail(camId) {
  currentCam = camId;
  const label = `CAM ${camId + 1}`;

  document.getElementById('gridView').classList.add('hidden');
  document.getElementById('detailView').classList.remove('hidden');
  document.getElementById('detailTitle').textContent    = `${label} — FULL VIEW`;
  document.getElementById('detailCamLabel').textContent = `LIVE FEED — ${label}`;

  // Load the stream for this camera
  const feed = document.getElementById('detailFeed');
  const err  = document.getElementById('detailFeedErr');
  err.classList.add('hidden');
  feed.style.visibility = 'visible';
  feed.src = `/stream/${camId}?t=${Date.now()}`;
  feed.onerror = () => {
    err.classList.remove('hidden');
    feed.style.visibility = 'hidden';
  };

  // Start polling stats for this camera
  if (detailPollTimer) clearInterval(detailPollTimer);
  pollDetailStats();
  detailPollTimer = setInterval(pollDetailStats, 1500);

  // Load violation log
  loadViolations();
}

function retryDetailFeed() {
  const feed = document.getElementById('detailFeed');
  document.getElementById('detailFeedErr').classList.add('hidden');
  feed.style.visibility = 'visible';
  feed.src = `/stream/${currentCam}?t=${Date.now()}`;
}

// ─── Grid stats polling (all cameras) ─────────────────────────────────────────
async function pollGridStats() {
  try {
    const res  = await fetch('/api/stats');
    if (!res.ok) throw new Error();
    const all  = await res.json();

    // System status
    const badge = document.getElementById('sysStatus');
    badge.textContent = '● ONLINE';
    badge.className   = 'badge badge-ok';

    // Count active cameras
    const active = all.filter(s => s.fps > 0).length;
    document.getElementById('gridOnline').textContent =
      `${active}/${N_CAMS} cameras active`;

    all.forEach((s, i) => {
      const vEl  = document.getElementById(`gridVio${i}`);
      const fEl  = document.getElementById(`gridFps${i}`);
      const rEl  = document.getElementById(`gridRec${i}`);
      if (vEl) vEl.textContent = `${s.violation_count ?? 0} violation${s.violation_count === 1 ? '' : 's'}`;
      if (fEl) fEl.textContent = s.fps ? `${s.fps} fps` : '— fps';
      if (rEl) rEl.classList.toggle('hidden', !s.is_recording);
    });

  } catch {
    const badge = document.getElementById('sysStatus');
    badge.textContent = '● OFFLINE';
    badge.className   = 'badge badge-err';
  }
}
setInterval(pollGridStats, 1500);
pollGridStats();

// ─── Detail stats polling (single camera) ─────────────────────────────────────
async function pollDetailStats() {
  try {
    const res = await fetch(`/api/stats/${currentCam}`);
    if (!res.ok) throw new Error();
    const d = await res.json();

    document.getElementById('detailViolations').textContent = d.violation_count ?? 0;

    const recCard  = document.getElementById('detailRecCard');
    const recTxt   = document.getElementById('detailRec');
    const recBadge = document.getElementById('detailRecBadge');
    if (d.is_recording) {
      recTxt.textContent = 'ON';
      recCard.className  = 'stat-card safe';
      recBadge.classList.remove('hidden');
    } else {
      recTxt.textContent = 'OFF';
      recCard.className  = 'stat-card';
      recBadge.classList.add('hidden');
    }

    const fmt = v => v ?? '—';
    document.getElementById('detailLast').textContent       = fmt(d.last_violation);
    document.getElementById('detailSource').textContent     = fmt(d.source);
    document.getElementById('detailFps').textContent        = d.fps ? `${d.fps} fps` : '—';
    document.getElementById('detailMetaSource').textContent = 'Source: ' + fmt(d.source);
    document.getElementById('detailMetaFps').textContent    = 'FPS: ' + (d.fps ?? '—');

  } catch { /* ignore transient failures */ }
}

// ─── Violation log ─────────────────────────────────────────────────────────────
async function loadViolations() {
  const list = document.getElementById('violationLog');
  list.innerHTML = '<div class="empty">Loading…</div>';
  try {
    const res   = await fetch('/api/violations');
    const files = await res.json();
    if (!Array.isArray(files) || !files.length) {
      list.innerHTML = '<div class="empty">No violations recorded</div>';
      return;
    }
    list.innerHTML = files.map(f => `
      <div class="log-item">
        <div style="overflow:hidden;min-width:0">
          <div class="log-name" title="${f.name}">${f.name}</div>
          <div class="log-meta">${f.created} &nbsp;·&nbsp; ${f.size_mb} MB</div>
        </div>
        <a class="log-dl" href="/videos/${encodeURIComponent(f.name)}" download>⬇ DL</a>
      </div>
    `).join('');
  } catch {
    list.innerHTML = '<div class="empty">Failed to load violations</div>';
  }
}

// Auto-refresh violation log every 10 s while in detail view
setInterval(() => {
  if (!document.getElementById('detailView').classList.contains('hidden')) {
    loadViolations();
  }
}, 10_000);
