import time
import unicodedata

import gspread
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Time Aliados", page_icon="📊", layout="wide")

# =========================
# CONFIG
# =========================
SHEET_ID = "1KvGqEJ26oGsayOYZv3ynaiiN0ya9VxG6ofDoBOKu22w"
LOGO_PATH = "logo_time_aliados.png"

RANGE_CONSULTOR = "A1:AF10"
RANGE_PROCESSOS = "A1:I50"
RANGE_METAS = "A1:G50"
RANGE_ROLETA = "A1:B40"

CACHE_TTL = 300

ETAPAS = [
    "Leads",
    "Atendimento",
    "Agendamento Visita",
    "Pasta Docs",
    "Crédito Aprovado",
]

ABAS_PROCESSOS_CANDIDATAS = [
    "PROCESSOS_QUENTES",
    "PROCESSOS QUENTES",
    "Processos Quentes",
    "PIPE",
    "Pipe",
]

ABAS_METAS_CANDIDATAS = [
    "METAS",
    "Metas",
    "META",
    "Meta",
]

ABAS_ROLETA_CANDIDATAS = [
    "ROLETA",
    "Roleta",
    "ROLETA - CONTROLE DE LEADS",
    "ROLETA – CONTROLE DE LEADS",
]

ABAS_EXCLUIDAS_FIXAS = set(
    ABAS_PROCESSOS_CANDIDATAS + ABAS_METAS_CANDIDATAS + ABAS_ROLETA_CANDIDATAS
)

COLUNAS_PROCESSOS_MAP = {
    "gerente": ["gerente"],
    "corretor": ["corretor", "consultor", "responsavel", "responsável"],
    "cliente": ["cliente", "nome cliente"],
    "construtora": ["construtora"],
    "produto": ["produto", "empreendimento"],
    "status": ["status", "etapa"],
    "correspondente": ["correspondente"],
    "valor_imovel": [
        "valor do imovel",
        "valor do imóvel",
        "valor imovel",
        "valor imóvel",
        "valor",
    ],
    "valor_financiamento": [
        "valor financiamento aprovado",
        "valor do financiamento aprovado",
        "financiamento aprovado",
        "valor financiamento",
    ],
}

COLUNAS_METAS_MAP = {
    "consultor": ["consultor", "corretor", "nome"],
    "meta_leads": ["meta leads", "leads", "meta lead"],
    "meta_atendimento": ["meta atendimento", "atendimento"],
    "meta_agendamento": [
        "meta agendamento",
        "meta agendamento visita",
        "agendamento visita",
        "agendamento",
    ],
    "meta_pasta_docs": ["meta pasta docs", "pasta docs", "meta docs"],
    "meta_credito": [
        "meta credito",
        "meta crédito",
        "credito aprovado",
        "crédito aprovado",
        "meta credito aprovado",
        "meta crédito aprovado",
    ],
    "meta_valor": [
        "meta valor",
        "meta valor venda",
        "meta financeira",
        "meta valor total",
    ],
}

STATUS_CORES = {
    "APROVADO": "#22c55e",
    "EM ANALISE": "#f59e0b",
    "EM ANÁLISE": "#f59e0b",
    "AGUARDANDO IR": "#38bdf8",
    "AGUARDANDO DOCS": "#a78bfa",
    "REPROVADO": "#ef4444",
    "VENDA REALIZADA": "#10b981",
}

