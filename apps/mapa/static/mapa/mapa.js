// Tela: mapa/mapa.html
// Dados do servidor chegam pelo json_script do template (o Django escapa o conteúdo).

// 1. Inicializa o mapa centralizado em Recife
// O zoom padrão é desligado e recolocado à direita, para não ficar
// embaixo da etiqueta "Recife · PE".
const map = L.map('map', { zoomControl: false }).setView([-8.05, -34.9], 12);

// 2. Mapas de fundo: Ruas (padrão) e Satélite, ambos da Esri.
const baseRuas = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
  attribution: 'Tiles &copy; Esri'
});
const baseSatelite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
  attribution: 'Tiles &copy; Esri'
});
baseRuas.addTo(map);
L.control.zoom({ position: 'topright' }).addTo(map);
L.control.layers({ 'Ruas': baseRuas, 'Satélite': baseSatelite }, null, { position: 'topright' }).addTo(map);

// Linha de detalhe dos cards: rótulo à esquerda, valor à direita
function linhaPop(rotulo, valor) {
  return '<li><span>' + rotulo + '</span><span>' + valor + '</span></li>';
}

// 3. Busca os distritos no MongoDB via API
// O GeoJSON do portal do Recife traz apenas o campo numerico
// 'cdistscodi' (1 a 8), sem o nome do distrito.
const ROMANOS = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII'];

function nomeDistrito(props) {
  const codigo = props && props.cdistscodi;
  return codigo && ROMANOS[codigo - 1] ? 'DS ' + ROMANOS[codigo - 1] : null;
}

// Cor por nível: vem dos gatilhos reais de chuva e maré (/api/situacao-distritos/)
const CORES_RISCO = { 'ALTO': '#ef4444', 'MÉDIO': '#f59e0b', 'NORMAL': '#22c55e', 'SEM DADO': '#94a3b8' };
let situacao = {};

function corDoDistrito(nome) {
  const d = situacao[nome];
  return (d && CORES_RISCO[d.nivel]) || CORES_RISCO['SEM DADO'];
}

fetch('/api/situacao-distritos/')
  .then(r => r.json())
  .then(dados => {
    dados.distritos.forEach(d => { situacao[d.nome] = d; });
    const alvo = new URLSearchParams(location.search).get('distrito');
    if (alvo && situacao[alvo]) { distritoSelecionado = alvo; }
    if (typeof redesenharDistritos === 'function') redesenharDistritos();
  })
  .catch(err => console.error('Erro ao carregar a situação dos distritos:', err));

let camadaDistritos = null;
let distritoSelecionado = null;
// roxo nao colide com nenhuma outra cor do mapa: risco (vermelho,
// amarelo, verde), chuva (azuis) e mouse (cinza-escuro)
const COR_SELECAO = '#7c3aed';

function chuvaLigada() {
  return document.getElementById('camada-chuva').checked;
}

function riscoLigado() {
  return document.getElementById('camada-risco').checked;
}

function arboLigado() {
  return document.getElementById('camada-arbo').checked;
}

// as camadas de risco e de arboviroses pintam os mesmos bairros:
// ligar uma desliga a outra, para os polígonos não se sobreporem
function desligar(id) {
  const caixa = document.getElementById(id);
  if (caixa.checked) {
    caixa.checked = false;
    caixa.dispatchEvent(new Event('change'));
  }
}

// com uma camada tematica por cima, os distritos viram so contorno
function distritosEmContorno() {
  return chuvaLigada() || riscoLigado() || arboLigado() || comLigado() || vulLigado() || perfilLigado();
}

// o painel "Nivel de risco" descreve a cor dos distritos, que some
// quando eles viram contorno
function atualizarPainelRisco() {
  document.getElementById('painel-risco').style.opacity = distritosEmContorno() ? '0.4' : '1';
}

function formatarMm(mm) {
  if (mm === null || mm === undefined) return 'sem dado';
  return mm.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' mm';
}

// Tres estados visuais:
//  - normal: preenchido pela cor de risco
//  - chuva ligada: so um contorno fino e tracejado, para a borda
//    grossa das zonas (por baixo) ser a linha dominante
//  - selecionado: contorno grosso e roxo enquanto o distrito estiver
//    selecionado (clique no distrito; clique de novo para desmarcar)
function estiloDistrito(feature) {
  const selecionado = nomeDistrito(feature.properties) === distritoSelecionado;
  if (distritosEmContorno()) {
    return {
      fillColor: COR_SELECAO,
      fillOpacity: selecionado ? 0.15 : 0,
      color: selecionado ? COR_SELECAO : '#64748b',
      weight: selecionado ? 4 : 1,
      dashArray: selecionado ? null : '3 4'
    };
  }
  return {
    fillColor: corDoDistrito(nomeDistrito(feature.properties)),
    fillOpacity: 0.45,
    color: selecionado ? COR_SELECAO : '#0f172a',
    weight: selecionado ? 4 : 1.5,
    dashArray: null
  };
}

