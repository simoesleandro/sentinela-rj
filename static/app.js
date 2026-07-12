'use strict';

const BASE = '';

const TIPO_LABELS = {
  outlier_valor: 'Outlier de valor',
  concentracao_fornecedor: 'Concentração de fornecedor',
  sem_licitacao_inexigibilidade: 'Inexigibilidade',
  sem_licitacao_emergencia: 'Emergência',
  sem_licitacao_dispensa: 'Dispensa',
  fracionamento_ap: 'Fracionamento',
  fracionamento_empenhos: 'Fracionamento de empenhos',
  asfalto_fatiado: 'Asfalto fatiado',
  contrato_sem_empenho: 'Contrato sem empenho',
  empenho_total_dia_unico: 'Empenho total em dia único',
  empenho_acima_contrato: 'Empenho acima do contrato',
  desconto_zero_licitacao: 'Desconto zero em licitação',
  licitacao_itens_desertos: 'Itens desertos na licitação',
  socio_doou_campanha: 'Sócio doou à campanha',
  socio_compartilhado: 'Sócio compartilhado',
  adesao_carona: 'Adesão a ata (carona)',
  empresa_inativa: 'Empresa inativa',
  capital_social_baixo: 'Capital social baixo',
  empresa_jovem_contrato_grande: 'Empresa jovem, contrato alto',
  watchlist_match: 'Match em Watchlist',
  evolucao_temporal_fornecedor: 'Aceleração contratual',
};

// Rótulo humano de um tipo de alerta. Fallback humaniza qualquer slug novo
// (troca _ por espaço, capitaliza) para nunca exibir o identificador cru.
function labelTipo(tipo) {
  if (TIPO_LABELS[tipo]) return TIPO_LABELS[tipo];
  return String(tipo || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const SEV_LABELS = {
  alta: 'Alta',
  media: 'Média',
  baixa: 'Baixa',
};

function labelSeveridade(sev) {
  return SEV_LABELS[sev] || String(sev || '').replace(/\b\w/g, (c) => c.toUpperCase());
}

const SEV_COLORS = {
  alta: '#ef4444',
  media: '#f97316',
  baixa: '#6b7280',
};

const MOTIVOS_DESCARTE = {
  valor_rotineiro: 'Valor rotineiro para a categoria',
  categoria_diferente: 'Categoria/objeto não se aplica ao detector',
  dados_incompletos: 'Dados insuficientes ou inconsistentes',
  duplicado: 'Alerta duplicado ou já investigado',
  outro: 'Outro motivo',
};

const STATUS_LABELS = {
  aberto: 'Aberto',
  investigando: 'Investigando',
  confirmado: 'Confirmado',
  descartado: 'Descartado',
};

// Ícones SVG monocromáticos (herdam currentColor) — substituem emojis no tom sóbrio.
const ICON = {
  ia: '<svg class="ico" viewBox="0 0 16 16" width="1em" height="1em" fill="currentColor" aria-hidden="true"><path d="M8 1.5l1.15 3.6a2 2 0 0 0 1.3 1.3L14 7.5l-3.55 1.1a2 2 0 0 0-1.3 1.3L8 13.5l-1.15-3.6a2 2 0 0 0-1.3-1.3L2 7.5l3.55-1.1a2 2 0 0 0 1.3-1.3z"/></svg>',
  lupa: '<svg class="ico" viewBox="0 0 16 16" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/></svg>',
  link: '<svg class="ico" viewBox="0 0 16 16" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6.5 9.5 9.5 6.5"/><path d="M7.2 4.6 8.6 3.2a2.7 2.7 0 0 1 3.8 3.8L11 8.4"/><path d="M8.8 11.4 7.4 12.8a2.7 2.7 0 0 1-3.8-3.8L5 7.6"/></svg>',
  check: '<svg class="ico" viewBox="0 0 16 16" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8.5 6.5 12 13 4.5"/></svg>',
  flag: '<svg class="ico" viewBox="0 0 16 16" width="1em" height="1em" fill="currentColor" stroke="none" aria-hidden="true"><rect x="3.4" y="2" width="1.2" height="12" rx="0.6"/><path d="M5.2 2.8h7.2l-1.7 2.5 1.7 2.5H5.2z"/></svg>',
};

// Selo de conflito de interesse (sócio-servidor) cruzado com o fornecedor do
// alerta. `forte` = há candidato com lotação × órgão contratante. Match é por
// nome, sem certeza — o selo é "candidato a", nunca acusação.
function conflitoBadge(conflito) {
  if (!conflito || !conflito.qtd) return '';
  const n = conflito.qtd;
  const plural = n > 1 ? 's' : '';
  const titulo = conflito.forte
    ? `Sócio de empresa contratada com lotação no órgão contratante (${n} candidato${plural} a conflito). Indício forte — match por nome, verificar identidade.`
    : `Fornecedor tem ${n} sócio${plural} candidato${plural} a servidor público. Match por nome — verificar.`;
  const rotulo = conflito.forte ? 'Sócio-servidor' : 'Sócio-servidor?';
  return `<span class="badge-conflito${conflito.forte ? ' forte' : ''}" title="${esc(titulo)}">${ICON.flag} ${rotulo}</span>`;
}

const STATUS_BADGE_CLASS = {
  aberto: 'status-aberto',
  investigando: 'status-investigando',
  confirmado: 'status-confirmado',
  descartado: 'status-descartado',
};

const TIPO_TOOLTIPS = {
  outlier_valor: 'Contrato com valor muito acima da média histórica para o mesmo tipo de serviço. Pode indicar sobrepreço.',
  concentracao_fornecedor: 'Empresa recebeu muitos contratos em pouco tempo do mesmo órgão. Pode indicar favorecimento.',
  sem_licitacao_inexigibilidade: 'Contrato firmado sem licitação por alegação de fornecedor exclusivo. Precisa de justificativa sólida.',
  sem_licitacao_emergencia: 'Contrato emergencial sem licitação. Emergências reais existem, mas o uso excessivo é suspeito.',
  sem_licitacao_dispensa: 'Contrato dispensado de licitação por valor baixo ou outras condições legais.',
  fracionamento_ap: 'Mesmo serviço dividido entre várias empresas por região. Pode ser tentativa de driblar o limite de licitação.',
};

const MUNICIPIO_STORAGE_KEY = 'sentinela_municipio_ibge';
const MUNICIPIO_FILTER_PREFIXES = [
  '/api/stats', '/api/anomalias', '/api/alertas/agrupados', '/api/alertas/triagem',
  '/api/timeline', '/api/fornecedores/ranking', '/api/fornecedores/investigados',
  '/api/orgaos/ranking', '/api/socios/compartilhados', '/api/export/',
];

const state = {
  currentTab: 'visao-geral',
  municipioIbge: localStorage.getItem(MUNICIPIO_STORAGE_KEY) || '',
  municipioNome: '',
  coletaIbge: '',
  coletaNome: '',
  coletaRotulo: '',
  monitorados: [],
  alertasPage: 1,
  alertasFiltros: { status: 'fila', tipo: '', severidade: '', ano: '', fornecedor: '', valorMin: '', conflito: '' },
  alertasSort: { column: 'prioridade', direction: 'desc' },
  charts: {},
  tabLoaded: {},
  timelineData: null,
  timelineGranularity: 'month',
  fornecedoresOrderby: 'valor',
  orgaosData: {},
};

function shouldFilterMunicipio(path) {
  return MUNICIPIO_FILTER_PREFIXES.some(prefix => path.startsWith(prefix));
}

function apiUrl(path) {
  if (!state.municipioIbge || !shouldFilterMunicipio(path) || path.includes('municipio_ibge=')) {
    return `${BASE}${path}`;
  }
  const sep = path.includes('?') ? '&' : '?';
  return `${BASE}${path}${sep}municipio_ibge=${encodeURIComponent(state.municipioIbge)}`;
}

function updateExportLinks() {
  document.querySelectorAll('.btn-download').forEach(link => {
    const base = link.getAttribute('data-export-base') || link.getAttribute('href')?.split('?')[0];
    if (!base) return;
    link.setAttribute('data-export-base', base);
    link.href = state.municipioIbge ? `${base}?municipio_ibge=${encodeURIComponent(state.municipioIbge)}` : base;
  });
}

function updateMunicipioHeader() {
  const subtitle = document.getElementById('header-subtitle');
  const hint = document.getElementById('municipio-coleta-hint');
  if (subtitle && state.municipioIbge) {
    subtitle.textContent = `Exibindo dados de ${state.municipioNome || 'município ' + state.municipioIbge}`;
  }
  if (hint) {
    const n = state.monitorados?.length || 0;
    const coletaLabel = state.coletaRotulo || state.coletaNome || state.coletaIbge;
    if (n > 1) {
      hint.textContent = `Coleta automática: ${n} municípios (Rio é prioridade 1)`;
    } else if (state.coletaIbge) {
      hint.textContent = state.municipioIbge === state.coletaIbge
        ? `Coleta PNCP: ${coletaLabel}`
        : `Coleta PNCP: ${coletaLabel} · visualizando outro município`;
    }
  }
}

function reloadDashboardData() {
  state.tabLoaded = {};
  updateExportLinks();
  updateMunicipioHeader();
  loadTab(state.currentTab);
  state.tabLoaded[state.currentTab] = true;
}

async function initMunicipioSelector() {
  const select = document.getElementById('municipio-select');
  if (!select) return;
  try {
    const res = await fetch(`${BASE}/api/municipios`);
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    state.coletaIbge = data.coleta_ibge || '';
    state.coletaNome = data.coleta_nome || '';
    state.monitorados = data.monitorados || [];
    state.coletaRotulo = data.coleta_rotulo || '';

    const items = data.items || [];
    if (!state.municipioIbge && state.coletaIbge) {
      state.municipioIbge = state.coletaIbge;
    }
    const hasSaved = items.some(i => i.ibge === state.municipioIbge);
    if (!hasSaved && state.coletaIbge) {
      state.municipioIbge = state.coletaIbge;
    }

    select.innerHTML = [
      '<option value="">Todos os municípios no banco</option>',
      ...items.map(i => {
        const label = `${i.nome || i.ibge} (${(i.contratos || 0).toLocaleString('pt-BR')} contratos)`;
        return `<option value="${escapeHtml(i.ibge)}">${escapeHtml(label)}</option>`;
      }),
    ].join('');
    select.value = state.municipioIbge || '';

    const selected = items.find(i => i.ibge === state.municipioIbge);
    state.municipioNome = selected?.nome || state.coletaNome || '';
    if (state.municipioIbge) {
      localStorage.setItem(MUNICIPIO_STORAGE_KEY, state.municipioIbge);
    }

    select.addEventListener('change', () => {
      state.municipioIbge = select.value;
      const opt = items.find(i => i.ibge === state.municipioIbge);
      state.municipioNome = opt?.nome || '';
      if (state.municipioIbge) {
        localStorage.setItem(MUNICIPIO_STORAGE_KEY, state.municipioIbge);
      } else {
        localStorage.removeItem(MUNICIPIO_STORAGE_KEY);
      }
      reloadDashboardData();
    });

    updateMunicipioHeader();
    updateExportLinks();
  } catch (e) {
    select.innerHTML = '<option value="">Município indisponível</option>';
  }
}

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
  let s = String(str);
  // 'YYYYMMDD' compacto (ex.: período do pipeline PNCP) → normaliza p/ ISO
  if (/^\d{8}$/.test(s)) {
    s = `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
  }
  // Handles 'YYYY-MM-DD' and ISO strings
  const d = new Date(s.length === 10 ? s + 'T12:00:00' : s);
  if (isNaN(d.getTime())) return str;
  return d.toLocaleDateString('pt-BR');
}

function formatDateTime(str) {
  if (!str) return '—';
  // Aceita 'YYYY-MM-DD HH:MM:SS' (SQLite) e ISO; devolve data + hora pt-BR.
  const d = new Date(String(str).replace(' ', 'T'));
  if (isNaN(d.getTime())) return String(str);
  return d.toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function truncate(str, n) {
  if (!str) return '—';
  return str.length > n ? str.slice(0, n) + '…' : str;
}

function renderTransparenciaRjHtml(items) {
  if (!items || !items.length) return '';
  const rows = items.map(e => `
    <tr>
      <td>${formatDate(e.data_lancamento)}</td>
      <td style="white-space:nowrap">${formatCurrency(e.valor)}</td>
      <td>${esc(e.orgao || '—')}</td>
      <td title="${esc(e.descricao || '')}">${esc(truncate(e.descricao, 72))}</td>
      <td>${esc(e.documento || '—')}</td>
      <td>${e.score != null ? `${Math.round(e.score * 100)}%` : '—'}</td>
    </tr>
  `).join('');
  return `
    <div class="detail-block transparencia-rj-block">
      <label>Transparência RJ — empenhos vinculados</label>
      <p class="section-note">Cruzamento automático fornecedor + valor (PNCP × portal RJ).</p>
      <div class="transp-rj-table-wrap">
        <table class="transp-rj-table">
          <thead>
            <tr>
              <th>Data</th><th>Valor</th><th>Órgão</th><th>Descrição</th><th>Doc.</th><th>Match</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

const esc = escapeHtml;

// Remove marcadores de markdown que a IA às vezes emite (**negrito**, *itálico*,
// ### títulos, listas) — o parecer é renderizado como texto puro, não markdown.
function limparMarkdown(str) {
  return String(str || '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')  // **negrito**
    .replace(/__([^_]+)__/g, '$1')       // __negrito__
    .replace(/\*([^*]+)\*/g, '$1')       // *itálico*
    .replace(/(^|\s)#{1,6}\s+/g, '$1')  // ### títulos
    .replace(/[*_#]+/g, '')              // marcadores soltos remanescentes
    .replace(/[ \t]{2,}/g, ' ')
    .trim();
}

async function api(path, { method = 'GET', body, ...rest } = {}) {
  const init = { method, ...rest };
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json', ...(rest.headers || {}) };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(apiUrl(path), init);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || res.statusText || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  return res;
}

// ─── Sessão / autenticação ──────────────────────────────────────────────────

const sessao = { usuario: null, ia: null };

function irParaLogin() {
  location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
}

async function carregarSessao() {
  try {
    const res = await fetch(`${BASE}/api/auth/me`);
    const data = await res.json();
    sessao.usuario = data.usuario;
    sessao.ia = data.ia;
  } catch {
    sessao.usuario = null;
    sessao.ia = null;
  }
  renderAuthArea();
}

function renderAuthArea() {
  // Esconde a coluna de seleção em lote para anônimos (a triagem é autenticada).
  document.body.classList.toggle('is-anon', !sessao.usuario);
  const area = document.getElementById('auth-area');
  if (!area) return;
  if (!sessao.usuario) {
    area.innerHTML = `<a href="/login?next=${encodeURIComponent(location.pathname)}" class="auth-link">Entrar</a>`;
    return;
  }
  const u = sessao.usuario;
  const nome = esc(u.nome || u.email);
  let cota = '';
  let reenviar = '';
  if (sessao.ia) {
    if (sessao.ia.ilimitado) {
      cota = '<span class="auth-cota auth-admin">IA ilimitada</span>';
    } else if (sessao.ia.verificar) {
      cota = '<span class="auth-cota auth-warn" title="Confirme seu email para liberar a IA">⚠ Confirme seu email</span>';
      reenviar = '<button type="button" id="auth-reenviar" class="auth-link">Reenviar</button>';
    } else {
      cota = `<span class="auth-cota">IA: ${sessao.ia.restante}/${sessao.ia.limite} hoje</span>`;
    }
  }
  area.innerHTML = `
    <span class="auth-user" title="${esc(u.email)}">Olá, ${nome}</span>
    ${cota}
    ${reenviar}
    <button type="button" id="auth-logout" class="auth-link">Sair</button>
  `;
  document.getElementById('auth-logout')?.addEventListener('click', async () => {
    await fetch(`${BASE}/api/auth/logout`, { method: 'POST' });
    sessao.usuario = null;
    sessao.ia = null;
    renderAuthArea();
  });
  document.getElementById('auth-reenviar')?.addEventListener('click', reenviarConfirmacao);
}

async function reenviarConfirmacao() {
  const btn = document.getElementById('auth-reenviar');
  if (btn) { btn.disabled = true; btn.textContent = 'Enviando…'; }
  try {
    const res = await fetch(`${BASE}/api/auth/reenviar`, { method: 'POST' });
    const data = await res.json();
    if (data.email_enviado) {
      alert('Link de confirmação reenviado! Verifique seu email — e confira a pasta de SPAM se não chegar.');
    } else if (data.email_erro) {
      alert('Não consegui enviar o email: ' + data.email_erro);
    } else {
      alert('Confirmação processada. Se não chegar, verifique o spam.');
    }
  } catch {
    alert('Falha ao reenviar. Tente novamente.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Reenviar'; }
  }
}

const VEREDITO_MARKER = '[Recomendação de Veredito]';

function parseVereditoIa(narrativa) {
  const texto = String(narrativa || '').trim();
  if (!texto) return { corpo: '', veredito: null, statusSugerido: null, justificativa: null };

  const idx = texto.indexOf(VEREDITO_MARKER);
  if (idx === -1) {
    return { corpo: texto, veredito: null, statusSugerido: null, justificativa: null };
  }

  const corpo = texto.slice(0, idx).trim();
  const veredito = texto.slice(idx).trim();
  const statusMatch = veredito.match(
    /Status sugerido:\s*(Aberto|Investigando|Confirmado|Descartado)/i
  );
  const statusSugerido = statusMatch ? statusMatch[1].toLowerCase() : null;
  const justMatch = veredito.match(/Justificativa:\s*(.+)/is);
  const justificativa = justMatch ? justMatch[1].trim() : null;

  return { corpo, veredito, statusSugerido, justificativa };
}

const PLAUS_META = {
  provavel_problema: { label: 'Provável problema', cls: 'plaus-alerta' },
  provavel_explicavel: { label: 'Provavelmente explicável', cls: 'plaus-ok' },
  inconclusivo: { label: 'Inconclusivo', cls: 'plaus-neutro' },
};

function renderParecerHtml(parecer, provedorNome) {
  if (!parecer) return '<p class="narrativa-empty">Nenhum parecer gerado.</p>';
  const plaus = PLAUS_META[parecer.plausibilidade] || PLAUS_META.inconclusivo;
  const statusKey = String(parecer.status_sugerido || '').toLowerCase();
  const statusLabel = STATUS_LABELS[statusKey] || statusKey || '—';
  const motivoLabel = parecer.motivo_sugerido ? (MOTIVOS_DESCARTE[parecer.motivo_sugerido] || '') : '';
  return `
    <div class="parecer-card">
      <div class="parecer-head">
        <span class="plaus-pill ${plaus.cls}">${plaus.label}</span>
        <span class="parecer-prov">${provedorNome ? 'IA · ' + escapeHtml(provedorNome) : 'IA'}</span>
      </div>
      <p class="parecer-analise">${escapeHtml(limparMarkdown(parecer.analise))}</p>
      <div class="parecer-sug">
        <span class="parecer-sug-txt">Sugestão: <strong>${escapeHtml(statusLabel)}</strong>${motivoLabel ? ` — ${escapeHtml(motivoLabel)}` : ''}</span>
        <button type="button" id="btn-aplicar-parecer" class="btn-aplicar-veredito">Aplicar sugestão</button>
      </div>
    </div>`;
}

function tipoBadge(tipo) {
  const label = labelTipo(tipo);
  // Cor é reservada para severidade e status (o que define prioridade de
  // triagem). O tipo é um rótulo neutro — evita o arco-íris e a colisão de
  // "verde = ok" num tipo grave. (PRODUCT.md: severidade com sobriedade.)
  const cls = 'gray';
  const tooltip = TIPO_TOOLTIPS[tipo];
  if (tooltip) {
    return `<span class="badge badge-${cls} tooltip-wrap">${label}<span class="tooltip-text">${tooltip}</span></span>`;
  }
  return `<span class="badge badge-${cls}">${label}</span>`;
}

function sevBadge(sev) {
  const map = { alta: 'red', media: 'orange', baixa: 'gray' };
  const cls = map[sev] || 'gray';
  const label = sev ? labelSeveridade(sev) : '—';
  return `<span class="badge badge-${cls}">${label}</span>`;
}

function statusBadge(status) {
  const st = status || 'aberto';
  const cls = STATUS_BADGE_CLASS[st] || 'status-aberto';
  const label = STATUS_LABELS[st] || st;
  return `<span class="badge ${cls}">${label}</span>`;
}

function renderTriagemResumo(resumo) {
  const el = document.getElementById('triagem-resumo');
  if (!el || !resumo) return;
  const chips = [
    ['fila', 'Fila', resumo.fila, true],
    ['aberto', 'Abertos', resumo.aberto, false],
    ['investigando', 'Investigando', resumo.investigando, false],
    ['confirmado', 'Confirmados', resumo.confirmado, false],
    ['descartado', 'Descartados', resumo.descartado, false],
  ];
  el.innerHTML = chips.map(([key, label, n, primary]) => `
    <button type="button" class="triagem-chip ${primary ? 'triagem-chip-primary' : ''} ${state.alertasFiltros.status === key ? 'active' : ''}" data-status="${key}">
      <span class="triagem-chip-label">${label}</span>
      <span class="triagem-chip-value">${(n || 0).toLocaleString('pt-BR')}</span>
    </button>
  `).join('');
  el.querySelectorAll('.triagem-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      state.alertasFiltros.status = chip.dataset.status;
      state.alertasPage = 1;
      const sel = document.getElementById('filter-status');
      if (sel) sel.value = chip.dataset.status;
      loadAlertas();
    });
  });
}

function showError(containerId, msg) {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = `<div class="error-msg">Erro ao carregar: ${msg}</div>`;
}

// Chart.js anima com 1000ms por padrão — motion decorativo de page-load que
// disputa a main-thread. Encurtamos para um draw rápido e respeitamos
// prefers-reduced-motion (que o Chart.js, controlado por JS, ignora sozinho).
if (window.Chart) {
  const _reduzMovimento = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  Chart.defaults.animation = _reduzMovimento ? false : { duration: 300 };
}

function chartOptions(extraX = {}, extraY = {}) {
  return {
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: '#8a8a8a', font: { size: 11 } }, grid: { color: '#1f1f1f' }, ...extraX },
      y: { ticks: { color: '#8a8a8a', font: { size: 11 } }, grid: { color: '#1f1f1f' }, ...extraY },
    },
  };
}

