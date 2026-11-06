// Tela: alertas/acoes.html
// Dados do servidor chegam pelo json_script do template (o Django escapa o conteúdo).

function getToday() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}


function formatDate(isoDate) {
  const [year, month, day] = isoDate.split('-');
  return `${day}/${month}/${year}`;
}

// Concluída -> não aceita data futura | Em andamento -> sem limite
function updateDateLimit() {
  const status = document.getElementById('action-status-input').value;
  const dateInput = document.getElementById('action-date-input');

  if (status === 'Concluída') {
    dateInput.max = getToday();
  } else {
    dateInput.removeAttribute('max');
  }
}


document.getElementById('action-status-input').addEventListener('change', updateDateLimit);
updateDateLimit();


let actionsList = JSON.parse(document.getElementById('dados-acoes').textContent);

let currentFilter = 'Todos';

function renderActions() {
  const tbody = document.getElementById('actions-table-body');
  tbody.innerHTML = '';

  const filtered = currentFilter === 'Todos'
    ? actionsList
    : actionsList.filter(a => a.status === currentFilter);

  filtered.forEach(action => {
    const tr = document.createElement('tr');
    const badgeStyle = action.status === 'Em andamento' ? 'bg-blue-100 text-blue-800' : 'bg-green-100 text-green-800';

    tr.innerHTML = `
          <td class="px-5 py-4 font-semibold text-slate-900">${action.name}</td>
          <td class="px-5 py-4 text-slate-500">${action.team}</td>
          <td class="px-5 py-4 text-slate-900">${action.district}</td>
          <td class="px-5 py-4 text-slate-500">${action.date}</td>
          <td class="px-5 py-4"><span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${badgeStyle}">${action.status}</span></td>
        `;
    tbody.appendChild(tr);
  });
}

function setFilter(filter) {
  currentFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.className = 'filter-btn rounded px-3 py-1 text-xs font-semibold text-slate-600 hover:text-slate-900';
  });

  const activeBtn = document.getElementById(`filter-${filter}`);
  if (activeBtn) activeBtn.className = 'filter-btn rounded px-3 py-1 text-xs font-semibold bg-blue-600 text-white';

  renderActions();
}

function toggleModal(show) {
  const modal = document.getElementById('action-modal');
  if (show) modal.classList.remove('hidden');
  else modal.classList.add('hidden');
}

function submitNewAction(e) {
  e.preventDefault();
  const name = document.getElementById('action-name-input').value.trim();
  const team = document.getElementById('action-team-input').value.trim() || 'Equipe designada';
  const district = document.getElementById('action-district-input').value;
  const date = document.getElementById('action-date-input').value;
  const status = document.getElementById('action-status-input').value;

  if (!name || !date) return;

  // Validação extra: o max não barra datas digitadas à mão
  // nem o caso de trocar o status para Concluída depois de escolher uma data futura
  if (status === 'Concluída' && date > getToday()) {
    alert('Uma ação concluída não pode ter data posterior a hoje.');
    return;
  }

  const csrf = document.cookie.split('; ').find(c => c.startsWith('csrftoken='))?.split('=')[1] || '';
  fetch('/api/acoes/', {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
    body: JSON.stringify({name, team, district, date, status})
  }).then(async r => {
    const dados = await r.json();
    if (!r.ok) { alert(dados.erro || 'Não foi possível salvar a ação.'); return; }
    actionsList.unshift(dados);
    e.target.reset();
    updateDateLimit();
    toggleModal(false);
    renderActions();
  });

  e.target.reset();
  updateDateLimit();
  toggleModal(false);
  renderActions();

}

lucide.createIcons();
renderActions();
