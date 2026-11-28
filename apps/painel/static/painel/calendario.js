// Calendário: os dois gráficos de demanda (previsão do modelo e sazonalidade dos atendimentos).
(function () {
  if (!window.Chart) return;
  Chart.defaults.font.family = "'DM Sans', system-ui, sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.maintainAspectRatio = false;
  const dados = (id) => { const el = document.getElementById(id); return el ? JSON.parse(el.textContent) : null; };

  const porDistrito = dados('d-demanda-distrito');
  if (porDistrito) {
    const series = [
      { label: 'Previsto', data: porDistrito.previsto, backgroundColor: '#ea580c' },
      { label: 'Normal da época', data: porDistrito.normal, backgroundColor: '#94a3b8' },
    ];
    if (porDistrito.real) series.push({ label: 'Real', data: porDistrito.real, backgroundColor: '#334155' });
    new Chart(document.getElementById('demanda-distrito'), {
      type: 'bar', data: { labels: porDistrito.distritos, datasets: series },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
  }

  const ano = dados('d-demanda-ano');
  if (ano) {
    const ponto = ano.rotulos.map((_, i) => (i + 1 === ano.semana_atual ? ano.previsto : null));
    new Chart(document.getElementById('demanda-ano'), {
      data: { labels: ano.rotulos, datasets: [
        { type: 'line', data: ano.maximo, borderColor: 'transparent', pointRadius: 0,
          backgroundColor: 'rgba(148,163,184,0.25)', fill: '+1' },
        { type: 'line', data: ano.minimo, borderColor: 'transparent', pointRadius: 0, fill: false },
        { type: 'line', data: ano.media, borderColor: '#334155', borderWidth: 2, pointRadius: 0, tension: 0.3 },
        { type: 'line', data: ponto, backgroundColor: '#ea580c', borderColor: '#ea580c', pointRadius: 7, showLine: false },
      ] },
      options: { plugins: { legend: { display: false }, tooltip: { enabled: false } },
                 scales: { y: { beginAtZero: true }, x: { ticks: { maxTicksLimit: 13 } } } },
    });
  }
})();
