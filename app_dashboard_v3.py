
# ===============================
# DASHBOARD V3 - COMPLETO E OTIMIZADO
# ===============================

import time
import unicodedata
import pandas as pd
import streamlit as st
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components

st.set_page_config(page_title="Time Aliados", layout="wide")

# ===============================
# CONFIG
# ===============================

SHEET_ID = "COLOQUE_AQUI_O_ID_DA_PLANILHA"

RANGE_CONSULTOR = "A1:AF20"
RANGE_PROCESSOS = "A1:I500"
RANGE_METAS = "A1:G50"
RANGE_ROLETA = "A1:B40"

ETAPAS = [
    "Leads",
    "Atendimento",
    "Agendamento Visita",
    "Pasta Docs",
    "Crédito Aprovado"
]

# ===============================
# AUTO REFRESH
# ===============================

def auto_refresh(segundos):
    components.html(
        f"<script>setTimeout(function(){{window.parent.location.reload();}}, {segundos*1000});</script>",
        height=0,
    )


# ===============================
# NORMALIZAÇÃO
# ===============================

def normalizar_texto(t):
    if t is None:
        return ""
    t = str(t).lower().strip()
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")


def normalizar_numero(v):
    try:
        v = str(v).replace("R$", "").replace(".", "").replace(",", ".")
        return float(v)
    except:
        return 0


# ===============================
# GOOGLE
# ===============================

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


# ===============================
# PRODUTIVIDADE (BATCH)
# ===============================

@st.cache_data(ttl=300)
def carregar_produtividade():

    sh = abrir_planilha()

    abas = [ws.title for ws in sh.worksheets()]

    ranges = [f"'{a}'!{RANGE_CONSULTOR}" for a in abas]

    try:
        respostas = sh.values_batch_get(ranges).get("valueRanges", [])
    except:
        return pd.DataFrame()

    dados = []

    for aba, bloco in zip(abas, respostas):

        valores = bloco.get("values", [])

        if not valores:
            continue

        for etapa in ETAPAS:

            linha = None

            for i, l in enumerate(valores):
                if len(l) > 0 and normalizar_texto(l[0]) == normalizar_texto(etapa):
                    linha = i

            if linha is None:
                continue

            for dia in range(1, 31):

                try:
                    valor = normalizar_numero(valores[linha][dia])
                except:
                    valor = 0

                dados.append(
                    {
                        "Consultor": aba,
                        "Etapa": etapa,
                        "Dia": dia,
                        "Valor": valor,
                    }
                )

    df = pd.DataFrame(dados)

    return df


# ===============================
# PROCESSOS QUENTES
# ===============================

@st.cache_data(ttl=300)
def carregar_processos():

    sh = abrir_planilha()

    try:
        ws = sh.worksheet("PROCESSOS_QUENTES")
    except:
        return pd.DataFrame()

    valores = ws.get(RANGE_PROCESSOS)

    if len(valores) < 2:
        return pd.DataFrame()

    df = pd.DataFrame(valores[1:], columns=valores[0])

    if "status" in df.columns:
        df["status"] = df["status"].astype(str)

    if "valor do imóvel" in df.columns:
        df["valor"] = df["valor do imóvel"].apply(normalizar_numero)

    return df


# ===============================
# METAS
# ===============================

@st.cache_data(ttl=300)
def carregar_metas():

    sh = abrir_planilha()

    try:
        ws = sh.worksheet("METAS")
    except:
        return pd.DataFrame()

    valores = ws.get(RANGE_METAS)

    if len(valores) < 2:
        return pd.DataFrame()

    df = pd.DataFrame(valores[1:], columns=valores[0])

    return df


# ===============================
# ROLETA
# ===============================

@st.cache_data(ttl=300)
def carregar_roleta():

    sh = abrir_planilha()

    try:
        ws = sh.worksheet("ROLETA")
    except:
        return pd.DataFrame()

    valores = ws.get(RANGE_ROLETA)

    if len(valores) < 2:
        return pd.DataFrame()

    df = pd.DataFrame(valores[1:], columns=valores[0])

    return df


# ===============================
# UI
# ===============================

st.title("📊 Dashboard Time Aliados")

with st.sidebar:

    auto = st.toggle("Atualização automática", False)

    intervalo = st.selectbox("Intervalo", [300, 600, 900])

    if st.button("Atualizar"):
        st.cache_data.clear()
        st.rerun()

if auto:
    auto_refresh(intervalo)


# ===============================
# LOAD
# ===============================

df_prod = carregar_produtividade()
df_proc = carregar_processos()
df_metas = carregar_metas()
df_roleta = carregar_roleta()


# ===============================
# PRODUTIVIDADE
# ===============================

st.header("Produtividade")

if not df_prod.empty:

    col1, col2, col3, col4, col5 = st.columns(5)

    for i, etapa in enumerate(ETAPAS):

        total = int(df_prod[df_prod["Etapa"] == etapa]["Valor"].sum())

        [col1, col2, col3, col4, col5][i].metric(etapa, total)

    evolucao = (
        df_prod.groupby(["Dia", "Etapa"])["Valor"]
        .sum()
        .reset_index()
    )

    fig = px.line(evolucao, x="Dia", y="Valor", color="Etapa")
    st.plotly_chart(fig, use_container_width=True)

    ranking = (
        df_prod[df_prod["Etapa"] == "Leads"]
        .groupby("Consultor")["Valor"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )

    fig = px.bar(ranking, x="Valor", y="Consultor", orientation="h")
    st.plotly_chart(fig, use_container_width=True)


# ===============================
# PROCESSOS
# ===============================

st.header("Processos Quentes")

if not df_proc.empty:

    if "status" in df_proc.columns:

        status = df_proc["status"].value_counts().reset_index()

        fig = px.bar(status, x="index", y="status")

        st.plotly_chart(fig, use_container_width=True)

    if "valor" in df_proc.columns:

        st.metric("Pipeline Total", int(df_proc["valor"].sum()))


# ===============================
# METAS
# ===============================

st.header("Metas")

if not df_metas.empty:

    st.dataframe(df_metas)


# ===============================
# ROLETA
# ===============================

st.header("Roleta")

if not df_roleta.empty:

    if "roleta" in df_roleta.columns:

        fig = px.line(df_roleta, x="data", y="roleta")

        st.plotly_chart(fig, use_container_width=True)
