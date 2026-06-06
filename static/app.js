'use strict';

const BASE = '';

const TIPO_LABELS = {
  outlier_valor: 'Outlier de valor',
  concentracao_fornecedor: 'Concentração de fornecedor',
  sem_licitacao_inexigibilidade: 'Inexigibilidade',
  sem_licitacao_emergencia: 'Emergência',
  sem_licitacao_dispensa: 'Dispensa',
  fracionamento_ap: 'Fracionamento',
};

const TIPO_COLORS = {
  outlier_valor: '#ef4444',
  concentracao_fornecedor: '#f97316',
  sem_licitacao_inexigibilidade: '#a855f7',
  sem_licitacao_emergencia: '#eab308',
  sem_licitacao_dispensa: '#3b82f6',
  fracionamento_ap: '#22c55e',
};

const SEV_COLORS = {
  alta: '#ef4444',
  media: '#f97316',
  baixa: '#6b7280',
};

const TIPO_BADGE_CLASS = {
  outlier_valor: 'red',
  concentracao_fornecedor: 'orange',
  sem_licitacao_inexigibilidade: 'purple',
  sem_licitacao_emergencia: 'yellow',
  sem_licitacao_dispensa: 'blue',
  fracionamento_ap: 'green',
};

const state = {
  currentTab: 'visao-geral',
  alertasPage: 1,
  alertasFiltros: { tipo: '', severidade: '', ano: '', fornecedor: '' },
  charts: {},
  tabLoaded: {},
  timelineData: null,
  timelineGranularity: 'month',
  fornecedoresOrderby: 'valor',
};

// ─── Helpers ───────────────────────────────────────────────────────────────

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

function formatCurrency(val) {
  if (val == null) return '—';
  const n = parseFloat(val);
  if (isNaN(n)) return '—';
  if (n >= 1e9) return `R$ ${(n / 1e9).toFixed(2).replace('.', ',')} bi`;
  if (n >= 1e6) return `R$ ${(n / 1e6).toFixed(1).replace('.', ',')} mi`;
  return 'R$ ' + n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatDate(str) {
  if (!str) return '—';
  // Handles 'YYYY-MM-DD' and ISO strings
  const d = new Date(str.length === 10 ? str + 'T12:00:00' : str);
  if (isNaN(d.getTime())) return str;
  return d.toLocaleDateString('pt-BR');
}

function truncate(str, n) {
  if (!str) return '—';
  return str.length > n ? str.slice(0, n) + '…' : str;
}

function tipoBadge(tipo) {
  const label = TIPO_LABELS[tipo] || tipo;
  const cls = TIPO_BADGE_CLASS[tipo] || 'gray';
  return `<span class="badge badge-${cls}">${label}</span>`;
}

function sevBadge(sev) {
  const map = { alta: 'red', media: 'orange', baixa: 'gray' };
  const cls = map[sev] || 'gray';
  const label = sev ? sev.charAt(0).toUpperCase() + sev.slice(1) : '—';
  return `<span class="badge badge-${cls}">${label}</span>`;
}

function showError(containerId, msg) {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = `<div class="error-msg">Erro ao carregar: ${msg}</div>`;
}

function chartOptions(extraX = {}, extraY = {}) {
  return {
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: '#737373', font: { size: 11 } }, grid: { color: '#1f1f1f' }, ...extraX },
      y: { ticks: { color: '#737373', font: { size: 11 } }, grid: { color: '#1f1f1f' }, ...extraY },
    },
  };
}

// ─── Tab management ────────────────────────────────────────────────────────

function setupTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;

      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      document.querySelectorAll('.tab-section').forEach(s => s.classList.remove('active'));
      document.getElementById(`tab-${tab}`).classList.add('active');

      state.currentTab = tab;

      if (!state.tabLoaded[tab]) {
        loadTab(tab);
        state.tabLoaded[tab] = true;
      }
    });
  });
}