// ─── Tab management ────────────────────────────────────────────────────────

function setupTabs() {
  // button.tab-btn (não .tab-btn) exclui o link de navegação para
  // /conflitos-interesse, que reaproveita a classe visual mas é uma página
  // separada, não uma aba desta SPA.
  document.querySelectorAll('button.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;

      document.querySelectorAll('button.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      document.querySelectorAll('.tab-section').forEach(s => s.classList.remove('active'));
      document.getElementById(`tab-${tab}`).classList.add('active');

      state.currentTab = tab;

      if (!state.tabLoaded[tab]) {
        loadTab(tab);
        state.tabLoaded[tab] = true;
      } else if (tab === 'rede') {
        loadComparadorCatalogo();
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
    case 'rede':
      loadComparadorCatalogo();
      loadRede();
      break;
    case 'monitoramento':
      loadMonitoramento();
      break;
    case 'empenhos':
      loadEmpenhos();
      break;
  }
}

// ─── Stats ─────────────────────────────────────────────────────────────────

async function loadStats() {
  const container = document.getElementById('kpi-cards');
  container.innerHTML = '<div class="loading-msg">Carregando…</div>';
  try {
    const res = await fetch(apiUrl('/api/stats'));
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
      <div class="kpi-card highlight kpi-clickable" role="button" tabindex="0" title="Ver todos os alertas abertos" onclick="goToAlertasFiltrado({status:'aberto'})" onkeydown="if(event.key==='Enter')goToAlertasFiltrado({status:'aberto'})">
        <div class="kpi-value">${(d.alertas_total || 0).toLocaleString('pt-BR')}</div>
        <div class="kpi-label">Anomalias Detectadas</div>
        <div class="kpi-hint">Ver alertas abertos →</div>
      </div>
      <div class="kpi-card kpi-clickable" role="button" tabindex="0" title="Ver alertas de risco alto" onclick="goToAlertasFiltrado({severidade:'alta'})" onkeydown="if(event.key==='Enter')goToAlertasFiltrado({severidade:'alta'})">
        <div class="kpi-value" style="color:#ef4444">${(d.alertas_alta || 0).toLocaleString('pt-BR')}</div>
        <div class="kpi-label">Risco Alto</div>
        <div class="kpi-hint">Ver severidade alta →</div>
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
    loadPipelineStatus();
  } catch (e) {
    showError('kpi-cards', e.message);
    loadPipelineStatus();
  }
}

// ─── Charts: Tipos + Severidade ────────────────────────────────────────────

async function loadChartTipos() {
  try {
    const res = await fetch(apiUrl('/api/anomalias/por-tipo'));
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
        labels: Object.keys(byTipo).map(t => labelTipo(t)),
        datasets: [{
          data: Object.values(byTipo),
          backgroundColor: '#64748b',
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
        labels: sevKeys.map(s => labelSeveridade(s)),
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

// Seleção para triagem em lote. `sel` guarda ids de alertas marcados;
// `statusMap` mapeia id→status atual (para decidir as transições na execução).
const loteState = { sel: new Set(), statusMap: new Map() };

// Popula o filtro de ano de 2023 (início da base) ao ano corrente, sem
// hardcode — assim vira o ano novo sozinho. Preserva a opção "Todos".
function populateYearFilter() {
  const el = document.getElementById('filter-ano');
  if (!el || el._populated) return;
  const anoAtual = new Date().getFullYear();
  const ANO_INICIAL = 2023;
  const anos = [];
  for (let a = Math.max(anoAtual, ANO_INICIAL); a >= ANO_INICIAL; a--) anos.push(a);
  el.insertAdjacentHTML('beforeend',
    anos.map(a => `<option value="${a}">${a}</option>`).join(''));
  el._populated = true;
}

function setupFilters() {
  populateYearFilter();
  const debouncedLoad = debounce(() => {
    state.alertasPage = 1;
    limparLote();
    loadAlertas();
  }, 300);

  const statusEl = document.getElementById('filter-status');
  if (statusEl && !statusEl._bound) {
    statusEl.value = state.alertasFiltros.status || 'fila';
    statusEl.addEventListener('change', () => {
      state.alertasFiltros.status = statusEl.value;
      state.alertasPage = 1;
      limparLote();
      loadAlertas();
    });
    statusEl._bound = true;
  }

  [
    ['filter-tipo',       'tipo'],
    ['filter-severidade', 'severidade'],
    ['filter-ano',        'ano'],
    ['filter-conflito',   'conflito'],
  ].forEach(([id, key]) => {
    const el = document.getElementById(id);
    if (el && !el._bound) {
      el.addEventListener('change', () => {
        state.alertasFiltros[key] = el.value;
        state.alertasPage = 1;
        limparLote();
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

  const selAll = document.getElementById('lote-select-all');
  if (selAll && !selAll._bound) {
    selAll.addEventListener('change', () => {
      const tbody = document.getElementById('alertas-tbody');
      const ids = [...tbody.querySelectorAll('.lote-cb-item')].map(cb => parseInt(cb.dataset.id, 10));
      ids.forEach(id => { if (selAll.checked) loteState.sel.add(id); else loteState.sel.delete(id); });
      syncLoteUI(tbody);
    });
    selAll._bound = true;
  }
}

async function loadAlertas() {
  const tbody = document.getElementById('alertas-tbody');
  tbody.innerHTML = '<tr><td colspan="8" class="loading-msg">Carregando…</td></tr>';

  try {
    const params = new URLSearchParams({ page: state.alertasPage, per_page: 20 });
    const f = state.alertasFiltros;
    if (f.status)     params.set('status',     f.status);
    if (f.tipo)       params.set('tipo',       f.tipo);
    if (f.severidade) params.set('severidade', f.severidade);
    if (f.ano)        params.set('ano',        f.ano);
    if (f.fornecedor) params.set('fornecedor', f.fornecedor);
    if (f.valorMin)   params.set('valor_min',  f.valorMin);
    if (f.conflito)   params.set('conflito',   f.conflito);

    const res = await fetch(apiUrl(`/api/alertas/agrupados?${params}`));
    if (!res.ok) throw new Error(res.statusText);
    const d = await res.json();

    const resumoRes = await fetch(apiUrl('/api/alertas/triagem?per_page=1&status=fila'));
    if (resumoRes.ok) {
      const triagem = await resumoRes.json();
      renderTriagemResumo(triagem.resumo);
    }

    if (!d.items.length) {
      tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:2rem">Nenhuma anomalia encontrada.</td></tr>';
    } else {
      const SEV_SORT_VAL = { alta: 3, media: 2, baixa: 1 };
      const groups = [...d.items];
      if (state.alertasSort.column) {
        const dir = state.alertasSort.direction === 'asc' ? 1 : -1;
        groups.sort((a, b) => {
          switch (state.alertasSort.column) {
            case 'prioridade': return dir * ((a.score_composto || 0) - (b.score_composto || 0));
            case 'valor':      return dir * ((a.valor_total || 0) - (b.valor_total || 0));
            case 'severidade': return dir * ((SEV_SORT_VAL[a.severidade] || 0) - (SEV_SORT_VAL[b.severidade] || 0));
            case 'data':       return dir * ((a.data_mais_recente || '').localeCompare(b.data_mais_recente || ''));
            case 'fornecedor': return dir * (a.fornecedor || '').localeCompare(b.fornecedor || '');
            case 'tipo':       return dir * (a.tipo || '').localeCompare(b.tipo || '');
            default:           return 0;
          }
        });
      }
      const logado = !!sessao.usuario;
      const flatIds = [];
      loteState.statusMap.clear();
      const html = [];
      groups.forEach(grupo => {
        const countBadge = grupo.ocorrencias > 1
          ? `<span class="badge-count">${grupo.ocorrencias} contratos</span>`
          : `<span class="badge-count badge-count-single">1 contrato</span>`;
        const firstId = grupo.alertas[0]?.id ?? '';
        const analisBtn = firstId !== ''
          ? `<button class="btn-ver-detalhes btn-acao-principal" data-id="${firstId}" title="Abrir triagem, narrativa IA e dossiê">Detalhes</button>`
          : '<span style="color:var(--muted)">—</span>';
        const gid = grupo.grupo_id;

        const prioPct = Math.round((grupo.score_composto || 0) * 100);
        const totalG = (grupo.alertas || []).length;
        const triadosG = (grupo.alertas || []).filter(
          a => a.status === 'confirmado' || a.status === 'descartado'
        ).length;
        const progressoHtml = totalG > 1
          ? `<div class="grupo-progresso${triadosG === totalG ? ' completo' : ''}" title="Cada contrato do grupo é triado individualmente">${triadosG}/${totalG} triados</div>`
          : '';
        const grupoIds = (grupo.alertas || []).map(a => a.id);
        const grupoCb = logado
          ? `<input type="checkbox" class="lote-cb-grupo" data-ids="${grupoIds.join(',')}" aria-label="Selecionar todos os contratos deste grupo" title="Selecionar todos os contratos deste grupo">`
          : '';
        html.push(`
          <tr class="row-group" data-grupo="${gid}">
            <td class="cell-select">${grupoCb}<button class="expand-btn" data-grupo="${gid}">▶</button></td>
            <td><span class="prio-score" title="Score composto">${prioPct}</span></td>
            <td>${tipoBadge(grupo.tipo)}</td>
            <td>${sevBadge(grupo.severidade)}</td>
            <td>${statusBadge(grupo.status)}${progressoHtml}</td>
            <td style="white-space:nowrap;font-weight:500">${formatCurrency(grupo.valor_total)}</td>
            <td>${truncate(grupo.fornecedor || '—', 30)} ${countBadge}${conflitoBadge(grupo.conflito)}</td>
            <td style="white-space:nowrap;color:var(--muted)">${formatDate(grupo.data_mais_recente)}</td>
            <td>${analisBtn}</td>
          </tr>
        `);

        grupo.alertas.forEach(a => {
          flatIds.push(a.id);
          loteState.statusMap.set(a.id, a.status);
          const pncpBtn = a.numero_controle_pncp
            ? `<a href="https://pncp.gov.br/app/contratos/${a.numero_controle_pncp}" target="_blank" rel="noopener" class="btn-pncp">PNCP ↗</a>`
            : '';
          const itemCb = logado
            ? `<input type="checkbox" class="lote-cb-item" data-id="${a.id}" aria-label="Selecionar este contrato">`
            : '';
          html.push(`
            <tr class="row-detail" data-grupo="${gid}">
              <td colspan="9">
                <div class="detail-compact">
                  ${itemCb}
                  <span class="detail-compact-status">${statusBadge(a.status)}</span>
                  <span class="detail-compact-valor">${formatCurrency(a.valor_referencia)}</span>
                  <span class="detail-compact-data">${formatDate(a.data_assinatura)}</span>
                  <span class="detail-compact-objeto" title="${esc(a.objeto || '')}">${esc(truncate(a.objeto || '—', 60))}</span>
                  <div class="detail-compact-actions">
                    ${pncpBtn}
                    <button class="btn-ver-detalhes btn-acao-principal" data-id="${a.id}">Detalhes e IA</button>
                  </div>
                </div>
              </td>
            </tr>
          `);
        });
      });

      tbody.innerHTML = html.join('');
      state.alertaFlatOrder = flatIds;

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
          if (e.target.closest('.btn-ver-detalhes, .btn-ver-analise, .btn-acao-principal, .lote-cb-grupo, .cell-select')) return;
          expandToggle();
        });
      });

      tbody.querySelectorAll('.btn-ver-analise, .btn-ver-detalhes, .btn-acao-principal').forEach(btn => {
        btn.addEventListener('click', e => {
          e.stopPropagation();
          openDetail(parseInt(btn.dataset.id, 10));
        });
      });

      wireLoteCheckboxes(tbody);
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

    // Rótulos das colunas ordenáveis. Todas recebem o mesmo indicador neutro
    // (⇅) quando inativas e ▲/▼ quando ativas — consistência entre colunas.
    const SORT_BASE = {
      prioridade: 'Prioridade', tipo: 'Tipo', severidade: 'Severidade',
      valor: 'Valor', fornecedor: 'Fornecedor', data: 'Data',
    };
    document.querySelectorAll('#alertas-table th[data-sort]').forEach(th => {
      const col = th.dataset.sort;
      const active = col === state.alertasSort.column;
      th.classList.toggle('sort-active', active);
      const arrow = active ? (state.alertasSort.direction === 'asc' ? '▲' : '▼') : '⇅';
      th.innerHTML = `${SORT_BASE[col]}<span class="sort-ind">${arrow}</span>`;
    });

    const indicator = document.getElementById('page-indicator');
    if (indicator) indicator.textContent = `Página ${d.page} de ${Math.max(1, d.pages)}`;

    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');
    if (btnPrev) btnPrev.disabled = d.page <= 1;
    if (btnNext) btnNext.disabled = d.page >= d.pages;

  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8"><div class="error-msg">Erro: ${e.message}</div></td></tr>`;
  }
}

// ─── Triagem em lote ───────────────────────────────────────────────────────
// A fila tem ~1.600 alertas triados um-a-um. O lote deixa o fiscal marcar
// vários (por grupo de fornecedor ou individualmente) e descartar / mover para
// "investigando" de uma vez — o maior ganho de eficiência na triagem.

function wireLoteCheckboxes(tbody) {
  tbody.querySelectorAll('.lote-cb-item').forEach(cb => {
    const id = parseInt(cb.dataset.id, 10);
    cb.checked = loteState.sel.has(id);
    cb.addEventListener('change', () => {
      if (cb.checked) loteState.sel.add(id); else loteState.sel.delete(id);
      syncLoteUI(tbody);
    });
  });
  tbody.querySelectorAll('.lote-cb-grupo').forEach(cb => {
    const ids = (cb.dataset.ids || '').split(',').filter(Boolean).map(Number);
    cb.addEventListener('change', () => {
      ids.forEach(id => { if (cb.checked) loteState.sel.add(id); else loteState.sel.delete(id); });
      syncLoteUI(tbody);
    });
  });
  syncLoteUI(tbody);
}

// Reflete o estado da seleção nos checkboxes (item, grupo, "todos") e na barra.
function syncLoteUI(tbody) {
  tbody = tbody || document.getElementById('alertas-tbody');
  if (!tbody) return;
  tbody.querySelectorAll('.lote-cb-item').forEach(cb => {
    cb.checked = loteState.sel.has(parseInt(cb.dataset.id, 10));
  });
  tbody.querySelectorAll('.lote-cb-grupo').forEach(cb => {
    const ids = (cb.dataset.ids || '').split(',').filter(Boolean).map(Number);
    const marcados = ids.filter(id => loteState.sel.has(id)).length;
    cb.checked = marcados > 0 && marcados === ids.length;
    cb.indeterminate = marcados > 0 && marcados < ids.length;
  });
  const selAll = document.getElementById('lote-select-all');
  if (selAll) {
    const visiveis = [...tbody.querySelectorAll('.lote-cb-item')].map(cb => parseInt(cb.dataset.id, 10));
    const marcados = visiveis.filter(id => loteState.sel.has(id)).length;
    selAll.checked = visiveis.length > 0 && marcados === visiveis.length;
    selAll.indeterminate = marcados > 0 && marcados < visiveis.length;
  }
  renderLoteBar();
}

function limparLote() {
  loteState.sel.clear();
  syncLoteUI();
}

function renderLoteBar() {
  const bar = document.getElementById('lote-bar');
  if (!bar) return;
  const n = loteState.sel.size;
  if (!n) { bar.classList.remove('visible'); bar.setAttribute('hidden', ''); return; }
  bar.removeAttribute('hidden');
  bar.classList.add('visible');
  const motivoOpts = Object.entries(MOTIVOS_DESCARTE)
    .map(([k, lbl]) => `<option value="${k}">${lbl}</option>`).join('');
  bar.innerHTML = `
    <span class="lote-bar-count"><strong>${n}</strong> ${n === 1 ? 'contrato selecionado' : 'contratos selecionados'}</span>
    <div class="lote-bar-actions">
      <label class="lote-bar-motivo">Motivo do descarte
        <select id="lote-motivo"><option value="">Selecione…</option>${motivoOpts}</select>
      </label>
      <button type="button" class="btn-page lote-btn-descartar" id="lote-descartar">Descartar</button>
      <button type="button" class="btn-page lote-btn-invest" id="lote-investigar">Marcar investigando</button>
      <button type="button" class="btn-link" id="lote-limpar">Limpar</button>
    </div>
    <div id="lote-progresso" class="lote-progresso" hidden></div>`;
  document.getElementById('lote-limpar').addEventListener('click', limparLote);
  document.getElementById('lote-investigar').addEventListener('click', () => executarLote('investigando'));
  document.getElementById('lote-descartar').addEventListener('click', () => {
    const motivo = document.getElementById('lote-motivo').value;
    if (!motivo) {
      const sel = document.getElementById('lote-motivo');
      sel.classList.add('campo-invalido');
      sel.focus();
      return;
    }
    executarLote('descartado', motivo);
  });
}

// Executa uma transição de status em cada alerta selecionado, respeitando a
// máquina de estados (aberto→investigando→confirmado; descarte precisa motivo).
// Roda com concorrência limitada e mostra progresso; recarrega ao final.
async function executarLote(alvo, motivo) {
  const ids = [...loteState.sel];
  const prog = document.getElementById('lote-progresso');
  const botoes = document.querySelectorAll('#lote-bar button, #lote-bar select');
  botoes.forEach(b => b.disabled = true);
  let ok = 0, pulados = 0, falhas = 0, feitos = 0;
  const mostrar = () => {
    if (!prog) return;
    prog.hidden = false;
    prog.textContent = `Processando ${feitos}/${ids.length}… (${ok} aplicados, ${pulados} ignorados)`;
  };
  mostrar();

  const processarUm = async (id) => {
    const atual = loteState.statusMap.get(id);
    // Alvo já atingido ou transição inválida: pula sem erro.
    if (atual === alvo) { pulados++; return; }
    if (alvo === 'descartado' && atual === 'confirmado') { pulados++; return; }
    try {
      // aberto→confirmado não é permitido; descarte de "aberto" é direto.
      const extra = alvo === 'descartado' ? { motivo_descarte: motivo } : {};
      const res = await patchAlertaStatus(id, alvo, extra);
      if (res.ok) { ok++; loteState.statusMap.set(id, alvo); }
      else if (res.auth) { falhas++; }
      else { pulados++; }
    } catch (_) { falhas++; }
  };

  // Concorrência limitada (4 em paralelo) para não sobrecarregar a API.
  const fila = [...ids];
  const trabalhadores = Array.from({ length: Math.min(4, fila.length) }, async () => {
    while (fila.length) {
      const id = fila.shift();
      await processarUm(id);
      feitos++;
      mostrar();
    }
  });
  await Promise.all(trabalhadores);

  if (prog) {
    const partes = [`${ok} aplicado(s)`];
    if (pulados) partes.push(`${pulados} ignorado(s)`);
    if (falhas) partes.push(`${falhas} com falha`);
    prog.textContent = partes.join(' · ');
  }
  // Remove da seleção os que foram aplicados; mantém os que falharam.
  ids.forEach(id => { if (loteState.statusMap.get(id) === alvo) loteState.sel.delete(id); });
  botoes.forEach(b => b.disabled = false);
  // Falha total de autenticação: não recarrega (apagaria a mensagem); mostra o
  // convite a entrar de novo. Nos demais casos, recarrega para refletir o novo
  // status na tabela e no resumo.
  if (falhas && !ok) {
    const href = `/login?next=${encodeURIComponent(location.pathname)}`;
    if (prog) prog.innerHTML = `Sua sessão expirou. <a href="${href}">Entre novamente</a> para triar em lote.`;
    return;
  }
  setTimeout(() => loadAlertas(), 700);
}

async function patchAlertaStatus(id, status, extra = {}) {
  const res = await fetch(`${BASE}/api/alertas/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, ...extra }),
  });
  const payload = await res.json().catch(() => ({}));
  if (res.status === 401 || payload.auth === 'login') return { ok: false, auth: true };
  return { ok: res.ok, payload };
}

// ─── Detail panel ──────────────────────────────────────────────────────────

// Elemento que tinha o foco antes de abrir o painel — para devolvê-lo ao fechar.
let _detailReturnFocus = null;

async function openDetail(id) {
  const panel    = document.getElementById('detail-panel');
  const backdrop = document.getElementById('detail-backdrop');
  const content  = document.getElementById('detail-content');

  _stopInvProfundaPolling();
  state.currentAlertaId = id;
  // Guarda o foco de origem só na primeira abertura (openDetail se re-chama
  // após salvar a triagem; não queremos sobrescrever com o botão interno).
  if (!panel.classList.contains('panel-open')) {
    _detailReturnFocus = document.activeElement;
  }
  content.innerHTML = '<div class="loading-msg">Carregando…</div>';
  panel.classList.add('panel-open');
  backdrop.classList.add('backdrop-open');
  // Move o foco para dentro do diálogo (botão fechar sempre presente).
  document.getElementById('detail-close')?.focus();

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

    const temNarrativa = Boolean(d.narrativa_ia && String(d.narrativa_ia).trim());
    // Back-compat: narrativas salvas no formato antigo carregam o corpo; mostramos
    // só o texto da análise (sem o antigo bloco de veredito).
    const parecerSalvo = temNarrativa ? parseVereditoIa(d.narrativa_ia).corpo : '';
    const logado = !!sessao.usuario;
    const loginHref = `/login?next=${encodeURIComponent(location.pathname)}`;
    const parecerVazioMsg = logado
      ? 'Nenhum parecer ainda. Clique em “Investigar com IA” para um parecer único: plausibilidade, análise e status/motivo sugeridos.'
      : 'Nenhum parecer de IA para este alerta. A geração de pareceres é feita por fiscais autenticados.';
    const parecerInicialHtml = parecerSalvo
      ? `<p class="parecer-analise">${escapeHtml(limparMarkdown(parecerSalvo))}</p>`
      : `<p class="narrativa-empty">${parecerVazioMsg}</p>`;
    const btnIaLabel = temNarrativa ? 'Regenerar parecer' : 'Investigar com IA';

    const transicoes = (d.transicoes_permitidas || []).map(st =>
      `<option value="${st}">${STATUS_LABELS[st] || st}</option>`
    ).join('');

    const motivoOpts = Object.entries(MOTIVOS_DESCARTE).map(
      ([k, lbl]) => `<option value="${k}">${lbl}</option>`
    ).join('');

    const historicoHtml = (d.historico || []).length
      ? (d.historico || []).map(h => {
          // Salvar só uma nota registra uma transição X → X. Nesses casos
          // mostramos "anotação" em vez de repetir o mesmo status dos dois lados.
          const semMudanca = (h.status_anterior || '') === h.status_novo;
          const transicao = semMudanca
            ? `<span class="triage-hist-anotacao">Anotação</span> ${statusBadge(h.status_novo)}`
            : `${statusBadge(h.status_anterior || '—')} → ${statusBadge(h.status_novo)}`;
          return `
          <li>
            <span class="triage-hist-meta">${formatDate(h.criado_em)}</span>
            ${transicao}
            ${h.nota ? `<span class="triage-hist-nota">${escapeHtml(h.nota)}</span>` : ''}
          </li>
        `;
        }).join('')
      : '<li class="triage-hist-empty">Nenhuma movimentação registrada.</li>';

    // Modo leitor: a triagem e a IA são operações de escrita autenticadas
    // (o backend responde 401 sem sessão). Para o visitante anônimo — o
    // jornalista/cidadão — mostramos o status e o histórico (leitura) com um
    // convite a entrar, em vez de um formulário que falharia ao salvar.
    const triageBlockHtml = logado
      ? `
      <div class="triage-block">
        <label class="section-title" style="margin-bottom:0.75rem">Triagem</label>
        <div class="triage-form">
          <label for="triage-status">Novo status</label>
          <select id="triage-status">
            <option value="${d.status}">${STATUS_LABELS[d.status] || d.status} (atual)</option>
            ${transicoes}
          </select>
          <div id="triage-motivo-wrap" class="triage-motivo-wrap" hidden>
            <label for="triage-motivo">Motivo do descarte</label>
            <select id="triage-motivo">
              <option value="">Selecione o motivo…</option>
              ${motivoOpts}
            </select>
          </div>
          <label for="triage-nota">Nota / histórico</label>
          <textarea id="triage-nota" rows="3" placeholder="Observações da investigação…">${escapeHtml(d.notas_triagem || '')}</textarea>
          <button type="button" id="triage-save" class="btn-page">Salvar triagem</button>
          <div id="triage-erro" class="error-msg" style="display:none;margin-top:0.5rem"></div>
          <p class="triage-atalhos">Atalhos: <kbd>I</kbd> investigar · <kbd>C</kbd> confirmar · <kbd>D</kbd> descartar · <kbd>S</kbd> salvar · <kbd>J</kbd>/<kbd>K</kbd> próximo/anterior</p>
        </div>
        <div class="triage-historico">
          <label>Histórico</label>
          <ul>${historicoHtml}</ul>
        </div>
      </div>`
      : `
      <div class="triage-block triage-block-readonly">
        <label class="section-title" style="margin-bottom:0.75rem">Triagem</label>
        <p class="section-note">Status atual: ${statusBadge(d.status)}. A triagem — confirmar, descartar ou anotar — é feita por fiscais autenticados.</p>
        <a href="${loginHref}" class="btn-page btn-entrar-triar">Entrar para triar</a>
        <div class="triage-historico">
          <label>Histórico</label>
          <ul>${historicoHtml}</ul>
        </div>
      </div>`;

    const iaBtnHtml = logado
      ? `<button type="button" id="btn-investigar-ia" class="btn-investigar" title="IA em nuvem emite um parecer único: plausibilidade, análise e status/motivo sugeridos">
          ${ICON.ia} ${btnIaLabel}
        </button>`
      : `<a href="${loginHref}" class="btn-investigar btn-investigar-login" title="Entre para gerar um parecer de IA deste alerta">
          ${ICON.ia} Entrar para investigar com IA
        </a>`;

    const conflitoDetailHtml = d.conflito && d.conflito.qtd ? `
      <div class="detail-conflito${d.conflito.forte ? ' forte' : ''}">
        ${ICON.flag}
        <div>
          <strong>Conflito de interesse — sócio-servidor</strong>
          <p>${d.conflito.qtd} sócio(s) desta empresa coincidem por nome com servidor(es) público(s)${d.conflito.forte ? ', com <strong>lotação no órgão contratante</strong> (indício forte)' : ''}${d.conflito.cpf_confirmado ? '; ao menos um com CPF confirmado via TSE' : ''}. O casamento é por nome — homônimos são esperados, verifique a identidade.
          <a href="/conflitos-interesse" class="detail-link">Ver triagem de conflitos →</a></p>
        </div>
      </div>` : '';

    content.innerHTML = `
      <div class="detail-fornecedor">${escapeHtml(d.fornecedor || 'Fornecedor não identificado')}</div>
      <div class="detail-badges">
        ${tipoBadge(d.tipo)}
        ${sevBadge(d.severidade)}
        ${statusBadge(d.status)}
      </div>
      ${conflitoDetailHtml}
      ${triageBlockHtml}
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
      ${renderTransparenciaRjHtml(d.transparencia_rj)}
      <div class="investigation-toolbar">
        ${iaBtnHtml}
        <button type="button" id="btn-export-dossie" class="btn-dossie" title="Baixa dossiê Markdown deste alerta">
          📄 Exportar Dossiê
        </button>
        <span id="investigacao-status" class="investigacao-status" aria-live="polite"></span>
      </div>
      <div id="parecer-container" class="narrativa-block">
        <label>Parecer da IA</label>
        ${parecerInicialHtml}
      </div>
      <div class="detail-actions">
        ${pncpLink}
        ${d.fornecedor_ni ? `<a href="/fornecedor/${d.fornecedor_ni}" target="_self" class="detail-link">Ver página do fornecedor →</a>` : ''}
        <button id="share-btn" class="btn-page" onclick="shareAlert(${id})" style="font-size:0.8rem">${ICON.link} Copiar link</button>
      </div>
    `;

    // Listeners de escrita só existem no modo autenticado; no modo leitor os
    // controles correspondentes são links de login, não botões.
    if (logado) {
      const statusAtual = d.status;
      const toggleMotivoDescarte = () => {
        const sel = document.getElementById('triage-status');
        const wrap = document.getElementById('triage-motivo-wrap');
        if (!sel || !wrap) return;
        wrap.hidden = !(sel.value === 'descartado' && sel.value !== statusAtual);
      };
      document.getElementById('triage-status')?.addEventListener('change', toggleMotivoDescarte);
      toggleMotivoDescarte();

      document.getElementById('triage-save')?.addEventListener('click', () => {
        salvarTriagem(id);
      });
      document.getElementById('btn-investigar-ia')?.addEventListener('click', () => {
        investigarComIa(id);
      });
    }
    // Dossiê é leitura pública (sem gerar_ia): disponível para todos.
    document.getElementById('btn-export-dossie')?.addEventListener('click', () => {
      exportarDossie(id);
    });
  } catch (e) {
    content.innerHTML = `<div class="error-msg">Erro ao carregar: ${e.message}</div>`;
  }
}

const IA_LOADING_STEPS = [
  { id: 'analise', label: 'IA analisando o contexto...' },
  { id: 'parecer', label: 'Formando o parecer...' },
];

function _iaLoadingHtml(stepIndex) {
  const steps = IA_LOADING_STEPS.map((s, i) => {
    let cls = 'ia-step';
    if (i < stepIndex) cls += ' is-done';
    else if (i === stepIndex) cls += ' is-active';
    return `<div class="${cls}" data-ia-step="${s.id}"><span class="ia-step-dot"></span>${s.label}</div>`;
  }).join('');
  const current = IA_LOADING_STEPS[stepIndex] || IA_LOADING_STEPS[0];
  return `
    <label>Narrativa IA</label>
    <div class="ia-progress" role="status" aria-live="polite" aria-busy="true">
      <div class="ia-spinner" aria-hidden="true"></div>
      <div class="ia-progress-text">
        <strong id="ia-step-title">${current.label}…</strong>
        <p id="ia-step-hint">Pode levar até 2 minutos — não feche este painel.</p>
      </div>
    </div>
    <div class="ia-progress-steps" id="ia-progress-steps">${steps}</div>
    <div class="narrativa-skeleton" aria-hidden="true">
      <div class="narrativa-skeleton-line"></div>
      <div class="narrativa-skeleton-line"></div>
      <div class="narrativa-skeleton-line"></div>
      <div class="narrativa-skeleton-line"></div>
    </div>
  `;
}

function _setIaLoadingUi(stepIndex) {
  const container = document.getElementById('parecer-container');
  const statusEl = document.getElementById('investigacao-status');
  const toolbar = document.querySelector('.investigation-toolbar');
  if (!container) return;

  container.classList.add('is-loading');
  container.innerHTML = _iaLoadingHtml(stepIndex);
  if (toolbar) toolbar.classList.add('is-loading');
  if (statusEl) {
    const step = IA_LOADING_STEPS[stepIndex];
    statusEl.textContent = step ? `Em andamento: ${step.label}…` : 'Investigação em andamento…';
    statusEl.className = 'investigacao-status investigacao-loading';
  }
}

function _startIaLoadingTimers() {
  let stepIndex = 0;
  const timers = [];

  const advance = () => {
    if (stepIndex >= IA_LOADING_STEPS.length - 1) return;
    stepIndex += 1;
    _setIaLoadingUi(stepIndex);
  };

  timers.push(setTimeout(advance, 8000));
  timers.push(setTimeout(advance, 35000));

  return () => timers.forEach(clearTimeout);
}

async function investigarComIa(alertaId) {
  const btn = document.getElementById('btn-investigar-ia');
  const statusEl = document.getElementById('investigacao-status');
  const container = document.getElementById('parecer-container');
  const dossieBtn = document.getElementById('btn-export-dossie');
  const toolbar = document.querySelector('.investigation-toolbar');
  if (!btn || !statusEl || !container) return;

  const btnLabelOriginal = btn.textContent;
  btn.disabled = true;
  if (dossieBtn) dossieBtn.disabled = true;
  btn.innerHTML = '<span class="btn-spinner" aria-hidden="true"></span> Analisando…';

  _setIaLoadingUi(0);
  const stopTimers = _startIaLoadingTimers();

  try {
    const res = await fetch(`${BASE}/api/alertas/${alertaId}/investigar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const payload = await res.json();
    if (res.status === 401 && payload.auth === 'login') { irParaLogin(); return; }
    if (res.status === 403 && payload.auth === 'verificar') {
      carregarSessao();
      throw new Error('Confirme seu email para usar a IA. Use "Reenviar" no topo se não recebeu o link.');
    }
    if (!res.ok) throw new Error(payload.error || res.statusText);
    carregarSessao();

    const parecer = payload.parecer || null;
    container.classList.remove('is-loading');
    container.innerHTML = `
      <label>Parecer da IA</label>
      ${renderParecerHtml(parecer, payload.provedor_nome)}
    `;
    document.getElementById('btn-aplicar-parecer')?.addEventListener('click', () => {
      aplicarVereditoSugerido(
        alertaId,
        parecer && parecer.status_sugerido,
        parecer && parecer.motivo_sugerido,
        parecer && parecer.analise
      );
    });

    btn.innerHTML = `${ICON.ia} Regenerar parecer`;
    statusEl.textContent = parecer
      ? 'Parecer gerado. Revise e clique em “Aplicar sugestão” para triar.'
      : 'Parecer indisponível.';
    statusEl.className = 'investigacao-status investigacao-ok';

    if (state.currentTab === 'alertas') {
      loadAlertas();
    }
  } catch (e) {
    container.classList.remove('is-loading');
    container.innerHTML = `
      <label>Parecer da IA</label>
      <p class="narrativa-empty">Falha ao gerar parecer: ${escapeHtml(e.message)}</p>
    `;
    statusEl.textContent = e.message;
    statusEl.className = 'investigacao-status investigacao-erro';
    btn.textContent = btnLabelOriginal;
  } finally {
    stopTimers();
    if (toolbar) toolbar.classList.remove('is-loading');
    btn.disabled = false;
    if (dossieBtn) dossieBtn.disabled = false;
  }
}

// ── Investigação Profunda ──────────────────────────────────────────────────

const INV_PROFUNDA_POLL_INTERVAL = 6000; // 6s
let _invProfundaTimer = null;

async function investigarProfundo(alertaId) {
  const btn = document.getElementById('btn-investigar-profundo');
  const statusEl = document.getElementById('inv-profunda-status');
  if (!btn) return;

  btn.disabled = true;
  btn.innerHTML = '<span class="btn-spinner" aria-hidden="true"></span> Iniciando…';
  if (statusEl) statusEl.textContent = 'Iniciando investigação profunda…';

  try {
    const res = await fetch(`${BASE}/api/alertas/${alertaId}/investigar_profundo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await res.json();

    if (res.status === 401 && data.auth === 'login') { irParaLogin(); return; }
    if (res.status === 403 && data.auth === 'verificar') {
      carregarSessao();
      throw new Error('Confirme seu email para usar a IA. Use "Reenviar" no topo se não recebeu o link.');
    }
    if (!res.ok && res.status !== 202) {
      throw new Error(data.error || res.statusText);
    }
    carregarSessao();

    if (data.status === 'ja_rodando') {
      if (statusEl) statusEl.textContent = 'Investigação já em andamento…';
    } else {
      if (statusEl) statusEl.textContent = 'Investigação iniciada — coletando dados…';
    }

    btn.innerHTML = '<span class="btn-spinner" aria-hidden="true"></span> Investigando…';
    _startInvProfundaPolling(alertaId);
  } catch (e) {
    btn.disabled = false;
    btn.innerHTML = `${ICON.lupa} Investigar Profundo`;
    if (statusEl) statusEl.textContent = `Erro: ${e.message}`;
  }
}

function _startInvProfundaPolling(alertaId) {
  _stopInvProfundaPolling();
  _invProfundaTimer = setInterval(() => _pollInvProfunda(alertaId), INV_PROFUNDA_POLL_INTERVAL);
  _pollInvProfunda(alertaId);
}

function _stopInvProfundaPolling() {
  if (_invProfundaTimer) {
    clearInterval(_invProfundaTimer);
    _invProfundaTimer = null;
  }
}

async function _pollInvProfunda(alertaId) {
  const btn = document.getElementById('btn-investigar-profundo');
  const statusEl = document.getElementById('inv-profunda-status');
  const containerEl = document.getElementById('inv-profunda-container');

  try {
    const res = await fetch(`${BASE}/api/investigacoes/${alertaId}/status`);
    const data = await res.json();

    if (data.status === 'nenhuma') {
      return;
    }

    if (data.status === 'rodando') {
      if (statusEl) {
        statusEl.textContent = 'Agente coletando dados… (pode levar alguns minutos)';
      }
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="btn-spinner" aria-hidden="true"></span> Investigando…';
      }
      if (!_invProfundaTimer) {
        _startInvProfundaPolling(alertaId);
      }
      return;
    }

    _stopInvProfundaPolling();

    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `${ICON.lupa} Re-investigar`;
    }

    if (data.status === 'erro') {
      if (statusEl) statusEl.textContent = `Erro: ${data.erro || 'desconhecido'}`;
      return;
    }

    if (containerEl) {
      containerEl.innerHTML = renderInvProfundaHtml(data);
    }
    if (statusEl) {
      const conf = data.grau_confianca ? ` · confiança ${data.grau_confianca}` : '';
      statusEl.textContent = `Investigação concluída — ${data.conclusao || '?'}${conf}`;
    }
  } catch (e) {
    console.warn('Polling inv profunda falhou:', e);
  }
}

function renderInvProfundaHtml(data) {
  const conclusaoCor = {
    confirmar: '#f59e0b',
    escalar: '#ef4444',
    arquivar: '#22c55e',
    inconclusivo: '#64748b',
  }[data.conclusao] || '#64748b';

  const resumos = data.resumos || {};
  const linhasResumo = Object.entries(resumos)
    .filter(([, v]) => v)
    .map(([k, v]) => `<li><strong>${k.replace(/_/g, ' ')}:</strong> ${escapeHtml(v)}</li>`)
    .join('');

  return `
    <div class="inv-profunda-result">
      <div class="inv-profunda-header">
        <span class="inv-profunda-title">Investigação Profunda</span>
        <span class="inv-profunda-badge" style="background:${conclusaoCor}20;border-color:${conclusaoCor};color:${conclusaoCor}">
          ${data.conclusao || '?'} · ${data.grau_confianca || '?'}
        </span>
      </div>
      ${linhasResumo ? `<ul class="inv-profunda-resumos">${linhasResumo}</ul>` : ''}
      ${data.sintese ? `
        <div class="inv-profunda-sintese">
          <div class="inv-profunda-sintese-label">Síntese do Agente</div>
          <div class="inv-profunda-sintese-text">${escapeHtml(data.sintese)}</div>
        </div>
      ` : ''}
      ${data.recomendacao ? `
        <div class="inv-profunda-rec">
          <strong>Recomendação:</strong> ${escapeHtml(data.recomendacao)}
        </div>
      ` : ''}
    </div>
  `;
}

async function aplicarVereditoSugerido(alertaId, statusSugerido, motivoSugerido, analise) {
  const statusEl = document.getElementById('triage-status');
  const motivoEl = document.getElementById('triage-motivo');
  const notaEl = document.getElementById('triage-nota');
  const btn = document.getElementById('btn-aplicar-parecer');
  if (!statusSugerido || !statusEl) return;

  // Garante que o status sugerido exista como opção antes de selecioná-lo.
  if (![...statusEl.options].some(o => o.value === statusSugerido)) {
    const opt = document.createElement('option');
    opt.value = statusSugerido;
    opt.textContent = STATUS_LABELS[statusSugerido] || statusSugerido;
    statusEl.appendChild(opt);
  }
  statusEl.value = statusSugerido;
  // Dispara o 'change' para revelar o campo de motivo (o bug era setar por
  // código sem disparar o evento, deixando o motivo escondido).
  statusEl.dispatchEvent(new Event('change'));

  if (statusSugerido === 'descartado' && motivoSugerido && motivoEl) {
    motivoEl.value = motivoSugerido;
  }
  if (notaEl && analise) {
    const prefixo = `[IA] ${analise}`;
    notaEl.value = notaEl.value.trim()
      ? `${prefixo}\n\n${notaEl.value.trim()}`
      : prefixo;
  }

  // Descarte sem motivo (IA não sugeriu): revela o campo e deixa o humano
  // escolher, em vez de tentar salvar e falhar.
  if (statusSugerido === 'descartado' && !(motivoEl && motivoEl.value)) {
    if (btn) btn.textContent = 'Escolha o motivo e salve';
    motivoEl?.focus();
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Aplicando…';
  }
  await salvarTriagem(alertaId);
  if (btn) {
    btn.disabled = false;
    btn.textContent = 'Aplicar sugestão';
  }
}

async function exportarDossie(alertaId) {
  const btn = document.getElementById('btn-export-dossie');
  const statusEl = document.getElementById('investigacao-status');
  if (btn) btn.disabled = true;
  if (statusEl) {
    statusEl.textContent = 'Preparando dossiê…';
    statusEl.className = 'investigacao-status investigacao-loading';
  }

  try {
    const res = await fetch(`${BASE}/api/dossie/${alertaId}?formato=md`);
    if (!res.ok) {
      let msg = res.statusText;
      try {
        const err = await res.json();
        msg = err.error || msg;
      } catch (_) { /* resposta não-JSON */ }
      throw new Error(msg);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `dossie-alerta-${alertaId}.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    if (statusEl) {
      statusEl.textContent = 'Dossiê exportado.';
      statusEl.className = 'investigacao-status investigacao-ok';
    }
  } catch (e) {
    if (statusEl) {
      statusEl.textContent = e.message;
      statusEl.className = 'investigacao-status investigacao-erro';
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function salvarTriagem(alertaId) {
  const statusEl = document.getElementById('triage-status');
  const notaEl = document.getElementById('triage-nota');
  const motivoEl = document.getElementById('triage-motivo');
  const erroEl = document.getElementById('triage-erro');
  const btn = document.getElementById('triage-save');
  if (!statusEl || !btn) return;

  const status = statusEl.value;
  const nota = notaEl ? notaEl.value.trim() : '';
  const motivo = motivoEl ? motivoEl.value : '';
  erroEl.style.display = 'none';
  btn.disabled = true;
  btn.textContent = 'Salvando…';

  const body = { status, nota };
  if (status === 'descartado' && motivo) {
    body.motivo_descarte = motivo;
  }

  try {
    const res = await fetch(`${BASE}/api/alertas/${alertaId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const payload = await res.json().catch(() => ({}));
    if (res.status === 401 || payload.auth === 'login') {
      const href = `/login?next=${encodeURIComponent(location.pathname)}`;
      erroEl.innerHTML = `Sua sessão expirou. <a href="${href}">Entre novamente</a> para salvar a triagem.`;
      erroEl.style.display = 'block';
      return;
    }
    if (!res.ok) throw new Error(payload.error || res.statusText);

    await openDetail(alertaId);
    if (state.currentTab === 'alertas') {
      loadAlertas();
    }
  } catch (e) {
    erroEl.textContent = e.message;
    erroEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Salvar triagem';
  }
}

function shareAlert(id) {
  const url = window.location.origin + '/dashboard?alerta=' + id;
  navigator.clipboard.writeText(url).then(() => {
    const btn = document.getElementById('share-btn');
    if (btn) {
      btn.textContent = '✓ Link copiado!';
      setTimeout(() => { btn.innerHTML = `${ICON.link} Copiar link`; }, 2000);
    }
  });
}

function closeDetail() {
  const panel = document.getElementById('detail-panel');
  if (!panel.classList.contains('panel-open')) return;
  panel.classList.remove('panel-open');
  document.getElementById('detail-backdrop').classList.remove('backdrop-open');
  _stopInvProfundaPolling();
  // Devolve o foco a quem abriu o painel (WCAG 2.4.3 — ordem de foco).
  if (_detailReturnFocus && typeof _detailReturnFocus.focus === 'function') {
    _detailReturnFocus.focus();
  }
  _detailReturnFocus = null;
  state.currentAlertaId = null;
}

// Navega para o próximo (dir=1) / anterior (dir=-1) alerta na ordem exibida
// na fila — para o fiscal percorrer a lista sem voltar à tabela (teclas j/k).
function navegarAlerta(dir) {
  const ordem = state.alertaFlatOrder || [];
  const atual = state.currentAlertaId;
  if (!ordem.length || atual == null) return;
  const i = ordem.indexOf(atual);
  if (i === -1) return;
  const prox = i + dir;
  if (prox < 0 || prox >= ordem.length) return;
  openDetail(ordem[prox]);
}

// ─── Timeline ──────────────────────────────────────────────────────────────

async function loadTimeline() {
  try {
    const res = await fetch(apiUrl(`/api/timeline?granularity=${state.timelineGranularity}`));
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

  const xTicks = { color: '#8a8a8a', font: { size: 10 }, maxRotation: 45 };

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
          y: { ticks: { color: '#8a8a8a', font: { size: 11 } }, grid: { color: '#1f1f1f' } },
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
              color: '#8a8a8a',
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
    const res = await fetch(apiUrl(`/api/fornecedores/ranking?${params}`));
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
              color: '#8a8a8a',
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

function goToAlertasFiltrado({ severidade = '', status = '' } = {}) {
  if (severidade) {
    state.alertasFiltros.severidade = severidade;
    const el = document.getElementById('filter-severidade');
    if (el) el.value = severidade;
  }
  if (status) {
    state.alertasFiltros.status = status;
    const el = document.getElementById('filter-status');
    if (el) el.value = status;
  }
  state.alertasPage = 1;
  const alertasBtn = document.querySelector('[data-tab="alertas"]');
  if (alertasBtn) alertasBtn.click();
  loadAlertas();
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
    const res = await fetch(apiUrl('/api/orgaos/ranking'));
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
          x: { ticks: { color: '#8a8a8a', font: { size: 11 } }, grid: { color: '#1f1f1f' } },
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
              color: '#8a8a8a',
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

// ─── Comparador multi-fornecedor ───────────────────────────────────────────

const comparadorState = {
  catalogo: [],
  selecionados: new Map(),
  busca: '',
};

const COMPARADOR_MAX = 4;

function _formatarCnpj(ni) {
  const d = String(ni || '').replace(/\D/g, '');
  if (d.length !== 14) return d;
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
}

function _atualizarComparadorBtn() {
  const btn = document.getElementById('comparador-btn');
  if (!btn) return;
  const n = comparadorState.selecionados.size;
  btn.textContent = `Comparar (${n}/${COMPARADOR_MAX})`;
  btn.disabled = n < 2;
}

function _renderComparadorChips() {
  const el = document.getElementById('comparador-chips');
  if (!el) return;
  if (!comparadorState.selecionados.size) {
    el.innerHTML = '<span class="section-note" style="margin:0">Nenhum fornecedor selecionado.</span>';
    _atualizarComparadorBtn();
    return;
  }
  el.innerHTML = [...comparadorState.selecionados.values()].map(f => `
    <span class="comparador-chip">
      ${esc(truncate(f.fornecedor || f.fornecedor_ni, 28))}
      <button type="button" data-ni="${esc(f.fornecedor_ni)}" title="Remover" aria-label="Remover">×</button>
    </span>
  `).join('');
  el.querySelectorAll('button[data-ni]').forEach(btn => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      toggleComparadorNi(btn.dataset.ni);
    });
  });
  _atualizarComparadorBtn();
}

function _renderComparadorLista() {
  const el = document.getElementById('comparador-lista');
  if (!el) return;
  const termo = comparadorState.busca.trim().toLowerCase();
  const filtrados = comparadorState.catalogo.filter(f => {
    if (!termo) return true;
    const ni = (f.fornecedor_ni || '').toLowerCase();
    const nome = (f.fornecedor || '').toLowerCase();
    return nome.includes(termo) || ni.includes(termo);
  });

  if (!comparadorState.catalogo.length) {
    el.innerHTML = '<div class="loading-msg" style="padding:1rem">Nenhum fornecedor com alertas no Sentinela.</div>';
    return;
  }
  if (!filtrados.length) {
    el.innerHTML = '<div class="loading-msg" style="padding:1rem">Nenhum resultado para o filtro.</div>';
    return;
  }

  el.innerHTML = filtrados.map(f => {
    const ni = f.fornecedor_ni;
    const sel = comparadorState.selecionados.has(ni);
    const lotado = !sel && comparadorState.selecionados.size >= COMPARADOR_MAX;
    const sancao = f.tem_sancao ? ' · sanção' : '';
    return `
      <label class="comparador-item ${sel ? 'selected' : ''} ${lotado ? 'disabled' : ''}">
        <input type="checkbox" ${sel ? 'checked' : ''} ${lotado ? 'disabled' : ''} data-ni="${esc(ni)}" />
        <div class="comparador-item-main">
          <div class="comparador-item-nome">${esc(f.fornecedor || 'Sem razão social')}</div>
          <div class="comparador-item-ni">${esc(_formatarCnpj(ni))}</div>
          <div class="comparador-item-meta">
            ${f.total_alertas} alerta(s) · ${f.alertas_alta || 0} alta · ${formatCurrency(f.valor_total)}${sancao}
          </div>
        </div>
      </label>
    `;
  }).join('');

  el.querySelectorAll('input[type="checkbox"][data-ni]').forEach(cb => {
    cb.addEventListener('change', () => toggleComparadorNi(cb.dataset.ni, cb.checked));
  });
}

function toggleComparadorNi(ni, forcar) {
  const limpo = String(ni || '').replace(/\D/g, '');
  if (!limpo) return;
  const item = comparadorState.catalogo.find(f => f.fornecedor_ni === limpo)
    || comparadorState.selecionados.get(limpo)
    || { fornecedor_ni: limpo, fornecedor: limpo };

  if (forcar === true) {
    if (comparadorState.selecionados.size >= COMPARADOR_MAX && !comparadorState.selecionados.has(limpo)) return;
    comparadorState.selecionados.set(limpo, item);
  } else if (forcar === false) {
    comparadorState.selecionados.delete(limpo);
  } else if (comparadorState.selecionados.has(limpo)) {
    comparadorState.selecionados.delete(limpo);
  } else {
    if (comparadorState.selecionados.size >= COMPARADOR_MAX) return;
    comparadorState.selecionados.set(limpo, item);
  }
  _renderComparadorChips();
  _renderComparadorLista();
}

function preencherComparadorNi(ni) {
  document.querySelector('.tab-btn[data-tab="rede"]')?.click();
  if (!comparadorState.catalogo.length) {
    loadComparadorCatalogo().then(() => toggleComparadorNi(ni, true));
    return;
  }
  toggleComparadorNi(ni, true);
}

function limparComparadorSelecao() {
  comparadorState.selecionados.clear();
  _renderComparadorChips();
  _renderComparadorLista();
}

async function loadComparadorCatalogo() {
  const lista = document.getElementById('comparador-lista');
  if (lista) {
    lista.innerHTML = '<div class="loading-msg" style="padding:1rem">Carregando fornecedores investigados…</div>';
  }
  try {
    const data = await api('/api/fornecedores/investigados');
    comparadorState.catalogo = data.items || [];
    _renderComparadorLista();
    _renderComparadorChips();
  } catch (e) {
    if (lista) {
      lista.innerHTML = `<div class="error-msg" style="padding:1rem">Erro ao carregar lista: ${esc(e.message)}</div>`;
    }
  }
}

function _comparadorSublistaHtml(items, mapper, vazio) {
  if (!items || !items.length) return `<p class="loading-msg">${esc(vazio)}</p>`;
  return `<ul class="comparador-list">${items.map(mapper).join('')}</ul>`;
}

function renderComparadorResultado(data) {
  const vinculos = data.vinculos?.socios_compartilhados || [];
  const vinculosHtml = vinculos.length
    ? `<div class="comparador-vinculos"><strong>Sócios em comum:</strong> ${
        vinculos.map(v =>
          `${esc(v.nome)} (${v.fornecedores.map(f => esc(truncate(f.razao_social, 28))).join(' · ')})`
        ).join(' · ')
      }</div>`
    : '';

  const cols = (data.fornecedores || []).map(p => {
    const id = p.identidade || {};
    const res = p.resumo || {};
    const sancao = id.tem_sancao
      ? '<span class="comparador-badge-sancao">Sanção CEIS/CNEP</span>'
      : '';
    const alertasHtml = _comparadorSublistaHtml(
      p.alertas,
      a => `<li>${sevBadge(a.severidade)} ${tipoBadge(a.tipo)}<br>${esc(truncate(a.descricao, 60))}</li>`,
      'Nenhum alerta'
    );
    const contratosHtml = _comparadorSublistaHtml(
      p.contratos,
      c => `<li>${formatCurrency(c.valor_global)} — ${esc(truncate(c.objeto, 50))}</li>`,
      'Sem contratos'
    );
    const sociosHtml = _comparadorSublistaHtml(
      (p.socios || []).map(n => ({ nome: n })),
      s => `<li>${esc(s.nome)}</li>`,
      'Sócios não cadastrados'
    );
    return `
      <div class="comparador-col">
        <h3>${esc(truncate(id.razao_social || '—', 48))}</h3>
        <div class="comparador-ni">${esc(id.ni)}</div>
        ${sancao}
        <div class="comparador-kpis">
          <div><span>Contratos</span>${res.total_contratos ?? 0}</div>
          <div><span>Valor total</span>${formatCurrency(res.valor_total)}</div>
          <div><span>Alertas</span>${res.total_alertas ?? 0}</div>
          <div><span>Alta</span>${res.alertas_alta ?? 0}</div>
        </div>
        <div class="comparador-section"><label>Alertas</label>${alertasHtml}</div>
        <div class="comparador-section"><label>Contratos</label>${contratosHtml}</div>
        <div class="comparador-section"><label>Sócios</label>${sociosHtml}</div>
        <a href="/fornecedor/${esc(id.ni)}" class="detail-link" style="display:inline-block;margin-top:0.5rem">Perfil completo →</a>
      </div>
    `;
  }).join('');

  return `${vinculosHtml}<div class="comparador-grid" style="grid-template-columns:repeat(${data.fornecedores.length}, minmax(220px, 1fr))">${cols}</div>`;
}

async function executarComparador() {
  const wrap = document.getElementById('comparador-resultado');
  if (!wrap) return;
  const nis = [...comparadorState.selecionados.keys()];
  if (nis.length < 2) {
    wrap.innerHTML = '<div class="error-msg">Selecione ao menos dois fornecedores na lista.</div>';
    return;
  }
  wrap.innerHTML = '<div class="loading-msg">Comparando fornecedores…</div>';
  try {
    const params = new URLSearchParams();
    nis.forEach(ni => params.append('ni', ni));
    const data = await api(`/api/fornecedores/comparar?${params}`);
    wrap.innerHTML = renderComparadorResultado(data);
  } catch (e) {
    wrap.innerHTML = `<div class="error-msg">${esc(e.message)}</div>`;
  }
}

// ─── Rede ──────────────────────────────────────────────────────────────────

async function loadRede() {
  const tbody = document.getElementById('rede-tbody');
  tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--muted)">Carregando…</td></tr>';

  try {
    const res = await fetch(apiUrl('/api/socios/compartilhados'));
    if (!res.ok) throw new Error(res.statusText);
    const d = await res.json();
    const items = d.items || [];

    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--muted)">Nenhum sócio em comum encontrado.</td></tr>';
      return;
    }

    tbody.innerHTML = items.map((item, idx) => {
      const sevBadge = item.severidade === 'alta'
        ? '<span class="badge badge-red">Alta</span>'
        : '<span class="badge badge-yellow">Média</span>';

      const empresasHtml = item.fornecedores.map(f =>
        `<div style="margin:0.2rem 0">
          <a href="/fornecedor/${f.ni}" target="_self" class="fornecedor-link" style="font-size:0.82rem">${truncate(f.razao_social, 50)}</a>
          <span style="color:var(--muted);font-size:0.78rem;margin-left:0.5rem">${formatCurrency(f.valor_total)}</span>
          <button type="button" class="btn-grafo" data-ni="${f.ni}" data-nome="${escapeHtml(truncate(f.razao_social, 40))}" style="margin-left:0.5rem;font-size:0.72rem;padding:2px 8px;border:1px solid var(--border);background:#111;color:var(--text);border-radius:4px;cursor:pointer">Grafo</button>
          <button type="button" class="btn-comparar-add" data-ni="${f.ni}" style="margin-left:0.35rem;font-size:0.72rem;padding:2px 8px;border:1px solid var(--border);background:#1a1208;color:#fbbf24;border-radius:4px;cursor:pointer">+ Comparar</button>
        </div>`
      ).join('');

      const detailId = `rede-detail-${idx}`;
      return `
        <tr class="rede-row" data-detail="${detailId}" style="cursor:pointer">
          <td style="font-weight:500">${item.nome_socio}</td>
          <td style="white-space:nowrap">${item.total_fornecedores} empresa${item.total_fornecedores !== 1 ? 's' : ''}</td>
          <td style="white-space:nowrap">${(item.total_contratos || 0).toLocaleString('pt-BR')}</td>
          <td style="white-space:nowrap">${formatCurrency(item.valor_total)}</td>
          <td>${sevBadge}</td>
        </tr>
        <tr id="${detailId}" class="rede-detail" style="display:none">
          <td colspan="5" style="padding:0.75rem 1rem;background:#141414;border-top:none">
            ${empresasHtml}
          </td>
        </tr>
      `;
    }).join('');

    tbody.querySelectorAll('.rede-row').forEach(row => {
      row.addEventListener('click', () => {
        const detailRow = document.getElementById(row.dataset.detail);
        const isOpen = detailRow.style.display !== 'none';
        detailRow.style.display = isOpen ? 'none' : 'table-row';
      });
    });

    tbody.querySelectorAll('.btn-grafo').forEach(btn => {
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        loadGrafoFornecedor(btn.dataset.ni, btn.dataset.nome);
      });
    });
    tbody.querySelectorAll('.btn-comparar-add').forEach(btn => {
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        preencherComparadorNi(btn.dataset.ni);
      });
    });

  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" style="color:#ef4444;padding:1rem">Erro: ${e.message}</td></tr>`;
  }
}

let _grafoNetwork = null;

const _GRAFO_CORES = {
  fornecedor: { background: '#7c3aed', border: '#a78bfa' },
  orgao: { background: '#2563eb', border: '#60a5fa' },
  contrato: { background: '#475569', border: '#94a3b8' },
  socio: { background: '#ea580c', border: '#fb923c' },
};

async function loadGrafoFornecedor(ni, nome) {
  const panel = document.getElementById('grafo-panel');
  const container = document.getElementById('grafo-network');
  const titulo = document.getElementById('grafo-titulo');
  if (!panel || !container || typeof vis === 'undefined') return;

  panel.style.display = 'block';
  titulo.textContent = `Grafo — ${nome || ni}`;
  container.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--muted)">Carregando grafo…</div>';

  try {
    const res = await fetch(`${BASE}/api/grafo/fornecedor/${encodeURIComponent(ni)}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    container.innerHTML = '';

    const nodes = new vis.DataSet(
      (data.nodes || []).map(n => ({
        id: n.id,
        label: truncate(n.label, 28),
        title: n.label,
        color: _GRAFO_CORES[n.tipo] || _GRAFO_CORES.contrato,
        font: { color: '#f5f5f5', size: 12 },
      }))
    );
    const edges = new vis.DataSet(
      (data.edges || []).map(e => ({
        from: e.from,
        to: e.to,
        label: e.label || '',
        arrows: 'to',
        color: { color: '#525252', highlight: '#a3a3a3' },
        font: { color: '#8a8a8a', size: 10, strokeWidth: 0 },
      }))
    );

    if (_grafoNetwork) {
      _grafoNetwork.destroy();
    }
    _grafoNetwork = new vis.Network(
      container,
      { nodes, edges },
      {
        physics: { stabilization: { iterations: 120 } },
        interaction: { hover: true, tooltipDelay: 120 },
        layout: { improvedLayout: true },
      }
    );
  } catch (e) {
    container.innerHTML = `<div style="padding:1rem;color:#ef4444">Erro ao carregar grafo: ${escapeHtml(e.message)}</div>`;
  }
}

document.getElementById('grafo-fechar')?.addEventListener('click', () => {
  const panel = document.getElementById('grafo-panel');
  if (panel) panel.style.display = 'none';
  if (_grafoNetwork) {
    _grafoNetwork.destroy();
    _grafoNetwork = null;
  }
});

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

// ─── Pipeline status ───────────────────────────────────────────────────────

// Converte uma expressão cron (5 campos) numa frase em pt-BR. Cobre os casos
// que o pipeline usa (diário/semanal em horário fixo); expressões fora do
// padrão caem no rótulo cru como fallback, sem quebrar.
function humanizeCron(expr) {
  const partes = String(expr).trim().split(/\s+/);
  if (partes.length < 5) return `Agendamento: ${expr}`;
  const [min, hora, diaMes, mes, diaSem] = partes;
  const DIAS = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'];
  const numerico = v => /^\d+$/.test(v);
  if (!numerico(min) || !numerico(hora)) return `Agendamento: ${expr}`;
  const horario = `${hora.padStart(2, '0')}h${min === '0' ? '' : min.padStart(2, '0')}`;
  if (diaMes === '*' && mes === '*') {
    if (diaSem === '*') return `Todo dia às ${horario}`;
    if (numerico(diaSem) && DIAS[Number(diaSem) % 7]) {
      return `Toda ${DIAS[Number(diaSem) % 7]}-feira às ${horario}`.replace('sábado-feira', 'sábado').replace('domingo-feira', 'domingo');
    }
  }
  return `Agendamento: ${expr}`;
}

async function loadPipelineStatus() {
  const el = document.getElementById('pipeline-status-card');
  if (!el) return;
  try {
    const data = await api('/api/pipeline/status');
    const ultima = data.ultima_coleta || {};
    const cfg = data.pipeline || {};
    const saude = data.saude || 'desconhecido';
    const badgeCls = saude === 'ok' ? 'ok' : saude === 'atencao' ? 'warn' : 'fail';
    const linhas = (data.log_ultimas_linhas || []).join('\n');
    const agendador = cfg.cron ? humanizeCron(cfg.cron) : 'Manual / Agendador do sistema';
    el.innerHTML = `
      <div class="pipeline-status-header">
        <h3>Pipeline automático</h3>
        <span class="pipeline-badge ${badgeCls}">${esc(saude)}</span>
      </div>
      <div class="pipeline-status-grid">
        <div class="pipeline-stat"><label>Última coleta</label><span>${esc(formatDateTime(ultima.finalizado_em || ultima.iniciado_em))}</span></div>
        <div class="pipeline-stat"><label>Período coletado</label><span>${esc(formatDate(ultima.data_inicial))} → ${esc(formatDate(ultima.data_final))}</span></div>
        <div class="pipeline-stat"><label>Registros RJ</label><span>${ultima.registros_municipio ?? '—'}</span></div>
        <div class="pipeline-stat"><label>Agendador</label><span>${esc(agendador)}</span></div>
        <div class="pipeline-stat"><label>Janela (dias)</label><span>${cfg.janela_dias ?? '—'}</span></div>
        <div class="pipeline-stat"><label>Discord</label><span>${cfg.discord_configurado ? 'sim' : 'não'}</span></div>
      </div>
      ${linhas ? `<pre class="pipeline-log-snippet">${esc(linhas)}</pre>` : ''}
    `;
  } catch (e) {
    el.innerHTML = `<div class="error-msg">Falha ao carregar pipeline: ${esc(e.message)}</div>`;
  }
}

// ─── Watchlists & Regras ───────────────────────────────────────────────────

let _configFormMode = null;
let _configFormId = null;

function _openConfigModal(title, fieldsHtml) {
  const modal = document.getElementById('config-form-modal');
  document.getElementById('config-form-title').textContent = title;
  document.getElementById('config-form').innerHTML = fieldsHtml;
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function _closeConfigModal() {
  const modal = document.getElementById('config-form-modal');
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
  _configFormMode = null;
  _configFormId = null;
}

function _watchlistCriterio(w) {
  if (w.fornecedor_ni) return `Fornecedor ${w.fornecedor_ni}`;
  if (w.orgao_cnpj) return `Órgão ${w.orgao_cnpj}`;
  if (w.palavra_chave_objeto) return `"${w.palavra_chave_objeto}"`;
  return '—';
}

function _watchlistFormHtml(w = {}) {
  return `
    <label>Rótulo</label><input name="rotulo" required value="${esc(w.rotulo || '')}" />
    <label>CNPJ fornecedor</label><input name="fornecedor_ni" value="${esc(w.fornecedor_ni || '')}" placeholder="opcional" />
    <label>CNPJ órgão</label><input name="orgao_cnpj" value="${esc(w.orgao_cnpj || '')}" placeholder="opcional" />
    <label>Palavra-chave no objeto</label><input name="palavra_chave_objeto" value="${esc(w.palavra_chave_objeto || '')}" placeholder="opcional" />
    <p class="section-note">Informe ao menos um critério acima.</p>
    <label><input type="checkbox" name="ativo" ${w.ativo !== 0 ? 'checked' : ''} /> Ativo</label>
  `;
}

function _regraFormHtml(r = {}) {
  const tipos = ['', ...Object.keys(TIPO_LABELS)];
  return `
    <label>Tipo de alerta</label>
    <select name="tipo">
      ${tipos.map(t => {
        const label = t ? labelTipo(t) : 'Todos os tipos';
        return `<option value="${esc(t)}" ${(r.tipo || '') === t ? 'selected' : ''}>${esc(label)}</option>`;
      }).join('')}
    </select>
    <label>Severidade mínima</label>
    <select name="severidade_min">
      ${['baixa', 'media', 'alta'].map(s =>
        `<option value="${s}" ${r.severidade_min === s ? 'selected' : ''}>${s}</option>`
      ).join('')}
    </select>
    <label>Valor mínimo (R$)</label><input name="valor_min" type="number" step="0.01" min="0" value="${r.valor_min ?? 0}" />
    <label><input type="checkbox" name="ativo" ${r.ativo !== 0 ? 'checked' : ''} /> Ativo</label>
  `;
}

function _watchlistPayload(form) {
  const g = (name) => form.querySelector(`[name="${name}"]`)?.value.trim() || null;
  return {
    rotulo: g('rotulo'),
    fornecedor_ni: g('fornecedor_ni'),
    orgao_cnpj: g('orgao_cnpj'),
    palavra_chave_objeto: g('palavra_chave_objeto'),
    ativo: form.querySelector('[name=ativo]')?.checked ? 1 : 0,
  };
}

function _regraPayload(form) {
  const tipo = form.querySelector('[name=tipo]')?.value.trim();
  return {
    tipo: tipo || null,
    severidade_min: form.querySelector('[name=severidade_min]').value,
    valor_min: parseFloat(form.querySelector('[name=valor_min]').value) || 0,
    ativo: form.querySelector('[name=ativo]')?.checked ? 1 : 0,
  };
}

async function loadWatchlists() {
  const wrap = document.getElementById('watchlists-table-wrap');
  if (!wrap) return;
  try {
    const data = await api('/api/watchlists');
    const rows = data.items || [];
    if (!rows.length) {
      wrap.innerHTML = '<p class="loading-msg">Nenhuma watchlist cadastrada.</p>';
      return;
    }
    wrap.innerHTML = `
      <table class="config-table">
        <thead><tr><th>Rótulo</th><th>Critério</th><th>Ativo</th><th></th></tr></thead>
        <tbody>${rows.map(w => `
          <tr>
            <td>${esc(w.rotulo)}</td><td>${esc(_watchlistCriterio(w))}</td>
            <td>${w.ativo ? 'sim' : 'não'}</td>
            <td class="config-actions">
              <button type="button" data-edit-wl="${w.id}">Editar</button>
              <button type="button" class="danger" data-del-wl="${w.id}">Desativar</button>
            </td>
          </tr>`).join('')}
        </tbody>
      </table>`;
    wrap.querySelectorAll('[data-edit-wl]').forEach(btn => {
      btn.addEventListener('click', () => {
        const w = rows.find(x => x.id === parseInt(btn.dataset.editWl, 10));
        _configFormMode = 'watchlist-edit';
        _configFormId = w.id;
        _openConfigModal('Editar watchlist', _watchlistFormHtml(w));
      });
    });
    wrap.querySelectorAll('[data-del-wl]').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('Desativar esta watchlist?')) return;
        await api(`/api/watchlists/${btn.dataset.delWl}`, { method: 'DELETE' });
        loadWatchlists();
      });
    });
  } catch (e) {
    wrap.innerHTML = `<div class="error-msg">${esc(e.message)}</div>`;
  }
}

async function loadRegras() {
  const wrap = document.getElementById('regras-table-wrap');
  if (!wrap) return;
  try {
    const data = await api('/api/regras-alerta');
    const rows = data.items || [];
    if (!rows.length) {
      wrap.innerHTML = '<p class="loading-msg">Nenhuma regra cadastrada.</p>';
      return;
    }
    wrap.innerHTML = `
      <table class="config-table">
        <thead><tr><th>Tipo</th><th>Severidade mín.</th><th>Valor mín.</th><th>Ativo</th><th></th></tr></thead>
        <tbody>${rows.map(r => `
          <tr>
            <td>${esc(r.tipo ? labelTipo(r.tipo) : 'Todos')}</td>
            <td>${esc(r.severidade_min)}</td>
            <td>${formatCurrency(r.valor_min)}</td>
            <td>${r.ativo ? 'sim' : 'não'}</td>
            <td class="config-actions">
              <button type="button" data-edit-rg="${r.id}">Editar</button>
              <button type="button" class="danger" data-del-rg="${r.id}">Desativar</button>
            </td>
          </tr>`).join('')}
        </tbody>
      </table>`;
    wrap.querySelectorAll('[data-edit-rg]').forEach(btn => {
      btn.addEventListener('click', () => {
        const r = rows.find(x => x.id === parseInt(btn.dataset.editRg, 10));
        _configFormMode = 'regra-edit';
        _configFormId = r.id;
        _openConfigModal('Editar regra', _regraFormHtml(r));
      });
    });
    wrap.querySelectorAll('[data-del-rg]').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('Desativar esta regra?')) return;
        await api(`/api/regras-alerta/${btn.dataset.delRg}`, { method: 'DELETE' });
        loadRegras();
      });
    });
  } catch (e) {
    wrap.innerHTML = `<div class="error-msg">${esc(e.message)}</div>`;
  }
}

function loadMonitoramento() {
  loadWatchlists();
  loadRegras();
}

async function _salvarConfigForm() {
  const form = document.getElementById('config-form');
  if (!form || !_configFormMode) return;
  try {
    if (_configFormMode === 'watchlist-create') {
      await api('/api/watchlists', { method: 'POST', body: _watchlistPayload(form) });
      loadWatchlists();
    } else if (_configFormMode === 'watchlist-edit') {
      await api(`/api/watchlists/${_configFormId}`, { method: 'PATCH', body: _watchlistPayload(form) });
      loadWatchlists();
    } else if (_configFormMode === 'regra-create') {
      await api('/api/regras-alerta', { method: 'POST', body: _regraPayload(form) });
      loadRegras();
    } else if (_configFormMode === 'regra-edit') {
      await api(`/api/regras-alerta/${_configFormId}`, { method: 'PATCH', body: _regraPayload(form) });
      loadRegras();
    }
    _closeConfigModal();
  } catch (e) {
    alert(e.message);
  }
}

// ─── Empenhos ──────────────────────────────────────────────────────────────

const empenhoState = {
  page: 1,
  perPage: 50,
  total: 0,
  valorTotal: 0,
};

async function loadEmpenhos(page) {
  if (page !== undefined) empenhoState.page = page;

  const q      = (document.getElementById('empenhos-filter-q')?.value || '').trim();
  const ini    = (document.getElementById('empenhos-filter-ini')?.value || '').trim();
  const fim    = (document.getElementById('empenhos-filter-fim')?.value || '').trim();

  const tbody     = document.getElementById('empenhos-tbody');
  const counter   = document.getElementById('empenhos-counter');
  const indicator = document.getElementById('empenhos-page-indicator');
  const btnPrev   = document.getElementById('empenhos-btn-prev');
  const btnNext   = document.getElementById('empenhos-btn-next');

  if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="loading-msg">Carregando…</td></tr>';

  const params = new URLSearchParams({
    page: empenhoState.page,
    per_page: empenhoState.perPage,
  });
  if (q)   params.set('q', q);
  if (ini) params.set('data_ini', ini);
  if (fim) params.set('data_fim', fim);

  try {
    const data = await api(`/api/empenhos?${params}`);
    empenhoState.total      = data.total || 0;
    empenhoState.valorTotal = data.valor_total || 0;

    _renderEmpenhoResumoCards(empenhoState.total, empenhoState.valorTotal);

    const items = data.items || [];
    const totalPages = Math.max(1, Math.ceil(empenhoState.total / empenhoState.perPage));

    if (counter) {
      counter.textContent = empenhoState.total > 0
        ? `${empenhoState.total.toLocaleString('pt-BR')} registro(s) encontrado(s)`
        : 'Nenhum registro encontrado';
    }
    if (indicator) {
      indicator.textContent = `Página ${empenhoState.page} de ${totalPages}`;
    }
    if (btnPrev) btnPrev.disabled = empenhoState.page <= 1;
    if (btnNext) btnNext.disabled = empenhoState.page >= totalPages;

    if (!tbody) return;
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:2rem">Nenhum empenho encontrado para os filtros selecionados.</td></tr>';
      return;
    }

    tbody.innerHTML = items.map(e => `
      <tr>
        <td style="white-space:nowrap">${formatDate(e.data_lancamento)}</td>
        <td>
          <span title="${esc(e.fornecedor_ni || '')}">${esc(truncate(e.razao_social || e.fornecedor_ni || '—', 40))}</span>
        </td>
        <td style="white-space:nowrap;text-align:right">${formatCurrency(e.valor)}</td>
        <td title="${esc(e.descricao || '')}">${esc(truncate(e.descricao || '—', 72))}</td>
        <td style="white-space:nowrap;font-family:monospace;font-size:0.78rem">${esc(e.orgao || '—')}</td>
        <td style="font-size:0.8rem;word-break:break-all">${esc(e.documento || '—')}</td>
      </tr>
    `).join('');
  } catch (err) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="color:var(--danger,#ef4444);text-align:center;padding:1.5rem">Erro ao carregar empenhos: ${esc(err.message)}</td></tr>`;
    if (counter) counter.textContent = '';
  }
}

function _renderEmpenhoResumoCards(total, valorTotal) {
  const container = document.getElementById('empenhos-resumo-cards');
  if (!container) return;
  container.innerHTML = `
    <div class="kpi-card">
      <div class="kpi-value">${(total || 0).toLocaleString('pt-BR')}</div>
      <div class="kpi-label">Empenhos Coletados</div>
      <div class="kpi-hint">Lançamentos via PNCP</div>
    </div>
    <div class="kpi-card highlight">
      <div class="kpi-value" style="font-size:1.75rem">${formatCurrency(valorTotal)}</div>
      <div class="kpi-label">Valor Total Monitorado</div>
      <div class="kpi-hint">Soma dos empenhos filtrados</div>
    </div>
  `;
}

function setupEmpenhos() {
  const buscar  = document.getElementById('empenhos-buscar');
  const btnPrev = document.getElementById('empenhos-btn-prev');
  const btnNext  = document.getElementById('empenhos-btn-next');
  const qInput  = document.getElementById('empenhos-filter-q');

  buscar?.addEventListener('click', () => {
    empenhoState.page = 1;
    loadEmpenhos();
  });
  qInput?.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') { empenhoState.page = 1; loadEmpenhos(); }
  });
  btnPrev?.addEventListener('click', () => {
    if (empenhoState.page > 1) loadEmpenhos(empenhoState.page - 1);
  });
  btnNext?.addEventListener('click', () => {
    loadEmpenhos(empenhoState.page + 1);
  });
}

// ─── Bootstrap ─────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  setupTabs();
  carregarSessao();
  await initMunicipioSelector();
  loadTab('visao-geral');
  state.tabLoaded['visao-geral'] = true;

  // Detail panel close
  document.getElementById('detail-close')
    ?.addEventListener('click', closeDetail);
  document.getElementById('detail-backdrop')
    ?.addEventListener('click', closeDetail);

  // Diálogo modal: Esc fecha e Tab fica preso dentro do painel (WCAG 2.1.2).
  document.addEventListener('keydown', (e) => {
    const panel = document.getElementById('detail-panel');
    if (!panel || !panel.classList.contains('panel-open')) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      closeDetail();
      return;
    }

    // Atalhos de triagem (fiscal autenticado). Ctrl/Cmd+Enter salva mesmo com
    // foco no textarea; as teclas de letra só valem fora de campos de texto,
    // para não atrapalhar a digitação da nota.
    if (sessao.usuario) {
      const salvarBtn = document.getElementById('triage-save');
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && salvarBtn) {
        e.preventDefault();
        salvarBtn.click();
        return;
      }
      const alvoEditavel = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if (!alvoEditavel && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const setStatus = (valor) => {
          const sel = document.getElementById('triage-status');
          if (!sel) return false;
          const opt = [...sel.options].some(o => o.value === valor);
          if (!opt) return false;
          sel.value = valor;
          sel.dispatchEvent(new Event('change'));
          return true;
        };
        const tecla = e.key.toLowerCase();
        if (tecla === 'c' && setStatus('confirmado')) { e.preventDefault(); return; }
        if (tecla === 'd' && setStatus('descartado')) { e.preventDefault(); return; }
        if (tecla === 'i' && setStatus('investigando')) { e.preventDefault(); return; }
        if ((tecla === 's' || e.key === 'Enter') && salvarBtn) { e.preventDefault(); salvarBtn.click(); return; }
        if (tecla === 'j' || tecla === 'k') { e.preventDefault(); navegarAlerta(tecla === 'j' ? 1 : -1); return; }
      }
    }

    if (e.key === 'Tab') {
      const foco = panel.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (!foco.length) return;
      const primeiro = foco[0];
      const ultimo = foco[foco.length - 1];
      if (e.shiftKey && document.activeElement === primeiro) {
        e.preventDefault();
        ultimo.focus();
      } else if (!e.shiftKey && document.activeElement === ultimo) {
        e.preventDefault();
        primeiro.focus();
      }
    }
  });

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

  // Pre-fill empenhos tab from fornecedor page link
  const empenhoNi = urlParams.get('empenho_ni');
  if (empenhoNi) {
    document.querySelector('.tab-btn[data-tab="empenhos"]')?.click();
    const qInput = document.getElementById('empenhos-filter-q');
    if (qInput) {
      qInput.value = empenhoNi;
      empenhoState.page = 1;
      loadEmpenhos();
    }
  }

  // Auto-start tour on first visit
  setTimeout(() => {
    if (!localStorage.getItem('sentinela_tour_seen')) startTour();
  }, 1200);

  document.getElementById('btn-nova-watchlist')?.addEventListener('click', () => {
    _configFormMode = 'watchlist-create';
    _configFormId = null;
    _openConfigModal('Nova watchlist', _watchlistFormHtml());
  });
  document.getElementById('btn-nova-regra')?.addEventListener('click', () => {
    _configFormMode = 'regra-create';
    _configFormId = null;
    _openConfigModal('Nova regra de alerta', _regraFormHtml());
  });
  document.getElementById('config-form-cancel')?.addEventListener('click', _closeConfigModal);
  document.getElementById('config-form-save')?.addEventListener('click', _salvarConfigForm);
  document.getElementById('config-form-modal')?.addEventListener('click', (ev) => {
    if (ev.target.id === 'config-form-modal') _closeConfigModal();
  });

  setupEmpenhos();

  document.getElementById('comparador-btn')?.addEventListener('click', executarComparador);
  document.getElementById('comparador-limpar')?.addEventListener('click', limparComparadorSelecao);
  const comparadorBusca = document.getElementById('comparador-busca');
  if (comparadorBusca) {
    comparadorBusca.addEventListener('input', debounce(() => {
      comparadorState.busca = comparadorBusca.value;
      _renderComparadorLista();
    }, 200));
  }

  const compararParam = new URLSearchParams(window.location.search).get('comparar');
  if (compararParam) {
    const nisUrl = compararParam.split(/[,;]/).map(s => s.trim()).filter(Boolean);
    setTimeout(async () => {
      document.querySelector('.tab-btn[data-tab="rede"]')?.click();
      await loadComparadorCatalogo();
      nisUrl.slice(0, COMPARADOR_MAX).forEach(ni => toggleComparadorNi(ni, true));
      if (comparadorState.selecionados.size >= 2) executarComparador();
    }, 400);
  }
});
