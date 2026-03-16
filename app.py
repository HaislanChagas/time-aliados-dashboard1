import time
import unicodedata

import gspread
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Time Aliados", page_icon="📊", layout="wide")

# =========================
# CONFIG
# =========================
SHEET_ID = "1KvGqEJ26oGsayOYZv3ynaiiN0ya9VxG6ofDoBOKu22w"
LOGO_PATH = "logo_time_aliados.png"

# Intervalos fixos para reduzir leituras da API
RANGE_CONSULTOR = "A1:AF20"
RANGE_PROCESSOS = "A1:I500"
RANGE_METAS = "A1:G50"
RANGE_ROLETA = "A1:B40"

ETAPAS = ["Leads", "Atendimento", "Agendamento Visita", "Pasta Docs", "Crédito Aprovado"]

ABAS_PROCESSOS_CANDIDATAS = ["PROCESSOS_QUENTES", "PROCESSOS QUENTES", "Processos Quentes", "PIPE", "Pipe"]
ABAS_METAS_CANDIDATAS = ["METAS", "Metas", "META", "Meta"]
ABAS_ROLETA_CANDIDATAS = ["ROLETA", "Roleta", "ROLETA - CONTROLE DE LEADS", "ROLETA – CONTROLE DE LEADS"]

COLUNAS_PROCESSOS_MAP = {
    "gerente": ["gerente"],
    "corretor": ["corretor", "consultor"],
    "cliente": ["cliente", "nome cliente"],
    "construtora": ["construtora"],
    "produto": ["produto", "empreendimento"],
    "status": ["status", "etapa"],
    "correspondente": ["correspondente"],
    "valor_imovel": ["valor do imovel", "valor do imóvel", "valor imovel", "valor imóvel", "valor"],
    "valor_financiamento": ["valor financiamento aprovado", "valor do financiamento aprovado", "financiamento aprovado", "valor financiamento"],
}