function loadTab(name) {
  switch (name) {
    case 'visao-geral':
      loadStats();
      loadChartTipos();
      break;
    case 'alertas':
      setupFilters();
      loadAlertas();
      break;
    case 'timeline':
      loadTimeline();
      break;
    case 'fornecedores':
      loadFornecedores();
      break;
  }
}

// ─── Stats ─────────────────────────────────────────────────────────────────

async function loadStats() {
  const container = document.getElementById('kpi-cards');
  container.innerHTML = '<div class="loading-msg">Carregando…</div>';
  try {
    const res = await fetch(`${BASE}/api/stats`);
    if (!res.ok) throw new Error(res.statusText);
    const d = await res.json();

    const periodo = (d.periodo_inicio && d.periodo_fim)
      ? `${formatDate(d.periodo_inicio)} – ${formatDate(d.periodo_fim)}`
      : '—';

    container.innerHTML = `
      <div class="kpi-card">
        <div class="kpi-value">${(d.contratos_total || 0).toLocaleString('pt-BR')}</div>
        <div class="kpi-label">Contratos Analisados</div>
        <div class="kpi-hint">Com valor registrado</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="font-size:1.75rem">${formatCurrency(d.valor_total)}</div>
        <div class="kpi-label">Valor Total</div>
        <div class="kpi-hint">Soma dos contratos</div>
      </div>
      <div class="kpi-card highlight">
        <div class="kpi-value">${(d.alertas_total || 0).toLocaleString('pt-BR')}</div>
        <div class="kpi-label">Anomalias Detectadas</div>
        <div class="kpi-hint">Todos os tipos</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="color:#ef4444">${(d.alertas_alta || 0).toLocaleString('pt-BR')}</div>
        <div class="kpi-label">Risco Alto</div>
        <div class="kpi-hint">Severidade alta</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value">${(d.fornecedores_distintos || 0).toLocaleString('pt-BR')}</div>
        <div class="kpi-label">Fornecedores</div>
        <div class="kpi-hint">Empresas distintas</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="font-size:1rem;padding-top:0.75rem;line-height:1.4">${periodo}</div>
        <div class="kpi-label">Período</div>
        <div class="kpi-hint">Intervalo dos contratos</div>
      </div>
    `;
  } catch (e) {
    showError('kpi-cards', e.message);
  }
}

// ─── Charts: Tipos + Severidade ────────────────────────────────────────────

async function loadChartTipos() {
  try {
    const res = await fetch(`${BASE}/api/anomalias/por-tipo`);
    if (!res.ok) throw new Error(res.statusText);
    const d = await res.json();

    // Aggregate by tipo
    const byTipo = {};
    const bySev  = {};
    d.items.forEach(item => {
      byTipo[item.tipo] = (byTipo[item.tipo] || 0) + item.quantidade;
      bySev[item.severidade] = (bySev[item.severidade] || 0) + item.quantidade;
    });

    if (state.charts.tipos) state.charts.tipos.destroy();
    state.charts.tipos = new Chart(document.getElementById('chart-tipos'), {
      type: 'bar',
      data: {
        labels: Object.keys(byTipo).map(t => TIPO_LABELS[t] || t),
        datasets: [{
          data: Object.values(byTipo),
          backgroundColor: Object.keys(byTipo).map(t => TIPO_COLORS[t] || '#6b7280'),
          borderRadius: 4,
        }],
      },
      options: {
        ...chartOptions(),
        indexAxis: 'y',
        plugins: { legend: { display: false } },
      },
    });

    const sevKeys = Object.keys(bySev);
    if (state.charts.severidade) state.charts.severidade.destroy();
    state.charts.severidade = new Chart(document.getElementById('chart-severidade'), {
      type: 'doughnut',
      data: {
        labels: sevKeys.map(s => s.charAt(0).toUpperCase() + s.slice(1)),
        datasets: [{
          data: sevKeys.map(s => bySev[s]),
          backgroundColor: sevKeys.map(s => SEV_COLORS[s] || '#6b7280'),
          borderWidth: 0,
        }],
      },
      options: {
        plugins: {
          legend: { labels: { color: '#a3a3a3', font: { size: 11 } } },
        },
      },
    });

  } catch (e) {
    showError('chart-tipos', e.message);
  }
}

