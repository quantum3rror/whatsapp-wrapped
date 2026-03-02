"""
WhatsApp Wrapped — pywebview GUI entry point.

Double-click this file (or the built .app) to open the landing screen.
The analysis runs in a background thread so the UI stays responsive.
"""

import sys
import os
import threading
from pathlib import Path

# Ensure the project root is on the import path when running from a built bundle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib.util
import webview

# Resolve base directory: sys._MEIPASS inside a PyInstaller bundle, otherwise
# the directory containing this script.
if getattr(sys, 'frozen', False):
    _base = Path(sys._MEIPASS)
else:
    _base = Path(__file__).parent

# Load whatsapp_wrapped.py explicitly — the whatsapp_wrapped/ package directory
# would otherwise shadow the script when using a plain import.
_spec = importlib.util.spec_from_file_location(
    "whatsapp_wrapped_main",
    _base / "whatsapp_wrapped.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

find_ios_backups      = _mod.find_ios_backups
find_whatsapp_db      = _mod.find_whatsapp_db
analyze_whatsapp_db   = _mod.analyze_whatsapp_db
generate_html_wrapped = _mod.generate_html_wrapped


# ---------------------------------------------------------------------------
# Landing page HTML
# ---------------------------------------------------------------------------

LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WhatsApp Wrapped</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:      #0d0d0d;
    --card:    #1a1a1a;
    --border:  #2a2a2a;
    --accent:  #25D366;
    --accent2: #128C7E;
    --text:    #e8e8e8;
    --muted:   #888;
    --error:   #ff5f5f;
    --warn:    #f0a500;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 48px 44px;
    width: 500px;
    max-width: 95vw;
    box-shadow: 0 8px 40px rgba(0,0,0,.6);
  }

  .logo {
    text-align: center;
    margin-bottom: 32px;
  }
  .logo-icon {
    width: 64px; height: 64px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 32px;
    margin-bottom: 14px;
  }
  .logo h1 { font-size: 26px; font-weight: 700; letter-spacing: -0.5px; }
  .logo p  { color: var(--muted); font-size: 14px; margin-top: 4px; }

  label {
    display: block;
    font-size: 12px;
    font-weight: 700;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .07em;
    margin-bottom: 6px;
  }

  .field { margin-bottom: 20px; }

  input[type="number"],
  input[type="text"],
  select {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-size: 15px;
    padding: 11px 14px;
    outline: none;
    transition: border-color .2s;
    appearance: none;
    -webkit-appearance: none;
  }
  input[type="number"]:focus,
  input[type="text"]:focus,
  select:focus { border-color: var(--accent); }

  .select-wrap { position: relative; }
  .select-wrap::after {
    content: '▾';
    position: absolute;
    right: 14px; top: 50%;
    transform: translateY(-50%);
    color: var(--muted);
    pointer-events: none;
    font-size: 13px;
  }

  .hint { font-size: 12px; color: var(--muted); margin-top: 6px; }

  /* No-backup warning */
  .no-backup-msg {
    background: #1f1300;
    border: 1px solid #3a2a00;
    border-radius: 8px;
    color: var(--warn);
    font-size: 13px;
    padding: 12px 14px;
    margin-bottom: 8px;
    display: none;
    line-height: 1.7;
  }
  .no-backup-msg code {
    display: block;
    background: rgba(0,0,0,.3);
    border-radius: 5px;
    padding: 6px 10px;
    font-size: 11px;
    color: #ccc;
    word-break: break-all;
    margin-top: 6px;
    user-select: all;
    cursor: pointer;
    transition: background .15s, color .15s;
  }
  .no-backup-msg code:hover { background: rgba(37,211,102,.12); color: #eee; }
  .no-backup-msg code.copied { background: rgba(37,211,102,.25); color: var(--accent); }

  /* Advanced / manual DB section */
  .advanced-toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    color: var(--muted);
    font-size: 13px;
    margin-bottom: 16px;
    user-select: none;
  }
  .advanced-toggle:hover { color: var(--text); }
  .chevron { font-size: 11px; transition: transform .2s; }
  .chevron.open { transform: rotate(90deg); }

  .advanced-body { display: none; }
  .advanced-body.open { display: block; }

  .db-row { display: flex; gap: 8px; }
  .db-row input { flex: 1; }

  .btn-browse {
    background: var(--border);
    border: 1px solid #3a3a3a;
    border-radius: 8px;
    color: var(--text);
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    padding: 0 14px;
    white-space: nowrap;
    transition: background .2s;
  }
  .btn-browse:hover { background: #333; }

  .btn-generate {
    width: 100%;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border: none;
    border-radius: 10px;
    color: #fff;
    cursor: pointer;
    font-size: 16px;
    font-weight: 700;
    padding: 14px;
    margin-top: 4px;
    transition: opacity .2s, transform .1s;
  }
  .btn-generate:hover:not(:disabled) { opacity: .9; }
  .btn-generate:active:not(:disabled) { transform: scale(.98); }
  .btn-generate:disabled { opacity: .45; cursor: not-allowed; }

  #status {
    font-size: 13px;
    text-align: center;
    min-height: 20px;
    margin-top: 14px;
    color: var(--muted);
  }
  #status.error { color: var(--error); }
  #status.info  { color: var(--accent); }
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <div class="logo-icon">💬</div>
    <h1>WhatsApp Wrapped</h1>
    <p>Your year in messages</p>
  </div>

  <!-- Year -->
  <div class="field">
    <label for="year">Year / Range</label>
    <input type="text" id="year" value="2025" placeholder="e.g. 2025 or 2023-2025 or 0">
    <p class="hint">Single year (2025), range (2023-2025), or 0 for all time</p>
  </div>

  <!-- Backup selector (populated on load) -->
  <div class="field" id="backup-field">
    <label>iOS Backup</label>
    <div class="no-backup-msg" id="no-backup-msg">
      No iOS backups found — the app may need Full Disk Access.<br>
      <button id="fda-btn" style="display:none;margin-top:8px;margin-bottom:4px;background:var(--accent);border:none;border-radius:7px;color:#fff;cursor:pointer;font-size:13px;font-weight:600;padding:6px 14px;" onclick="window.pywebview.api.open_fda_settings()">Open Full Disk Access settings →</button><br>
      Grant access, then relaunch. Or browse to the file directly:<br>
      <code onclick="copyPath(this)" title="Click to copy">~/Library/Application Support/MobileSync/Backup/&lt;id&gt;/7c/7c7fba66680ef796b916b067077cc246adacf01d</code>
    </div>
    <div class="select-wrap" id="backup-select-wrap">
      <select id="backup-select"></select>
    </div>
    <p class="hint" id="backup-hint">Using the most recent backup by default</p>
  </div>

  <!-- Advanced: manual DB path -->
  <div class="advanced-toggle" onclick="toggleAdvanced()">
    <span class="chevron" id="chevron">▶</span>
    Advanced — specify database path manually
  </div>
  <div class="advanced-body" id="advanced-body">
    <div class="field">
      <label for="db">Database path</label>
      <div class="db-row">
        <input type="text" id="db" placeholder="Path to ChatStorage.sqlite">
        <button class="btn-browse" onclick="browse()">Browse…</button>
      </div>
      <p class="hint">Overrides the backup selection above when set</p>
    </div>
  </div>

  <button class="btn-generate" id="btn" onclick="generate()">
    Generate Wrapped
  </button>
  <div id="status"></div>