// destaque ao passar o mouse: deixa claro a que poligono a dica se refere
function destacar(layer) {
  layer.setStyle({
    weight: 4,
    color: '#0f172a',
    dashArray: null,
    fillColor: distritosEmContorno() ? '#0f172a' : layer.options.fillColor,
    fillOpacity: distritosEmContorno() ? 0.18 : 0.7
  });
  // com o risco ligado, nao puxa o distrito para cima: esconderia os bairros
  if (!riscoLigado() && !arboLigado() && !comLigado()) layer.bringToFront();
}

function redesenharDistritos() {
  if (camadaDistritos) camadaDistritos.setStyle(estiloDistrito);
}

fetch('/api/distritos/')
  .then(response => response.json())
  .then(data => {
    const camada = L.geoJSON(data, {
      style: estiloDistrito,
      onEachFeature: function (feature, layer) {
        const nome = nomeDistrito(feature.properties);
        if (nome) {
          // dica dinamica: com a chuva ligada, mostra a chuva medida do distrito
          layer.bindTooltip(function () {
            const zona = chuvaLigada() && zonaDoDistrito[nome];
            return zona
              ? '<strong>' + nome + '</strong><br>' + formatarMm(zona.chuva_24h_mm) + ' em 24h' +
                (zona.estacao ? '<br>pior pluviômetro: ' + zona.estacao : '')
              : '<strong>' + nome + '</strong>';
          }, { sticky: true });
        }
        layer.on('mouseover', function () { destacar(layer); });
        layer.on('mouseout', function () { camadaDistritos.resetStyle(layer); });
        layer.on('click', function () {
          // seleciona e destaca o distrito; clicar de novo no mesmo tira o destaque
          distritoSelecionado = (distritoSelecionado === nome) ? null : nome;
          redesenharDistritos();
        });
      }
    }).addTo(map);
    camadaDistritos = camada;

    // enquadra o mapa nos limites reais dos distritos
    if (camada.getBounds().isValid()) {
      map.fitBounds(camada.getBounds(), { padding: [20, 20] });
    }
  })
  .catch(err => console.error('Erro ao carregar distritos:', err));


// ─── Camada: unidades de saúde (CNES) ───────────────────────
// 410 pontos. circleMarker em vez de marker: não carrega ícone
// por ponto, o que mantém o mapa fluido nesse volume.
const CORES_TIPO = {
  2: '#2563eb',   // UBS
  5: '#dc2626',   // hospital geral
  7: '#dc2626',   // hospital especializado
  4: '#7c3aed',   // policlínica
  20: '#ea580c',  // pronto-socorro geral
  21: '#ea580c',  // pronto-socorro especializado
  73: '#ea580c',  // UPA
  42: '#0d9488',  // SAMU
  40: '#0d9488',  // unidade móvel
  50: '#ca8a04',  // vigilância em saúde
};

const camadaUnidades = L.layerGroup();

fetch('/api/unidades/')
  .then(r => r.json())
  .then(dados => {
    L.geoJSON(dados, {
      pointToLayer: function (feature, latlng) {
        const p = feature.properties;
        return L.circleMarker(latlng, {
          radius: 5,
          fillColor: CORES_TIPO[p.codigo_tipo] || '#64748b',
          color: '#ffffff',
          weight: 1.5,
          fillOpacity: 0.9
        });
      },
      onEachFeature: function (feature, layer) {
        const p = feature.properties;
        layer.bindPopup(
          '<div class="pop">' +
            '<div class="pop-topo"><span class="pop-tag">' + (p.tipo || 'Unidade de saúde') + '</span>' +
            '<div class="pop-titulo">' + (p.nome || 'Sem nome') + '</div></div>' +
            '<ul class="pop-linhas">' +
              (p.bairro && p.bairro !== 'SN' ? linhaPop('Bairro', p.bairro) : '') +
              (p.turno ? linhaPop('Atendimento', p.turno) : '') +
            '</ul></div>'
        );
      }
    }).addTo(camadaUnidades);

    camadaUnidades.addTo(map);

    const total = dados.features.length;
    document.getElementById('contador-unidades').innerText = total ? '(' + total + ')' : '(indisponível)';
    if (!total) document.getElementById('camada-unidades').disabled = true;
  })
  .catch(err => console.error('Erro ao carregar unidades:', err));

// liga/desliga a camada pelo checkbox
document.getElementById('camada-unidades')
  .addEventListener('change', function (e) {
    if (e.target.checked) {
      map.addLayer(camadaUnidades);
    } else {
      map.removeLayer(camadaUnidades);
    }
  });


// ─── Camada: chuva medida por distrito (CEMADEN) ────────────
// O modelo enxerga o Recife em poucas celulas; distritos na mesma
// celula recebem a mesma chuva. Cada zona e um poligono unico com
// um unico valor - em vez de repetir o numero em varios distritos.
function corChuva(mm) {
  if (mm < 1) return '#dbeafe';
  if (mm < 10) return '#93c5fd';
  if (mm < 30) return '#3b82f6';
  if (mm < 50) return '#1d4ed8';
  return '#1e3a8a';
}