# =========================
# CSS
# =========================
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 1rem;
        }
        .brand-header {
            padding: 0.4rem 0 1rem 0;
        }
        .brand-title {
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: -0.02em;
        }
        .brand-subtitle {
            font-size: 0.95rem;
            opacity: 0.85;
            margin-top: 0.15rem;
        }
        .section-title {
            font-size: 1.15rem;
            font-weight: 700;
            margin-top: 1rem;
            margin-bottom: 0.6rem;
        }
        .kpi-card {
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 14px 16px;
            background: rgba(255,255,255,0.03);
            box-shadow: 0 2px 10px rgba(0,0,0,0.12);
            min-height: 92px;
        }
        .kpi-title {
            font-size: 0.82rem;
            opacity: 0.78;
            margin-bottom: 0.25rem;
        }
        .kpi-value {
            font-size: 1.85rem;
            font-weight: 800;
            line-height: 1;
        }
        .small-note {
            font-size: 0.8rem;
            opacity: 0.75;
        }
        .kanban-card {
            border-radius: 18px;
            padding: 14px 16px;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            min-height: 120px;
        }
        .kanban-status {
            font-size: 0.85rem;
            opacity: 0.82;
        }
        .kanban-value {
            font-size: 1.75rem;
            font-weight: 800;
            margin-top: 0.2rem;
            margin-bottom: 0.4rem;
        }
        .kanban-bar {
            width: 100%;
            height: 10px;
            border-radius: 999px;
            background: rgba(255,255,255,0.08);
            overflow: hidden;
        }
        .kanban-fill {
            height: 100%;
            border-radius: 999px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# HELPERS
# =========================
def auto_refresh(segundos: int) -> None:
    components.html(
        f"""
        <script>
            setTimeout(function(){{
                window.parent.location.reload();
            }}, {segundos * 1000});
        </script>
        """,
        height=0,
    )


def normalizar_texto(texto) -> str:
    if texto is None:
        return ""
    texto = str(texto).strip().lower()
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def normalizar_numero(valor) -> float:
    try:
        s = str(valor).strip()
        if s == "":
            return 0.0
        s = s.replace("R$", "").replace(" ", "")
        s = s.replace(".", "").replace(",", ".")
        return float(s)
    except Exception:
        return 0.0


def localizar_aba(sh, nomes_candidatos):
    try:
        titulos = [ws.title for ws in sh.worksheets()]
    except Exception:
        return None

    mapa = {normalizar_texto(t): t for t in titulos}
    for nome in nomes_candidatos:
        chave = normalizar_texto(nome)
        if chave in mapa:
            return mapa[chave]
    return None


def encontrar_indice_coluna(colunas, aliases):
    colunas_norm = [normalizar_texto(c) for c in colunas]
    for alias in aliases:
        alias_norm = normalizar_texto(alias)
        if alias_norm in colunas_norm:
            return colunas_norm.index(alias_norm)
    return None


def safe_values_batch_get(sh, ranges, tentativas=3, pausa=2):
    for tentativa in range(tentativas):
        try:
            resp = sh.values_batch_get(ranges)
            return resp.get("valueRanges", [])
        except Exception:
            if tentativa < tentativas - 1:
                time.sleep(pausa)
            else:
                return []


def ler_intervalo_seguro(ws, intervalo, tentativas=3, pausa=2):
    for tentativa in range(tentativas):
        try:
            return ws.get(
                intervalo,
                maintain_size=True,
                pad_values=True,
            )
        except Exception:
            if tentativa < tentativas - 1:
                time.sleep(pausa)
            else:
                return []


def status_cor(status: str) -> str:
    chave = str(status).strip().upper()
    return STATUS_CORES.get(chave, "#64748b")


def kpi_card(titulo: str, valor, subtitulo: str = ""):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-title">{titulo}</div>
            <div class="kpi-value">{valor}</div>
            <div class="small-note">{subtitulo}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def padronizar_linhas(valores):
    if not valores:
        return [], []

    max_cols = max(len(l) for l in valores)
    linhas = []
    for linha in valores:
        if len(linha) < max_cols:
            linha = linha + [""] * (max_cols - len(linha))
        else:
            linha = linha[:max_cols]
        linhas.append(linha)

    header = linhas[0]
    if len(set([str(c).strip() for c in header])) != len(header):
        usados = {}
        novo_header = []
        for c in header:
            nome = str(c).strip() if str(c).strip() else "coluna"
            if nome not in usados:
                usados[nome] = 0
                novo_header.append(nome)
            else:
                usados[nome] += 1
                novo_header.append(f"{nome}_{usados[nome]}")
        header = novo_header

    return header, linhas[1:]


# =========================
# GOOGLE
# =========================
@st.cache_resource
def conectar_google():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    return gspread.authorize(creds)


@st.cache_resource
def abrir_planilha():
    gc = conectar_google()
    return gc.open_by_key(SHEET_ID)


@st.cache_data(ttl=CACHE_TTL)
def listar_abas():
    try:
        sh = abrir_planilha()
        return [ws.title for ws in sh.worksheets()]
    except Exception:
        return []


# =========================
# CARGA PRODUTIVIDADE
# =========================
@st.cache_data(ttl=CACHE_TTL)
def carregar_dados_produtividade():
    try:
        sh = abrir_planilha()
        abas = listar_abas()
        abas_consultores = [
            a for a in abas
            if normalizar_texto(a) not in {normalizar_texto(x) for x in ABAS_EXCLUIDAS_FIXAS}
        ]

        if not abas_consultores:
            return pd.DataFrame(columns=["Consultor", "Etapa", "Dia", "Valor"]), ["Nenhuma aba de consultor detectada."], []

        ranges = [f"'{aba}'!{RANGE_CONSULTOR}" for aba in abas_consultores]
        respostas = safe_values_batch_get(sh, ranges)

        if not respostas:
            return pd.DataFrame(columns=["Consultor", "Etapa", "Dia", "Valor"]), ["Não foi possível ler as abas de consultores via batch_get."], abas_consultores

        dados = []
        avisos = []

        for idx, aba in enumerate(abas_consultores):
            bloco = respostas[idx] if idx < len(respostas) else {}
            valores = bloco.get("values", [])

            if not valores:
                avisos.append(f"A aba {aba} está vazia ou sem retorno no batch_get.")
                continue

            for etapa in ETAPAS:
                linha_etapa = None
                for i, linha in enumerate(valores):
                    if len(linha) > 0 and normalizar_texto(linha[0]) == normalizar_texto(etapa):
                        linha_etapa = i
                        break

                if linha_etapa is None:
                    avisos.append(f"Aba {aba}: etapa '{etapa}' não encontrada.")
                    continue

                for dia in range(1, 31):
                    try:
                        valor = normalizar_numero(valores[linha_etapa][dia])
                    except Exception:
                        valor = 0.0

                    dados.append(
                        {
                            "Consultor": aba,
                            "Etapa": etapa,
                            "Dia": dia,
                            "Valor": valor,
                        }
                    )

        df = pd.DataFrame(dados)
        if df.empty:
            return pd.DataFrame(columns=["Consultor", "Etapa", "Dia", "Valor"]), avisos, abas_consultores

        df["Dia"] = pd.to_numeric(df["Dia"], errors="coerce").fillna(0).astype(int)
        df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0.0)
        return df, avisos, abas_consultores
    except Exception as e:
        return pd.DataFrame(columns=["Consultor", "Etapa", "Dia", "Valor"]), [f"Produtividade: {type(e).__name__}: {str(e)}"], []


