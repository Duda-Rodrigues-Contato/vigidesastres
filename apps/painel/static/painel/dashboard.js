// Dashboard: gráficos simples, só com dados atualizados. Cada um lê o seu JSON (json_script "d-...").
(function () {
  if (!window.Chart) return;
  Chart.defaults.font.family = "'DM Sans', system-ui, sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.maintainAspectRatio = false;
  const dados = (id) => { const el = document.getElementById('d-' + id); return el ? JSON.parse(el.textContent) : null; };
  const semLegenda = { legend: { display: false } };

  // Calor nas próximas 48 h: sensação térmica, com as faixas de cautela extrema e perigo
  const calor = dados('calor');
  if (calor) {
    const n = calor.rotulos.length;
    const faixa = (valor, cor) => ({ data: Array(n).fill(valor), borderColor: cor, borderDash: [6, 4],
                                     borderWidth: 1.5, pointRadius: 0 });
    new Chart(document.getElementById('calor'), {
      type: 'line',
      data: { labels: calor.rotulos, datasets: [
        { data: calor.indice, borderColor: '#dc2626', backgroundColor: 'rgba(220,38,38,0.12)', fill: true,
          borderWidth: 2.5, pointRadius: 0, tension: 0.35 },
        faixa(calor.cautela_extrema, '#f59e0b'),
        faixa(calor.perigo, '#7f1d1d'),
      ] },
      options: { plugins: { ...semLegenda, tooltip: { filter: (item) => item.datasetIndex === 0 } },
                 scales: { y: { suggestedMin: 24, suggestedMax: 44, ticks: { callback: (v) => v + ' °C' } },
                           x: { ticks: { maxTicksLimit: 12 } } } },
    });
  }

  // Chuva prevista para as próximas 24 h, por distrito (cor = classe de chuva)
  const prevista = dados('chuva-prevista');
  if (prevista) {
    new Chart(document.getElementById('chuva-prevista'), {
      type: 'bar',
      data: { labels: prevista.distritos, datasets: [{ data: prevista.mm, backgroundColor: prevista.cores }] },
      options: { plugins: { ...semLegenda, tooltip: { callbacks: {
                   label: (c) => `${c.raw} mm · ${prevista.classes[c.dataIndex].toLowerCase()}` } } },
                 scales: { y: { beginAtZero: true, ticks: { callback: (v) => v + ' mm' } } } },
    });
  }

  // Chuva dos últimos 30 dias x normal
  const chuva30 = dados('chuva-30');
  if (chuva30) {
    new Chart(document.getElementById('chuva-30'), {
      data: { labels: chuva30.rotulos, datasets: [
        { type: 'bar', data: chuva30.chuva, backgroundColor: '#2563eb' },
        { type: 'line', data: chuva30.normal, borderColor: '#94a3b8', borderWidth: 2, pointRadius: 0, tension: 0.3 },
      ] },
      options: { plugins: semLegenda,
                 scales: { y: { beginAtZero: true, ticks: { callback: (v) => v + ' mm' } }, x: { ticks: { maxTicksLimit: 8 } } } },
    });
  }

  // Arboviroses: este ano x ano anterior
  const arbo = dados('arbo');
  if (arbo) {
    new Chart(document.getElementById('arbo'), {
      type: 'line',
      data: { labels: arbo.rotulos, datasets: [
        { data: arbo.anterior, borderColor: '#c4b5fd', borderWidth: 2, pointRadius: 0, tension: 0.3 },
        { data: arbo.atual, borderColor: '#7c3aed', borderWidth: 3, pointRadius: 0, tension: 0.3 },
      ] },
      options: { plugins: semLegenda, scales: { y: { beginAtZero: true }, x: { ticks: { maxTicksLimit: 9 } } } },
    });
  }

  // Alertas dos últimos 30 dias
  const alertas = dados('alertas');
  if (alertas) {
    new Chart(document.getElementById('alertas'), {
      type: 'bar',
      data: { labels: alertas.rotulos, datasets: [
        { data: alertas.alto, backgroundColor: '#dc2626' },
        { data: alertas.medio, backgroundColor: '#f59e0b' },
      ] },
      options: { plugins: semLegenda,
                 scales: { x: { stacked: true, ticks: { maxTicksLimit: 8 } },
                           y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } } } },
    });
  }
})();