// ─── Alertas list ──────────────────────────────────────────────────────────

function setupFilters() {
  const debouncedLoad = debounce(() => {
    state.alertasPage = 1;
    loadAlertas();
  }, 300);

  [
    ['filter-tipo',       'tipo'],
    ['filter-severidade', 'severidade'],
    ['filter-ano',        'ano'],
  ].forEach(([id, key]) => {
    const el = document.getElementById(id);
    if (el && !el._bound) {
      el.addEventListener('change', () => {
        state.alertasFiltros[key] = el.value;
        state.alertasPage = 1;
        loadAlertas();
      });
      el._bound = true;
    }
  });

  const fornEl = document.getElementById('filter-fornecedor');
  if (fornEl && !fornEl._bound) {
    fornEl.addEventListener('input', () => {
      state.alertasFiltros.fornecedor = fornEl.value;
      debouncedLoad();
    });
    fornEl._bound = true;
  }

  const btnPrev = document.getElementById('btn-prev');
  const btnNext = document.getElementById('btn-next');

  if (btnPrev && !btnPrev._bound) {
    btnPrev.addEventListener('click', () => {
      if (state.alertasPage > 1) { state.alertasPage--; loadAlertas(); }
    });
    btnPrev._bound = true;
  }
  if (btnNext && !btnNext._bound) {
    btnNext.addEventListener('click', () => {
      state.alertasPage++;
      loadAlertas();
    });
    btnNext._bound = true;
  }
}

