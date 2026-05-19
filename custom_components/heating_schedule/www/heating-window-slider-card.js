/**
 * heating-window-slider-card
 *
 * Lovelace card: multi-window per-room heating schedule.
 *
 * Each card shows one or more (1..4) heating windows on a shared 24h track,
 * a target-temperature spinner for that room's comfort temp, an active /
 * inactive badge for whether the current time falls inside any window,
 * the current room temperature, and a window open/closed indicator.
 *
 * Storage: a single input_text per room holding a JSON list of
 * [["HH:MM","HH:MM"], ...] window pairs. The last entry may wrap midnight
 * (end < start). The number of windows is determined by the JSON array
 * length — it's a setup decision, not a runtime UI control. To add or
 * remove a window: edit the helper's value (Developer Tools → States, or
 * call input_text.set_value).
 *
 * Config:
 *   type: custom:heating-window-slider-card
 *   name: Bedroom                              # optional
 *   windows_entity: input_text.x               # required, JSON array of HH:MM pairs
 *   comfort_entity: input_number.y             # required
 *   climate_entity: climate.bedroom_heating    # optional, drives subtitle + heating tint
 *   current_temp_entity: sensor.bedroom_temp   # optional
 *   window_entity: binary_sensor.bedroom_open  # optional
 *   step_minutes: 5                            # optional, default 5
 *
 * Drag rules:
 *   - Each handle is clamped between its cyclic neighbours (going clockwise
 *     and counter-clockwise around the 24h circle). Equal values are allowed.
 *   - When two adjacent handles meet, neither can pass the other.
 *   - The schedule is re-canonicalised after each commit (windows sorted by
 *     start). A window with end < start renders as a wrap arc — drawn from
 *     start to 24:00 plus 0:00 to end. The slider visually constrains drags
 *     to the valid arc, so wrap state is reachable through ordinary drags
 *     (no special "wrap" toggle).
 */

const CARD_TAG = 'heating-window-slider-card';
const EDITOR_TAG = 'heating-window-slider-card-editor';
const DEFAULT_STEP = 5;
const MAX_WINDOWS = 4;
const DAY = 1440;