const camadaChuva = L.layerGroup();
const zonaDoDistrito = {};

const legendaChuva = L.control({ position: 'bottomright' });
legendaChuva.onAdd = function () {
  const div = L.DomUtil.create('div');
  div.style.cssText = 'background:#fff;padding:8px 10px;border-radius:6px;' +
    'font-size:11px;line-height:1.6;box-shadow:0 1px 3px rgba(0,0,0,.2)';
  const faixas = [[0, '< 1'], [1, '1–10'], [10, '10–30'], [30, '30–50'], [50, '≥ 50']];
  div.innerHTML = '<strong>Chuva 24h (mm)</strong><br>' +
    faixas.map(([v, rotulo]) =>
      '<i style="display:inline-block;width:12px;height:12px;margin-right:6px;' +
      'vertical-align:middle;background:' + corChuva(v + 0.1) + '"></i>' + rotulo
    ).join('<br>') +
    '<br><span style="color:#64748b">Pior pluviômetro do distrito<br>Dados da Rede Observacional<br>do CEMADEN/MCTIC</span>';
  return div;
};

fetch('/api/chuva-distritos/')
  .then(r => r.json())
  .then(dados => {
    L.geoJSON(dados, {
      // nao-interativa: nunca rouba o mouse dos distritos
      interactive: false,
      style: function (feature) {
        return {
          fillColor: feature.properties.chuva_24h_mm === null ? '#e2e8f0' : corChuva(feature.properties.chuva_24h_mm),
          fillOpacity: 0.45,
          color: '#1e3a8a',
          weight: 1.5
        };
      },
      onEachFeature: function (feature, layer) {
        const p = feature.properties;
        p.distritos.forEach(d => { zonaDoDistrito[d.nome] = p; });

        // rotulo fixo dentro da zona: o valor fica visivel mesmo quando
        // todas as zonas caem na mesma faixa de cor. O ponto vem do
        // conector (garantidamente dentro do poligono); sem ele, usa o
        // centro do retangulo envolvente.
        const ponto = p.ponto_rotulo
          ? [p.ponto_rotulo[1], p.ponto_rotulo[0]]
          : layer.getBounds().getCenter();
        const siglas = p.nome.replace('DS ', '');
        L.marker(ponto, {
          interactive: false,
          icon: L.divIcon({
            className: '',
            iconSize: null,
            html: '<div style="transform:translate(-50%,-50%);background:#1e3a8a;color:#fff;' +
                  'padding:3px 8px;border-radius:6px;text-align:center;white-space:nowrap;' +
                  'box-shadow:0 1px 3px rgba(0,0,0,.3);font-family:inherit">' +
                  '<div style="font-size:13px;font-weight:700">' + formatarMm(p.chuva_24h_mm) + '</div>' +
                  '<div style="font-size:10px;opacity:.85">DS ' + siglas + '</div></div>'
          })
        }).addTo(camadaChuva);
      }
    }).addTo(camadaChuva);
  })
  .catch(err => console.error('Erro ao carregar a chuva por distrito:', err));

// pluviômetros: um ponto por estação, com a chuva medida em 24 h
fetch('/api/estacoes-chuva/')
  .then(r => r.json())
  .then(dados => {
    L.geoJSON(dados, {
      pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
        radius: 6, weight: 2, color: '#fff', fillOpacity: 1,
        fillColor: feature.properties.chuva_24h_mm === null ? '#94a3b8' : corChuva(feature.properties.chuva_24h_mm)
      }),
      onEachFeature: (feature, layer) => {
        const p = feature.properties;
        layer.bindTooltip('<strong>' + p.nome + '</strong> (' + p.distrito + ')<br>' +
          formatarMm(p.chuva_24h_mm) + ' em 24h<br><span style="color:#64748b">pluviômetro CEMADEN</span>');
      }
    }).addTo(camadaChuva);
  })
  .catch(err => console.error('Erro ao carregar os pluviômetros:', err));

document.getElementById('camada-chuva')
  .addEventListener('change', function (e) {
    if (e.target.checked) {
      camadaChuva.addTo(map);
      // por baixo dos distritos, para o clique no distrito continuar funcionando
      camadaChuva.eachLayer(l => l.bringToBack && l.bringToBack());
      legendaChuva.addTo(map);
    } else {
      map.removeLayer(camadaChuva);
      legendaChuva.remove();
    }
    // o painel de risco descreve a cor dos distritos, que some com a chuva ligada
    atualizarPainelRisco();
    redesenharDistritos();
  });


// ─── Camada: áreas de risco (Defesa Civil) ──────────────────────
// Fonte: Plano de Contingência 2024 da SEDEC. O plano identifica
// comunidades DENTRO dos bairros: o bairro aparece porque contém
// áreas de risco alto/muito alto, não porque esteja todo em risco.
const CORES_RISCO_AREA = { alagamento: '#0891b2', deslizamento: '#b45309', ambos: '#be123c' };

