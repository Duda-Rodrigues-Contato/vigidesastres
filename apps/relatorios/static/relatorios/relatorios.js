// Tela: relatorios/relatorios.html
// Dados do servidor chegam pelo json_script do template (o Django escapa o conteúdo).

function getToday() {
  // Monta "aaaa-mm-dd" com a data LOCAL (não UTC)
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0'); // Mês começa em 0
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}


function formatDate(isoDate) {
  // "2026-08-20" -> "20/08/2026"
  // Não usa new Date() para evitar bug de fuso horário (data aparecer 1 dia antes)
  const [year, month, day] = isoDate.split('-');
  return `${day}/${month}/${year}`;
}


function generateReport(e) {
  e.preventDefault();

  const start = document.getElementById('report-start').value;
  const end = document.getElementById('report-end').value;
  const district = document.getElementById('report-district').value;

  // ValidaçÕes
  if (!start || !end) {
    alert('Preenhca a data inicial e a data final.');
    return;
  }

  if (start > end) {
    alert('A data inicial não pode ser maior que a data final.');
    return;
  }

  if (start > getToday() || end > getToday()) {
    alert('As datas não podem ser posteriores à data de hoje.');
    return;
  }

  document.getElementById('preview-subtitle').innerText = `${formatDate(start)} a ${formatDate(end)} · ${district}`;

  const checkboxes = document.querySelectorAll('.report-option:checked');
  const listContainer = document.getElementById('selected-list');
  listContainer.innerHTML = '';

  checkboxes.forEach(cb => {
    const li = document.createElement('li');
    li.className = 'flex items-center gap-2 text-slate-700';
    li.innerHTML = `<i data-lucide="check-circle-2" class="w-4 h-4 text-green-600"></i> ${cb.value}`;
    listContainer.appendChild(li);
  });

  document.getElementById('empty-preview').classList.add('hidden');
  document.getElementById('generated-preview').classList.remove('hidden');

  lucide.createIcons();
}

const startInput = document.getElementById('report-start');
const endInput = document.getElementById('report-end');
const today = getToday();

startInput.max = today;
endInput.max = today;

// Opcional: a data final nunca pode ser anterior à inicial
startInput.addEventListener('change', () => {
  endInput.min = startInput.value;
});
