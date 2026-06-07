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

const TIPO_TOOLTIPS = {
  outlier_valor: 'Contrato com valor muito acima da média histórica para o mesmo tipo de serviço. Pode indicar sobrepreço.',
  concentracao_fornecedor: 'Empresa recebeu muitos contratos em pouco tempo do mesmo órgão. Pode indicar favorecimento.',
  sem_licitacao_inexigibilidade: 'Contrato firmado sem licitação por alegação de fornecedor exclusivo. Precisa de justificativa sólida.',
  sem_licitacao_emergencia: 'Contrato emergencial sem licitação. Emergências reais existem, mas o uso excessivo é suspeito.',
  sem_licitacao_dispensa: 'Contrato dispensado de licitação por valor baixo ou outras condições legais.',
  fracionamento_ap: 'Mesmo serviço dividido entre várias empresas por região. Pode ser tentativa de driblar o limite de licitação.',
};

const state = {
  currentTab: 'visao-geral',
  alertasPage: 1,
  alertasFiltros: { tipo: '', severidade: '', ano: '', fornecedor: '', valorMin: '' },
  alertasSort: { column: null, direction: 'desc' },
  charts: {},
  tabLoaded: {},
  timelineData: null,
  timelineGranularity: 'month',
  fornecedoresOrderby: 'valor',
  orgaosData: {},
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
  const tooltip = TIPO_TOOLTIPS[tipo];
  if (tooltip) {
    return `<span class="badge badge-${cls} tooltip-wrap">${label}<span class="tooltip-text">${tooltip}</span></span>`;
  }
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
    case 'orgaos':
      loadOrgaos();
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

  const valorMinEl = document.getElementById('filter-valor-min');
  if (valorMinEl && !valorMinEl._bound) {
    valorMinEl.addEventListener('input', () => {
      state.alertasFiltros.valorMin = valorMinEl.value;
      debouncedLoad();
    });
    valorMinEl._bound = true;
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
    if (f.valorMin)   params.set('valor_min',  f.valorMin);

    const res = await fetch(`${BASE}/api/alertas/agrupados?${params}`);
    if (!res.ok) throw new Error(res.statusText);
    const d = await res.json();

    if (!d.items.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:2rem">Nenhuma anomalia encontrada.</td></tr>';
    } else {
      const SEV_SORT_VAL = { alta: 3, media: 2, baixa: 1 };
      const groups = [...d.items];
      if (state.alertasSort.column) {
        const dir = state.alertasSort.direction === 'asc' ? 1 : -1;
        groups.sort((a, b) => {
          switch (state.alertasSort.column) {
            case 'valor':      return dir * ((a.valor_total || 0) - (b.valor_total || 0));
            case 'severidade': return dir * ((SEV_SORT_VAL[a.severidade] || 0) - (SEV_SORT_VAL[b.severidade] || 0));
            case 'data':       return dir * ((a.data_mais_recente || '').localeCompare(b.data_mais_recente || ''));
            case 'fornecedor': return dir * (a.fornecedor || '').localeCompare(b.fornecedor || '');
            case 'tipo':       return dir * (a.tipo || '').localeCompare(b.tipo || '');
            default:           return 0;
          }
        });
      }
      const html = [];
      groups.forEach(grupo => {
        const countBadge = grupo.ocorrencias > 1
          ? `<span class="badge-count">${grupo.ocorrencias} contratos</span>`
          : `<span class="badge-count badge-count-single">1 contrato</span>`;
        const firstId = grupo.alertas[0]?.id ?? '';
        const analisBtn = grupo.narrativa_ia && firstId !== ''
          ? `<button class="btn-ver-analise" data-id="${firstId}">Ver análise</button>`
          : '<span style="color:var(--muted)">—</span>';
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
            ? `<a href="https://pncp.gov.br/app/contratos/${a.numero_controle_pncp}" target="_blank" rel="noopener" class="btn-pncp">PNCP ↗</a>`
            : '';
          html.push(`
            <tr class="row-detail" data-grupo="${gid}">
              <td colspan="7">
                <div class="detail-inner" style="border-left-color:${tipoColor}">
                  <div class="detail-objeto">
                    <span class="detail-label">Objeto</span>
                    <span class="detail-value">
                      <span class="obj-preview">${truncate(a.objeto || '—', 80)}</span>
                      ${a.objeto && a.objeto.length > 80 ? `
                        <span class="obj-full" hidden>${a.objeto}</span>
                        <button class="btn-expand-obj" onclick="toggleObj(this)">Ver mais</button>
                      ` : ''}
                    </span>
                  </div>
                  <div class="detail-meta">
                    <div class="detail-item">
                      <span class="detail-label">Valor</span>
                      <span class="detail-value" style="white-space:nowrap;font-weight:500">${formatCurrency(a.valor_referencia)}</span>
                    </div>
                    <div class="detail-item">
                      <span class="detail-label">Data</span>
                      <span class="detail-value" style="white-space:nowrap">${formatDate(a.data_assinatura)}</span>
                    </div>
                    <div class="detail-item">
                      <span class="detail-label">Órgão</span>
                      <span class="detail-value">${truncate(a.orgao || '—', 40)}</span>
                    </div>
                    <div class="detail-item" style="grid-column:1/-1">
                      <span class="detail-label">Anomalia</span>
                      <span class="detail-value" style="font-size:0.8rem;color:#d4d4d4">${a.descricao || '—'}</span>
                    </div>
                  </div>
                  <div class="detail-actions">
                    ${pncpLink}
                    <button class="btn-ver-detalhes" data-id="${a.id}">Ver detalhes</button>
                  </div>
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
          if (e.target.classList.contains('btn-ver-analise') || e.target.classList.contains('btn-ver-detalhes')) return;
          expandToggle();
        });
      });

      tbody.querySelectorAll('.btn-ver-analise').forEach(btn => {
        btn.addEventListener('click', () => openDetail(parseInt(btn.dataset.id, 10)));
      });

      tbody.querySelectorAll('.btn-ver-detalhes').forEach(btn => {
        btn.addEventListener('click', () => openDetail(parseInt(btn.dataset.id, 10)));
      });
    }

    const counter = document.getElementById('resultados-counter');
    if (counter) {
      if (d.total === 0) {
        counter.textContent = '';
      } else {
        const x = (d.page - 1) * 20 + 1;
        const y = Math.min(d.page * 20, d.total);
        counter.textContent = `Mostrando ${x}–${y} de ${d.total} grupos`;
      }
    }

    const SORT_BASE = { tipo: 'Tipo', severidade: 'Severidade', valor: 'Valor ▲▼', fornecedor: 'Fornecedor', data: 'Data ▲▼' };
    document.querySelectorAll('#alertas-table th[data-sort]').forEach(th => {
      const col = th.dataset.sort;
      th.classList.toggle('sort-active', col === state.alertasSort.column);
      if (col === state.alertasSort.column) {
        th.textContent = SORT_BASE[col].replace(' ▲▼', '') + (state.alertasSort.direction === 'asc' ? ' ▲' : ' ▼');
      } else {
        th.textContent = SORT_BASE[col];
      }
    });

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
      <div class="detail-actions">
        ${pncpLink}
        ${d.fornecedor_ni ? `<a href="/fornecedor/${d.fornecedor_ni}" target="_self" class="detail-link">Ver página do fornecedor →</a>` : ''}
        <button id="share-btn" class="btn-page" onclick="shareAlert(${id})" style="font-size:0.8rem">🔗 Copiar link</button>
      </div>
    `;
  } catch (e) {
    content.innerHTML = `<div class="error-msg">Erro ao carregar: ${e.message}</div>`;
  }
}

function shareAlert(id) {
  const url = window.location.origin + '/dashboard?alerta=' + id;
  navigator.clipboard.writeText(url).then(() => {
    const btn = document.getElementById('share-btn');
    if (btn) {
      btn.textContent = '✓ Link copiado!';
      setTimeout(() => { btn.textContent = '🔗 Copiar link'; }, 2000);
    }
  });
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
    const q = (document.getElementById('filter-fornecedor-ranking')?.value || '').trim();
    const params = new URLSearchParams({ limit: 15, orderby: state.fornecedoresOrderby });
    if (q) params.set('q', q);
    const res = await fetch(`${BASE}/api/fornecedores/ranking?${params}`);
    if (!res.ok) throw new Error(res.statusText);
    const d = await res.json();

    const isValor = state.fornecedoresOrderby === 'valor';
    const chartItems = [...d.items].sort((a, b) =>
      isValor ? (b.valor_total || 0) - (a.valor_total || 0) : (b.total_contratos || 0) - (a.total_contratos || 0)
    );
    const labels = chartItems.map(r => truncate(r.fornecedor || 'N/I', 32));
    const values = chartItems.map(r => isValor ? r.valor_total : r.total_contratos);

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

    const sortedItems = [...d.items].sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0));

    const tbody = document.getElementById('fornecedores-tbody');
    tbody.innerHTML = sortedItems.map(r => {
      const sancaoIcon = r.tem_sancao ? ' <span title="Fornecedor sancionado (CEIS/CNEP)">⚠️</span>' : '';
      const riskCell = r.risk_score != null
        ? `<span class="badge-risk" style="background:${r.risk_color}20;color:${r.risk_color};border:1px solid ${r.risk_color}40">${r.risk_score} ${r.risk_label}</span>${sancaoIcon}`
        : '—';
      const link = r.fornecedor_ni
        ? `<a href="/fornecedor/${r.fornecedor_ni}" target="_self" class="fornecedor-link">${r.fornecedor || 'N/I'}</a>`
        : (r.fornecedor || 'N/I');
      const perfilLink = r.fornecedor_ni
        ? `<a href="/fornecedor/${r.fornecedor_ni}" class="fornecedor-link" style="font-size:0.78rem">Ver perfil →</a>`
        : '';
      return `
        <tr>
          <td>${link}</td>
          <td>${(r.total_contratos || 0).toLocaleString('pt-BR')}</td>
          <td>${formatCurrency(r.valor_total)}</td>
          <td>${r.alertas || 0}</td>
          <td>${riskCell}</td>
          <td>${perfilLink}</td>
        </tr>
      `;
    }).join('');

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

function toggleObj(btn) {
  const wrap    = btn.closest('.detail-value');
  const preview = wrap.querySelector('.obj-preview');
  const full    = wrap.querySelector('.obj-full');
  const expanded = !full.hidden;
  preview.hidden = !expanded;
  full.hidden    = expanded;
  btn.textContent = expanded ? 'Ver mais' : 'Ver menos';
}

// ─── Órgãos ────────────────────────────────────────────────────────────────

async function loadOrgaos() {
  const cardsEl = document.getElementById('orgaos-cards');
  const tbody   = document.getElementById('orgaos-tbody');
  if (cardsEl) cardsEl.innerHTML = '<div class="loading-msg">Carregando…</div>';
  if (tbody)   tbody.innerHTML   = '<tr><td colspan="8" class="loading-msg">Carregando…</td></tr>';

  try {
    const res = await fetch(`${BASE}/api/orgaos/ranking`);
    if (!res.ok) throw new Error(res.statusText);
    const d = await res.json();
    const items = d.items || [];

    state.orgaosData = {};
    items.forEach(r => { state.orgaosData[r.cnpj] = r; });

    // KPI cards
    const topAlerta = items[0];
    if (cardsEl) {
      cardsEl.innerHTML = `
        <div class="kpi-card">
          <div class="kpi-value">${items.length.toLocaleString('pt-BR')}</div>
          <div class="kpi-label">Órgãos monitorados</div>
          <div class="kpi-hint">Com contratos registrados</div>
        </div>
        <div class="kpi-card highlight">
          <div class="kpi-value" style="font-size:1.1rem;padding-top:0.4rem;line-height:1.4">${topAlerta ? truncate(topAlerta.orgao || '—', 35) : '—'}</div>
          <div class="kpi-label">Órgão com mais alertas</div>
          <div class="kpi-hint">${topAlerta ? `${(topAlerta.total_alertas || 0).toLocaleString('pt-BR')} alertas` : '—'}</div>
        </div>
      `;
    }

    // Chart: top 10 por alertas
    const top10Alertas = [...items].sort((a, b) => (b.total_alertas || 0) - (a.total_alertas || 0)).slice(0, 10);
    if (state.charts.orgaosAlertas) state.charts.orgaosAlertas.destroy();
    state.charts.orgaosAlertas = new Chart(document.getElementById('chart-orgaos-alertas'), {
      type: 'bar',
      data: {
        labels: top10Alertas.map(r => truncate(r.orgao || '—', 30)),
        datasets: [{ data: top10Alertas.map(r => r.total_alertas), backgroundColor: '#ef4444', borderRadius: 4 }],
      },
      options: {
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#737373', font: { size: 11 } }, grid: { color: '#1f1f1f' } },
          y: { ticks: { color: '#a3a3a3', font: { size: 10 } }, grid: { color: '#1f1f1f' } },
        },
      },
    });

    // Chart: top 10 por valor
    const top10Valor = [...items].sort((a, b) => (b.valor_total || 0) - (a.valor_total || 0)).slice(0, 10);
    if (state.charts.orgaosValor) state.charts.orgaosValor.destroy();
    state.charts.orgaosValor = new Chart(document.getElementById('chart-orgaos-valor'), {
      type: 'bar',
      data: {
        labels: top10Valor.map(r => truncate(r.orgao || '—', 30)),
        datasets: [{ data: top10Valor.map(r => r.valor_total), backgroundColor: '#3b82f6', borderRadius: 4 }],
      },
      options: {
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: {
          x: {
            ticks: {
              color: '#737373',
              font: { size: 11 },
              callback: v => v >= 1e9 ? `${(v / 1e9).toFixed(1)}bi` : v >= 1e6 ? `${(v / 1e6).toFixed(0)}mi` : v,
            },
            grid: { color: '#1f1f1f' },
          },
          y: { ticks: { color: '#a3a3a3', font: { size: 10 } }, grid: { color: '#1f1f1f' } },
        },
      },
    });

    // Table
    if (tbody) {
      if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:2rem">Nenhum órgão encontrado.</td></tr>';
      } else {
        tbody.innerHTML = items.map(r => {
          const alertasCell = r.total_alertas > 0 ? `<span class="count-red">${r.total_alertas}</span>` : '<span class="count-gray">0</span>';
          const altaCell    = r.alertas_alta > 0   ? `<span class="count-red">${r.alertas_alta}</span>`   : '<span class="count-gray">0</span>';
          const semLicCell  = r.sem_licitacao > 0  ? `<span class="count-orange">${r.sem_licitacao}</span>` : '<span class="count-gray">0</span>';
          const fracCell    = r.fracionamento > 0  ? `<span class="count-green">${r.fracionamento}</span>`  : '<span class="count-gray">0</span>';
          const cnpjSafe    = (r.cnpj || '').replace(/"/g, '');
          return `
            <tr>
              <td>${truncate(r.orgao || '—', 40)}</td>
              <td style="white-space:nowrap">${(r.total_contratos || 0).toLocaleString('pt-BR')}</td>
              <td style="white-space:nowrap">${formatCurrency(r.valor_total)}</td>
              <td style="white-space:nowrap">${alertasCell}</td>
              <td style="white-space:nowrap">${altaCell}</td>
              <td style="white-space:nowrap">${semLicCell}</td>
              <td style="white-space:nowrap">${fracCell}</td>
              <td><button class="btn-ver-analise btn-ver-orgao" data-cnpj="${cnpjSafe}">Ver contratos</button></td>
            </tr>
          `;
        }).join('');

        tbody.querySelectorAll('.btn-ver-orgao').forEach(btn => {
          btn.addEventListener('click', () => {
            const cnpj = btn.dataset.cnpj;
            const item = state.orgaosData[cnpj];
            openOrgaoDetail(cnpj, item ? (item.orgao || cnpj) : cnpj);
          });
        });
      }
    }

  } catch (e) {
    if (cardsEl) cardsEl.innerHTML = `<div class="error-msg">Erro ao carregar: ${e.message}</div>`;
    if (tbody)   tbody.innerHTML   = `<tr><td colspan="8"><div class="error-msg">Erro: ${e.message}</div></td></tr>`;
  }
}

async function openOrgaoDetail(cnpj, nome) {
  const panel    = document.getElementById('detail-panel');
  const backdrop = document.getElementById('detail-backdrop');
  const content  = document.getElementById('detail-content');

  content.innerHTML = '<div class="loading-msg">Carregando contratos…</div>';
  panel.classList.add('panel-open');
  backdrop.classList.add('backdrop-open');

  try {
    const res = await fetch(`${BASE}/api/orgaos/${encodeURIComponent(cnpj)}/contratos`);
    if (!res.ok) throw new Error(res.statusText);
    const d = await res.json();
    const items = d.items || [];

    const rows = items.map(c => {
      const pncpLink = c.numero_controle_pncp
        ? `<a href="https://pncp.gov.br/app/contratos/${c.numero_controle_pncp}" target="_blank" rel="noopener" class="btn-pncp" style="font-size:0.75rem">PNCP ↗</a>`
        : '';
      return `
        <tr>
          <td style="font-size:0.8rem;line-height:1.4">${truncate(c.objeto || '—', 60)}</td>
          <td style="white-space:nowrap;font-size:0.8rem">${formatCurrency(c.valor_global)}</td>
          <td style="white-space:nowrap;font-size:0.8rem;color:var(--muted)">${formatDate(c.data_assinatura)}</td>
          <td style="white-space:nowrap">${pncpLink}</td>
        </tr>
      `;
    }).join('');

    content.innerHTML = `
      <div class="detail-fornecedor">${nome}</div>
      <div class="detail-badges">
        <span class="badge badge-gray">${items.length} contrato${items.length !== 1 ? 's' : ''}</span>
      </div>
      <div class="table-wrap" style="margin-top:1rem">
        <table>
          <thead>
            <tr>
              <th>Objeto</th>
              <th>Valor</th>
              <th>Data</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${rows || '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:1.5rem">Nenhum contrato encontrado.</td></tr>'}
          </tbody>
        </table>
      </div>
    `;
  } catch (e) {
    content.innerHTML = `<div class="error-msg">Erro ao carregar: ${e.message}</div>`;
  }
}

// ─── Tour ──────────────────────────────────────────────────────────────────

const TOUR_STEPS = [
  {
    title: 'Bem-vindo ao Sentinela RJ',
    text: 'Este sistema monitora contratos públicos do Rio de Janeiro e detecta automaticamente padrões suspeitos. Vamos mostrar como usar?',
    element: null,
    tab: null,
  },
  {
    title: 'Visão geral dos dados',
    text: 'Aqui você vê quantos contratos foram analisados, o valor total movimentado e quantas anomalias foram detectadas.',
    element: '#kpi-cards',
    tab: 'visao-geral',
  },
  {
    title: 'Dados abertos para verificação',
    text: 'Baixe todos os dados em CSV para verificar por conta própria. Os mesmos dados que usamos para detectar as anomalias.',
    element: '.download-bar',
    tab: 'visao-geral',
  },
  {
    title: 'Filtre os alertas',
    text: 'Filtre por tipo de anomalia, severidade, ano ou nome/CNPJ do fornecedor. Clique em qualquer linha para ver detalhes completos do contrato.',
    element: '.filter-bar',
    tab: 'alertas',
  },
  {
    title: 'Linha do tempo',
    text: 'Acompanhe a evolução dos contratos ao longo do tempo. Compare diferentes anos para identificar padrões sazonais ou picos suspeitos.',
    element: '.timeline-controls',
    tab: 'timeline',
  },
  {
    title: 'Ranking de fornecedores',
    text: 'Veja quais empresas concentram mais contratos suspeitos. Clique no nome de qualquer fornecedor para ver o dossiê completo.',
    element: '#chart-fornecedores',
    tab: 'fornecedores',
  },
  {
    title: 'Pronto para explorar!',
    text: 'Use o botão ? no canto inferior direito a qualquer momento para rever este guia.',
    element: null,
    tab: null,
  },
];

let _tourStep   = 0;
let _tourActive = false;

function _initTour() {
  document.body.insertAdjacentHTML('beforeend', `
    <div id="tour-backdrop"></div>
    <svg id="tour-overlay" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <mask id="tour-mask">
          <rect width="100%" height="100%" fill="white"/>
          <rect id="tour-highlight-hole" fill="black" rx="6" x="0" y="0" width="0" height="0"/>
        </mask>
      </defs>
      <rect width="100%" height="100%" fill="rgba(0,0,0,0.78)" mask="url(#tour-mask)"/>
    </svg>
    <div id="tour-card">
      <div class="tour-step-count"></div>
      <h3 class="tour-title"></h3>
      <p class="tour-text"></p>
      <div class="tour-footer">
        <div class="tour-nav">
          <button id="tour-prev" class="tour-btn-nav">← Anterior</button>
          <button id="tour-next" class="tour-btn-nav tour-btn-primary">Próximo →</button>
        </div>
        <button id="tour-skip" class="tour-skip">Pular tour</button>
      </div>
    </div>
  `);

  document.getElementById('tour-prev').addEventListener('click', () => {
    if (_tourStep > 0) _showTourStep(_tourStep - 1);
  });

  document.getElementById('tour-next').addEventListener('click', () => {
    if (_tourStep < TOUR_STEPS.length - 1) {
      _showTourStep(_tourStep + 1);
    } else {
      endTour();
    }
  });

  document.getElementById('tour-skip').addEventListener('click', endTour);

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && _tourActive) endTour();
  });
}