function corRisco(tipos) {
  return tipos.length > 1 ? CORES_RISCO_AREA.ambos : CORES_RISCO_AREA[tipos[0]];
}

function listaHtml(titulo, itens) {
  if (!itens.length) return '';
  return '<p class="pop-secao">' + titulo + ' <span class="pop-badge">' + itens.length + '</span></p>' +
    '<ul class="pop-lista">' + itens.map(i => '<li>' + i + '</li>').join('') + '</ul>';
}

const camadaRisco = L.layerGroup();

fetch('/api/areas-risco/')
  .then(r => r.json())
  .then(dados => {
    L.geoJSON(dados, {
      style: f => ({
        fillColor: corRisco(f.properties.tipos),
        color: corRisco(f.properties.tipos),
        weight: 1.5,
        fillOpacity: 0.35
      }),
      onEachFeature: function (feature, layer) {
        const p = feature.properties;
        layer.bindTooltip('<strong>' + p.bairro + '</strong><br>' + p.total_areas +
          (p.total_areas === 1 ? ' área' : ' áreas') + ' de risco alto ou muito alto', { sticky: true });
        layer.bindPopup(
          '<div class="pop">' +
            '<div class="pop-topo"><span class="pop-tag">Área de risco</span>' +
            '<div class="pop-titulo">' + p.bairro + '</div></div>' +
            '<p class="pop-meta">Contém áreas de risco alto ou muito alto (R3/R4). ' +
            'O risco está nas áreas listadas, não no bairro inteiro.</p>' +
            listaHtml('Deslizamento', p.deslizamento) +
            listaHtml('Alagamento', p.alagamento) +
            '<p class="pop-nota">' + p.fonte + '</p></div>'
        );
      }
    }).addTo(camadaRisco);
  })
  .catch(err => console.error('Erro ao carregar áreas de risco:', err));

document.getElementById('camada-risco')
  .addEventListener('change', function (e) {
    if (e.target.checked) {
      desligar('camada-arbo');
      desligar('camada-com');
      desligar('camada-vul'); desligar('camada-perfil');
      camadaRisco.addTo(map);
      // por cima dos distritos, para o clique abrir o detalhe do bairro...
      camadaRisco.eachLayer(l => l.bringToFront && l.bringToFront());
      // ...mas por baixo das unidades de saúde, que continuam clicáveis
      if (map.hasLayer(camadaUnidades)) {
        camadaUnidades.eachLayer(l => l.bringToFront && l.bringToFront());
      }
    } else {
      map.removeLayer(camadaRisco);
    }
    document.getElementById('legenda-risco').classList.toggle('hidden', !e.target.checked);
    atualizarPainelRisco();
    redesenharDistritos();
  });


// ─── Camada: arboviroses por bairro (SINAN, histórico anual) ────
// Incidência = casos prováveis (notificados exceto descartados) por
// 10 mil habitantes, com a população do Censo 2022. O arquivo mais
// recente da prefeitura é anual; a semana atual vem do InfoDengue.
const CORES_ARBO = ['#ffffb2', '#fecc5c', '#fd8d3c', '#f03b20', '#bd0026'];
const camadaArbo = L.layerGroup();
let quebrasArbo = [];

const fmt1 = v => v.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

// quebras por quantis: cada cor reúne ~1/5 dos bairros. Valores de
// incidência variam muito de um ano para outro (epidemias), então
// quebras fixas deixariam anos inteiros de uma cor só.
function calcularQuebras(valores) {
  const v = valores.filter(x => x !== null).sort((a, b) => a - b);
  if (!v.length || v[0] === v[v.length - 1]) return [];
  const q = [0.2, 0.4, 0.6, 0.8].map(p => v[Math.floor(p * (v.length - 1))]);
  return [...new Set(q)];
}

function corArbo(valor) {
  if (valor === null) return '#e2e8f0';
  let i = 0;
  while (i < quebrasArbo.length && valor > quebrasArbo[i]) i++;
  return CORES_ARBO[Math.min(i, CORES_ARBO.length - 1)];
}

function desenharLegendaArbo(maximo) {
  const limites = [0, ...quebrasArbo, maximo];
  const div = document.getElementById('legenda-arbo');
  if (limites.length < 2 || maximo === 0) {
    div.innerHTML = '<p>Nenhum caso provável no período selecionado.</p>';
    return;
  }
  div.innerHTML = limites.slice(0, -1).map((ini, i) =>
    '<div class="flex items-center gap-2"><i class="inline-block size-3 rounded-sm" style="background:' +
    CORES_ARBO[i] + '"></i> ' + fmt1(ini) + ' a ' + fmt1(limites[i + 1]) + '</div>'
  ).join('');
}

