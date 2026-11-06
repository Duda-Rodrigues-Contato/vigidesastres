// Tela: painel/dashboard.html
// Dados do servidor chegam pelo json_script do template (o Django escapa o conteúdo).

// Grafico de chuva diaria por zona. Os dados vem do servidor via
// json_script (o Django escapa o conteudo, evitando injecao de HTML).
const elDados = document.getElementById('dados-chuva-diaria');
if (elDados) {
  const dados = JSON.parse(elDados.textContent);
  const cores = ['#93c5fd', '#1e3a8a', '#0ea5e9', '#14b8a6', '#6366f1', '#64748b'];
  const mm = v => v.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' mm';

  new Chart(document.getElementById('graficoChuva'), {
    type: 'line',
    data: {
      labels: dados.rotulos,
      datasets: dados.series.map((s, i) => ({
        label: s.nome,
        data: s.valores,
        borderColor: cores[i % cores.length],
        backgroundColor: cores[i % cores.length],
        type: s.tipo || 'line',
        order: s.tipo === 'bar' ? 2 : 1,
        borderWidth: s.tipo === 'bar' ? 0 : 2.5,
        borderRadius: 2,
        pointRadius: 3,
        tension: 0,
        spanGaps: false,  // dia sem coleta fica como lacuna, nao como zero
        // "hoje" ainda está acontecendo: barra clara e linha tracejada
        ...(s.tipo === 'bar'
          ? { backgroundColor: s.valores.map((_, j) => j === s.valores.length - 1 ? '#dbeafe' : cores[i % cores.length]) }
          : { segment: { borderDash: c => c.p1DataIndex === s.valores.length - 1 ? [5, 4] : undefined } })
      })).concat((dados.limiares || []).map(l => ({
        type: 'line', label: l.nome + ' (' + mm(l.mm) + ')', data: dados.rotulos.map(() => l.mm),
        borderColor: l.cor, borderDash: [6, 4], borderWidth: 1.2, pointRadius: 0, order: 0
      })))
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: c => c.dataset.label + ': ' + (c.parsed.y === null ? 'sem dado' : mm(c.parsed.y))
          }
        }
      },
      scales: {
        x: { grid: { display: false } },
        y: {
          beginAtZero: true,
          suggestedMax: 20,  // a linha de chuva forte (18,6 mm) sempre aparece como referência
          grid: { color: '#f1f5f9' },
          ticks: { callback: v => v.toLocaleString('pt-BR') + ' mm' }
        }
      }
    }
  });
}

// Proximas 48h: chuva prevista (barras, eixo da esquerda) x mare
// (linha, eixo da direita). As horas em que as duas sobem juntas sao
// a versao visual do gatilho de alagamento.
const el48 = document.getElementById('dados-48h');
if (el48) {
  const d48 = JSON.parse(el48.textContent);
  const fmt = (v, casas, un) => v.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas }) + ' ' + un;
  const series = [
    { type: 'bar', label: 'Chuva prevista', data: d48.chuva, yAxisID: 'chuva',
      backgroundColor: '#3b82f6', borderRadius: 2, order: 2 },
    { type: 'line', label: 'Maré', data: d48.mare, yAxisID: 'mare',
      borderColor: '#0f766e', backgroundColor: '#0f766e', borderWidth: 2.5,
      pointRadius: 0, tension: 0.35, order: 1 }
  ];
  if (d48.limiar_mare !== null) {
    series.push({ type: 'line', label: 'Limiar de maré alta', yAxisID: 'mare',
      data: d48.rotulos.map(() => d48.limiar_mare),
      borderColor: '#d97706', borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0, order: 0 });
  }
  // noites (18h às 6h) sombreadas e uma linha na virada de cada dia
  const hora = r => parseInt(r.split(' ')[1], 10);
  const diasENoites = {
    id: 'diasENoites',
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea: a, scales: { x } } = chart;
      const passo = (x.getPixelForValue(1) - x.getPixelForValue(0)) || 0;
      ctx.save();
      d48.rotulos.forEach((r, i) => {
        const px = x.getPixelForValue(i), h = hora(r);
        if (h >= 18 || h < 6) {
          ctx.fillStyle = 'rgba(100, 116, 139, 0.07)';
          ctx.fillRect(px - passo / 2, a.top, passo, a.bottom - a.top);
        }
        if (h === 0) {
          ctx.strokeStyle = '#94a3b8'; ctx.setLineDash([3, 3]);
          ctx.beginPath(); ctx.moveTo(px - passo / 2, a.top); ctx.lineTo(px - passo / 2, a.bottom); ctx.stroke();
          ctx.setLineDash([]); ctx.fillStyle = '#64748b'; ctx.font = '11px sans-serif';
          ctx.fillText(r.split(' ')[0], px - passo / 2 + 4, a.top + 12);
        }
      });
      ctx.restore();
    }
  };
  new Chart(document.getElementById('grafico48h'), {
    plugins: [diasENoites],
    data: { labels: d48.rotulos, datasets: series },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: { callbacks: { label: c => {
          if (c.parsed.y === null) return c.dataset.label + ': sem dado';
          return c.dataset.label + ': ' + (c.dataset.yAxisID === 'chuva' ? fmt(c.parsed.y, 1, 'mm') : fmt(c.parsed.y, 2, 'm'));
        } } }
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } },
        chuva: { position: 'left', beginAtZero: true, suggestedMax: 5,
                 title: { display: true, text: 'chuva (mm/h)' },
                 ticks: { callback: v => v.toLocaleString('pt-BR') } },
        mare: { position: 'right', grid: { drawOnChartArea: false },
                title: { display: true, text: 'maré (m)' },
                ticks: { callback: v => v.toLocaleString('pt-BR') } }
      }
    }
  });
}