function _fadeIn(el) {
  if (!el) return;
  if (el.style.display !== 'block') {
    el.style.opacity = '0';
    el.style.display = 'block';
  }
  requestAnimationFrame(() => { el.style.opacity = '1'; });
}

function _fadeOut(el) {
  if (!el || el.style.display === 'none') return;
  el.style.opacity = '0';
  setTimeout(() => { if (el.style.opacity === '0') el.style.display = 'none'; }, 320);
}

async function _showTourStep(index) {
  _tourStep = index;
  const step     = TOUR_STEPS[index];
  const overlay  = document.getElementById('tour-overlay');
  const backdrop = document.getElementById('tour-backdrop');
  const card     = document.getElementById('tour-card');
  const hole     = document.getElementById('tour-highlight-hole');

  // Fade out card before switching
  card.style.opacity   = '0';
  card.style.transform = 'translateY(8px)';
  await new Promise(r => setTimeout(r, 200));

  // Switch tab if needed — hide overlay immediately to avoid sliding across tabs
  if (step.tab) {
    overlay.style.opacity = '0';
    document.querySelector(`[data-tab="${step.tab}"]`)?.click();
    await new Promise(r => setTimeout(r, 200));
  }

  // Update card content
  document.querySelector('.tour-step-count').textContent = `Passo ${index + 1} de ${TOUR_STEPS.length}`;
  document.querySelector('.tour-title').textContent       = step.title;
  document.querySelector('.tour-text').textContent        = step.text;
  document.getElementById('tour-prev').disabled           = index === 0;
  document.getElementById('tour-next').textContent        =
    index === TOUR_STEPS.length - 1 ? 'Começar a explorar' : 'Próximo →';

  if (step.element) {
    const el = document.querySelector(step.element);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      await new Promise(r => setTimeout(r, 150));

      const rect = el.getBoundingClientRect();
      const pad  = 8;

      // Set via style so CSS transitions on x/y/width/height animate the hole
      hole.style.x      = (rect.left   - pad) + 'px';
      hole.style.y      = (rect.top    - pad) + 'px';
      hole.style.width  = (rect.width  + pad * 2) + 'px';
      hole.style.height = (rect.height + pad * 2) + 'px';

      _fadeIn(overlay);
      _fadeIn(backdrop);

      const vw    = window.innerWidth;
      const vh    = window.innerHeight;
      const cardW = 300;
      const cardH = card.offsetHeight || 200;

      let top  = rect.bottom + 16;
      if (top + cardH > vh - 16) top = rect.top - cardH - 16;
      if (top < 16) top = 16;

      let left = rect.left + rect.width / 2 - cardW / 2;
      left = Math.max(16, Math.min(left, vw - cardW - 16));

      card.style.top  = top  + 'px';
      card.style.left = left + 'px';
    }
  } else {
    _fadeOut(overlay);
    _fadeIn(backdrop);

    const vw    = window.innerWidth;
    const vh    = window.innerHeight;
    const cardW = card.offsetWidth  || 300;
    const cardH = card.offsetHeight || 200;
    card.style.top  = Math.round(vh / 2 - cardH / 2) + 'px';
    card.style.left = Math.round(vw / 2 - cardW / 2) + 'px';
  }

  // Fade in card (double rAF ensures layout is settled before transition starts)
  requestAnimationFrame(() => requestAnimationFrame(() => {
    card.style.opacity   = '1';
    card.style.transform = 'translateY(0)';
  }));
}