function carregarArbo() {
  const ano = document.getElementById('arbo-ano').value;
  const doenca = document.getElementById('arbo-doenca').value;
  const params = new URLSearchParams({ doenca });
  if (ano) params.set('ano', ano);

  fetch('/api/arboviroses-bairros/?' + params)
    .then(r => r.json())
    .then(dados => {
      // preenche a lista de anos na primeira carga
      const seletor = document.getElementById('arbo-ano');
      if (!seletor.options.length && dados.anos) {
        dados.anos.slice().reverse().forEach(a => seletor.add(new Option(a, a)));
        seletor.value = dados.ano;
      }

      const valores = dados.features.map(f => f.properties.incidencia_10k);
      quebrasArbo = calcularQuebras(valores);
      desenharLegendaArbo(Math.max(0, ...valores.filter(x => x !== null)));

      camadaArbo.clearLayers();
      L.geoJSON(dados, {
        style: f => ({
          fillColor: corArbo(f.properties.incidencia_10k),
          color: '#7c2d12', weight: 0.8, fillOpacity: 0.7
        }),
        onEachFeature: function (feature, layer) {
          const p = feature.properties;
          const nomes = { dengue: 'Dengue', chikungunya: 'Chikungunya', zika: 'Zika' };
          const linhas = Object.entries(p.por_doenca)
            .map(([d, n]) => linhaPop(nomes[d], n.toLocaleString('pt-BR'))).join('');
          layer.bindTooltip('<strong>' + p.bairro + '</strong><br>' +
            (p.incidencia_10k === null ? 'sem dado' : fmt1(p.incidencia_10k) + ' por 10 mil hab.'), { sticky: true });
          layer.bindPopup(
            '<div class="pop">' +
              '<div class="pop-topo"><span class="pop-tag">' +
              '<i class="pop-chip" style="background:' + corArbo(p.incidencia_10k) + '"></i>Arboviroses · ' + dados.ano + '</span>' +
              '<div class="pop-titulo">' + p.bairro + '</div></div>' +
              '<div class="pop-destaque"><span class="pop-num">' +
              (p.incidencia_10k === null ? '--' : fmt1(p.incidencia_10k)) +
              '</span><span class="pop-un">por 10 mil hab.</span></div>' +
              '<p class="pop-meta">' + p.provaveis.toLocaleString('pt-BR') + ' casos prováveis · ' +
              p.populacao.toLocaleString('pt-BR') + ' habitantes</p>' +
              '<ul class="pop-linhas">' + linhas + '</ul>' +
              '<p class="pop-nota">Casos prováveis = notificados exceto descartados, por bairro de residência. ' +
              dados.fonte + '.</p></div>'
          );
        }
      }).addTo(camadaArbo);

      if (map.hasLayer(camadaArbo)) {
        camadaArbo.eachLayer(l => l.bringToFront && l.bringToFront());
        if (map.hasLayer(camadaUnidades)) camadaUnidades.eachLayer(l => l.bringToFront && l.bringToFront());
      }
    })
    .catch(err => console.error('Erro ao carregar arboviroses:', err));
}

document.getElementById('camada-arbo')
  .addEventListener('change', function (e) {
    if (e.target.checked) {
      desligar('camada-risco');
      desligar('camada-com');
      desligar('camada-vul'); desligar('camada-perfil');
      camadaArbo.addTo(map);
      carregarArbo();
    } else {
      map.removeLayer(camadaArbo);
    }
    document.getElementById('controles-arbo').classList.toggle('hidden', !e.target.checked);
    atualizarPainelRisco();
    redesenharDistritos();
  });
document.getElementById('arbo-ano').addEventListener('change', carregarArbo);
document.getElementById('arbo-doenca').addEventListener('change', carregarArbo);

// ─── Card: arboviroses agora (InfoDengue, município) ────────────
const CORES_NIVEL = { 1: ['#dcfce7', '#166534'], 2: ['#fef9c3', '#854d0e'], 3: ['#ffedd5', '#9a3412'], 4: ['#fee2e2', '#991b1b'] };
fetch('/api/arboviroses-resumo/')
  .then(r => r.json())
  .then(({ resumo }) => {
    if (!resumo) return;
    const dm = s => s.slice(8, 10) + '/' + s.slice(5, 7);
    document.getElementById('info-estimados').innerText = resumo.estimados.toLocaleString('pt-BR');
    document.getElementById('info-faixa').innerText =
      'entre ' + resumo.estimados_min + ' e ' + resumo.estimados_max + ' · ' + resumo.notificados + ' já notificados';
    const nivel = document.getElementById('info-nivel');
    const [fundo, texto] = CORES_NIVEL[resumo.nivel] || ['#f1f5f9', '#334155'];
    nivel.innerText = resumo.nivel_nome;
    nivel.style.background = fundo; nivel.style.color = texto;
    nivel.title = resumo.nivel_texto;
    document.getElementById('info-semana').innerText =
      'SE ' + resumo.semana + ' · ' + dm(resumo.inicio) + ' a ' + dm(resumo.fim);
    document.getElementById('card-infodengue').classList.remove('hidden');
  })
  .catch(err => console.error('Erro ao carregar o resumo do InfoDengue:', err));


