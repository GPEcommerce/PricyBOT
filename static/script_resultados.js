const originalFullData = typeof fullData !== 'undefined' ? [...fullData] : []; 
let activeData = typeof fullData !== 'undefined' ? [...fullData] : []; 
let currentDisplayData = [...activeData];
let sortState = {
    columnKey: null,
    direction: 'asc'
};

// --- FUNÇÕES DE LÓGICA ---

/**
 * Renderiza as linhas da tabela com base nos dados fornecidos.
 * @param {Array} data - O array de objetos de produto a ser renderizado.
 */
function renderTable(data) {
    const tableBody = document.querySelector("#tabela-resultados tbody");
    if (!tableBody) return;
    tableBody.innerHTML = ''; 
    currentDisplayData = data; // Atualiza os dados que estão na tela

    data.forEach(produto => {
        const row = document.createElement('tr');
        const linkIdentifier = produto['Link do anuncio'] || produto['link'] || '';
        row.setAttribute('data-link-id', linkIdentifier);

        let rowHTML = `<td class="col-checkbox" style="text-align: center;"><input type="checkbox" class="checkbox-item"></td>`;
        allHeaders.forEach(header => {
            const headerClass = 'col-' + header.replace(/[\s()]/g, '-').toLowerCase();
            let value = produto[header] !== undefined && produto[header] !== null ? produto[header] : '';
            let cellContent = value;

            if (header === 'Foto' && String(value).includes('IMAGEM')) {
                try {
                    const urlMatch = String(value).match(/IMAGEM\("([^"]+)"\)/);
                    if (urlMatch && urlMatch[1]) cellContent = `<img src="${urlMatch[1]}" alt="Imagem">`;
                    else cellContent = 'URL inválida';
                } catch { cellContent = 'Erro na imagem'; }
            } else if (header === 'Link do anuncio' || header === 'link') {
                cellContent = `<a href="${value}" target="_blank">Abrir Anúncio</a>`;
            } else if (['Preço anunciado', 'preco_anunciado', 'nosso_preco', 'diferenca_reais', 'Quantidade de vendas', 'vendas', 'Giro'].includes(header)) {
                const numValue = parseNumericValue(value);
                if (['Preço anunciado', 'preco_anunciado', 'nosso_preco', 'diferenca_reais'].includes(header)) {
                    cellContent = isNaN(numValue) ? 'N/A' : numValue.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
                } else {
                    cellContent = isNaN(numValue) ? 'N/A' : numValue.toLocaleString('pt-BR');
                }
            }
            rowHTML += `<td class="${headerClass}">${cellContent}</td>`;
        });
        row.innerHTML = rowHTML;
        tableBody.appendChild(row);
    });
    toggleColumnVisibility(); 
    updateSortIndicators();
}

/**
 * Converte uma string (ex: "R$ 1.234,56") para um número float.
 * @param {*} value - O valor a ser convertido.
 */
function parseNumericValue(value) {
    if (typeof value !== 'string') return parseFloat(value) || 0;
    return parseFloat(value.replace(/R\$\s?/, '').replace(/\./g, '').replace(',', '.')) || 0;
}


/**
 * Mostra ou oculta colunas da tabela com base nos checkboxes do modal.
 */
function toggleColumnVisibility() {
    const checkboxes = document.querySelectorAll('#modal-columns-body input[type="checkbox"]');
    checkboxes.forEach(chk => {
        const headerClass = 'col-' + chk.value.replace(/[\s()]/g, '-').toLowerCase();
        const cells = document.querySelectorAll(`.${headerClass}`);
        cells.forEach(cell => {
            cell.style.display = chk.checked ? '' : 'none';
        });
    });
}

/**
 * Converte os dados para o formato CSV e inicia o download.
 */