COLUNAS_METAS_MAP = {
    "consultor": ["consultor", "corretor", "nome"],
    "meta_leads": ["meta leads", "leads", "meta lead"],
    "meta_atendimento": ["meta atendimento", "atendimento"],
    "meta_agendamento": ["meta agendamento", "meta agendamento visita", "agendamento visita", "agendamento"],
    "meta_pasta_docs": ["meta pasta docs", "pasta docs", "meta docs"],
    "meta_credito": ["meta credito", "meta crédito", "credito aprovado", "crédito aprovado", "meta credito aprovado", "meta crédito aprovado"],
    "meta_valor": ["meta valor", "meta valor venda", "meta financeira", "meta valor total"],
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

STATUS_PROB = {
    "APROVADO": 0.90,
    "EM ANALISE": 0.60,
    "EM ANÁLISE": 0.60,
    "AGUARDANDO IR": 0.40,
    "AGUARDANDO DOCS": 0.50,
    "REPROVADO": 0.00,
    "VENDA REALIZADA": 1.00,
}

st.markdown("""
<style>
.stApp { background: radial-gradient(circle at top, #122543 0%, #08111f 45%, #070d18 100%); color: #e8edf7; }
.block-container { padding-top: 1.6rem; padding-bottom: 1rem; max-width: 1540px; }
.card { background: linear-gradient(180deg, rgba(19,31,54,0.96), rgba(10,18,34,0.98)); border: 1px solid rgba(255,255,255,0.08); border-radius: 18px; padding: 18px 20px; box-shadow: 0 12px 30px rgba(0,0,0,0.25); min-height: 110px; }
.card-title { color: #b7c3da; font-size: 14px; margin-bottom: 8px; }
.card-value { color: #ffffff; font-size: 34px; font-weight: 700; line-height: 1.1; }
.section-title { font-size: 22px; font-weight: 700; color: #ffffff; margin: 10px 0 8px 0; }
.kanban-card { background: linear-gradient(180deg, rgba(19,31,54,0.95), rgba(10,18,34,0.98)); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 14px 16px; box-shadow: 0 10px 22px rgba(0,0,0,0.22); margin-bottom: 8px; }
.kanban-status { font-size: 13px; color: #b7c3da; margin-bottom: 10px; font-weight: 600; }
.kanban-value { font-size: 30px; color: #fff; font-weight: 800; line-height: 1; margin-bottom: 10px; }
.kanban-bar { width: 100%; height: 8px; border-radius: 999px; background: rgba(255,255,255,0.08); overflow: hidden; }
.kanban-fill { height: 100%; border-radius: 999px; }
.small-note { color: #9fb0cf; font-size: 12px; margin-top: 6px; }
.brand-header { padding-top: 10px; padding-bottom: 8px; }
.brand-title { font-size: 34px; font-weight: 800; line-height: 1.1; margin-bottom: 6px; background: linear-gradient(90deg, #ffffff 0%, #f2c14e 55%, #d89b00 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.brand-subtitle { color: #b7c3da; font-size: 14px; margin-bottom: 6px; }
</style>
""", unsafe_allow_html=True)

def auto_refresh(seconds=300):
    components.html(
        f"<script>setTimeout(function(){{window.parent.location.reload();}}, {seconds*1000});</script>",
        height=0, width=0
    )

def normalizar_texto(texto):
    if texto is None:
        return ""
    texto = str(texto).strip().lower()
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")

def normalizar_numero(valor):
    if valor is None:
        return 0
    texto = str(valor).strip()
    if texto == "":
        return 0
    texto = texto.replace("R$", "").replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except Exception:
        return 0

def formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def encontrar_linha_etapa(valores_planilha, etapa):
    etapa_norm = normalizar_texto(etapa)
    for idx, linha in enumerate(valores_planilha):
        if len(linha) > 0 and normalizar_texto(linha[0]) == etapa_norm:
            return idx
    return None

def encontrar_indice_coluna(colunas, possiveis_nomes):
    colunas_norm = [normalizar_texto(c) for c in colunas]
    for nome in possiveis_nomes:
        nome_norm = normalizar_texto(nome)
        if nome_norm in colunas_norm:
            return colunas_norm.index(nome_norm)
    return None

def status_cor(status):
    return STATUS_CORES.get(str(status).strip().upper(), "#64748b")

def status_prob(status):
    return STATUS_PROB.get(str(status).strip().upper(), 0.20)

def kpi_card(title, value, subtitle=""):
    st.markdown(
        f'<div class="card"><div class="card-title">{title}</div><div class="card-value" style="font-size:28px;">{value}</div><div class="small-note">{subtitle}</div></div>',
        unsafe_allow_html=True
    )

@st.cache_resource
def conectar_google():
    creds_info = dict(st.secrets["gcp_service_account"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
    return gspread.authorize(credentials)

@st.cache_resource
def abrir_planilha():
    gc = conectar_google()
    return gc.open_by_key(SHEET_ID)

def ler_intervalo_seguro(ws, intervalo, tentativas=3):
    ultimo = None
    for _ in range(tentativas):
        try:
            return ws.get(intervalo)
        except Exception as e:
            ultimo = e
            time.sleep(1.5)
    raise ultimo

def localizar_aba(sheet, candidatas):
    nomes = [ws.title for ws in sheet.worksheets()]
    nomes_norm = {normalizar_texto(n): n for n in nomes}
    for candidata in candidatas:
        if normalizar_texto(candidata) in nomes_norm:
            return nomes_norm[normalizar_texto(candidata)]
    return None

def aba_parece_consultor(valores):
    encontrados = 0
    for etapa in ETAPAS:
        if encontrar_linha_etapa(valores, etapa) is not None:
            encontrados += 1
    return encontrados >= 4

@st.cache_data(ttl=300)
def listar_abas_consultores():
    try:
        sh = abrir_planilha()
    except Exception:
        return []
    ignorar = set(normalizar_texto(x) for x in (ABAS_PROCESSOS_CANDIDATAS + ABAS_METAS_CANDIDATAS + ABAS_ROLETA_CANDIDATAS))
    consultores = []
    for ws in sh.worksheets():
        if normalizar_texto(ws.title) in ignorar:
            continue
        try:
            valores = ler_intervalo_seguro(ws, RANGE_CONSULTOR)
            if aba_parece_consultor(valores):
                consultores.append(ws.title)
        except Exception:
            continue
    return consultores

@st.cache_data(ttl=300)
def carregar_dados_produtividade():
    try:
        sh = abrir_planilha()
    except Exception as e:
        return pd.DataFrame(columns=["Consultor", "Etapa", "Dia", "Valor"]), [f"Planilha: {type(e).__name__}"], []

    consultores = listar_abas_consultores()
    if not consultores:
        return pd.DataFrame(columns=["Consultor", "Etapa", "Dia", "Valor"]), ["Nenhuma aba de consultor encontrada."], []

    erros = []
    dados = []

    try:
        ranges = [f"'{aba}'!{RANGE_CONSULTOR}" for aba in consultores]
        respostas = sh.values_batch_get(ranges).get("valueRanges", [])
    except Exception as e:
        return pd.DataFrame(columns=["Consultor", "Etapa", "Dia", "Valor"]), [f"Batch produtividade: {type(e).__name__}"], consultores

    for aba, bloco in zip(consultores, respostas):
        try:
            valores = bloco.get("values", [])
            if not valores:
                erros.append(f"{aba}: vazio")
                continue

            max_dia = 31 if any(normalizar_texto(c) == "31" for linha in valores[:6] for c in linha) else 30

            for etapa in ETAPAS:
                idx = encontrar_linha_etapa(valores, etapa)
                if idx is None:
                    linha_numeros = [0] * max_dia
                else:
                    linha = valores[idx]
                    linha_numeros = [normalizar_numero(linha[i]) if i < len(linha) else 0 for i in range(1, max_dia + 1)]

                for dia_idx in range(max_dia):
                    dados.append({
                        "Consultor": aba,
                        "Etapa": etapa,
                        "Dia": dia_idx + 1,
                        "Valor": linha_numeros[dia_idx],
                    })
        except Exception as e:
            erros.append(f"{aba}: {type(e).__name__}")

    if not dados:
        return pd.DataFrame(columns=["Consultor", "Etapa", "Dia", "Valor"]), erros, consultores

    df = pd.DataFrame(dados)
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0)
    df["Dia"] = pd.to_numeric(df["Dia"], errors="coerce").fillna(0).astype(int)
    return df, erros, consultores

def detectar_header_generico(valores, mapa_colunas, min_encontrados=2, limite_linhas=15):
    chaves = list(mapa_colunas.keys())
    for idx, linha in enumerate(valores[:limite_linhas]):
        encontrados = 0
        for chave in chaves:
            col_idx = encontrar_indice_coluna(linha, mapa_colunas[chave])
            if col_idx is not None:
                encontrados += 1
        if encontrados >= min_encontrados:
            return idx
    return None

@st.cache_data(ttl=300)
def carregar_processos_quentes():
    try:
        sh = abrir_planilha()
        nome_aba = localizar_aba(sh, ABAS_PROCESSOS_CANDIDATAS)
        if not nome_aba:
            return pd.DataFrame(), ["Aba de processos quentes não encontrada."]
        ws = sh.worksheet(nome_aba)
        valores = ler_intervalo_seguro(ws, RANGE_PROCESSOS)
        if not valores:
            return pd.DataFrame(), [f"A aba {nome_aba} está vazia."]
        header_idx = detectar_header_generico(valores, COLUNAS_PROCESSOS_MAP, min_encontrados=4)
        if header_idx is None:
            return pd.DataFrame(), [f"Não consegui identificar o cabeçalho da aba {nome_aba}."]
        header = valores[header_idx]
        linhas = valores[header_idx + 1:]
        max_cols = len(header)
        linhas_ajustadas = []
        for linha in linhas:
            linha = linha[:max_cols] + [""] * max(0, max_cols - len(linha))
            if any(str(c).strip() != "" for c in linha):
                linhas_ajustadas.append(linha)
        if not linhas_ajustadas:
            return pd.DataFrame(), [f"A aba {nome_aba} está sem linhas preenchidas."]
        df_raw = pd.DataFrame(linhas_ajustadas, columns=header)
        dados = {}
        for campo, aliases in COLUNAS_PROCESSOS_MAP.items():
            idx = encontrar_indice_coluna(list(df_raw.columns), aliases)
            dados[campo] = df_raw.iloc[:, idx] if idx is not None else ""
        df = pd.DataFrame(dados)
        mascara = df["cliente"].astype(str).str.strip().ne("") | df["corretor"].astype(str).str.strip().ne("") | df["status"].astype(str).str.strip().ne("")
        df = df[mascara].copy()
        if df.empty:
            return pd.DataFrame(), [f"A aba {nome_aba} foi encontrada, mas não há processos válidos."]
        for col in ["status", "corretor", "cliente", "produto", "construtora", "correspondente", "gerente"]:
            df[col] = df[col].astype(str).str.strip()
        df["valor_imovel_num"] = df["valor_imovel"].apply(normalizar_numero)
        df["valor_financiamento_num"] = df["valor_financiamento"].apply(normalizar_numero)
        df["probabilidade"] = df["status"].apply(status_prob)
        df["valor_previsto_num"] = df["valor_imovel_num"] * df["probabilidade"]
        return df, []
    except Exception as e:
        return pd.DataFrame(), [f"Processos Quentes: {type(e).__name__}"]

@st.cache_data(ttl=300)
def carregar_metas():
    try:
        sh = abrir_planilha()
        nome_aba = localizar_aba(sh, ABAS_METAS_CANDIDATAS)
        if not nome_aba:
            return pd.DataFrame(), ["Aba de metas não encontrada."]
        ws = sh.worksheet(nome_aba)
        valores = ler_intervalo_seguro(ws, RANGE_METAS)
        if not valores:
            return pd.DataFrame(), [f"A aba {nome_aba} está vazia."]
        header_idx = detectar_header_generico(valores, COLUNAS_METAS_MAP, min_encontrados=2)
        if header_idx is None:
            return pd.DataFrame(), [f"Não consegui identificar o cabeçalho da aba {nome_aba}."]
        header = valores[header_idx]
        linhas = valores[header_idx + 1:]
        max_cols = len(header)
        linhas_ajustadas = []
        for linha in linhas:
            linha = linha[:max_cols] + [""] * max(0, max_cols - len(linha))
            if any(str(c).strip() != "" for c in linha):
                linhas_ajustadas.append(linha)
        if not linhas_ajustadas:
            return pd.DataFrame(), [f"A aba {nome_aba} está sem dados de metas."]
        df_raw = pd.DataFrame(linhas_ajustadas, columns=header)
        dados = {}
        for campo, aliases in COLUNAS_METAS_MAP.items():
            idx = encontrar_indice_coluna(list(df_raw.columns), aliases)
            dados[campo] = df_raw.iloc[:, idx] if idx is not None else ""
        df = pd.DataFrame(dados)
        df["consultor"] = df["consultor"].astype(str).str.strip()
        df = df[df["consultor"] != ""].copy()
        for col in ["meta_leads", "meta_atendimento", "meta_agendamento", "meta_pasta_docs", "meta_credito", "meta_valor"]:
            df[col] = df[col].apply(normalizar_numero)
        return df, []
    except Exception as e:
        return pd.DataFrame(), [f"Metas: {type(e).__name__}"]

@st.cache_data(ttl=300)
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
        header = valores[header_idx]
        idx_data = encontrar_indice_coluna(header, ["data"])
        idx_roleta = encontrar_indice_coluna(header, ["roleta"])
        rows = []
        for linha in valores[header_idx + 1:]:
            data_val = linha[idx_data] if idx_data is not None and idx_data < len(linha) else ""
            roleta_val = linha[idx_roleta] if idx_roleta is not None and idx_roleta < len(linha) else ""
            if str(data_val).strip() != "" or str(roleta_val).strip() != "":
                rows.append({"Dia": normalizar_numero(data_val), "Roleta": normalizar_numero(roleta_val)})
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(), [f"A aba {nome_aba} não possui dados de roleta."]
        df["Dia"] = pd.to_numeric(df["Dia"], errors="coerce").fillna(0).astype(int)
        df["Roleta"] = pd.to_numeric(df["Roleta"], errors="coerce").fillna(0)
        return df, []
    except Exception as e:
        return pd.DataFrame(), [f"Roleta: {type(e).__name__}"]

header_col1, header_col2 = st.columns([1, 6])
with header_col1:
    try:
        st.image(LOGO_PATH, width=95)
    except Exception:
        pass
with header_col2:
    st.markdown('<div class="brand-header"><div class="brand-title">Time Aliados</div><div class="brand-subtitle">Painel com batch get para reduzir chamadas da API e evitar erro 429 nas abas dos consultores.</div></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Filtros")
    auto_atualizar = st.toggle("Atualização automática", value=False)
    intervalo = st.selectbox("Intervalo", [300, 600, 900], index=0, format_func=lambda x: f"{x} segundos")
    if st.button("Atualizar agora"):
        st.cache_data.clear()
        st.rerun()

if auto_atualizar:
    auto_refresh(intervalo)

df, erros, CONSULTOR_ABAS = carregar_dados_produtividade()
df_processos, erros_processos = carregar_processos_quentes()
df_metas, erros_metas = carregar_metas()
df_roleta, erros_roleta = carregar_roleta()

with st.sidebar:
    pagina = st.radio("Área do dashboard", ["Visão Completa", "Produtividade", "Processos Quentes", "Metas", "Roleta"], index=0)
    visao = st.radio("Modo de visualização", ["Equipe", "Consultor"], index=0)
    consultor_escolhido = None
    if visao == "Consultor":
        consultor_escolhido = st.selectbox("Selecione o consultor", CONSULTOR_ABAS if CONSULTOR_ABAS else ["Sem abas detectadas"])

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
elif visao == "Consultor" and consultor_escolhido:
    df_base = df[df["Consultor"] == consultor_escolhido].copy()
    titulo_visao = consultor_escolhido
else:
    df_base = df.copy()
    titulo_visao = "Equipe"

def render_produtividade():
    if df_base.empty:
        st.info("Sem dados de produtividade disponíveis no momento.")
        return
    kpis = df_base.groupby("Etapa", as_index=False)["Valor"].sum().set_index("Etapa")["Valor"].to_dict()
    cols = st.columns(5)
    cards = [("Leads", int(kpis.get("Leads", 0))), ("Atendimento", int(kpis.get("Atendimento", 0))), ("Agendamento Visita", int(kpis.get("Agendamento Visita", 0))), ("Pasta Docs", int(kpis.get("Pasta Docs", 0))), ("Crédito Aprovado", int(kpis.get("Crédito Aprovado", 0)))]
    for col, (titulo, valor) in zip(cols, cards):
        with col:
            kpi_card(f"{titulo_visao} • {titulo}", valor)
    st.markdown("<div class='section-title'>Produtividade da equipe</div>", unsafe_allow_html=True)
    evolucao = df_base.groupby(["Dia", "Etapa"], as_index=False)["Valor"].sum().sort_values("Dia")
    fig = px.line(evolucao, x="Dia", y="Valor", color="Etapa", markers=True, title=f"Evolução diária • {titulo_visao}")
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#EAF0FF", xaxis=dict(dtick=1))
    st.plotly_chart(fig, use_container_width=True)

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
            st.markdown(f'<div class="kanban-card"><div class="kanban-status">{row["Status"]}</div><div class="kanban-value">{int(row["Quantidade"])}</div><div class="kanban-bar"><div class="kanban-fill" style="width:{perc}%; background:{cor};"></div></div><div class="small-note">{perc}% do pipeline atual</div></div>', unsafe_allow_html=True)

def render_processos():
    st.markdown("<div class='section-title'>Processos quentes e previsão comercial</div>", unsafe_allow_html=True)
    if df_processos.empty:
        st.info("A aba de processos quentes não está disponível no momento.")
        return
    cols = st.columns(4)
    with cols[0]:
        kpi_card("Processos", len(df_processos))
    with cols[1]:
        kpi_card("Valor pipeline", formatar_moeda(df_processos["valor_imovel_num"].sum()))
    with cols[2]:
        kpi_card("Financiamento", formatar_moeda(df_processos["valor_financiamento_num"].sum()))
    with cols[3]:
        kpi_card("Valor previsto", formatar_moeda(df_processos["valor_previsto_num"].sum()))
    render_pipeline_visual(df_processos)

def montar_realizado_por_consultor():
    if df.empty:
        return pd.DataFrame(columns=["consultor", "realizado_leads", "realizado_credito", "realizado_valor_previsto"])
    resumo = df.groupby(["Consultor", "Etapa"], as_index=False)["Valor"].sum().pivot(index="Consultor", columns="Etapa", values="Valor").fillna(0).reset_index()
    for etapa in ETAPAS:
        if etapa not in resumo.columns:
            resumo[etapa] = 0
    resumo = resumo.rename(columns={"Consultor": "consultor", "Leads": "realizado_leads", "Crédito Aprovado": "realizado_credito"})
    if not df_processos.empty:
        valor_por_cons = df_processos.groupby("corretor", as_index=False).agg(realizado_valor_previsto=("valor_previsto_num", "sum")).rename(columns={"corretor": "consultor"})
        resumo = resumo.merge(valor_por_cons, on="consultor", how="left")
    else:
        resumo["realizado_valor_previsto"] = 0
    resumo["realizado_valor_previsto"] = resumo["realizado_valor_previsto"].fillna(0)
    return resumo

def render_metas():
    st.markdown("<div class='section-title'>Metas</div>", unsafe_allow_html=True)
    if df_metas.empty:
        st.info("A aba METAS não está disponível no momento.")
        return
    realizado = montar_realizado_por_consultor()
    merged = df_metas.copy().merge(realizado, on="consultor", how="left").fillna(0)
    cols = st.columns(3)
    with cols[0]:
        kpi_card("Meta Leads", int(merged["meta_leads"].sum()))
    with cols[1]:
        kpi_card("Meta Crédito", int(merged["meta_credito"].sum()))
    with cols[2]:
        kpi_card("Meta Valor", formatar_moeda(merged["meta_valor"].sum()))

def render_roleta():
    st.markdown("<div class='section-title'>Roleta</div>", unsafe_allow_html=True)
    if df_roleta.empty:
        st.info("A aba ROLETA não está disponível no momento.")
        return
    cols = st.columns(3)
    with cols[0]:
        kpi_card("Total", int(df_roleta["Roleta"].sum()))
    with cols[1]:
        media = df_roleta["Roleta"].replace(0, pd.NA).dropna().mean()
        kpi_card("Média", f"{(media if pd.notna(media) else 0):.2f}")
    with cols[2]:
        kpi_card("Maior dia", int(df_roleta["Roleta"].max()))

if pagina == "Produtividade":
    render_produtividade()
elif pagina == "Processos Quentes":
    render_processos()
elif pagina == "Metas":
    render_metas()
elif pagina == "Roleta":
    render_roleta()
else:
    render_produtividade()
    st.divider()
    render_processos()
    st.divider()
    render_metas()
    st.divider()
    render_roleta()