// ─── Rede de apoio: abrigos, escolas e CRAS ─────────────────────
// L.marker com divIcon vive no markerPane, acima de todos os
// polígonos: nenhuma combinação de camadas esconde um abrigo.
const REDE = {
  abrigo: { rotulo: 'Abrigo', html: '<div style="width:18px;height:18px;border-radius:3px;background:#15803d;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4);color:#fff;font:700 10px/14px sans-serif;text-align:center">A</div>', tamanho: 18 },
  escola: { rotulo: 'Escola municipal', html: '<div style="width:10px;height:10px;border-radius:50%;background:#1e40af;border:1.5px solid #fff;box-shadow:0 1px 2px rgba(0,0,0,.4)"></div>', tamanho: 10 },
  cras:   { rotulo: 'CRAS', html: '<div style="width:10px;height:10px;transform:rotate(45deg);background:#ea580c;border:1.5px solid #fff;box-shadow:0 1px 2px rgba(0,0,0,.4)"></div>', tamanho: 10 }
};
const camadasRede = { abrigo: L.layerGroup(), escola: L.layerGroup(), cras: L.layerGroup() };

function popupRede(p) {
  const linhas = Object.entries(p.detalhe || {})
    .filter(([k]) => !['CODESCOLA', 'CEP'].includes(k))
    .map(([k, v]) => linhaPop(k.replaceAll('_', ' ').toLowerCase(), v)).join('');
  const local = [p.endereco, p.bairro].filter(Boolean).join(' · ');
  return '<div class="pop">' +
    '<div class="pop-topo"><span class="pop-tag">' + REDE[p.tipo].rotulo + '</span>' +
    '<div class="pop-titulo">' + p.nome + '</div></div>' +
    (local ? '<p class="pop-meta">' + local + '</p>' : '') +
    (linhas ? '<ul class="pop-linhas">' + linhas + '</ul>' : '') +
    (p.tipo === 'abrigo' ? '<p class="pop-aviso">Cadastro: não indica se está aberto nem a capacidade.</p>' : '') +
    '<p class="pop-nota">' + p.fonte + '</p></div>';
}

fetch('/api/rede-apoio/')
  .then(r => r.json())
  .then(dados => {
    const contagem = { abrigo: 0, escola: 0, cras: 0 };
    dados.features.forEach(f => {
      const p = f.properties, cfg = REDE[p.tipo];
      if (!cfg) return;
      const [lon, lat] = f.geometry.coordinates;
      L.marker([lat, lon], {
        icon: L.divIcon({ className: '', html: cfg.html, iconSize: [cfg.tamanho, cfg.tamanho], iconAnchor: [cfg.tamanho / 2, cfg.tamanho / 2] }),
        title: p.nome,
        zIndexOffset: p.tipo === 'abrigo' ? 1000 : 0  // abrigo por cima das escolas
      }).bindPopup(popupRede(p)).addTo(camadasRede[p.tipo]);
      contagem[p.tipo]++;
    });
    Object.entries(contagem).forEach(([tipo, n]) => {
      document.getElementById('contador-' + tipo).innerText = n ? '(' + n + ')' : '(indisponível)';
      if (!n) { const c = document.getElementById('camada-' + tipo); c.checked = false; c.disabled = true; }
      if (document.getElementById('camada-' + tipo).checked) camadasRede[tipo].addTo(map);
    });
  })
  .catch(err => console.error('Erro ao carregar a rede de apoio:', err));

Object.keys(camadasRede).forEach(tipo => {
  document.getElementById('camada-' + tipo).addEventListener('change', e => {
    if (e.target.checked) camadasRede[tipo].addTo(map); else map.removeLayer(camadasRede[tipo]);
  });
});


// ─── Camada: comunidades de interesse social (2014) ─────────────
const CORES_COM = ['#fff7bc', '#fee391', '#fec44f', '#ec7014', '#993404'];
const NOMES_IND = { IND_ALAGAM: 'alagamento', DENS_ESCOR: 'deslizamento', DRENAGEM: 'drenagem (deficiência)',
  PAVIMENTAC: 'pavimentação (deficiência)', ESGOTAMENT: 'esgotamento', COLETA_LIX: 'coleta de lixo',
  Indice_COM: 'índice composto' };
const camadaCom = L.layerGroup();
let quebrasCom = [];

function comLigado() { return document.getElementById('camada-com').checked; }

// zero = sem indicação; as cores dividem só as comunidades com nota
function corCom(v) {
  if (v === null || v === undefined) return '#e2e8f0';
  if (v <= 0) return '#f8fafc';
  let i = 0;
  while (i < quebrasCom.length && v > quebrasCom[i]) i++;
  return CORES_COM[Math.min(i, CORES_COM.length - 1)];
}