const css = `
  :host { display: block; }
  ha-card {
    padding: 12px 16px 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .header {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 36px;
  }
  .climate-icon {
    --mdc-icon-size: 22px;
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    /* Idle: blue radiator-disabled. */
    background: rgba(33,150,243,0.22);
    color: var(--state-climate-cool-color, #2196f3);
    opacity: 1;
    transition: background 0.15s, color 0.15s;
  }
  .climate-icon.heating {
    /* Heating: yellow/active radiator. */
    background: rgba(255,152,0,0.18);
    color: var(--state-active-color, #ff9800);
  }
  .name-block {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    line-height: 1.15;
  }
  .name {
    font-size: 1rem;
    font-weight: 500;
    color: var(--primary-text-color);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .subtitle {
    font-size: 0.78rem;
    color: var(--secondary-text-color);
    font-variant-numeric: tabular-nums;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .badge {
    font-size: 0.72rem;
    padding: 2px 8px;
    border-radius: 10px;
    background: var(--secondary-background-color);
    color: var(--secondary-text-color);
    white-space: nowrap;
    text-transform: lowercase;
    letter-spacing: 0.02em;
  }
  .badge.active {
    background: var(--state-active-color, #ff9800);
    color: var(--text-primary-color, #fff);
  }
  .window-icon {
    --mdc-icon-size: 18px;
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    border-radius: 50%;
    background: var(--disabled-color, rgba(127,127,127,0.15));
    color: var(--state-icon-color, var(--secondary-text-color));
    opacity: 0.6;
    transition: background 0.15s, color 0.15s, opacity 0.15s;
  }
  .window-icon.open {
    background: rgba(0,188,212,0.25);
    color: var(--cyan-color, #00bcd4);
    opacity: 1;
  }
  .spinner {
    display: inline-flex;
    align-items: center;
    background: var(--secondary-background-color, rgba(127,127,127,0.15));
    border-radius: 999px;
    padding: 2px;
    gap: 2px;
    font-variant-numeric: tabular-nums;
    height: 28px;
  }
  .spinner button {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 0;
    background: transparent;
    color: var(--primary-text-color);
    font-size: 1.05rem;
    line-height: 24px;
    padding: 0;
    cursor: pointer;
    font-family: inherit;
  }
  .spinner button:hover:not(:disabled) { background: rgba(127,127,127,0.2); }
  .spinner button:disabled { opacity: 0.4; cursor: not-allowed; }
  .spinner .value {
    font-size: 0.85rem;
    min-width: 52px;
    text-align: center;
    color: var(--primary-text-color);
    user-select: none;
  }
  .slider-wrap {
    position: relative;
    height: 42px;
    margin: 4px 6px 0;
    touch-action: none;
    user-select: none;
  }
  .track {
    position: absolute;
    top: 18px;
    left: 0;
    right: 0;
    height: 6px;
    background: var(--divider-color, rgba(127,127,127,0.3));
    border-radius: 3px;
  }
  .fill {
    position: absolute;
    top: 18px;
    height: 6px;
    background: var(--primary-color, #ff9800);
    border-radius: 3px;
    pointer-events: none;
  }
  .now-mark {
    position: absolute;
    top: 10px;
    width: 2px;
    height: 22px;
    background: var(--accent-color, #e91e63);
    border-radius: 1px;
    pointer-events: none;
    opacity: 0.7;
  }
  .handle {
    position: absolute;
    top: 9px;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: var(--card-background-color, #fff);
    border: 2px solid var(--primary-color, #ff9800);
    box-shadow: 0 1px 3px rgba(0,0,0,0.25);
    transform: translateX(-50%);
    cursor: grab;
    z-index: 2;
    box-sizing: border-box;
  }
  .handle.dragging { cursor: grabbing; box-shadow: 0 2px 6px rgba(0,0,0,0.35); }
  .handle::after {
    content: '';
    position: absolute;
    inset: 4px;
    border-radius: 50%;
    background: var(--primary-color, #ff9800);
  }
  .tooltip {
    position: absolute;
    bottom: 32px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color);
    border: 1px solid var(--divider-color, #ccc);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 0.78rem;
    font-variant-numeric: tabular-nums;
    pointer-events: none;
    white-space: nowrap;
    opacity: 0;
    transition: opacity 0.1s;
  }
  .handle.dragging .tooltip { opacity: 1; }
  .ticks {
    position: absolute;
    top: 28px;
    left: 0;
    right: 0;
    pointer-events: none;
    font-size: 0.65rem;
    color: var(--secondary-text-color);
    font-variant-numeric: tabular-nums;
  }
  .ticks span {
    position: absolute;
    transform: translateX(-50%);
    top: 0;
  }
`;

// Service domain matches the entity domain: input_text.set_value /
// text.set_value / input_number.set_value / number.set_value all take the
// same args, so we just split the entity_id and call the matching domain.
// Keeps the card working against both the YAML install path (input_*) and
// the heating_schedule integration's native text/number entities.
const serviceDomain = (entityId) => (entityId || '').split('.')[0];

const pad2 = (n) => String(n).padStart(2, '0');
const minToHHMM = (m) => {
  const v = ((Math.round(m) % DAY) + DAY) % DAY;
  return `${pad2(Math.floor(v / 60))}:${pad2(v % 60)}`;
};
const minToHHMMSS = (m) => `${minToHHMM(m)}:00`;
const hhmmToMin = (s) => {
  if (!s || typeof s !== 'string') return 0;
  const [h, m] = s.split(':');
  return (parseInt(h, 10) || 0) * 60 + (parseInt(m, 10) || 0);
};
const formatTemp = (v, step) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return '--';
  const dp = (step && step < 1) ? 1 : 0;
  return `${n.toFixed(dp)} °C`;
};
const inWindow = (s, e, n) => {
  if (s === e) return false;
  if (s < e) return n >= s && n < e;
  return n >= s || n < e;
};

class HeatingWindowSliderCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._config = null;
    this._rendered = false;
    this._nowTimer = null;
    this._resizeObs = null;
    this._optimisticComfort = null;
    this._optimisticWindows = null;     // [{start, end}] override during/just after drag
    this._dragging = null;              // {windowIdx, handle}
    this._dragValue = null;             // current dragged minute value
  }

  setConfig(config) {
    if (!config.windows_entity) {
      throw new Error('windows_entity is required');
    }
    this._config = config;
    this._render();
    this._safeUpdate();
  }

  set hass(hass) {
    this._hass = hass;
    this._safeUpdate();
  }

  getCardSize() { return 2; }

  connectedCallback() {
    this._nowTimer = setInterval(() => this._updateNowMark(), 30 * 1000);
    if (this._els && 'ResizeObserver' in window && !this._resizeObs) {
      this._resizeObs = new ResizeObserver(() => this._safeUpdate());
      this._resizeObs.observe(this._els.wrap);
    }
  }
  disconnectedCallback() {
    clearInterval(this._nowTimer);
    if (this._resizeObs) { this._resizeObs.disconnect(); this._resizeObs = null; }
    this._unbindPointer();
  }

  _safeUpdate() {
    try { this._update(); } catch (e) { /* non-fatal render error */ }
  }

  _render() {
    if (this._rendered) return;
    const root = this.shadowRoot;
    const style = document.createElement('style');
    style.textContent = css;
    root.appendChild(style);

    const card = document.createElement('ha-card');
    card.innerHTML = `
      <div class="header">
        <ha-icon class="climate-icon" icon="mdi:radiator"></ha-icon>
        <div class="name-block">
          <div class="name"></div>
          <div class="subtitle"></div>
        </div>
        <div class="badge"></div>
        <ha-icon class="window-icon" style="display:none"></ha-icon>
        <div class="spinner" role="group" aria-label="Target temperature">
          <button class="dec" type="button" aria-label="Decrease">−</button>
          <span class="value">--</span>
          <button class="inc" type="button" aria-label="Increase">+</button>
        </div>
      </div>
      <div class="slider-wrap">
        <div class="track"></div>
        <div class="fills"></div>
        <div class="now-mark"></div>
        <div class="handles"></div>
        <div class="ticks">
          <span style="left:0%">0</span>
          <span style="left:25%">6</span>
          <span style="left:50%">12</span>
          <span style="left:75%">18</span>
          <span style="left:100%">24</span>
        </div>
      </div>
    `;
    root.appendChild(card);

    this._els = {
      card,
      climateIcon: card.querySelector('.climate-icon'),
      name: card.querySelector('.name'),
      subtitle: card.querySelector('.subtitle'),
      badge: card.querySelector('.badge'),
      windowIcon: card.querySelector('.window-icon'),
      spinner: card.querySelector('.spinner'),
      btnInc: card.querySelector('.inc'),
      btnDec: card.querySelector('.dec'),
      spinVal: card.querySelector('.value'),
      wrap: card.querySelector('.slider-wrap'),
      fills: card.querySelector('.fills'),
      handles: card.querySelector('.handles'),
      nowMark: card.querySelector('.now-mark'),
    };

    this._els.btnInc.addEventListener('click', () => this._adjustComfort(+1));
    this._els.btnDec.addEventListener('click', () => this._adjustComfort(-1));

    if (this.isConnected && 'ResizeObserver' in window && !this._resizeObs) {
      this._resizeObs = new ResizeObserver(() => this._safeUpdate());
      this._resizeObs.observe(this._els.wrap);
    }

    this._rendered = true;
  }

  // ── Window state helpers ──────────────────────────────────────────────

  _readWindows() {
    if (this._optimisticWindows) return this._optimisticWindows;
    const eid = this._config.windows_entity;
    if (!eid || !this._hass) return [];
    const s = this._hass.states[eid];
    if (!s || ['unavailable','unknown'].includes(s.state)) return [];
    try {
      const parsed = JSON.parse(s.state);
      if (!Array.isArray(parsed)) return [];
      return parsed
        .filter(w => Array.isArray(w) && w.length === 2)
        .slice(0, MAX_WINDOWS)
        .map(([a, b]) => ({ start: hhmmToMin(a), end: hhmmToMin(b) }));
    } catch (e) {
      return [];
    }
  }

  _writeWindows(windows) {
    const eid = this._config.windows_entity;
    if (!eid || !this._hass) return;
    const value = JSON.stringify(windows.map(w => [minToHHMM(w.start), minToHHMM(w.end)]));
    this._optimisticWindows = windows;
    this._safeUpdate();
    this._hass.callService(serviceDomain(eid), 'set_value', { entity_id: eid, value })
      .then(() => { this._optimisticWindows = null; })
      .catch(() => { this._optimisticWindows = null; this._safeUpdate(); });
  }

  // Sort windows by start ascending. If there is a wrap window (end < start),
  // it ends up last because its start is necessarily ≥ any non-wrap start
  // (otherwise it would overlap a sibling).
  _canonicalise(windows) {
    return windows
      .map(w => ({ start: w.start, end: w.end }))
      .sort((a, b) => a.start - b.start);
  }

  // ── Drag and clamp ────────────────────────────────────────────────────

  // For the handle being dragged, return its cyclic neighbours among all
  // OTHER handles' positions. The valid drag arc is [prev, next] going
  // clockwise around the 24h circle (both endpoints inclusive).
  _cyclicNeighbours(windowIdx, handle) {
    const windows = this._readWindows();
    const others = [];
    windows.forEach((w, i) => {
      if (!(i === windowIdx && handle === 'start')) others.push(w.start);
      if (!(i === windowIdx && handle === 'end')) others.push(w.end);
    });
    if (others.length === 0) return { prev: 0, next: 0, free: true };
    const p = handle === 'start' ? windows[windowIdx].start : windows[windowIdx].end;
    // prev: largest position ≤ p, falling back to max of all (wrap)
    const leq = others.filter(o => o <= p);
    const geq = others.filter(o => o >= p);
    const prev = leq.length ? Math.max(...leq) : Math.max(...others);
    const next = geq.length ? Math.min(...geq) : Math.min(...others);
    return { prev, next, free: false };
  }

  _arcContains(prev, next, value) {
    if (prev === next) return true;        // full circle, single point excluded but equal ok
    if (prev < next) return value >= prev && value <= next;
    return value >= prev || value <= next; // wraps midnight
  }

  _clampToArc(prev, next, value) {
    if (this._arcContains(prev, next, value)) return value;
    const cwDist = (a, b) => ((b - a + DAY) % DAY);   // clockwise from a to b
    const dPrev = Math.min(cwDist(prev, value), cwDist(value, prev));
    const dNext = Math.min(cwDist(next, value), cwDist(value, next));
    return dPrev <= dNext ? prev : next;
  }

  // ── Drag handlers ─────────────────────────────────────────────────────

  _startDrag(ev, windowIdx, handle) {
    ev.preventDefault();
    ev.stopPropagation();
    const w = this._readWindows()[windowIdx];
    if (!w) return;
    this._dragging = { windowIdx, handle };
    this._dragValue = handle === 'start' ? w.start : w.end;
    const handleEl = ev.currentTarget;
    handleEl.classList.add('dragging');
    this._move = (e) => this._onMove(e);
    this._up = (e) => this._endDrag(e);
    window.addEventListener('pointermove', this._move);
    window.addEventListener('pointerup', this._up);
    window.addEventListener('pointercancel', this._up);
  }

  _onMove(ev) {
    if (!this._dragging) return;
    const rect = this._els.wrap.getBoundingClientRect();
    if (rect.width <= 0) return;
    let pct = (ev.clientX - rect.left) / rect.width;
    pct = Math.max(0, Math.min(1, pct));
    const step = this._config.step_minutes || DEFAULT_STEP;
    let proposed = Math.round((pct * DAY) / step) * step;
    if (proposed >= DAY) proposed = DAY - step;
    const { prev, next } = this._cyclicNeighbours(this._dragging.windowIdx, this._dragging.handle);
    proposed = this._clampToArc(prev, next, proposed);
    // Apply optimistic update — mutate the windows array for live render.
    const windows = this._readWindows().map((w, i) => {
      if (i !== this._dragging.windowIdx) return { ...w };
      return this._dragging.handle === 'start'
        ? { start: proposed, end: w.end }
        : { start: w.start, end: proposed };
    });
    this._optimisticWindows = windows;
    this._dragValue = proposed;
    this._safeUpdate();
  }

  _endDrag(ev) {
    if (!this._dragging) return;
    const { windowIdx, handle } = this._dragging;
    const value = this._dragValue;
    this._dragging = null;
    this._dragValue = null;
    this._unbindPointer();
    this._els.handles.querySelectorAll('.handle.dragging').forEach(h => h.classList.remove('dragging'));
    // Commit: rebuild windows from current optimistic + canonicalise + write.
    const live = this._readWindows();
    const next = this._canonicalise(live);
    this._optimisticWindows = next;
    this._writeWindows(next);
  }

  _unbindPointer() {
    if (this._move) window.removeEventListener('pointermove', this._move);
    if (this._up) {
      window.removeEventListener('pointerup', this._up);
      window.removeEventListener('pointercancel', this._up);
    }
    this._move = null;
    this._up = null;
  }

  // ── Comfort spinner ───────────────────────────────────────────────────

  _comfortState() {
    const eid = this._config.comfort_entity;
    if (!eid || !this._hass) return null;
    return this._hass.states[eid] || null;
  }
  _currentComfort() {
    if (this._optimisticComfort != null) return this._optimisticComfort;
    const s = this._comfortState();
    return s ? Number(s.state) : NaN;
  }
  _adjustComfort(direction) {
    const s = this._comfortState();
    const eid = this._config.comfort_entity;
    if (!s || !eid) return;
    const step = parseFloat(s.attributes.step) || 0.5;
    const min = parseFloat(s.attributes.min);
    const max = parseFloat(s.attributes.max);
    const cur = this._currentComfort();
    if (!Number.isFinite(cur)) return;
    let next = cur + direction * step;
    next = Math.round(next / step) * step;
    if (Number.isFinite(min)) next = Math.max(min, next);
    if (Number.isFinite(max)) next = Math.min(max, next);
    if (Math.abs(next - cur) < 1e-9) return;
    this._optimisticComfort = next;
    this._safeUpdate();
    this._hass.callService(serviceDomain(eid), 'set_value', { entity_id: eid, value: next })
      .then(() => { this._optimisticComfort = null; })
      .catch(() => { this._optimisticComfort = null; this._safeUpdate(); });
  }

  // ── Render ────────────────────────────────────────────────────────────

  _nowMinutes() {
    const d = new Date();
    return d.getHours() * 60 + d.getMinutes();
  }

  _update() {
    if (!this._rendered || !this._hass || !this._config) return;
    const windows = this._readWindows();
    const now = this._nowMinutes();
    const anyActive = windows.some(w => inWindow(w.start, w.end, now));
    const climate = this._config.climate_entity ? this._hass.states[this._config.climate_entity] : null;

    this._els.name.textContent = this._config.name || (this._hass.states[this._config.windows_entity]?.attributes?.friendly_name) || 'Heating schedule';

    const tempState = this._config.current_temp_entity ? this._hass.states[this._config.current_temp_entity] : null;
    const subtitleParts = [];
    if (tempState && !['unavailable','unknown','none',''].includes(tempState.state)) {
      const v = Number(tempState.state);
      if (Number.isFinite(v)) subtitleParts.push(`${v.toFixed(1)} °C`);
    }
    if (climate?.attributes?.hvac_action) subtitleParts.push(climate.attributes.hvac_action);
    this._els.subtitle.textContent = subtitleParts.join(' · ');
    this._els.subtitle.style.display = subtitleParts.length ? '' : 'none';

    const heating = climate?.attributes?.hvac_action === 'heating';
    this._els.climateIcon.icon = heating ? 'mdi:radiator' : 'mdi:radiator-disabled';
    this._els.climateIcon.classList.toggle('heating', !!heating);

    this._els.badge.textContent = anyActive ? 'active' : 'inactive';
    this._els.badge.classList.toggle('active', anyActive);

    const winState = this._config.window_entity ? this._hass.states[this._config.window_entity] : null;
    if (winState && ['on','off'].includes(winState.state)) {
      const open = winState.state === 'on';
      this._els.windowIcon.icon = open ? 'mdi:window-open-variant' : 'mdi:window-closed-variant';
      this._els.windowIcon.classList.toggle('open', open);
      this._els.windowIcon.title = open ? 'Window open' : 'Window closed';
      this._els.windowIcon.style.display = '';
    } else {
      this._els.windowIcon.style.display = 'none';
    }

    const comfort = this._currentComfort();
    const comfortState = this._comfortState();
    const step = comfortState ? parseFloat(comfortState.attributes.step) || 0.5 : 0.5;
    const min = comfortState ? parseFloat(comfortState.attributes.min) : 5;
    const max = comfortState ? parseFloat(comfortState.attributes.max) : 30;
    this._els.spinVal.textContent = formatTemp(comfort, step);
    this._els.btnDec.disabled = !comfortState || !(comfort > min + 1e-6);
    this._els.btnInc.disabled = !comfortState || !(comfort < max - 1e-6);
    this._els.spinner.style.display = this._config.comfort_entity ? '' : 'none';

    this._renderWindows(windows);
    this._updateNowMark();
  }

  _renderWindows(windows) {
    // Fills.
    while (this._els.fills.firstChild) this._els.fills.removeChild(this._els.fills.firstChild);
    windows.forEach(w => {
      const pctS = (w.start / DAY) * 100;
      const pctE = (w.end / DAY) * 100;
      if (w.start === w.end) {
        // zero-width: skip
        return;
      } else if (w.start < w.end) {
        const f = document.createElement('div');
        f.className = 'fill';
        f.style.left = pctS + '%';
        f.style.width = (pctE - pctS) + '%';
        this._els.fills.appendChild(f);
      } else {
        const f1 = document.createElement('div');
        f1.className = 'fill';
        f1.style.left = pctS + '%';
        f1.style.width = (100 - pctS) + '%';
        this._els.fills.appendChild(f1);
        const f2 = document.createElement('div');
        f2.className = 'fill';
        f2.style.left = '0%';
        f2.style.width = pctE + '%';
        this._els.fills.appendChild(f2);
      }
    });
    // Handles. Rebuild if window count changed; otherwise reuse existing.
    const wanted = windows.length * 2;
    const existing = this._els.handles.children.length;
    if (existing !== wanted) {
      while (this._els.handles.firstChild) this._els.handles.removeChild(this._els.handles.firstChild);
      windows.forEach((_, i) => {
        ['start', 'end'].forEach(role => {
          const h = document.createElement('div');
          h.className = 'handle';
          h.dataset.windowIdx = String(i);
          h.dataset.role = role;
          const tip = document.createElement('div');
          tip.className = 'tooltip';
          tip.textContent = '--:--';
          h.appendChild(tip);
          h.addEventListener('pointerdown', (ev) => this._startDrag(ev, i, role));
          this._els.handles.appendChild(h);
        });
      });
    }
    // Position handles + tooltip text.
    const handleEls = Array.from(this._els.handles.children);
    windows.forEach((w, i) => {
      ['start', 'end'].forEach((role, j) => {
        const el = handleEls[i * 2 + j];
        if (!el) return;
        const pos = role === 'start' ? w.start : w.end;
        el.style.left = `${(pos / DAY) * 100}%`;
        el.dataset.windowIdx = String(i);
        el.dataset.role = role;
        const tip = el.querySelector('.tooltip');
        if (tip) tip.textContent = minToHHMM(pos);
      });
    });
  }

  _updateNowMark() {
    if (!this._els) return;
    const pct = (this._nowMinutes() / DAY) * 100;
    this._els.nowMark.style.left = `calc(${pct}% - 1px)`;
  }

  static getStubConfig() {
    return {
      windows_entity: 'text.bedroom_windows',
      comfort_entity: 'number.bedroom_comfort',
      climate_entity: 'climate.bedroom',
      current_temp_entity: 'sensor.bedroom_temperature',
      window_entity: 'binary_sensor.bedroom_window',
      name: 'Bedroom',
    };
  }

  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }
}