# =========================
# CARGA PROCESSOS QUENTES
# =========================
@st.cache_data(ttl=CACHE_TTL)
def carregar_processos_quentes():
    try:
        sh = abrir_planilha()
        nome_aba = localizar_aba(sh, ABAS_PROCESSOS_CANDIDATAS)
        if not nome_aba:
            return pd.DataFrame(), ["Aba de processos quentes não encontrada."]

        ws = sh.worksheet(nome_aba)
        valores = ler_intervalo_seguro(ws, RANGE_PROCESSOS)

        if len(valores) < 2:
            return pd.DataFrame(), [f"A aba {nome_aba} está vazia ou sem linhas suficientes."]

        header, linhas = padronizar_linhas(valores)
        if not header:
            return pd.DataFrame(), [f"A aba {nome_aba} não possui cabeçalho válido."]

        df_raw = pd.DataFrame(linhas, columns=header)

        if df_raw.empty:
            return pd.DataFrame(), [f"A aba {nome_aba} não possui dados."]

        dados = {}

        for campo, aliases in COLUNAS_PROCESSOS_MAP.items():
            idx = encontrar_indice_coluna(list(df_raw.columns), aliases)
            if idx is not None:
                dados[campo] = df_raw.iloc[:, idx].reset_index(drop=True)
            else:
                dados[campo] = pd.Series([""] * len(df_raw), index=df_raw.index)

        df = pd.DataFrame(dados)

        for col in ["status", "corretor", "cliente", "produto", "construtora", "gerente", "correspondente"]:
            df[col] = df[col].astype(str).str.strip()

        df["valor_imovel"] = df["valor_imovel"].apply(normalizar_numero)
        df["valor_financiamento"] = df["valor_financiamento"].apply(normalizar_numero)

        df = df[
            (df["cliente"].astype(str).str.strip() != "")
            | (df["status"].astype(str).str.strip() != "")
            | (df["valor_imovel"] > 0)
            | (df["valor_financiamento"] > 0)
        ].copy()

        return df, []

    except Exception as e:
        return pd.DataFrame(), [f"Processos Quentes: {type(e).__name__}: {str(e)}"]


