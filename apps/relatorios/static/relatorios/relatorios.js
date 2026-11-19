// ============================================================================
// MÓDULO DE RELATÓRIOS: Utilitários de Data
// ============================================================================

/**
 * Retorna a data de hoje no formato "AAAA-MM-DD" (Local, não UTC).
 */
function getToday() {
  const hoje = new Date();
  const ano = hoje.getFullYear();
  const mes = String(hoje.getMonth() + 1).padStart(2, '0'); // Mês começa em 0
  const dia = String(hoje.getDate()).padStart(2, '0');

  return `${ano}-${mes}-${dia}`;
}

/**
 * Converte uma data "AAAA-MM-DD" para o formato brasileiro "DD/MM/AAAA".
 * (Separar a string evita o bug clássico de fuso horário do JS).
 */
function formatDate(isoDate) {
  const [ano, mes, dia] = isoDate.split('-');
  return `${dia}/${mes}/${ano}`;
}


// ============================================================================
// MÓDULO DE RELATÓRIOS: Geração e Pré-visualização
// ============================================================================

/**
 * Manipula a submissão do formulário: valida datas e monta a interface.
 */
function generateReport(e) {
  e.preventDefault();

  // 1. Captura os valores dos campos
  const inputStart = document.getElementById('report-start').value;
  const inputEnd = document.getElementById('report-end').value;
  const inputDistrict = document.getElementById('report-district').value;

  // 2. Validações de preenchimento e coerência
  if (!inputStart || !inputEnd) {
    return alert('Preencha a data inicial e a data final.');
  }

  if (inputStart > inputEnd) {
    return alert('A data inicial não pode ser maior que a data final.');
  }

  const hoje = getToday();
  if (inputStart > hoje || inputEnd > hoje) {
    return alert('As datas não podem ser posteriores à data de hoje.');
  }

  // 3. Atualiza o subtítulo com o período e local
  const subtitulo = document.getElementById('preview-subtitle');
  subtitulo.innerText = `${formatDate(inputStart)} a ${formatDate(inputEnd)} · ${inputDistrict}`;

  // 4. Monta a lista de opções selecionadas de forma limpa (sem múltiplos appendChild)
  const opcoesSelecionadas = Array.from(document.querySelectorAll('.report-option:checked'));
  const containerLista = document.getElementById('selected-list');
  
  containerLista.innerHTML = opcoesSelecionadas.map(opcao => `
    <li class="flex items-center gap-2 text-slate-700">
      <i data-lucide="check-circle-2" class="w-4 h-4 text-green-600"></i> 
      ${opcao.value}
    </li>
  `).join('');

  // 5. Alterna a visibilidade dos blocos (Esconde o aviso vazio -> Mostra preview)
  document.getElementById('empty-preview').classList.add('hidden');
  document.getElementById('generated-preview').classList.remove('hidden');

  // 6. Recarrega os ícones dinâmicos injetados no HTML
  lucide.createIcons();
}


// ============================================================================
// INICIALIZAÇÃO: Travas e Limites do Calendário
// ============================================================================

const startInput = document.getElementById('report-start');
const endInput = document.getElementById('report-end');
const today = getToday();

if (startInput && endInput) {
  // Impede a seleção de datas no futuro
  startInput.max = today;
  endInput.max = today;

  // Ao alterar a data inicial, a data final nunca pode ser anterior a ela
  startInput.addEventListener('change', () => {
    endInput.min = startInput.value;
  });
}