if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, HeatingWindowSliderCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: CARD_TAG,
    name: 'Heating Window Slider',
    description: 'Per-room multi-window heating schedule with cyclic-clamped drag handles.',
    preview: false,
  });
}

// ─── Visual editor ────────────────────────────────────────────────────────
//
// Renders inside Lovelace's "Edit card" dialog when the user opens the
// gear icon. ha-form drives the layout from a JSON schema; we just keep
// the form's data in sync with the card config and re-emit a config-changed
// event whenever the user touches a field.

const EDITOR_SCHEMA = [
  { name: 'name', selector: { text: {} } },
  {
    name: 'climate_entity',
    required: true,
    selector: { entity: { domain: 'climate' } },
  },
  {
    name: 'current_temp_entity',
    selector: { entity: { domain: 'sensor' } },
  },
  {
    name: 'window_entity',
    selector: { entity: { domain: 'binary_sensor' } },
  },
  {
    name: 'step_minutes',
    selector: { number: { min: 1, max: 60, step: 1, mode: 'box', unit_of_measurement: 'min' } },
  },
];

const EDITOR_LABELS = {
  name: 'Name (optional, defaults to entity friendly name)',
  climate_entity: 'Climate entity (the room\'s TRV)',
  current_temp_entity: 'Current temperature sensor (optional)',
  window_entity: 'Window open binary sensor (optional)',
  step_minutes: `Slider step (default ${DEFAULT_STEP})`,
};

