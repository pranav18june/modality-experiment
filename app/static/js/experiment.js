/**
 * experiment.js
 * Handles:
 *  1. Countdown timer (time-on-task logging)
 *  2. ROP/SS slider live display + absolute unit calculation
 *  3. Plotly chart rendering for the VISUAL modality
 *  4. Form submit guard (prevent double-submit)
 */

// ── 1. Timer ──────────────────────────────────────────────────────────────
(function initTimer() {
  const display = document.getElementById('timer-display');
  const hiddenInput = document.getElementById('elapsed-hidden');
  if (!display || !hiddenInput) return;

  const startTime = Date.now();

  function tick() {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const mins    = Math.floor(elapsed / 60);
    const secs    = elapsed % 60;
    display.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
    hiddenInput.value   = elapsed;
  }

  tick();
  setInterval(tick, 1000);

  // On form submit, record final elapsed time
  const form = document.getElementById('task-form');
  if (form) {
    form.addEventListener('submit', function() {
      hiddenInput.value = Math.floor((Date.now() - startTime) / 1000);
    });
  }
})();


// ── 2. Sliders ────────────────────────────────────────────────────────────
(function initSliders() {
  let sliderMoves = 0;
  const changesInput = document.getElementById('answer-changes-hidden');
  const autosaveInd  = document.getElementById('autosave-ind');

  function showAutosave() {
    if (autosaveInd) {
      autosaveInd.classList.add('saved');
      clearTimeout(autosaveInd.timer);
      autosaveInd.timer = setTimeout(() => autosaveInd.classList.remove('saved'), 1500);
    }
  }

  document.querySelectorAll('.exp-slider').forEach(function(slider) {
    const displayId = slider.dataset.display;
    const display   = displayId ? document.getElementById(displayId) : null;

    function update() {
      const val = parseInt(slider.value, 10);
      const sign = val >= 0 ? '+' : '';

      // Update the display badge
      if (display) display.textContent = sign + val + '%';

      // Update absolute unit calculation if BASE_ROP / BASE_SS are available
      if (typeof BASE_ROP !== 'undefined' && slider.id === 'rop-slider') {
        const absEl = document.getElementById('rop-abs');
        if (absEl) absEl.textContent = Math.round(BASE_ROP * (1 + val / 100));
      }
      if (typeof BASE_SS !== 'undefined' && slider.id === 'ss-slider') {
        const absEl = document.getElementById('ss-abs');
        if (absEl) absEl.textContent = Math.round(BASE_SS * (1 + val / 100));
      }

      // Colour the slider track to show deviation from AI suggestion
      const ai = parseFloat(slider.dataset.ai || 0);
      const pct = (val - parseInt(slider.min, 10)) /
                  (parseInt(slider.max, 10) - parseInt(slider.min, 10)) * 100;

      slider.style.background = `linear-gradient(
        to right,
        #2a3050 0%,
        #2a3050 ${pct}%,
        #1a2035 ${pct}%,
        #1a2035 100%
      )`;

      // Highlight display if user deviates > 5pp from AI suggestion
      if (display) {
        const deviation = Math.abs(val - ai);
        display.style.color = deviation > 5 ? '#f59e0b' : '#3b82f6';
      }
    }

    slider.addEventListener('input', update);
    slider.addEventListener('change', () => {
      sliderMoves++;
      if (changesInput) changesInput.value = sliderMoves;
      showAutosave();
    });
    // Init display
    update();
  });
})();