# =========================
# CARGA METAS
# =========================
@st.cache_data(ttl=CACHE_TTL)
def carregar_metas():
    try:
        sh = abrir_planilha()
        nome_aba = localizar_aba(sh, ABAS_METAS_CANDIDATAS)
        if not nome_aba:
            return pd.DataFrame(), ["Aba de metas não encontrada."]

        ws = sh.worksheet(nome_aba)
        valores = ler_intervalo_seguro(ws, RANGE_METAS)

        if len(valores) < 2:
            return pd.DataFrame(), [f"A aba {nome_aba} está vazia ou sem linhas suficientes."]

        header, linhas = padronizar_linhas(valores)
        if not header:
            return pd.DataFrame(), [f"A aba {nome_aba} não possui cabeçalho válido."]

        df_raw = pd.DataFrame(linhas, columns=header)
        if df_raw.empty:
            return pd.DataFrame(), [f"A aba {nome_aba} não possui dados."]

        dados = {}

        for campo, aliases in COLUNAS_METAS_MAP.items():
            idx = encontrar_indice_coluna(list(df_raw.columns), aliases)
            if idx is not None:
                dados[campo] = df_raw.iloc[:, idx].reset_index(drop=True)
            else:
                dados[campo] = pd.Series([""] * len(df_raw), index=df_raw.index)

        df = pd.DataFrame(dados)
        df["consultor"] = df["consultor"].astype(str).str.strip()

        for col in [
            "meta_leads",
            "meta_atendimento",
            "meta_agendamento",
            "meta_pasta_docs",
            "meta_credito",
            "meta_valor",
        ]:
            df[col] = df[col].apply(normalizar_numero)

        df = df[df["consultor"] != ""].copy()
        return df, []
    except Exception as e:
        return pd.DataFrame(), [f"Metas: {type(e).__name__}: {str(e)}"]


# =========================
# CARGA ROLETA
# =========================
@st.cache_data(ttl=CACHE_TTL)
def carregar_roleta():
    try:
        sh = abrir_planilha()
        nome_aba = localizar_aba(sh, ABAS_ROLETA_CANDIDATAS)
        if not nome_aba:
            return pd.DataFrame(), ["Aba de roleta não encontrada."]

        ws = sh.worksheet(nome_aba)
        valores = ler_intervalo_seguro(ws, RANGE_ROLETA)

        if not valores:
            return pd.DataFrame(), [f"A aba {nome_aba} está vazia."]

        header_idx = None
        for idx, linha in enumerate(valores[:10]):
            cols_norm = [normalizar_texto(c) for c in linha]
            if "data" in cols_norm and "roleta" in cols_norm:
                header_idx = idx
                break

        if header_idx is None:
            return pd.DataFrame(), [f"Não consegui identificar DATA e ROLETA na aba {nome_aba}."]

        bloco = valores[header_idx:]
        header, linhas = padronizar_linhas(bloco)

        idx_data = encontrar_indice_coluna(header, ["data"])
        idx_roleta = encontrar_indice_coluna(header, ["roleta"])

        rows = []
        for linha in linhas:
            data_val = linha[idx_data] if idx_data is not None and idx_data < len(linha) else ""
            roleta_val = linha[idx_roleta] if idx_roleta is not None and idx_roleta < len(linha) else ""

            if str(data_val).strip() != "" or str(roleta_val).strip() != "":
                rows.append(
                    {
                        "Dia": normalizar_numero(data_val),
                        "Roleta": normalizar_numero(roleta_val),
                    }
                )

        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(), [f"A aba {nome_aba} não possui dados de roleta."]

        df["Dia"] = pd.to_numeric(df["Dia"], errors="coerce").fillna(0).astype(int)
        df["Roleta"] = pd.to_numeric(df["Roleta"], errors="coerce").fillna(0.0)
        df = df.sort_values("Dia").copy()
        return df, []
    except Exception as e:
        return pd.DataFrame(), [f"Roleta: {type(e).__name__}: {str(e)}"]


