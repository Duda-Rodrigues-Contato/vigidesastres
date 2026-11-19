// ============================================================================
// GRÁFICO 1: Histórico de Chuva Diária
// ============================================================================
const elDados = document.getElementById('dados-chuva-diaria');

if (elDados) {
  const dados = JSON.parse(elDados.textContent);
  const cores = ['#93c5fd', '#1e3a8a', '#0ea5e9', '#14b8a6', '#6366f1', '#64748b'];

  // Função auxiliar para formatar valores em milímetros
  const formatarMilimetros = (valor) => {
    return `${valor.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} mm`;
  };

  // 1.1 Configuração das linhas/barras de chuva
  const datasetsSeries = dados.series.map((serie, index) => {
    const corAtual = cores[index % cores.length];
    const isBar = serie.tipo === 'bar';

    return {
      label: serie.nome,
      data: serie.valores,
      type: serie.tipo || 'line',
      order: isBar ? 2 : 1,
      borderColor: corAtual,
      backgroundColor: isBar
        ? serie.valores.map((_, j) => (j === serie.valores.length - 1 ? '#dbeafe' : corAtual))
        : corAtual,
      borderWidth: isBar ? 0 : 2.5,
      borderRadius: 2,
      pointRadius: 3,
      tension: 0,
      spanGaps: false, // dia sem coleta fica como lacuna, não como zero
      segment: isBar ? undefined : {
        borderDash: (ctx) => (ctx.p1DataIndex === serie.valores.length - 1 ? [5, 4] : undefined)
      }
    };
  });

  // 1.2 Configuração das linhas de limiares (linhas de referência horizontais)
  const datasetsLimiares = (dados.limiares || []).map((limiar) => ({
    type: 'line',
    label: `${limiar.nome} (${formatarMilimetros(limiar.mm)})`,
    data: dados.rotulos.map(() => limiar.mm),
    borderColor: limiar.cor,
    borderDash: [6, 4],
    borderWidth: 1.2,
    pointRadius: 0,
    order: 0
  }));

  // 1.3 Renderização do Gráfico
  new Chart(document.getElementById('graficoChuva'), {
    type: 'line',
    data: {
      labels: dados.rotulos,
      datasets: [...datasetsSeries, ...datasetsLimiares]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'bottom',
          labels: { boxWidth: 12, font: { size: 11 } }
        },
        tooltip: {
          callbacks: {
            label: (contexto) => {
              const valor = contexto.parsed.y;
              return `${contexto.dataset.label}: ${valor === null ? 'sem dado' : formatarMilimetros(valor)}`;
            }
          }
        }
      },
      scales: {
        x: { grid: { display: false } },
        y: {
          beginAtZero: true,
          suggestedMax: 20, // a linha de chuva forte (18,6 mm) sempre aparece como referência
          grid: { color: '#f1f5f9' },
          ticks: { callback: (valor) => `${valor.toLocaleString('pt-BR')} mm` }
        }
      }
    }
  });
}


// ============================================================================
// GRÁFICO 2: Próximas 48h (Chuva Prevista × Maré)
// ============================================================================
const el48 = document.getElementById('dados-48h');

if (el48) {
  const d48 = JSON.parse(el48.textContent);

  // Função auxiliar para formatar números com unidades (ex: 'mm' ou 'm')
  const formatarValor = (valor, casasDecimais, unidade) => {
    return `${valor.toLocaleString('pt-BR', { minimumFractionDigits: casasDecimais, maximumFractionDigits: casasDecimais })} ${unidade}`;
  };

  // 2.1 Séries de Chuva e Maré
  const series = [
    {
      type: 'bar',
      label: 'Chuva prevista',
      data: d48.chuva,
      yAxisID: 'chuva',
      backgroundColor: '#3b82f6',
      borderRadius: 2,
      order: 2
    },
    {
      type: 'line',
      label: 'Maré',
      data: d48.mare,
      yAxisID: 'mare',
      borderColor: '#0f766e',
      backgroundColor: '#0f766e',
      borderWidth: 2.5,
      pointRadius: 0,
      tension: 0.35,
      order: 1
    }
  ];

  // 2.2 Adiciona a linha de limiar de maré alta, se existir
  if (d48.limiar_mare !== null) {
    series.push({
      type: 'line',
      label: 'Limiar de maré alta',
      yAxisID: 'mare',
      data: d48.rotulos.map(() => d48.limiar_mare),
      borderColor: '#d97706',
      borderDash: [6, 4],
      borderWidth: 1.5,
      pointRadius: 0,
      order: 0
    });
  }

  // Extrai a hora de uma string de data (espera algo como "DD/MM HH:MM")
  const obterHora = (rotulo) => parseInt(rotulo.split(' ')[1], 10);

  // 2.3 Plugin customizado (sombrear noites e marcar a virada do dia)
  const pluginDiasENoites = {
    id: 'diasENoites',
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea, scales: { x } } = chart;
      const passo = (x.getPixelForValue(1) - x.getPixelForValue(0)) || 0;

      ctx.save();

      d48.rotulos.forEach((rotulo, i) => {
        const px = x.getPixelForValue(i);
        const hora = obterHora(rotulo);

        // Desenha o fundo sombreado da noite (18h às 6h)
        if (hora >= 18 || hora < 6) {
          ctx.fillStyle = 'rgba(100, 116, 139, 0.07)';
          ctx.fillRect(px - passo / 2, chartArea.top, passo, chartArea.bottom - chartArea.top);
        }

        // Desenha a linha e o texto indicando o início de um novo dia (00h)
        if (hora === 0) {
          ctx.strokeStyle = '#94a3b8';
          ctx.setLineDash([3, 3]);

          ctx.beginPath();
          ctx.moveTo(px - passo / 2, chartArea.top);
          ctx.lineTo(px - passo / 2, chartArea.bottom);
          ctx.stroke();

          ctx.setLineDash([]);
          ctx.fillStyle = '#64748b';
          ctx.font = '11px sans-serif';
          ctx.fillText(rotulo.split(' ')[0], px - passo / 2 + 4, chartArea.top + 12);
        }
      });

      ctx.restore();
    }
  };

  // 2.4 Renderização do Gráfico
  new Chart(document.getElementById('grafico48h'), {
    plugins: [pluginDiasENoites],
    data: {
      labels: d48.rotulos,
      datasets: series
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'bottom',
          labels: { boxWidth: 12, font: { size: 11 } }
        },
        tooltip: {
          callbacks: {
            label: (contexto) => {
              if (contexto.parsed.y === null) return `${contexto.dataset.label}: sem dado`;

              const isChuva = contexto.dataset.yAxisID === 'chuva';
              const valorFormatado = isChuva
                ? formatarValor(contexto.parsed.y, 1, 'mm')
                : formatarValor(contexto.parsed.y, 2, 'm');

              return `${contexto.dataset.label}: ${valorFormatado}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 }
        },
        chuva: {
          position: 'left',
          beginAtZero: true,
          suggestedMax: 5,
          title: { display: true, text: 'chuva (mm/h)' },
          ticks: { callback: (valor) => valor.toLocaleString('pt-BR') }
        },
        mare: {
          position: 'right',
          grid: { drawOnChartArea: false },
          title: { display: true, text: 'maré (m)' },
          ticks: { callback: (valor) => valor.toLocaleString('pt-BR') }
        }
      }
    }
  });
}