// windows_entity + comfort_entity aren't surfaced in the editor — the
// integration's per-room device names them deterministically off the room
// slug, which we recover from the climate entity_id. Accepts both
// "climate.kitchen_heating" (user's BT pattern) and "climate.kitchen".
const deriveCompanionEntities = (climateEntityId) => {
  if (!climateEntityId || typeof climateEntityId !== 'string') return null;
  const m = climateEntityId.match(/^climate\.(.+?)(?:_heating)?$/);
  if (!m) return null;
  const slug = m[1];
  return {
    windows_entity: `text.${slug}_windows`,
    comfort_entity: `number.${slug}_comfort`,
  };
};

class HeatingWindowSliderCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._form = null;
  }

  setConfig(config) {
    const next = { ...config };
    // Migrate legacy configs and keep windows/comfort aligned with the
    // climate entity. If derivation changes anything, fire config-changed
    // immediately so the dashboard edit dialog picks up the migration on
    // first open.
    const initial = JSON.stringify(next);
    this._applyDerivation(next);
    this._config = next;
    if (JSON.stringify(next) !== initial) {
      // Defer so the dispatch happens after Lovelace has finished wiring
      // its listeners to this element.
      queueMicrotask(() => this._fireConfigChanged());
    }
    this._renderOrUpdate();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
  }

  connectedCallback() {
    this._renderOrUpdate();
  }

  _applyDerivation(cfg) {
    const derived = deriveCompanionEntities(cfg.climate_entity);
    if (derived) Object.assign(cfg, derived);
  }

  _fireConfigChanged() {
    this.dispatchEvent(new CustomEvent('config-changed', {
      detail: { config: this._config },
      bubbles: true,
      composed: true,
    }));
  }

  _renderOrUpdate() {
    if (!this._form) {
      const form = document.createElement('ha-form');
      form.computeLabel = (s) => EDITOR_LABELS[s.name] || s.name;
      form.addEventListener('value-changed', (e) => {
        e.stopPropagation();
        // ha-form sends the full updated object as e.detail.value. Preserve
        // any keys outside the schema (notably `type` and the derived
        // windows_entity/comfort_entity) by spreading on top of our
        // previous config rather than replacing wholesale.
        const next = { ...this._config, ...e.detail.value };
        // Drop keys the user explicitly cleared, except `type` and the
        // derived companion entities.
        const protectedKeys = new Set(['type', 'windows_entity', 'comfort_entity']);
        Object.keys(next).forEach((k) => {
          if (!protectedKeys.has(k) && (next[k] === undefined || next[k] === '')) delete next[k];
        });
        this._applyDerivation(next);
        this._config = next;
        this._fireConfigChanged();
      });
      this.appendChild(form);
      this._form = form;
    }
    this._form.schema = EDITOR_SCHEMA;
    this._form.data = this._config;
    if (this._hass) this._form.hass = this._hass;
  }
}

if (!customElements.get(EDITOR_TAG)) {
  customElements.define(EDITOR_TAG, HeatingWindowSliderCardEditor);
}