# =========================
# HEADER
# =========================
header_col1, header_col2 = st.columns([1, 6])
with header_col1:
    try:
        st.image(LOGO_PATH, width=95)
    except Exception:
        pass

with header_col2:
    st.markdown(
        """
        <div class="brand-header">
            <div class="brand-title">Time Aliados</div>
            <div class="brand-subtitle">
                Dashboard Streamlit conectado ao Google Sheets com batch get, cache e ranges fixos.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.header("Filtros")
    auto_atualizar = st.toggle("Atualização automática", value=False)
    intervalo = st.selectbox(
        "Intervalo",
        [300, 600, 900],
        index=0,
        format_func=lambda x: f"{x} segundos",
    )
    if st.button("Atualizar agora", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

if auto_atualizar:
    auto_refresh(intervalo)

# =========================
# LOAD
# =========================
df, erros, CONSULTOR_ABAS = carregar_dados_produtividade()
df_processos, erros_processos = carregar_processos_quentes()
df_metas, erros_metas = carregar_metas()
df_roleta, erros_roleta = carregar_roleta()

with st.sidebar:
    pagina = st.radio(
        "Área do dashboard",
        ["Visão Completa", "Produtividade", "Processos Quentes", "Metas", "Roleta"],
        index=0,
    )
    visao = st.radio("Modo de visualização", ["Equipe", "Consultor"], index=0)
    consultor_escolhido = None
    if visao == "Consultor":
        consultor_escolhido = st.selectbox(
            "Selecione o consultor",
            CONSULTOR_ABAS if CONSULTOR_ABAS else ["Sem abas detectadas"],
        )

for titulo, items in [
    ("Avisos da produtividade", erros),
    ("Avisos dos processos quentes", erros_processos),
    ("Avisos das metas", erros_metas),
    ("Avisos da roleta", erros_roleta),
]:
    if items:
        with st.expander(titulo, expanded=False):
            for msg in items:
                st.warning(msg)

if df.empty:
    st.warning("Nenhuma aba de consultor foi detectada no momento.")
    df_base = pd.DataFrame(columns=["Consultor", "Etapa", "Dia", "Valor"])
    titulo_visao = "Equipe"
elif visao == "Consultor" and consultor_escolhido and consultor_escolhido in df["Consultor"].unique():
    df_base = df[df["Consultor"] == consultor_escolhido].copy()
    titulo_visao = consultor_escolhido
else:
    df_base = df.copy()
    titulo_visao = "Equipe"

if not df_processos.empty and visao == "Consultor" and consultor_escolhido:
    df_processos_base = df_processos[
        df_processos["corretor"].astype(str).str.strip().str.lower()
        == str(consultor_escolhido).strip().lower()
    ].copy()
else:
    df_processos_base = df_processos.copy()

if not df_metas.empty and visao == "Consultor" and consultor_escolhido:
    df_metas_base = df_metas[
        df_metas["consultor"].astype(str).str.strip().str.lower()
        == str(consultor_escolhido).strip().lower()
    ].copy()
else:
    df_metas_base = df_metas.copy()


# =========================
# RENDERS
# =========================
def render_produtividade():
    if df_base.empty:
        st.info("Sem dados de produtividade disponíveis no momento.")
        return

    kpis = (
        df_base.groupby("Etapa", as_index=False)["Valor"]
        .sum()
        .set_index("Etapa")["Valor"]
        .to_dict()
    )

    cols = st.columns(5)
    cards = [
        ("Leads", int(kpis.get("Leads", 0))),
        ("Atendimento", int(kpis.get("Atendimento", 0))),
        ("Agendamento Visita", int(kpis.get("Agendamento Visita", 0))),
        ("Pasta Docs", int(kpis.get("Pasta Docs", 0))),
        ("Crédito Aprovado", int(kpis.get("Crédito Aprovado", 0))),
    ]

    for col, (titulo, valor) in zip(cols, cards):
        with col:
            kpi_card(f"{titulo_visao} • {titulo}", valor)

    st.markdown("<div class='section-title'>Evolução diária por etapa</div>", unsafe_allow_html=True)
    evolucao = (
        df_base.groupby(["Dia", "Etapa"], as_index=False)["Valor"]
        .sum()
        .sort_values("Dia")
    )
    fig = px.line(
        evolucao,
        x="Dia",
        y="Valor",
        color="Etapa",
        markers=True,
        title=f"Evolução diária • {titulo_visao}",
    )
    fig.update_layout(xaxis=dict(dtick=1))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("<div class='section-title'>Ranking de leads</div>", unsafe_allow_html=True)
        ranking = (
            df_base[df_base["Etapa"] == "Leads"]
            .groupby("Consultor", as_index=False)["Valor"]
            .sum()
            .sort_values("Valor", ascending=False)
        )
        if ranking.empty:
            st.info("Sem dados de leads para ranking.")
        else:
            fig_rank = px.bar(
                ranking,
                x="Valor",
                y="Consultor",
                orientation="h",
                text_auto=".0f",
                title=f"Ranking de Leads • {titulo_visao}",
            )
            fig_rank.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_rank, use_container_width=True)

    with c2:
        st.markdown("<div class='section-title'>Participação por consultor</div>", unsafe_allow_html=True)
        ranking = (
            df_base[df_base["Etapa"] == "Leads"]
            .groupby("Consultor", as_index=False)["Valor"]
            .sum()
            .sort_values("Valor", ascending=False)
        )
        if ranking.empty:
            st.info("Sem dados para participação.")
        else:
            fig_pie = px.pie(
                ranking,
                names="Consultor",
                values="Valor",
                hole=0.58,
                title=f"Participação dos Leads • {titulo_visao}",
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    c3, c4 = st.columns(2)

    with c3:
        st.markdown("<div class='section-title'>Funil consolidado</div>", unsafe_allow_html=True)
        funil = (
            df_base.groupby("Etapa", as_index=False)["Valor"]
            .sum()
            .copy()
        )
        funil["ordem"] = funil["Etapa"].apply(lambda x: ETAPAS.index(x) if x in ETAPAS else 999)
        funil = funil.sort_values("ordem")
        fig_funil = go.Figure(go.Funnel(y=funil["Etapa"], x=funil["Valor"], textinfo="value+percent initial"))
        fig_funil.update_layout(title=f"Funil • {titulo_visao}")
        st.plotly_chart(fig_funil, use_container_width=True)

    with c4:
        st.markdown("<div class='section-title'>Comparativo por etapa</div>", unsafe_allow_html=True)
        comp = (
            df_base.groupby(["Consultor", "Etapa"], as_index=False)["Valor"]
            .sum()
        )
        if comp.empty:
            st.info("Sem dados para comparativo.")
        else:
            fig_comp = px.bar(
                comp,
                x="Consultor",
                y="Valor",
                color="Etapa",
                barmode="group",
                title=f"Comparativo por consultor • {titulo_visao}",
            )
            st.plotly_chart(fig_comp, use_container_width=True)

    st.markdown("<div class='section-title'>Heatmap de leads por dia</div>", unsafe_allow_html=True)
    heat = (
        df_base[df_base["Etapa"] == "Leads"]
        .pivot_table(index="Consultor", columns="Dia", values="Valor", aggfunc="sum", fill_value=0)
    )
    if heat.empty:
        st.info("Sem dados suficientes para heatmap.")
    else:
        fig_heat = px.imshow(
            heat,
            aspect="auto",
            text_auto=True,
            title=f"Leads por dia e consultor • {titulo_visao}",
        )
        st.plotly_chart(fig_heat, use_container_width=True)


def render_pipeline_visual(dfp):
    st.markdown("<div class='section-title'>Pipeline visual de status</div>", unsafe_allow_html=True)
    status_counts = dfp["status"].replace("", pd.NA).dropna().value_counts().reset_index()
    if status_counts.empty:
        st.info("Não há status preenchidos.")
        return

    status_counts.columns = ["Status", "Quantidade"]
    total = max(int(status_counts["Quantidade"].sum()), 1)
    cols = st.columns(min(4, len(status_counts)))

    for i, (_, row) in enumerate(status_counts.iterrows()):
        perc = int((int(row["Quantidade"]) / total) * 100)
        cor = status_cor(row["Status"])
        with cols[i % len(cols)]:
            st.markdown(
                f"""
                <div class="kanban-card">
                    <div class="kanban-status">{row["Status"]}</div>
                    <div class="kanban-value">{int(row["Quantidade"])}</div>
                    <div class="kanban-bar">
                        <div class="kanban-fill" style="width:{perc}%; background:{cor};"></div>
                    </div>
                    <div class="small-note">{perc}% do pipeline atual</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_processos():
    if df_processos_base.empty:
        st.info("Sem dados de processos quentes disponíveis no momento.")
        return

    total_pipeline = float(df_processos_base["valor_imovel"].sum())
    total_financiamento = float(df_processos_base["valor_financiamento"].sum())
    qtd_processos = int(len(df_processos_base))

    c1, c2, c3 = st.columns(3)
    with c1:
        kpi_card("Qtd. Processos", qtd_processos)
    with c2:
        kpi_card("Pipeline Total", f"R$ {total_pipeline:,.0f}".replace(",", "."))
    with c3:
        kpi_card("Financiamento Total", f"R$ {total_financiamento:,.0f}".replace(",", "."))

    render_pipeline_visual(df_processos_base)

    c4, c5 = st.columns(2)

    with c4:
        st.markdown("<div class='section-title'>Processos por status</div>", unsafe_allow_html=True)
        status_df = (
            df_processos_base["status"]
            .replace("", pd.NA)
            .dropna()
            .value_counts()
            .reset_index()
        )
        if status_df.empty:
            st.info("Sem status para exibir.")
        else:
            status_df.columns = ["Status", "Quantidade"]
            fig_status = px.bar(
                status_df,
                x="Status",
                y="Quantidade",
                text_auto=True,
                title="Distribuição por status",
            )
            st.plotly_chart(fig_status, use_container_width=True)

    with c5:
        st.markdown("<div class='section-title'>Participação dos status</div>", unsafe_allow_html=True)
        status_df = (
            df_processos_base["status"]
            .replace("", pd.NA)
            .dropna()
            .value_counts()
            .reset_index()
        )
        if status_df.empty:
            st.info("Sem status para exibir.")
        else:
            status_df.columns = ["Status", "Quantidade"]
            fig_pie = px.pie(
                status_df,
                names="Status",
                values="Quantidade",
                hole=0.55,
                title="Participação por status",
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("<div class='section-title'>Pipeline por consultor</div>", unsafe_allow_html=True)
    pipe_consultor = (
        df_processos_base.groupby("corretor", as_index=False)["valor_imovel"]
        .sum()
        .sort_values("valor_imovel", ascending=False)
    )
    pipe_consultor = pipe_consultor[pipe_consultor["corretor"].astype(str).str.strip() != ""]
    if pipe_consultor.empty:
        st.info("Sem consultores para exibir pipeline.")
    else:
        fig_pipe = px.bar(
            pipe_consultor,
            x="valor_imovel",
            y="corretor",
            orientation="h",
            text_auto=".0f",
            title="Valor de pipeline por consultor",
        )
        fig_pipe.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_pipe, use_container_width=True)

    st.markdown("<div class='section-title'>Tabela de processos</div>", unsafe_allow_html=True)
    st.dataframe(df_processos_base, use_container_width=True, height=360)


def render_metas():
    if df_metas_base.empty:
        st.info("Sem dados de metas disponíveis no momento.")
        return

    st.markdown("<div class='section-title'>Tabela de metas</div>", unsafe_allow_html=True)
    st.dataframe(df_metas_base, use_container_width=True, height=320)

    if df_base.empty:
        st.info("Sem base de produtividade para comparar metas x realizado.")
        return

    realizado = (
        df_base.groupby(["Consultor", "Etapa"], as_index=False)["Valor"]
        .sum()
    )

    linhas = []
    for _, row in df_metas_base.iterrows():
        consultor = str(row["consultor"]).strip()

        rl = float(
            realizado[
                (realizado["Consultor"].astype(str).str.strip().str.lower() == consultor.lower())
                & (realizado["Etapa"] == "Leads")
            ]["Valor"].sum()
        )
        ra = float(
            realizado[
                (realizado["Consultor"].astype(str).str.strip().str.lower() == consultor.lower())
                & (realizado["Etapa"] == "Atendimento")
            ]["Valor"].sum()
        )
        rag = float(
            realizado[
                (realizado["Consultor"].astype(str).str.strip().str.lower() == consultor.lower())
                & (realizado["Etapa"] == "Agendamento Visita")
            ]["Valor"].sum()
        )
        rpd = float(
            realizado[
                (realizado["Consultor"].astype(str).str.strip().str.lower() == consultor.lower())
                & (realizado["Etapa"] == "Pasta Docs")
            ]["Valor"].sum()
        )
        rc = float(
            realizado[
                (realizado["Consultor"].astype(str).str.strip().str.lower() == consultor.lower())
                & (realizado["Etapa"] == "Crédito Aprovado")
            ]["Valor"].sum()
        )

        linhas.append(
            {
                "Consultor": consultor,
                "Meta Leads": row["meta_leads"],
                "Realizado Leads": rl,
                "Meta Atendimento": row["meta_atendimento"],
                "Realizado Atendimento": ra,
                "Meta Agendamento": row["meta_agendamento"],
                "Realizado Agendamento": rag,
                "Meta Pasta Docs": row["meta_pasta_docs"],
                "Realizado Pasta Docs": rpd,
                "Meta Crédito": row["meta_credito"],
                "Realizado Crédito": rc,
                "Meta Valor": row["meta_valor"],
            }
        )

    df_comp = pd.DataFrame(linhas)

    st.markdown("<div class='section-title'>Meta x realizado de leads</div>", unsafe_allow_html=True)
    fig_leads = go.Figure()
    fig_leads.add_bar(name="Meta", x=df_comp["Consultor"], y=df_comp["Meta Leads"])
    fig_leads.add_bar(name="Realizado", x=df_comp["Consultor"], y=df_comp["Realizado Leads"])
    fig_leads.update_layout(barmode="group", title="Leads • Meta x Realizado")
    st.plotly_chart(fig_leads, use_container_width=True)

    st.markdown("<div class='section-title'>Meta x realizado de crédito aprovado</div>", unsafe_allow_html=True)
    fig_credito = go.Figure()
    fig_credito.add_bar(name="Meta", x=df_comp["Consultor"], y=df_comp["Meta Crédito"])
    fig_credito.add_bar(name="Realizado", x=df_comp["Consultor"], y=df_comp["Realizado Crédito"])
    fig_credito.update_layout(barmode="group", title="Crédito Aprovado • Meta x Realizado")
    st.plotly_chart(fig_credito, use_container_width=True)

    st.markdown("<div class='section-title'>Resumo comparativo</div>", unsafe_allow_html=True)
    st.dataframe(df_comp, use_container_width=True, height=320)


def render_roleta():
    if df_roleta.empty:
        st.info("Sem dados de roleta disponíveis no momento.")
        return

    total = int(df_roleta["Roleta"].sum())
    media = round(float(df_roleta["Roleta"].mean()), 2) if not df_roleta.empty else 0
    pico = int(df_roleta["Roleta"].max()) if not df_roleta.empty else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        kpi_card("Total Roleta", total)
    with c2:
        kpi_card("Média por Dia", media)
    with c3:
        kpi_card("Pico Diário", pico)

    a, b = st.columns(2)

    with a:
        st.markdown("<div class='section-title'>Evolução da roleta</div>", unsafe_allow_html=True)
        fig_line = px.line(
            df_roleta,
            x="Dia",
            y="Roleta",
            markers=True,
            title="Evolução diária da roleta",
        )
        fig_line.update_layout(xaxis=dict(dtick=1))
        st.plotly_chart(fig_line, use_container_width=True)

    with b:
        st.markdown("<div class='section-title'>Volume por dia</div>", unsafe_allow_html=True)
        fig_bar = px.bar(
            df_roleta,
            x="Dia",
            y="Roleta",
            text_auto=".0f",
            title="Roleta por dia",
        )
        fig_bar.update_layout(xaxis=dict(dtick=1))
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("<div class='section-title'>Tabela da roleta</div>", unsafe_allow_html=True)
    st.dataframe(df_roleta, use_container_width=True, height=300)


# =========================
# PAGE ROUTING
# =========================
if pagina == "Visão Completa":
    render_produtividade()
    st.divider()
    render_processos()
    st.divider()
    render_metas()
    st.divider()
    render_roleta()

elif pagina == "Produtividade":
    render_produtividade()

elif pagina == "Processos Quentes":
    render_processos()

elif pagina == "Metas":
    render_metas()

elif pagina == "Roleta":
    render_roleta()