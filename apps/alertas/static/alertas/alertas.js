// Tela: alertas/alertas.html
// Dados do servidor chegam pelo json_script do template (o Django escapa o conteúdo).

const alertsData = JSON.parse(document.getElementById('dados-alertas').textContent);

function renderTable(items) {
  const tbody = document.getElementById('alerts-table-body');
  const noResults = document.getElementById('no-results');
  tbody.innerHTML = '';

  if (items.length === 0) {
    noResults.classList.remove('hidden');
    return;
  }
  noResults.classList.add('hidden');

  items.forEach(alert => {
    const tr = document.createElement('tr');
    tr.className = "hover:bg-slate-50 transition-colors";

    const sevBadge = alert.severity === 'ALTO' ? 'bg-red-100 text-red-800' : alert.severity === 'MÉDIO' ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800';
    const stBadge = alert.status === 'Em aberto' ? 'bg-red-100 text-red-800' : alert.status === 'Monitorando' ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-700';

    tr.innerHTML = `
      <td class="px-5 py-4"><span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${sevBadge}">${alert.severity}</span></td>
      <td class="px-5 py-4 font-semibold text-slate-900">${alert.title}</td>
      <td class="px-5 py-4 text-slate-500">${alert.type}</td>
      <td class="px-5 py-4 text-slate-900">${alert.area}</td>
      <td class="px-5 py-4 text-slate-500">${alert.date}</td>
      <td class="px-5 py-4 text-slate-500">${alert.time}</td>
      <td class="px-5 py-4"><span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${stBadge}">${alert.status}</span></td>
      <td class="px-5 py-4">
        <select onchange="mudarStatus(${alert.id}, this.value)" class="rounded border border-slate-300 bg-white px-2 py-1 text-xs">
          <option value="">Mudar status…</option>
          <option value="aberto">Em aberto</option>
          <option value="monitorando">Monitorando</option>
          <option value="encerrado">Encerrado</option>
        </select>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function filterAlerts() {
  const search = document.getElementById('search-input').value.toLowerCase();
  const type = document.getElementById('type-filter').value;
  const district = document.getElementById('district-filter').value;

  const filtered = alertsData.filter(a => {
    const matchesSearch = `${a.title} ${a.area}`.toLowerCase().includes(search);
    const matchesType = type === 'Todos' || a.type === type;
    const matchesDistrict = district === 'Todos' || a.area === district;
    return matchesSearch && matchesType && matchesDistrict;
  });

  renderTable(filtered);
}

function csrf() {
  return document.cookie.split('; ').find(c => c.startsWith('csrftoken='))?.split('=')[1] || '';
}

async function mudarStatus(id, status) {
  if (!status) return;
  const r = await fetch(`/api/alertas/${id}/status/`, {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
    body: JSON.stringify({status})
  });
  if (r.ok) location.reload();
  else alert('Não foi possível mudar o status.');
}

lucide.createIcons();
renderTable(alertsData);
