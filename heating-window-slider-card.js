/**
 * heating-window-slider-card
 *
 * Lovelace card: dual-handle 24h range slider that drives two input_datetime
 * helpers (start, end) plus an input_number comfort-temperature spinner.
 *
 * Config:
 *   type: custom:heating-window-slider-card
 *   name: Bedroom                       # optional, displayed in header
 *   start_entity: input_datetime.x      # required, time-only
 *   end_entity: input_datetime.y        # required, time-only
 *   comfort_entity: input_number.z      # required, comfort temperature
 *   climate_entity: climate.bedroom_heating       # optional, hvac action in subtitle
 *   current_temp_entity: sensor.temp_sensor_temperature  # optional, current room temp
 *   window_entity: binary_sensor.window_sensor_opening   # optional, open/closed icon
 *   step_minutes: 5                     # optional, slider granularity (default 5)
 *
 * Visual: horizontal track 00:00→24:00, hour ticks every 6h, two draggable
 * handles, coloured fill between them (wraps midnight when start > end).
 * A thin vertical "now" marker tracks the wall clock. Header has a +/-
 * target-temperature spinner bound to comfort_entity.
 */

const CARD_TAG = 'heating-window-slider-card';
const DEFAULT_STEP = 5;

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
    background: rgba(255,152,0,0.15);
    color: var(--state-active-color, #ff9800);
    opacity: 0.6;
    transition: background 0.15s, color 0.15s, opacity 0.15s;
  }
  .climate-icon.heating {
    background: rgba(255,111,34,0.32);
    color: #ff6f22;
    opacity: 1;
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
    cursor: default;
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
  .time-row {
    display: flex;
    justify-content: space-between;
    font-variant-numeric: tabular-nums;
    font-size: 0.95rem;
    color: var(--primary-text-color);
  }
  .time-row .label {
    font-size: 0.72rem;
    color: var(--secondary-text-color);
    text-transform: uppercase;
    letter-spacing: 0.04em;
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

const pad2 = (n) => String(n).padStart(2, '0');
const minutesToHHMMSS = (m) => {
  m = ((m % 1440) + 1440) % 1440;
  return `${pad2(Math.floor(m / 60))}:${pad2(m % 60)}:00`;
};
const parseToMinutes = (hhmmss) => {
  if (!hhmmss || typeof hhmmss !== 'string') return 0;
  const [h, m] = hhmmss.split(':');
  return (parseInt(h, 10) || 0) * 60 + (parseInt(m, 10) || 0);
};
const minutesToLabel = (m) => {
  m = ((Math.round(m) % 1440) + 1440) % 1440;
  return `${pad2(Math.floor(m / 60))}:${pad2(m % 60)}`;
};
const formatTemp = (v, step) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return '--';
  const dp = (step && step < 1) ? 1 : 0;
  return `${n.toFixed(dp)} °C`;
};

class HeatingWindowSliderCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._config = null;
    this._dragging = null;
    this._dragMinutes = null;
    this._rendered = false;
    this._nowTimer = null;
    this._resizeObs = null;
    this._optimisticComfort = null;
  }

  setConfig(config) {
    if (!config.start_entity || !config.end_entity) {
      throw new Error('start_entity and end_entity are required');
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
    if (this._els && 'ResizeObserver' in window) {
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
    // Render synchronously so updates land even when the tab is in the
    // background (rAF is throttled/paused for hidden tabs).
    try { this._update(); } catch (e) { /* render errors are non-fatal */ }
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
      <div class="time-row">
        <div><div class="label">Start</div><div class="start-val">--:--</div></div>
        <div style="text-align:right"><div class="label">End</div><div class="end-val">--:--</div></div>
      </div>
      <div class="slider-wrap">
        <div class="track"></div>
        <div class="fill"></div>
        <div class="fill fill2" style="display:none"></div>
        <div class="now-mark"></div>
        <div class="handle handle-start">
          <div class="tooltip tooltip-start">--:--</div>
        </div>
        <div class="handle handle-end">
          <div class="tooltip tooltip-end">--:--</div>
        </div>
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
      startVal: card.querySelector('.start-val'),
      endVal: card.querySelector('.end-val'),
      wrap: card.querySelector('.slider-wrap'),
      fill: card.querySelector('.fill'),
      fill2: card.querySelector('.fill2'),
      nowMark: card.querySelector('.now-mark'),
      hStart: card.querySelector('.handle-start'),
      hEnd: card.querySelector('.handle-end'),
      tipStart: card.querySelector('.tooltip-start'),
      tipEnd: card.querySelector('.tooltip-end'),
    };

    this._els.hStart.addEventListener('pointerdown', (e) => this._startDrag(e, 'start'));
    this._els.hEnd.addEventListener('pointerdown', (e) => this._startDrag(e, 'end'));
    this._els.btnInc.addEventListener('click', () => this._adjustComfort(+1));
    this._els.btnDec.addEventListener('click', () => this._adjustComfort(-1));

    if (this.isConnected && 'ResizeObserver' in window && !this._resizeObs) {
      this._resizeObs = new ResizeObserver(() => this._safeUpdate());
      this._resizeObs.observe(this._els.wrap);
    }

    this._rendered = true;
  }

  _update() {
    if (!this._rendered || !this._hass || !this._config) return;
    const startMin = this._currentStartMin();
    const endMin = this._currentEndMin();
    const comfort = this._currentComfort();
    const climate = this._config.climate_entity
      ? this._hass.states[this._config.climate_entity] : null;
    const inWindow = this._inWindow(startMin, endMin, this._nowMinutes());

    this._els.name.textContent = this._config.name || this._friendly(this._config.start_entity) || 'Heating window';

    // Subtitle: current room temperature + optional hvac action.
    const tempState = this._config.current_temp_entity
      ? this._hass.states[this._config.current_temp_entity] : null;
    let subtitleParts = [];
    if (tempState && tempState.state != null && !['unavailable','unknown','none',''].includes(tempState.state)) {
      const v = Number(tempState.state);
      if (Number.isFinite(v)) subtitleParts.push(`${v.toFixed(1)} °C`);
    }
    if (climate && climate.attributes && climate.attributes.hvac_action) {
      subtitleParts.push(climate.attributes.hvac_action);
    }
    this._els.subtitle.textContent = subtitleParts.join(' · ');
    this._els.subtitle.style.display = subtitleParts.length ? '' : 'none';

    // Climate icon tint reflects hvac_action.
    const heating = climate && climate.attributes && climate.attributes.hvac_action === 'heating';
    this._els.climateIcon.classList.toggle('heating', !!heating);

    // Badge: active/inactive
    this._els.badge.textContent = inWindow ? 'active' : 'inactive';
    this._els.badge.classList.toggle('active', inWindow);

    // Window icon: open → cyan + open icon, closed → muted + closed icon.
    const winState = this._config.window_entity
      ? this._hass.states[this._config.window_entity] : null;
    if (winState && ['on','off'].includes(winState.state)) {
      const open = winState.state === 'on';
      this._els.windowIcon.icon = open
        ? 'mdi:window-open-variant'
        : 'mdi:window-closed-variant';
      this._els.windowIcon.classList.toggle('open', open);
      this._els.windowIcon.title = open ? 'Window open' : 'Window closed';
      this._els.windowIcon.style.display = '';
    } else {
      this._els.windowIcon.style.display = 'none';
    }

    // Spinner: comfort temp
    const comfortState = this._comfortState();
    const step = comfortState ? parseFloat(comfortState.attributes.step) || 0.5 : 0.5;
    const min = comfortState ? parseFloat(comfortState.attributes.min) : 5;
    const max = comfortState ? parseFloat(comfortState.attributes.max) : 30;
    this._els.spinVal.textContent = formatTemp(comfort, step);
    this._els.btnDec.disabled = !comfortState || !(comfort > min + 1e-6);
    this._els.btnInc.disabled = !comfortState || !(comfort < max - 1e-6);
    this._els.spinner.style.display = this._config.comfort_entity ? '' : 'none';

    this._renderValues(startMin, endMin);
    this._updateNowMark();
  }

  _renderValues(startMin, endMin) {
    const w = this._els.wrap.clientWidth;
    const pctS = (startMin / 1440) * 100;
    const pctE = (endMin / 1440) * 100;
    this._els.hStart.style.left = pctS + '%';
    this._els.hEnd.style.left = pctE + '%';
    this._els.startVal.textContent = minutesToLabel(startMin);
    this._els.endVal.textContent = minutesToLabel(endMin);
    this._els.tipStart.textContent = minutesToLabel(startMin);
    this._els.tipEnd.textContent = minutesToLabel(endMin);

    if (startMin === endMin) {
      this._els.fill.style.left = pctS + '%';
      this._els.fill.style.width = '0%';
      this._els.fill2.style.display = 'none';
    } else if (startMin < endMin) {
      this._els.fill.style.left = pctS + '%';
      this._els.fill.style.width = (pctE - pctS) + '%';
      this._els.fill2.style.display = 'none';
    } else {
      this._els.fill.style.left = pctS + '%';
      this._els.fill.style.width = (100 - pctS) + '%';
      this._els.fill2.style.display = '';
      this._els.fill2.style.left = '0%';
      this._els.fill2.style.width = pctE + '%';
    }
    // If width was 0 (laid out hidden), the ResizeObserver will re-trigger
    // when the card becomes visible — no recursion needed.
    void w;
  }

  _updateNowMark() {
    if (!this._els) return;
    const pct = (this._nowMinutes() / 1440) * 100;
    this._els.nowMark.style.left = `calc(${pct}% - 1px)`;
  }

  _currentStartMin() {
    if (this._dragging === 'start' && this._dragMinutes != null) return this._dragMinutes;
    return parseToMinutes(this._stateOf(this._config.start_entity));
  }
  _currentEndMin() {
    if (this._dragging === 'end' && this._dragMinutes != null) return this._dragMinutes;
    return parseToMinutes(this._stateOf(this._config.end_entity));
  }
  _currentComfort() {
    if (this._optimisticComfort != null) return this._optimisticComfort;
    const s = this._comfortState();
    return s ? Number(s.state) : NaN;
  }
  _comfortState() {
    const eid = this._config.comfort_entity;
    if (!eid || !this._hass) return null;
    return this._hass.states[eid] || null;
  }
  _stateOf(eid) {
    const s = this._hass && this._hass.states && this._hass.states[eid];
    return s ? s.state : '';
  }
  _friendly(eid) {
    const s = this._hass && this._hass.states && this._hass.states[eid];
    return s && s.attributes && s.attributes.friendly_name;
  }
  _nowMinutes() {
    const d = new Date();
    return d.getHours() * 60 + d.getMinutes();
  }
  _inWindow(s, e, n) {
    if (s === e) return false;
    if (s < e) return n >= s && n < e;
    return n >= s || n < e;
  }

  _startDrag(ev, which) {
    ev.preventDefault();
    this._dragging = which;
    this._dragMinutes = which === 'start' ? this._currentStartMin() : this._currentEndMin();
    (which === 'start' ? this._els.hStart : this._els.hEnd).classList.add('dragging');
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
    let mins = Math.round((pct * 1440) / step) * step;
    if (mins >= 1440) mins = 1440 - step;
    this._dragMinutes = mins;
    this._safeUpdate();
  }

  _endDrag(ev) {
    if (!this._dragging) return;
    const which = this._dragging;
    const mins = this._dragMinutes;
    this._dragging = null;
    this._dragMinutes = null;
    this._unbindPointer();
    this._els.hStart.classList.remove('dragging');
    this._els.hEnd.classList.remove('dragging');
    const eid = which === 'start' ? this._config.start_entity : this._config.end_entity;
    if (this._hass && Number.isFinite(mins)) {
      this._hass.callService('input_datetime', 'set_datetime', {
        entity_id: eid,
        time: minutesToHHMMSS(mins),
      }).catch(() => {});
    }
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
    // Round to step grid to avoid float drift across many clicks.
    next = Math.round(next / step) * step;
    if (Number.isFinite(min)) next = Math.max(min, next);
    if (Number.isFinite(max)) next = Math.min(max, next);
    if (Math.abs(next - cur) < 1e-9) return;
    this._optimisticComfort = next;
    this._safeUpdate();
    this._hass.callService('input_number', 'set_value', {
      entity_id: eid,
      value: next,
    }).then(() => {
      this._optimisticComfort = null;
    }).catch(() => {
      this._optimisticComfort = null;
      this._safeUpdate();
    });
  }

  static getStubConfig() {
    return {
      start_entity: 'input_datetime.heating_window_bedroom_start',
      end_entity: 'input_datetime.heating_window_bedroom_end',
      comfort_entity: 'input_number.heating_comfort_bedroom',
      climate_entity: 'climate.bedroom_heating',
      name: 'Bedroom',
    };
  }
}

if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, HeatingWindowSliderCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: CARD_TAG,
    name: 'Heating Window Slider',
    description: 'Dual-handle 24h range slider for a room heating window.',
    preview: false,
  });
}
