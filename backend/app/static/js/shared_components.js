window.PDEUEComponents = {
  formatCents: function(c) { if (c === null || c === undefined) return '$0.00'; return '$' + (Number(c)/100).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}); },
  renderEquityChart: function(canvasId, labels, dataPointsCents, color='#38bdf8') {
    const el = document.getElementById(canvasId);
    if (!el || !window.Chart) return;
    return new Chart(el.getContext('2d'), {
      type: 'line',
      data: { labels: labels, datasets: [{ label: 'Equity (Cents)', data: dataPointsCents, borderColor: color, backgroundColor: 'rgba(56,189,248,0.05)', fill: true, tension: 0.3, pointRadius: 2 }] },
      options: { responsive: true, maintainAspectRatio: false, scales: { y: { ticks: { callback: v => '$' + (v/100).toFixed(0) }, grid: { color: '#334155' } }, x: { grid: { color: 'rgba(51,65,85,0.3)' } } }, plugins: { legend: { display: false } } }
    });
  },
  renderWaterfallDonut: function(canvasId, scma, cfcp, faep) {
    const el = document.getElementById(canvasId);
    if (!el || !window.Chart) return;
    return new Chart(el.getContext('2d'), {
      type: 'doughnut',
      data: { labels: ['SCMA (87%)', 'CFCP (10%)', 'FAEP (3%)'], datasets: [{ data: [scma, cfcp, faep], backgroundColor: ['#38bdf8', '#22c55e', '#a855f7'], borderColor: '#111c21', borderWidth: 2 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: '#f8fafc' } } } }
    });
  },
  openInspector: function(id, title, html) { const d = document.getElementById(id); if (!d) return; document.getElementById(id + '-title').innerText = title; document.getElementById(id + '-body').innerHTML = html; d.classList.add('open'); },
  closeInspector: function(id) { const d = document.getElementById(id); if (d) d.classList.remove('open'); }
};