</div>

<script>
// ── helpers ──────────────────────────────────────────────────────────────────
function setStatus(msg, cls) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = cls || '';
}

function copyPath(el) {
  const range = document.createRange();
  range.selectNodeContents(el);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  document.execCommand('copy');
  sel.removeAllRanges();

  el.classList.add('copied');
  const orig = el.textContent;
  el.textContent = 'Copied!';
  setTimeout(() => { el.textContent = orig; el.classList.remove('copied'); }, 1500);
}

function toggleAdvanced() {
  const body    = document.getElementById('advanced-body');
  const chevron = document.getElementById('chevron');
  body.classList.toggle('open');
  chevron.classList.toggle('open');
}

// ── populate backup dropdown ──────────────────────────────────────────────────
window.addEventListener('pywebviewready', async () => {
  const backups = await window.pywebview.api.get_backups();
  const sel     = document.getElementById('backup-select');
  const wrap    = document.getElementById('backup-select-wrap');
  const noMsg   = document.getElementById('no-backup-msg');
  const hint    = document.getElementById('backup-hint');
  const btn     = document.getElementById('btn');

  if (!backups || backups.length === 0) {
    wrap.style.display = 'none';
    hint.style.display = 'none';
    noMsg.style.display = 'block';
    document.getElementById('advanced-body').classList.add('open');
    document.getElementById('chevron').classList.add('open');
    // Show FDA button only on macOS
    if (navigator.platform.startsWith('Mac')) {
      document.getElementById('fda-btn').style.display = 'inline-block';
    }
  } else {
    backups.forEach(b => {
      const opt = document.createElement('option');
      opt.value = b.index;
      opt.textContent = b.label;
      sel.appendChild(opt);
    });
    if (backups.length === 1) hint.textContent = 'One backup found';
  }
  btn.disabled = false;
});

async function browse() {
  const path = await window.pywebview.api.browse_db();
  if (path) document.getElementById('db').value = path;
}