function carregarCom() {
  const ind = document.getElementById('com-indicador').value;
  fetch('/api/comunidades/?indicador=' + ind).then(r => r.json()).then(dados => {
    const positivos = dados.features.map(f => f.properties.valor).filter(v => v > 0);
    quebrasCom = calcularQuebras(positivos);
    const limites = [0, ...quebrasCom, Math.max(0, ...positivos)];
    document.getElementById('legenda-com').innerHTML =
      '<div class="flex items-center gap-2"><i class="inline-block size-3 rounded-sm border border-slate-300" style="background:#f8fafc"></i> 0 (sem indicação)</div>' +
      limites.slice(0, -1).map((ini, i) => '<div class="flex items-center gap-2"><i class="inline-block size-3 rounded-sm" style="background:' +
        CORES_COM[i] + '"></i> ' + fmt1(ini) + ' a ' + fmt1(limites[i + 1]) + '</div>').join('');
    camadaCom.clearLayers();
    L.geoJSON(dados, {
      style: f => ({ fillColor: corCom(f.properties.valor), color: '#78350f', weight: 0.6, fillOpacity: 0.75 }),
      onEachFeature: (f, layer) => {
        const p = f.properties;
        const linhas = Object.entries(NOMES_IND).filter(([k]) => p.indicadores[k] !== null && p.indicadores[k] !== undefined)
          .map(([k, n]) => linhaPop(n, fmt1(p.indicadores[k]))).join('');
        layer.bindTooltip('<strong>' + p.nome + '</strong><br>' + (p.valor === null ? 'sem dado' : fmt1(p.valor) + ' de 10'), { sticky: true });
        layer.bindPopup(
          '<div class="pop">' +
            '<div class="pop-topo"><span class="pop-tag">Comunidade</span>' +
            '<div class="pop-titulo">' + p.nome + '</div></div>' +
            '<p class="pop-meta">' + p.bairro + (p.populacao_2014 ? ' · ' + p.populacao_2014.toLocaleString('pt-BR') + ' hab. (2014)' : '') + '</p>' +
            (p.precariedade ? '<p class="pop-meta">' + p.precariedade + '</p>' : '') +
            '<ul class="pop-linhas">' + linhas + '</ul>' +
            '<p class="pop-nota">Notas de 0 a 10, maior = pior. Levantamento de 2014: retrato da estrutura, não da população atual.</p></div>'
        );
      }
    }).addTo(camadaCom);
    if (map.hasLayer(camadaCom) && map.hasLayer(camadaUnidades)) {
      camadaUnidades.eachLayer(l => l.bringToFront && l.bringToFront());
    }
  }).catch(err => console.error('Erro ao carregar comunidades:', err));
}

document.getElementById('camada-com').addEventListener('change', e => {
  if (e.target.checked) { desligar('camada-risco'); desligar('camada-arbo'); desligar('camada-vul'); desligar('camada-perfil'); camadaCom.addTo(map); carregarCom(); }
  else map.removeLayer(camadaCom);
  document.getElementById('controles-com').classList.toggle('hidden', !e.target.checked);
  atualizarPainelRisco();
  redesenharDistritos();
});
document.getElementById('com-indicador').addEventListener('change', carregarCom);

// ─── Camada: índice de vulnerabilidade por bairro (etapa 4b) ─────────
const camadaVul = L.layerGroup();
const CORES_VUL = ['#f1eef6', '#d7b5d8', '#df65b0', '#dd1c77', '#980043'];
const NOMES_VUL = { indice: 'Geral', indice_estrutural: 'Estrutural', indice_historico: 'Histórico' };

function vulLigado() { return document.getElementById('camada-vul').checked; }

function corVul(v) {
  if (v === null || v === undefined) return '#e2e8f0';
  return CORES_VUL[Math.min(Math.floor(v * CORES_VUL.length), CORES_VUL.length - 1)];
}

function carregarVul() {
  const campo = document.getElementById('vul-indice').value;
  fetch('/api/vulnerabilidade/').then(r => r.json()).then(dados => {
    document.getElementById('legenda-vul').innerHTML = CORES_VUL.map((c, i) =>
      '<div class="flex items-center gap-2"><i class="inline-block size-3 rounded-sm" style="background:' + c + '"></i> ' +
      fmt1(i / CORES_VUL.length) + ' a ' + fmt1((i + 1) / CORES_VUL.length) + '</div>').join('');
    camadaVul.clearLayers();
    L.geoJSON(dados, {
      style: f => ({ fillColor: corVul(f.properties[campo]), color: '#701a75', weight: 0.6, fillOpacity: 0.75 }),
      onEachFeature: (f, layer) => {
        const p = f.properties;
        const v = p[campo];
        layer.bindTooltip('<strong>' + p.nome + '</strong><br>' + NOMES_VUL[campo] + ': ' +
          (v === null || v === undefined ? 'sem dado' : fmt1(v)) + (p.posicao ? ' · ' + p.posicao + 'º de 94' : ''), { sticky: true });
        layer.bindPopup(
          '<div class="pop">' +
            '<div class="pop-topo"><span class="pop-tag">Vulnerabilidade</span>' +
            '<div class="pop-titulo">' + p.nome + '</div></div>' +
            '<p class="pop-meta">' + (p.posicao ? p.posicao + 'º mais vulnerável de 94 · classe ' + p.classe : 'sem índice') + '</p>' +
            '<ul class="pop-linhas">' +
              linhaPop('População em comunidades', p.pct_pop_comunidades === null ? 'sem dado' : Math.round(p.pct_pop_comunidades * 100) + '%') +
              linhaPop('Risco médio das comunidades', p.risco_comunidades == null ? 'sem dado' : fmt1(p.risco_comunidades) + ' de 10') +
              linhaPop('Áreas de risco (Plano 2024)', p.areas_risco) +
              linhaPop('Atendimentos por 10 mil hab. em dia de chuva forte',
                p.atendimentos_10k_por_dia_forte === null ? 'sem dado' : fmt1(p.atendimentos_10k_por_dia_forte)) +
            '</ul>' +
            '<p class="pop-nota">Índice relativo entre os bairros do Recife (0 a 1). ' +
            'Estrutural: cadastros. Histórico: Defesa Civil 2015-2024.</p></div>'
        );
      }
    }).addTo(camadaVul);
    if (map.hasLayer(camadaUnidades)) camadaUnidades.eachLayer(l => l.bringToFront && l.bringToFront());
  }).catch(err => console.error('Erro ao carregar a vulnerabilidade:', err));
}

