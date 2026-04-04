# ===============================
# DASHBOARD V3 - SUPABASE
# ===============================

import unicodedata
import pandas as pd
import streamlit as st
import plotly.express as px
import streamlit.components.v1 as components
from supabase import create_client, Client

st.set_page_config(page_title="Time Aliados", layout="wide")

# ===============================
# CONFIG
# ===============================

ETAPAS = [
    "Leads",
    "Atendimento",
    "Visitas Agendadas",
    "Visitas Realizadas",
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
# SUPABASE
# ===============================

@st.cache_resource
def conectar_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

# ===============================
# PRODUTIVIDADE
# ===============================

@st.cache_data(ttl=300)
def carregar_produtividade():
    supabase = conectar_supabase()

    # usuários
    usuarios_res = supabase.table("usuarios").select("id,nome").eq("ativo", True).execute()
    usuarios = usuarios_res.data or []

    if not usuarios:
        return pd.DataFrame()

    mapa_usuarios = {u["id"]: u["nome"] for u in usuarios}

    # etapas
    etapas_res = supabase.table("etapas").select("id,nome,ordem").eq("ativo", True).order("ordem").execute()
    etapas = etapas_res.data or []

    if not etapas:
        return pd.DataFrame()

    mapa_etapas = {e["id"]: e["nome"] for e in etapas}

    # produtividade
    prod_res = supabase.table("produtividade_diaria").select(
        "usuario_id,etapa_id,data_referencia,quantidade"
    ).execute()

    dados = prod_res.data or []

    if not dados:
        return pd.DataFrame()

    registros = []

    for row in dados:
        usuario_nome = mapa_usuarios.get(row["usuario_id"], "Desconhecido")
        etapa_nome = mapa_etapas.get(row["etapa_id"], "Desconhecida")
        data_ref = pd.to_datetime(row["data_referencia"], errors="coerce")

        if pd.isna(data_ref):
            continue

        registros.append({
            "Consultor": usuario_nome,
            "Etapa": etapa_nome,
            "Dia": int(data_ref.day),
            "Mes": int(data_ref.month),
            "Ano": int(data_ref.year),
            "Data": data_ref,
            "Valor": normalizar_numero(row["quantidade"]),
        })

    return pd.DataFrame(registros)

# ===============================
# PROCESSOS QUENTES
# ===============================

@st.cache_data(ttl=300)
def carregar_processos():
    supabase = conectar_supabase()

    try:
        res = supabase.table("processos_quentes").select("*").execute()
        dados = res.data or []
        if not dados:
            return pd.DataFrame()

        df = pd.DataFrame(dados)

        if "status" in df.columns:
            df["status"] = df["status"].astype(str)

        if "valor_imovel" in df.columns:
            df["valor"] = df["valor_imovel"].apply(normalizar_numero)

        return df
    except:
        return pd.DataFrame()

# ===============================
# METAS
# ===============================

@st.cache_data(ttl=300)
def carregar_metas():
    supabase = conectar_supabase()

    try:
        res = supabase.table("metas").select("*").execute()
        dados = res.data or []
        if not dados:
            return pd.DataFrame()
        return pd.DataFrame(dados)
    except:
        return pd.DataFrame()

# ===============================
# ROLETA
# ===============================

@st.cache_data(ttl=300)
def carregar_roleta():
    supabase = conectar_supabase()

    try:
        res = supabase.table("roleta").select("*").execute()
        dados = res.data or []
        if not dados:
            return pd.DataFrame()
        return pd.DataFrame(dados)
    except:
        return pd.DataFrame()

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
# FILTRO MÊS / ANO
# ===============================

if not df_prod.empty:
    st.sidebar.markdown("## Filtros")

    anos = sorted(df_prod["Ano"].dropna().unique().tolist())
    meses = sorted(df_prod["Mes"].dropna().unique().tolist())

    ano_sel = st.sidebar.selectbox("Ano", anos, index=len(anos)-1 if anos else 0)
    mes_sel = st.sidebar.selectbox("Mês", meses, index=len(meses)-1 if meses else 0)

    df_prod = df_prod[(df_prod["Ano"] == ano_sel) & (df_prod["Mes"] == mes_sel)]

# ===============================
# PRODUTIVIDADE
# ===============================

st.header("Produtividade")

if not df_prod.empty:

    cols = st.columns(len(ETAPAS))

    for i, etapa in enumerate(ETAPAS):
        total = int(df_prod[df_prod["Etapa"] == etapa]["Valor"].sum())
        cols[i].metric(etapa, total)

    # Métrica de comparecimento
    agendadas = df_prod[df_prod["Etapa"] == "Visitas Agendadas"]["Valor"].sum()
    realizadas = df_prod[df_prod["Etapa"] == "Visitas Realizadas"]["Valor"].sum()
    taxa_visita = (realizadas / agendadas * 100) if agendadas > 0 else 0

    st.metric("Taxa de Visitas Realizadas", f"{taxa_visita:.1f}%")

    # Evolução diária
    evolucao = (
        df_prod.groupby(["Dia", "Etapa"])["Valor"]
        .sum()
        .reset_index()
    )

    fig = px.line(
        evolucao,
        x="Dia",
        y="Valor",
        color="Etapa",
        title="Evolução diária por etapa"
    )
    st.plotly_chart(fig, use_container_width=True)

    # Ranking por leads
    ranking = (
        df_prod[df_prod["Etapa"] == "Leads"]
        .groupby("Consultor")["Valor"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )

    fig = px.bar(
        ranking,
        x="Valor",
        y="Consultor",
        orientation="h",
        title="Ranking de Leads por Consultor"
    )
    st.plotly_chart(fig, use_container_width=True)

    # Funil consolidado
    funil = (
        df_prod.groupby("Etapa")["Valor"]
        .sum()
        .reset_index()
    )

    funil["Etapa"] = pd.Categorical(funil["Etapa"], categories=ETAPAS, ordered=True)
    funil = funil.sort_values("Etapa")

    fig = px.funnel(funil, x="Valor", y="Etapa", title="Funil de Conversão")
    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("Nenhum dado encontrado para produtividade.")

# ===============================
# PROCESSOS QUENTES
# ===============================

st.header("Processos Quentes")

if not df_proc.empty:

    if "status" in df_proc.columns:
        status = df_proc["status"].value_counts().reset_index()
        status.columns = ["Status", "Quantidade"]

        fig = px.bar(status, x="Status", y="Quantidade", title="Status dos Processos")
        st.plotly_chart(fig, use_container_width=True)

    if "valor" in df_proc.columns:
        st.metric("Pipeline Total", f"R$ {df_proc['valor'].sum():,.0f}".replace(",", "."))

    st.dataframe(df_proc, use_container_width=True)

else:
    st.info("Nenhum dado em Processos Quentes.")

# ===============================
# METAS
# ===============================

st.header("Metas")

if not df_metas.empty:
    st.dataframe(df_metas, use_container_width=True)
else:
    st.info("Nenhuma meta cadastrada.")

# ===============================
# ROLETA
# ===============================

st.header("Roleta")

if not df_roleta.empty:
    if "roleta" in df_roleta.columns and "data" in df_roleta.columns:
        fig = px.line(df_roleta, x="data", y="roleta", title="Evolução da Roleta")
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(df_roleta, use_container_width=True)

else:
    st.info("Nenhum dado da roleta.")