async function generate() {
  const btn         = document.getElementById('btn');
  const raw         = document.getElementById('year').value.trim();
  const db          = document.getElementById('db').value.trim() || null;
  const backupSel   = document.getElementById('backup-select');
  const backupIndex = backupSel.value !== '' ? parseInt(backupSel.value) : 0;

  // ── Validate & parse year input ─────────────────────────────────────────
  let startYear = 0;
  let endYear   = 0;

  if (raw === '' || raw === '0') {
    startYear = 0;  // all time
    endYear   = 0;
  } else {
    const rangeMatch = raw.match(/^\s*(\d{4})\s*[-–]\s*(\d{4})\s*$/);
    const singleMatch = raw.match(/^\s*(\d{4})\s*$/);

    if (rangeMatch) {
      startYear = parseInt(rangeMatch[1]);
      endYear   = parseInt(rangeMatch[2]);
      if (startYear > endYear) { [startYear, endYear] = [endYear, startYear]; }
      if (startYear < 2000 || endYear > 2099) {
        setStatus('Year must be between 2000 and 2099.', 'error');
        return;
      }
    } else if (singleMatch) {
      startYear = parseInt(singleMatch[1]);
      if (startYear < 2000 || startYear > 2099) {
        setStatus('Year must be between 2000 and 2099.', 'error');
        return;
      }
    } else {
      setStatus('Invalid year. Use a single year (2025), a range (2023-2025), or 0 for all time.', 'error');
      return;
    }
  }

  btn.disabled = true;
  btn.textContent = 'Analysing…';
  setStatus('Running analysis, please wait…', 'info');

  try {
    const result = await window.pywebview.api.run_analysis(startYear, endYear, backupIndex, db);
    if (result && result.error) {
      setStatus('Error: ' + result.error, 'error');
      btn.disabled = false;
      btn.textContent = 'Generate Wrapped';
    }
    // On success the page is replaced ~50 ms later — nothing more to do here.
  } catch (e) {
    setStatus('Unexpected error: ' + e, 'error');
    btn.disabled = false;
    btn.textContent = 'Generate Wrapped';
  }
}

document.addEventListener('keydown', e => {
  if (e.key === 'Enter') generate();
});
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Python API
# ---------------------------------------------------------------------------

class Api:
    def __init__(self):
        self.window = None       # set after window creation
        self._backups  = []      # cached so run_analysis can index into it

    def get_backups(self):
        """Return serialisable list of discovered iOS backups for the dropdown."""
        self._backups = find_ios_backups(verbose=False)
        result = []
        for i, b in enumerate(self._backups):
            date_str = (
                b['backup_date'].strftime('%Y-%m-%d')
                if b.get('backup_date') else 'Unknown date'
            )
            device = b.get('device_name') or 'Unknown device'
            label = f"{device} — {date_str}"
            if i == 0:
                label += '  (latest)'
            result.append({'index': i, 'label': label})
        return result

    def open_fda_settings(self):
        """Open System Settings → Privacy & Security → Full Disk Access."""
        import subprocess
        subprocess.run(
            ['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles'],
            check=False,
        )

    def browse_db(self):
        """Open a native file picker and return the selected path (or None)."""
        result = self.window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=('SQLite Database (*.sqlite)', 'All files (*.*)'),
        )
        if result and len(result) > 0:
            return result[0]
        return None

    def run_analysis(self, start_year, end_year, backup_index, db_path):
        """
        Called from JS in a background thread.
        Returns {'error': str} on failure.
        On success, schedules load_html() 50 ms later (so the JS return-value
        callback fires before the page is replaced) and returns {'success': True}.
        """
        try:
            start_year = int(start_year) if start_year else 0
            end_year   = int(end_year) if end_year else 0
            year = start_year if start_year > 0 else None
            ey   = end_year if end_year > 0 else None

            if db_path:
                db = Path(db_path)
                if not db.exists():
                    return {'error': f'File not found: {db_path}'}
            else:
                if not self._backups:
                    self._backups = find_ios_backups(verbose=False)
                if not self._backups:
                    return {'error': 'No iOS backups found. Plug in your iPhone or provide a database path.'}
                idx = int(backup_index) if backup_index is not None else 0
                idx = max(0, min(idx, len(self._backups) - 1))
                db, _ = find_whatsapp_db(self._backups[idx]['path'], verbose=False)
                if not db:
                    return {'error': 'WhatsApp database not found in the selected backup.'}

            stats = analyze_whatsapp_db(db, year=year, end_year=ey)

            html = generate_html_wrapped(stats)

            if html is None:
                return {'error': 'HTML generation failed — template not found.'}

            # Delay load_html so pywebview's return-value callback fires first.
            threading.Timer(0.05, self.window.load_html, args=[html]).start()
            return {'success': True}

        except Exception as exc:
            return {'error': str(exc)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--html', metavar='FILE',
                        help='Load an existing wrapped HTML file directly (skips landing page)')
    args = parser.parse_args()

    api = Api()

    if args.html:
        html = Path(args.html).read_text(encoding='utf-8')
        window = webview.create_window(
            'WhatsApp Wrapped — Preview',
            html=html,
            js_api=api,
            width=1100,
            height=750,
            min_size=(800, 600),
        )
    else:
        window = webview.create_window(
            'WhatsApp Wrapped',
            html=LANDING_HTML,
            js_api=api,
            width=1100,
            height=750,
            min_size=(800, 600),
        )

    api.window = window
    webview.start()


if __name__ == '__main__':
    main()