document.getElementById('camada-vul').addEventListener('change', e => {
  if (e.target.checked) { desligar('camada-risco'); desligar('camada-arbo'); desligar('camada-com'); desligar('camada-perfil'); camadaVul.addTo(map); carregarVul(); }
  else map.removeLayer(camadaVul);
  document.getElementById('controles-vul').classList.toggle('hidden', !e.target.checked);
  atualizarPainelRisco();
  redesenharDistritos();
});
document.getElementById('vul-indice').addEventListener('change', carregarVul);

// ─── Camada: perfis de risco dos bairros (agrupamento K-means) ───────
const camadaPerfil = L.layerGroup();
const CORES_PERFIL = ['#b45309', '#0369a1', '#7c3aed', '#be123c', '#15803d', '#64748b'];

function perfilLigado() { return document.getElementById('camada-perfil').checked; }

function carregarPerfil() {
  fetch('/api/perfis/').then(r => r.json()).then(dados => {
    const nomes = [...new Set(dados.features.map(f => f.properties.perfil))].sort();
    const cor = nome => nome.startsWith('baixo risco') ? '#cbd5e1' : CORES_PERFIL[nomes.indexOf(nome) % CORES_PERFIL.length];
    document.getElementById('legenda-perfil').innerHTML = nomes.map(n =>
      '<div class="flex items-center gap-2"><i class="inline-block size-3 rounded-sm" style="background:' + cor(n) + '"></i> ' + n +
      ' (' + dados.features.filter(f => f.properties.perfil === n).length + ')</div>').join('') +
      '<p class="text-slate-400">Bairros agrupados pelo tipo de risco: atendimentos, eventos e cadastros.</p>';
    camadaPerfil.clearLayers();
    L.geoJSON(dados, {
      style: f => ({ fillColor: cor(f.properties.perfil), color: '#334155', weight: 0.6, fillOpacity: 0.7 }),
      onEachFeature: (f, layer) => layer.bindTooltip('<strong>' + f.properties.nome + '</strong><br>' + f.properties.perfil, { sticky: true })
    }).addTo(camadaPerfil);
  }).catch(err => console.error('Erro ao carregar os perfis:', err));
}

document.getElementById('camada-perfil').addEventListener('change', e => {
  if (e.target.checked) { desligar('camada-risco'); desligar('camada-arbo'); desligar('camada-com'); desligar('camada-vul'); camadaPerfil.addTo(map); carregarPerfil(); }
  else map.removeLayer(camadaPerfil);
  document.getElementById('legenda-perfil').classList.toggle('hidden', !e.target.checked);
  atualizarPainelRisco();
  redesenharDistritos();
});

// ─── Resumo das camadas ativas + botão "Limpar" (só interface) ───────
const CAMADAS_TEMATICAS = {
  'camada-chuva': 'Chuva', 'camada-risco': 'Áreas de risco', 'camada-com': 'Comunidades',
  'camada-vul': 'Vulnerabilidade', 'camada-perfil': 'Perfis', 'camada-arbo': 'Arboviroses'
};

function atualizarResumoCamadas() {
  const ativas = Object.entries(CAMADAS_TEMATICAS)
    .filter(([id]) => document.getElementById(id).checked)
    .map(([, nome]) => nome);
  document.getElementById('resumo-camadas').textContent =
    ativas.length ? ativas.join(' + ') : 'Nenhuma camada temática ligada';
  document.getElementById('limpar-camadas').classList.toggle('hidden', !ativas.length);
}

Object.keys(CAMADAS_TEMATICAS).forEach(id =>
  document.getElementById(id).addEventListener('change', atualizarResumoCamadas));
document.getElementById('limpar-camadas').addEventListener('click', () =>
  Object.keys(CAMADAS_TEMATICAS).forEach(id => desligar(id)));
atualizarResumoCamadas();