function startTour() {
  if (!document.getElementById('tour-card')) _initTour();
  _tourActive = true;
  const card = document.getElementById('tour-card');
  card.style.opacity   = '0';
  card.style.transform = 'translateY(8px)';
  card.style.display   = 'block';
  _showTourStep(0);
}

function endTour() {
  _tourActive = false;
  const card    = document.getElementById('tour-card');
  const overlay = document.getElementById('tour-overlay');
  const back    = document.getElementById('tour-backdrop');
  if (card) { card.style.opacity = '0'; card.style.transform = 'translateY(8px)'; }
  _fadeOut(overlay);
  _fadeOut(back);
  setTimeout(() => { if (card) card.style.display = 'none'; }, 320);
  localStorage.setItem('sentinela_tour_seen', '1');
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

  // Alertas sort headers
  document.querySelectorAll('#alertas-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      if (state.alertasSort.column === col) {
        state.alertasSort.direction = state.alertasSort.direction === 'asc' ? 'desc' : 'asc';
      } else {
        state.alertasSort.column = col;
        state.alertasSort.direction = 'desc';
      }
      loadAlertas();
    });
  });

  // Year checkboxes
  document.querySelectorAll('.year-check').forEach(cb => {
    cb.addEventListener('change', renderTimeline);
  });

  // Fornecedores search
  const fornRankingEl = document.getElementById('filter-fornecedor-ranking');
  if (fornRankingEl) {
    const debouncedForn = debounce(() => loadFornecedores(), 300);
    fornRankingEl.addEventListener('input', debouncedForn);
  }

  // Fornecedores orderby toggle
  document.querySelectorAll('#fornecedores-toggle .toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#fornecedores-toggle .toggle-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.fornecedoresOrderby = btn.dataset.orderby;
      loadFornecedores();
    });
  });

  // Open alert from share URL param
  const urlParams = new URLSearchParams(window.location.search);
  const alertaId = urlParams.get('alerta');
  if (alertaId) openDetail(parseInt(alertaId, 10));

  // Auto-start tour on first visit
  setTimeout(() => {
    if (!localStorage.getItem('sentinela_tour_seen')) startTour();
  }, 1200);
});