// ── 3. Visual Modality — Plotly chart ─────────────────────────────────────
(function initVisualChart() {
  if (typeof MODALITY === 'undefined' || MODALITY !== 'visual') return;
  if (typeof SCENARIO === 'undefined') return;

  const demandDiv    = document.getElementById('demand-chart');
  const inventoryDiv = document.getElementById('inventory-chart');
  if (!demandDiv) return;

  const demand = SCENARIO.demand_series;
  const ma30   = SCENARIO.ma30_series;
  const days   = Array.from({length: demand.length}, (_, i) => i + 1);

  const disStart = SCENARIO.disruption_start + 1;
  const disEnd   = SCENARIO.disruption_end + 1;

  // ── Demand trajectory chart ───────────────────────────────────────────
  const baselineInv = SCENARIO.baseline_inventory;
  const disInv      = SCENARIO.disruption_inventory;

  // LLM-adjusted demand estimate (linear from baseline mean to disruption mean
  // over the disruption window — represents the AI's forward-looking adjustment)
  const llmAdjusted = demand.map((d, i) => {
    if (i < disStart - 1) return baselineInv.mean;
    if (i >= disEnd - 1)  return baselineInv.mean;
    const prog = (i - (disStart - 1)) / ((disEnd - 1) - (disStart - 1));
    return baselineInv.mean + prog * (disInv.mean - baselineInv.mean);
  });

  // Deviation bands (±1σ around 30-day MA)
  const upperBand = ma30.map(v => v + baselineInv.std * 1.5);
  const lowerBand = ma30.map(v => v - baselineInv.std * 1.5);

  const demandTraces = [
    // Shaded deviation band
    {
      x: [...days, ...days.slice().reverse()],
      y: [...upperBand, ...lowerBand.slice().reverse()],
      fill: 'toself',
      fillcolor: 'rgba(59,130,246,0.06)',
      line: {width: 0},
      hoverinfo: 'skip',
      name: '±1.5σ band',
      showlegend: false,
    },
    // Disruption window shading
    {
      x: [disStart, disStart, disEnd, disEnd],
      y: [Math.min(...demand) * 0.85, Math.max(...demand) * 1.1,
          Math.max(...demand) * 1.1, Math.min(...demand) * 0.85],
      fill: 'toself',
      fillcolor: 'rgba(239,68,68,0.10)',
      line: {width: 0},
      hoverinfo: 'skip',
      name: 'Disruption window',
      showlegend: true,
    },
    // Actual demand
    {
      x: days, y: demand,
      mode: 'lines',
      name: 'Actual Demand',
      line: {color: '#3b82f6', width: 1.5},
    },
    // 30-day MA baseline
    {
      x: days, y: ma30,
      mode: 'lines',
      name: '30-day MA Baseline',
      line: {color: '#f59e0b', width: 1.8, dash: 'dot'},
    },
    // LLM-adjusted demand
    {
      x: days, y: llmAdjusted,
      mode: 'lines',
      name: 'AI-Adjusted Estimate',
      line: {color: '#a855f7', width: 1.5, dash: 'dashdot'},
    },
    // Disruption boundary vertical line
    {
      x: [disStart, disStart],
      y: [Math.min(...demand) * 0.85, Math.max(...demand) * 1.1],
      mode: 'lines',
      name: 'Disruption onset',
      line: {color: '#ef4444', dash: 'dash', width: 1.2},
      showlegend: false,
    },
  ];

  const demandLayout = {
    margin:  {t: 10, b: 40, l: 50, r: 16},
    height:  240,
    legend:  {orientation: 'h', y: -0.22, font: {size: 11}},
    xaxis: {
      title: {text: 'Day', standoff: 8},
      color: '#64748b',
      gridcolor: '#1e2840',
      zeroline: false,
    },
    yaxis: {
      title: {text: 'Units/day', standoff: 8},
      color: '#64748b',
      gridcolor: '#1e2840',
      zeroline: false,
    },
    paper_bgcolor: 'transparent',
    plot_bgcolor:  '#0b0e16',
    font:   {color: '#94a3b8', size: 11, family: '-apple-system, sans-serif'},
    hovermode: 'x unified',
  };

  Plotly.newPlot(demandDiv, demandTraces, demandLayout, {
    responsive: true,
    displayModeBar: true,
    modeBarButtonsToRemove: ['select2d', 'lasso2d', 'autoScale2d'],
    displaylogo: false,
  });

  // ── Inventory state chart ─────────────────────────────────────────────
  if (!inventoryDiv) return;

  // Compute rolling ROP and SS estimates across the series
  const windowSize = 14;
  const ropSeries  = days.map((_, i) => {
    const window  = demand.slice(Math.max(0, i - windowSize + 1), i + 1);
    const mu      = window.reduce((a, b) => a + b, 0) / window.length;
    const sigma   = Math.sqrt(window.reduce((a, b) => a + (b - mu) ** 2, 0) / window.length);
    return mu * SCENARIO.lead_time + 1.645 * sigma * Math.sqrt(SCENARIO.lead_time);
  });

  const ssSeries = days.map((_, i) => {
    const window = demand.slice(Math.max(0, i - windowSize + 1), i + 1);
    const mu     = window.reduce((a, b) => a + b, 0) / window.length;
    const sigma  = Math.sqrt(window.reduce((a, b) => a + (b - mu) ** 2, 0) / window.length);
    return 1.645 * sigma * Math.sqrt(SCENARIO.lead_time);
  });

  const invTraces = [
    {x: [disStart, disStart], y: [0, Math.max(...ropSeries) * 1.15],
     mode: 'lines', line: {color: '#ef4444', dash: 'dash', width: 1},
     showlegend: false, hoverinfo: 'skip'},
    {x: days, y: ropSeries, mode: 'lines', name: 'Rolling ROP',
     line: {color: '#3b82f6', width: 1.5}},
    {x: days, y: ssSeries,  mode: 'lines', name: 'Rolling SS',
     line: {color: '#22c55e', width: 1.5}},
  ];

  Plotly.newPlot(inventoryDiv, invTraces, {
    margin:  {t: 6, b: 36, l: 50, r: 16},
    height:  140,
    legend:  {orientation: 'h', y: -0.35, font: {size: 10}},
    xaxis:   {color: '#64748b', gridcolor: '#1e2840', title: {text: 'Day', standoff: 6}},
    yaxis:   {color: '#64748b', gridcolor: '#1e2840', title: {text: 'Units', standoff: 6}},
    paper_bgcolor: 'transparent',
    plot_bgcolor:  '#0b0e16',
    font:    {color: '#94a3b8', size: 10},
  }, {responsive: true, displayModeBar: false});
})();