function exportToCSV(data, selectedHeaders) {
    if (!data || data.length === 0) { alert("Não há dados para exportar."); return; }
    const headerRow = selectedHeaders.join(',');
    const bodyRows = data.map(item => {
        return selectedHeaders.map(header => {
            let value = item[header] !== undefined && item[header] !== null ? String(item[header]) : '';
            return `"${value.replace(/"/g, '""')}"`;
        }).join(',');
    });
    const csvContent = ["\uFEFF", headerRow, ...bodyRows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    const today = new Date();
    const dateStr = today.getFullYear() + String(today.getMonth() + 1).padStart(2, '0') + String(today.getDate()).padStart(2, '0');
    link.setAttribute("href", url);
    link.setAttribute("download", `export_shopee_${dateStr}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

/**
 * Ordena os dados atualmente visíveis na tabela.
 * @param {string} sortKey - A chave do dado pela qual ordenar.
 */
function sortTable(sortKey) {
    if (sortState.columnKey === sortKey) {
        sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
    } else {
        sortState.columnKey = sortKey;
        sortState.direction = 'asc';
    }
    const directionModifier = sortState.direction === 'asc' ? 1 : -1;

    // Ordena a lista de dados que está atualmente na tela
    currentDisplayData.sort((a, b) => {
        const valA = a[sortKey];
        const valB = b[sortKey];
        const numA = parseNumericValue(valA);
        const numB = parseNumericValue(valB);
        let comparison = 0;
        if (!isNaN(numA) && !isNaN(numB)) {
            comparison = numA - numB;
        } else {
            comparison = String(valA).toLowerCase().localeCompare(String(valB).toLowerCase());
        }
        return comparison * directionModifier;
    });

    renderTable(currentDisplayData);
}

/**
 * Atualiza as setas nos cabeçalhos da tabela para indicar a ordenação.
 */
function updateSortIndicators() {
    document.querySelectorAll('.sortable-header').forEach(header => {
        const key = header.getAttribute('data-sort-key');
        const arrowSpan = header.querySelector('span');
        if (arrowSpan) {
            if (key === sortState.columnKey) {
                arrowSpan.innerHTML = sortState.direction === 'asc' ? ' &#9650;' : ' &#9660;';
            } else {
                arrowSpan.innerHTML = '';
            }
        }
    });
}

/**
 * Adiciona uma nova opção ao dropdown de filtro de pesquisa, se ela ainda não existir.
 * @param {string} searchTerm - O novo termo de pesquisa a ser adicionado.
 */
function addSearchTermToFilter(searchTerm) {
    if (!searchTerm) return;
    const searchFilter = document.getElementById('filtro-pesquisa');
    if (!searchFilter) return;

    // Verifica se a opção já existe para não duplicar
    const existingOption = searchFilter.querySelector(`option[value="${searchTerm}"]`);
    if (!existingOption) {
        const newOption = document.createElement('option');
        newOption.value = searchTerm;
        newOption.textContent = searchTerm;
        searchFilter.appendChild(newOption);
    }
}


/**
 * Anexa os "escutadores de eventos" a elementos estáticos da página.
 */
function attachStaticListeners() {
    const btnExcluir = document.getElementById('btn-excluir');
    if (btnExcluir) {
        btnExcluir.addEventListener('click', function() {
            const checkboxesItens = document.querySelectorAll('.checkbox-item:checked');
            if (checkboxesItens.length === 0) {
                alert('Nenhum item selecionado para excluir.');
                return;
            }
            if (confirm(`Tem certeza que deseja excluir ${checkboxesItens.length} item(ns)?`)) {
                const linksParaExcluir = new Set();
                checkboxesItens.forEach(chk => {
                    const linkId = chk.closest('tr').getAttribute('data-link-id');
                    if (linkId) linksParaExcluir.add(linkId);
                });
                activeData = activeData.filter(item => {
                    const itemLink = item['Link do anuncio'] || item['link'] || '';
                    return !linksParaExcluir.has(itemLink);
                });
                document.getElementById('btn-aplicar-filtros').click();
            }
        });
    }

    const chkSelecionarTodos = document.getElementById('selecionar-todos');
    if (chkSelecionarTodos) {
        chkSelecionarTodos.addEventListener('change', function() {
            document.querySelectorAll('.checkbox-item').forEach(chk => { chk.checked = this.checked; });
        });
    }

    const btnAplicarFiltros = document.getElementById('btn-aplicar-filtros');
    if (btnAplicarFiltros) {
        btnAplicarFiltros.addEventListener('click', function() {
            const pesquisa = document.getElementById('filtro-pesquisa').value;
            const estado = document.getElementById('filtro-estado').value;
            const precoMin = parseFloat(document.getElementById('filtro-preco-min').value) || 0;
            const precoMax = parseFloat(document.getElementById('filtro-preco-max').value) || Infinity;
            const vendasMin = parseInt(document.getElementById('filtro-vendas-min').value) || 0;
            const giroMin = parseInt(document.getElementById('filtro-giro-min').value) || 0;

            const filteredData = activeData.filter(item => {
                const precoItem = parseNumericValue(item['Preço anunciado'] || item['preco_anunciado'] || '0');
                const vendasItem = parseNumericValue(item['Quantidade de vendas'] || item['vendas'] || '0');
                const giroItem = parseNumericValue(item['Giro'] || '0');
                
                // CORREÇÃO 1: A lógica de filtro por pesquisa foi adicionada aqui.
                if (pesquisa && item['Pesquisa'] !== pesquisa) return false;
                
                if (estado && item['Estado'] !== estado) return false;
                if (precoItem < precoMin) return false;
                if (precoItem > precoMax) return false;
                if (vendasItem < vendasMin) return false;
                if (giroItem < giroMin) return false;
                return true;
            });
            renderTable(filteredData);
        });
    }

    const btnLimparFiltros = document.getElementById('btn-limpar-filtros');
    if (btnLimparFiltros) {
        btnLimparFiltros.addEventListener('click', function() {
            document.getElementById('filtro-pesquisa').value = '';
            document.getElementById('filtro-estado').value = '';
            document.getElementById('filtro-preco-min').value = '';
            document.getElementById('filtro-preco-max').value = '';
            document.getElementById('filtro-vendas-min').value = '';
            document.getElementById('filtro-giro-min').value = '';
            renderTable(activeData);
        });
    }

    const modal = document.getElementById('exportModal');
    const btnExportar = document.getElementById('btn-exportar');
    const closeModalBtn = document.querySelector('.close-button');
    const columnsContainer = document.getElementById('modal-columns-body');
    const btnConfirmarExport = document.getElementById('btn-confirmar-export');

    if (allHeaders && columnsContainer) {
        columnsContainer.innerHTML = '';
        allHeaders.forEach(header => {
            const label = document.createElement('label');
            label.className = 'column-checkbox';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = header;
            checkbox.checked = true;
            checkbox.addEventListener('change', toggleColumnVisibility);
            label.appendChild(checkbox);
            label.appendChild(document.createTextNode(' ' + header));
            columnsContainer.appendChild(label);
        });
    }
    
    if (btnExportar) btnExportar.onclick = () => { if(modal) modal.style.display = 'block'; };
    if (closeModalBtn) closeModalBtn.onclick = () => { if(modal) modal.style.display = 'none'; };
    window.onclick = (event) => { if (event.target == modal) { if(modal) modal.style.display = 'none'; } };
    
    if (btnConfirmarExport) {
        btnConfirmarExport.onclick = function() {
            const selectedHeaders = Array.from(columnsContainer.querySelectorAll('input[type="checkbox"]:checked')).map(chk => chk.value);
            if (selectedHeaders.length > 0) {
                exportToCSV(currentDisplayData, selectedHeaders);
                if(modal) modal.style.display = 'none';
            } else {
                alert('Por favor, selecione pelo menos uma coluna para exportar.');
            }
        }
    }

    const btnNovaPesquisa = document.getElementById('btn-nova-pesquisa');
    if (btnNovaPesquisa) {
        btnNovaPesquisa.addEventListener('click', async function() {
            const termo = document.getElementById('nova-pesquisa-termo').value;
            const preco = document.getElementById('nova-pesquisa-preco').value;
            const tipoServico = document.body.dataset.tipoServico;

            if (!termo) {
                alert("Por favor, insira um termo para a nova pesquisa.");
                return;
            }

            const loadingOverlay = document.getElementById('loading-overlay');
            if (loadingOverlay) loadingOverlay.style.display = 'flex';

            try {
                const response = await fetch('/api/shopee/add_search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tipo_servico: tipoServico,
                        termo_busca: termo,
                        preco: preco
                    })
                });
                if (!response.ok) throw new Error('A resposta do servidor não foi bem-sucedida.');
                const novosResultados = await response.json();
                if (novosResultados && novosResultados.length > 0) {
                    activeData.push(...novosResultados);
                    originalFullData.push(...novosResultados); 
                    
                    // Correção 2: A chamada para adicionar o novo termo ao filtro foi garantida aqui.
                    addSearchTermToFilter(termo);
                    document.getElementById('filtro-pesquisa').value = termo;
                    document.getElementById('filtro-pesquisa').selectedIndex = 0;
                    document.getElementById('btn-aplicar-filtros').click();
                } else {
                    alert("A nova pesquisa não retornou resultados.");
                }
            } catch (error) {
                console.error("Erro na multi-pesquisa:", error);
                alert("Ocorreu um erro ao realizar a pesquisa adicional.");
            } finally {
                if (loadingOverlay) loadingOverlay.style.display = 'none';
                document.getElementById('nova-pesquisa-termo').value = '';
                document.getElementById('nova-pesquisa-preco').value = '';
            }
        });
    }

    const tipoServico = document.body.dataset.tipoServico;
    const campoPrecoNovaPesquisa = document.getElementById('nova-pesquisa-preco');
    if (campoPrecoNovaPesquisa && (tipoServico === 'pma' || tipoServico === 'manutencao_margem')) {
        campoPrecoNovaPesquisa.classList.remove('hidden');
    }
}


// --- LÓGICA PRINCIPAL ---
document.addEventListener('DOMContentLoaded', function() {
    // Renderiza a tabela inicial com os dados
    if (typeof activeData !== 'undefined' && activeData.length > 0) {
        renderTable(activeData);
    }
    
    // Anexa os listeners aos botões estáticos
    attachStaticListeners();

    // Anexa os listeners aos cabeçalhos da tabela para ordenação
    document.querySelectorAll('.sortable-header').forEach(header => {
        header.addEventListener('click', () => {
            const sortKey = header.getAttribute('data-sort-key');
            sortTable(sortKey);
        });
    });
});