async function loadAlertas() {
  const tbody = document.getElementById('alertas-tbody');
  tbody.innerHTML = '<tr><td colspan="7" class="loading-msg">Carregando…</td></tr>';

  try {
    const params = new URLSearchParams({ page: state.alertasPage, per_page: 20 });
    const f = state.alertasFiltros;
    if (f.tipo)       params.set('tipo',       f.tipo);
    if (f.severidade) params.set('severidade', f.severidade);
    if (f.ano)        params.set('ano',        f.ano);
    if (f.fornecedor) params.set('fornecedor', f.fornecedor);

    const res = await fetch(`${BASE}/api/alertas/agrupados?${params}`);
    if (!res.ok) throw new Error(res.statusText);
    const d = await res.json();

    if (!d.items.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:2rem">Nenhuma anomalia encontrada.</td></tr>';
    } else {
      const html = [];
      d.items.forEach(grupo => {
        const countBadge = grupo.ocorrencias > 1
          ? `<span class="badge-count">${grupo.ocorrencias} contratos</span>`
          : `<span class="badge-count badge-count-single">1 contrato</span>`;
        const analisBtn = grupo.narrativa_ia
          ? `<button class="btn-page btn-analise" data-grupo="${grupo.grupo_id}" style="font-size:0.75rem">Ver análise</button>`
          : '';
        const gid = grupo.grupo_id;

        html.push(`
          <tr class="row-group" data-grupo="${gid}">
            <td><button class="expand-btn" data-grupo="${gid}">▶</button></td>
            <td>${tipoBadge(grupo.tipo)}</td>
            <td>${sevBadge(grupo.severidade)}</td>
            <td style="white-space:nowrap;font-weight:500">${formatCurrency(grupo.valor_total)}</td>
            <td>${truncate(grupo.fornecedor || '—', 30)} ${countBadge}</td>
            <td style="white-space:nowrap;color:var(--muted)">${formatDate(grupo.data_mais_recente)}</td>
            <td>${analisBtn}</td>
          </tr>
        `);

        const tipoColor = TIPO_COLORS[grupo.tipo] || '#6b7280';
        grupo.alertas.forEach(a => {
          const pncpLink = a.numero_controle_pncp
            ? `<a href="https://pncp.gov.br/app/contratos/${a.numero_controle_pncp}" target="_blank" rel="noopener" class="detail-link" style="font-size:0.75rem;padding:0.2rem 0.5rem">PNCP ↗</a>`
            : '';
          html.push(`
            <tr class="row-detail" data-grupo="${gid}">
              <td colspan="7">
                <div class="detail-row-inner" style="border-left:3px solid ${tipoColor}">
                  <span class="detail-col-objeto">${truncate(a.objeto || '—', 60)}</span>
                  <span class="detail-col-valor">${formatCurrency(a.valor_referencia)}</span>
                  <span class="detail-col-data">${formatDate(a.data_assinatura)}</span>
                  <span class="detail-col-orgao">${truncate(a.orgao || '—', 30)}</span>
                  <span class="detail-col-actions">
                    ${pncpLink}
                    <button class="btn-page btn-ver-detalhes" data-id="${a.id}" style="font-size:0.75rem;padding:0.2rem 0.5rem">Ver detalhes</button>
                  </span>
                </div>
              </td>
            </tr>
          `);
        });
      });

      tbody.innerHTML = html.join('');

      tbody.querySelectorAll('.row-group').forEach(tr => {
        const gid = tr.dataset.grupo;
        const expandToggle = () => {
          const expanded = tr.classList.toggle('expanded');
          tr.querySelector('.expand-btn').textContent = expanded ? '▼' : '▶';
          tbody.querySelectorAll(`.row-detail[data-grupo="${gid}"]`).forEach(dr => {
            dr.classList.toggle('visible', expanded);
          });
        };
        tr.addEventListener('click', e => {
          if (e.target.classList.contains('btn-analise') || e.target.classList.contains('btn-ver-detalhes')) return;
          expandToggle();
        });
      });

      tbody.querySelectorAll('.btn-analise').forEach(btn => {
        btn.addEventListener('click', () => {
          const grupo = d.items.find(g => g.grupo_id === btn.dataset.grupo);
          if (grupo?.alertas[0]) openDetail(grupo.alertas[0].id);
        });
      });

      tbody.querySelectorAll('.btn-ver-detalhes').forEach(btn => {
        btn.addEventListener('click', () => openDetail(parseInt(btn.dataset.id, 10)));
      });
    }

    const indicator = document.getElementById('page-indicator');
    if (indicator) indicator.textContent = `Página ${d.page} de ${Math.max(1, d.pages)}`;

    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');
    if (btnPrev) btnPrev.disabled = d.page <= 1;
    if (btnNext) btnNext.disabled = d.page >= d.pages;

  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="error-msg">Erro: ${e.message}</div></td></tr>`;
  }
}

// ─── Detail panel ──────────────────────────────────────────────────────────

async function openDetail(id) {
  const panel    = document.getElementById('detail-panel');
  const backdrop = document.getElementById('detail-backdrop');
  const content  = document.getElementById('detail-content');

  content.innerHTML = '<div class="loading-msg">Carregando…</div>';
  panel.classList.add('panel-open');
  backdrop.classList.add('backdrop-open');

  try {
    const res = await fetch(`${BASE}/api/alertas/${id}`);
    if (!res.ok) throw new Error(res.statusText);
    const d = await res.json();

    const vigencia = [d.data_vigencia_inicio, d.data_vigencia_fim]
      .map(formatDate).filter(v => v !== '—').join(' → ') || '—';

    const pncpId = d.numero_controle_pncp;
    const pncpLink = pncpId && pncpId !== '—'
      ? `<a href="https://pncp.gov.br/app/contratos/${pncpId}" target="_blank" rel="noopener" class="detail-link">Ver no PNCP ↗</a>`
      : '';

    const complementar = d.informacao_complementar
      ? `<div class="detail-block">
           <label>Informação Complementar</label>
           <p>${d.informacao_complementar}</p>
         </div>`
      : '';

    const narrativa = d.narrativa_ia
      ? `<div class="narrativa-block">
           <label>Narrativa IA</label>
           <p>${d.narrativa_ia}</p>
         </div>`
      : '';

    content.innerHTML = `
      <div class="detail-fornecedor">${d.fornecedor || 'Fornecedor não identificado'}</div>
      <div class="detail-badges">
        ${tipoBadge(d.tipo)}
        ${sevBadge(d.severidade)}
      </div>
      <div class="detail-valor">${formatCurrency(d.valor_referencia)}</div>
      <div class="detail-grid">
        <div class="detail-field">
          <label>Data de Assinatura</label>
          <p>${formatDate(d.data_assinatura)}</p>
        </div>
        <div class="detail-field">
          <label>Vigência</label>
          <p>${vigencia}</p>
        </div>
        <div class="detail-field">
          <label>Órgão</label>
          <p>${d.orgao || '—'}</p>
        </div>
        <div class="detail-field">
          <label>Valor Global</label>
          <p>${formatCurrency(d.valor_global)}</p>
        </div>
      </div>
      <div class="detail-block">
        <label>Objeto</label>
        <p>${d.objeto || '—'}</p>
      </div>
      <div class="detail-block">
        <label>Descrição Técnica</label>
        <p>${d.descricao || '—'}</p>
      </div>
      ${complementar}
      ${narrativa}
      ${pncpLink}
    `;
  } catch (e) {
    content.innerHTML = `<div class="error-msg">Erro ao carregar: ${e.message}</div>`;
  }
}

function closeDetail() {
  document.getElementById('detail-panel').classList.remove('panel-open');
  document.getElementById('detail-backdrop').classList.remove('backdrop-open');
}

// ─── Timeline ──────────────────────────────────────────────────────────────

async function loadTimeline() {
  try {
    const res = await fetch(`${BASE}/api/timeline?granularity=${state.timelineGranularity}`);
    if (!res.ok) throw new Error(res.statusText);
    state.timelineData = await res.json();
    renderTimeline();
  } catch (e) {
    showError('chart-timeline-contratos', e.message);
  }
}

function getActiveYears() {
  return Array.from(document.querySelectorAll('.year-check:checked')).map(c => c.value);
}

function renderTimeline() {
  const d = state.timelineData;
  if (!d) return;

  const activeYears = getActiveYears();
  const filtered = d.labels.reduce(
    (acc, label, i) => {
      if (activeYears.includes(label.slice(0, 4))) {
        acc.labels.push(label);
        acc.contratos.push(d.contratos[i]);
        acc.valor.push(d.valor[i]);
      }
      return acc;
    },
    { labels: [], contratos: [], valor: [] }
  );

  const xTicks = { color: '#737373', font: { size: 10 }, maxRotation: 45 };

  if (state.charts.timelineContratos) state.charts.timelineContratos.destroy();
  state.charts.timelineContratos = new Chart(
    document.getElementById('chart-timeline-contratos'),
    {
      type: 'line',
      data: {
        labels: filtered.labels,
        datasets: [{
          label: 'Contratos',
          data: filtered.contratos,
          borderColor: '#3b82f6',
          backgroundColor: '#3b82f615',
          fill: true,
          tension: 0.3,
          pointRadius: 3,
        }],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: xTicks, grid: { color: '#1f1f1f' } },
          y: { ticks: { color: '#737373', font: { size: 11 } }, grid: { color: '#1f1f1f' } },
        },
      },
    }
  );

  if (state.charts.timelineValor) state.charts.timelineValor.destroy();
  state.charts.timelineValor = new Chart(
    document.getElementById('chart-timeline-valor'),
    {
      type: 'bar',
      data: {
        labels: filtered.labels,
        datasets: [{
          label: 'Valor (R$)',
          data: filtered.valor,
          backgroundColor: '#ef4444',
          borderRadius: 3,
        }],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: xTicks, grid: { color: '#1f1f1f' } },
          y: {
            ticks: {
              color: '#737373',
              font: { size: 11 },
              callback: v =>
                v >= 1e9 ? `${(v / 1e9).toFixed(1)}bi`
                : v >= 1e6 ? `${(v / 1e6).toFixed(0)}mi`
                : v,
            },
            grid: { color: '#1f1f1f' },
          },
        },
      },
    }
  );
}

// ─── Fornecedores ──────────────────────────────────────────────────────────

async function loadFornecedores() {
  try {
    const res = await fetch(`${BASE}/api/fornecedores/ranking?limit=15&orderby=${state.fornecedoresOrderby}`);
    if (!res.ok) throw new Error(res.statusText);
    const d = await res.json();

    const isValor = state.fornecedoresOrderby === 'valor';
    const labels = d.items.map(r => truncate(r.fornecedor || 'N/I', 32));
    const values = d.items.map(r => isValor ? r.valor_total : r.total_contratos);

    if (state.charts.fornecedores) state.charts.fornecedores.destroy();
    state.charts.fornecedores = new Chart(document.getElementById('chart-fornecedores'), {
      type: 'bar',
      data: {
        labels,
        datasets: [{ data: values, backgroundColor: '#3b82f6', borderRadius: 4 }],
      },
      options: {
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: {
          x: {
            ticks: {
              color: '#737373',
              font: { size: 11 },
              callback: v => isValor
                ? (v >= 1e6 ? `${(v / 1e6).toFixed(0)}mi` : v)
                : v,
            },
            grid: { color: '#1f1f1f' },
          },
          y: { ticks: { color: '#a3a3a3', font: { size: 10 } }, grid: { color: '#1f1f1f' } },
        },
      },
    });

    const tbody = document.getElementById('fornecedores-tbody');
    tbody.innerHTML = d.items.map(r => {
      const nome = (r.fornecedor || 'N/I').replace(/'/g, '&#39;');
      return `
        <tr>
          <td><button class="fornecedor-link" data-nome="${nome}">${r.fornecedor || 'N/I'}</button></td>
          <td>${(r.total_contratos || 0).toLocaleString('pt-BR')}</td>
          <td>${formatCurrency(r.valor_total)}</td>
          <td>${r.alertas || 0}</td>
        </tr>
      `;
    }).join('');

    tbody.querySelectorAll('.fornecedor-link').forEach(btn => {
      btn.addEventListener('click', () => filterByFornecedor(btn.dataset.nome));
    });

  } catch (e) {
    showError('chart-fornecedores', e.message);
  }
}

function filterByFornecedor(nome) {
  const alertasBtn = document.querySelector('[data-tab="alertas"]');
  if (alertasBtn) alertasBtn.click();

  const input = document.getElementById('filter-fornecedor');
  if (input) {
    input.value = nome;
    state.alertasFiltros.fornecedor = nome;
    state.alertasPage = 1;
    loadAlertas();
  }
}

// ─── Bootstrap ─────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  loadTab('visao-geral');
  state.tabLoaded['visao-geral'] = true;

  // Detail panel close
  document.getElementById('detail-close')
    ?.addEventListener('click', closeDetail);
  document.getElementById('detail-backdrop')
    ?.addEventListener('click', closeDetail);

  // Timeline granularity toggle
  document.querySelectorAll('#timeline-toggle [data-granularity]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#timeline-toggle .toggle-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.timelineGranularity = btn.dataset.granularity;
      state.timelineData = null;
      loadTimeline();
    });
  });

  // Year checkboxes
  document.querySelectorAll('.year-check').forEach(cb => {
    cb.addEventListener('change', renderTimeline);
  });

  // Fornecedores orderby toggle
  document.querySelectorAll('#fornecedores-toggle .toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#fornecedores-toggle .toggle-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.fornecedoresOrderby = btn.dataset.orderby;
      loadFornecedores();
    });
  });
});