// ── 4. Form submit guard ──────────────────────────────────────────────────
(function initSubmitGuard() {
  const form = document.getElementById('task-form');
  const btn  = document.getElementById('submit-btn');
  if (!form || !btn) return;

  let allowSubmit = false;

  form.addEventListener('submit', function(e) {
    if (allowSubmit) return;

    // Minimum time check
    const elapsedInput = document.getElementById('elapsed-hidden');
    const elapsed = elapsedInput ? parseInt(elapsedInput.value || '0', 10) : 0;
    if (elapsed < 15) {
      if (!confirm(`You've only spent ${elapsed} seconds reviewing this scenario. Are you sure you are ready to submit your decision?`)) {
        e.preventDefault();
        return;
      }
    }

    // Soft validation for extreme adjustments
    const ropSlider = document.getElementById('rop-slider');
    const ssSlider = document.getElementById('ss-slider');
    if (ropSlider && ssSlider && typeof SCENARIO !== 'undefined') {
      const ropDiff = Math.abs(parseInt(ropSlider.value, 10) - SCENARIO.ai_suggested_rop_pct);
      const ssDiff = Math.abs(parseInt(ssSlider.value, 10) - SCENARIO.ai_suggested_ss_pct);
      
      if (ropDiff > 40 || ssDiff > 40) {
        if (!confirm(`Your adjustment differs significantly from the AI recommendation (by over 40%). Are you sure you want to proceed with these values?`)) {
          e.preventDefault();
          return;
        }
      }
    }

    allowSubmit = true;
    btn.disabled     = true;
    btn.textContent  = 'Saving…';
  });
})();
