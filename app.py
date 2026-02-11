import streamlit as st
import pandas as pd
import math
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import random
import time
import altair as alt
import os
import re
from dotenv import load_dotenv
from fpdf import FPDF

# Carrega variáveis de ambiente
load_dotenv()

# Importação das funções do cliente Supabase local
from supabase_client import (
    auth_login, auth_logout,
    criar_atendimento, listar_atendimentos, atualizar_atendimento,
    criar_chamado_interno, listar_chamados_internos, atualizar_chamado_interno
)

# -------------------------------------------------------
# CONFIGURAÇÕES DE AMBIENTE
# -------------------------------------------------------
TZ_BR = ZoneInfo("America/Sao_Paulo")

# LÓGICA DE ADMINS VIA .ENV (SEGURANÇA)
admins_env = os.getenv("ADMIN_EMAILS", "")
ADMINS = {email.strip() for email in admins_env.split(",") if email.strip()}

st.set_page_config(page_title="Gestão de Chamados", layout="wide", page_icon="📞")

# -------------------------------------------------------
# FUNÇÕES DE UTILIDADE
# -------------------------------------------------------
def reproduzir_bip():
    """Toca um som de notificação curto usando HTML5 audio."""
    audio_url = "https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3"
    st.markdown(f'<audio autoplay><source src="{audio_url}" type="audio/mp3"></audio>', unsafe_allow_html=True)

def agora_br(): return datetime.now(TZ_BR)
def agora_utc_iso(): return datetime.now(timezone.utc).isoformat()

def formatar_data_br(data_iso):
    if not data_iso: return "—"
    try:
        data_str = str(data_iso).replace('Z', '+00:00')
        dt = datetime.fromisoformat(data_str)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ_BR).strftime("%d/%m/%Y às %H:%M")
    except: return data_iso

def gerar_ticket(prefixo="ATD"):
    return f"{prefixo}-{datetime.now(TZ_BR).strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

def limpar_apenas_numeros(texto):
    if not texto: return ""
    return re.sub(r'\D', '', texto)

# -------------------------------------------------------
# GERADOR DE PDF
# -------------------------------------------------------
def gerar_pdf_comprovante(row):
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 14)
            self.cell(0, 10, 'COMPROVANTE DE ATENDIMENTO', 0, 1, 'C')
            self.ln(5)
        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

    def txt(texto):
        if not texto: return ""
        return str(texto).encode('latin-1', 'replace').decode('latin-1')

    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, txt(f"DADOS DO CHAMADO: {row['numero_chamado']}"), 0, 1, 'L', fill=True)
    pdf.set_font("Arial", size=10)
    
    pdf.cell(95, 8, txt(f"Data Abertura: {formatar_data_br(row['data_atendimento'])}"), 0, 0)
    pdf.cell(95, 8, txt(f"Status Atual: {row['andamento']}"), 0, 1)
    pdf.cell(95, 8, txt(f"Funcionário: {row['funcionario_atendido']}"), 0, 0)
    pdf.cell(95, 8, txt(f"CPF: {row.get('cpf') or '---'}"), 0, 1)
    pdf.cell(95, 8, txt(f"Assunto: {row['assunto']}"), 0, 0)
    pdf.cell(95, 8, txt(f"Atendente: {row.get('quem_realizou') or '---'}"), 0, 1)
    pdf.ln(5)

    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, txt("MOTIVO / DESCRIÇÃO:"), 0, 1, 'L', fill=True)
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 6, txt(row['motivo_contato']))
    pdf.ln(5)

    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, txt("HISTÓRICO DE RESOLUÇÃO E CONVERSAS:"), 0, 1, 'L', fill=True)
    pdf.set_font("Arial", size=9)
    
    historico = row.get('tratativa') or "Nenhum histórico registrado."
    pdf.multi_cell(0, 6, txt(historico))
    
    pdf.ln(10)
    pdf.set_font("Arial", 'I', 8)
    pdf.cell(0, 5, txt("Este documento foi gerado automaticamente pelo sistema de gestão."), 0, 1, 'C')

    return pdf.output(dest='S').encode('latin-1')

# -------------------------------------------------------
# MODAL 1: ATENDIMENTO GERAL
# -------------------------------------------------------
@st.dialog("📂 Detalhes do Atendimento", width="large")
def modal_editar(row):
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.subheader(f"{row['numero_chamado']} - {row['assunto']}")
        st.caption(f"📅 Aberto em: {formatar_data_br(row['data_atendimento'])} | 🕒 Atualizado: {formatar_data_br(row.get('ultima_atualizacao'))}")
    with col_t2:
        pdf_bytes = gerar_pdf_comprovante(row)
        st.download_button("📄 Baixar Comprovante", data=pdf_bytes, file_name=f"Comprovante_{row['numero_chamado']}.pdf", mime="application/pdf", use_container_width=True)

    st.divider()
    st.markdown("#### 👤 Dados do Colaborador")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"**Funcionário:** {row['funcionario_atendido']}")
        st.markdown(f"**CPF:** {row.get('cpf') or '---'}")
        st.markdown(f"**Criado por:** {row.get('criado_por', '---')}")
    with c2:
        st.markdown(f"**Meio de Contato:** {row['meio_atendimento']}")
        
        # Exibe se foi recepção ou não
        is_recepcao = row.get('recepcao', False)
        if is_recepcao:
            st.markdown("📍 **Origem:** Recepção")
        
        tel_raw = row.get('telefone')
        st.markdown(f"**Telefone:** {tel_raw or '---'}")
        if tel_raw:
            nums = limpar_apenas_numeros(tel_raw)
            if len(nums) >= 10:
                if not nums.startswith('55'): nums = f"55{nums}"
                st.link_button("💬 Enviar WhatsApp", f"https://wa.me/{nums}")
    with c3:
        st.markdown(f"**Atendente Atual:** {row.get('quem_realizou') or '---'}")

    st.divider()
    st.markdown("#### 📝 Motivo do Contato")
    st.info(row['motivo_contato'])
    st.divider()

    st.markdown("#### 💬 Histórico de Conversa")
    historico_atual = row.get('tratativa') or ""
    if historico_atual:
        with st.container(height=250, border=True):
            st.markdown(historico_atual)
    else:
        st.caption("Nenhuma tratativa registrada ainda.")

    st.divider()
    st.markdown("#### ⚙️ Nova Interação")
    
    # === LÓGICA DE BLOQUEIO SE CONCLUÍDO ===
    status_atual = row['andamento']

    if status_atual == "Concluído":
        st.warning("🔒 **Este chamado está CONCLUÍDO.** Não é possível realizar novas alterações.")
        st.write("Deseja reabrir este chamado para continuar o atendimento?")
        
        if st.button("🔄 Reabrir Chamado", key=f"btn_reopen_{row['id']}", type="primary"):
            ts = agora_utc_iso()
            user_email = st.session_state.user.email
            dt_fmt = agora_br().strftime("%d/%m/%Y às %H:%M")
            
            # Log de Reabertura
            log_reopen = f"\n\n--- 🔄 **CHAMADO REABERTO** por {user_email} em {dt_fmt} ---\n"
            
            upd = {
                "andamento": "Aguardando", 
                "tratativa": (historico_atual or "") + log_reopen,
                "ultima_atualizacao": ts
            }
            
            atualizar_atendimento(row['id'], upd)
            st.success("Chamado reaberto com sucesso!")
            time.sleep(1)
            st.rerun()

    else:
        # === FORMULÁRIO PADRÃO (SE NÃO ESTIVER CONCLUÍDO) ===
        with st.form(key=f"form_atd_{row['id']}"):
            opcoes_status = ["Aguardando", "Concluído", "Excluído"]
            idx_status = opcoes_status.index(status_atual) if status_atual in opcoes_status else 0

            c_stat, c_atend = st.columns(2)
            n_status = c_stat.selectbox("Atualizar Status", opcoes_status, index=idx_status)
            n_atendente = c_atend.text_input("Atendente Responsável", value=row.get('quem_realizou') or "")
            
            nova_interacao = st.text_area("Adicionar Nova Resposta", height=100, placeholder="Digite a atualização do atendimento aqui...")
            
            if st.form_submit_button("💾 Enviar Atualização", use_container_width=True):
                if nova_interacao or n_status != status_atual or n_atendente != row.get('quem_realizou'):
                    ts = agora_utc_iso()
                    user_email = st.session_state.user.email
                    dt_fmt = agora_br().strftime("%d/%m/%Y às %H:%M")
                    
                    novo_bloco = ""
                    if nova_interacao: novo_bloco = f"\n\n**[{dt_fmt}] {user_email} escreveu:**\n{nova_interacao}\n___"
                    if n_status != status_atual: novo_bloco += f"\n\n*ℹ️ Status alterado de {status_atual} para {n_status} por {user_email} em {dt_fmt}*"

                    upd = {"andamento": n_status, "quem_realizou": n_atendente, "tratativa": historico_atual + novo_bloco, "ultima_atualizacao": ts}
                    if n_status == "Concluído" and not row.get("data_conclusao"): upd["data_conclusao"] = ts
                    
                    atualizar_atendimento(row['id'], upd)
                    st.success("Atendimento atualizado!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Nenhuma alteração realizada.")

    st.write("")
    with st.expander("🔒 Editar/Corrigir Histórico Completo (Requer Senha)"):
        senha_digitada = st.text_input("Senha de Administrador", type="password", key=f"pass_gen_{row['id']}")
        if senha_digitada == os.getenv("UNLOCK_PASSWORD"):
            st.warning("⚠️ Modo de Edição Completa.")
            texto_corrigido = st.text_area("Histórico Completo", value=historico_atual, height=300, key=f"full_edit_{row['id']}")
            if st.button("💾 Salvar Correção", key=f"btn_save_full_{row['id']}"):
                ts = agora_utc_iso()
                upd = {"tratativa": texto_corrigido, "ultima_atualizacao": ts}
                atualizar_atendimento(row['id'], upd)
                st.success("Histórico corrigido!")
                time.sleep(1)
                st.rerun()
        elif senha_digitada: st.error("Senha incorreta.")

# -------------------------------------------------------
# MODAL 2: CHAMADO INTERNO
# -------------------------------------------------------
@st.dialog("📂 Detalhes do Chamado Interno", width="large")
def modal_interno(row):
    st.subheader(f"{row['numero_ticket']} - {row['setor']}")
    st.caption(f"📅 Criado em: {formatar_data_br(row['created_at'])} | 🕒 Atualizado: {formatar_data_br(row.get('ultima_atualizacao'))}")
    st.divider()

    st.markdown("#### 👤 Dados do Solicitante")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Nome:** {row['solicitante']}")
        st.markdown(f"**Setor:** {row['setor']}")
    with c2:
        st.markdown(f"**E-mail:** {row['email']}")
        tel_raw = row.get('telefone')
        st.markdown(f"**Telefone:** {tel_raw or '---'}")
        if tel_raw:
            nums = limpar_apenas_numeros(tel_raw)
            if len(nums) >= 10:
                if not nums.startswith('55'): nums = f"55{nums}"
                st.link_button("💬 Enviar WhatsApp", f"https://wa.me/{nums}")
    
    st.divider()
    st.markdown("#### 📝 Descrição da Solicitação")
    st.info(row['descricao'])
    st.divider()

    st.markdown("#### 💬 Histórico de Tratativa")
    historico_atual = row.get('resolucao') or ""
    if historico_atual:
        with st.container(height=250, border=True):
            st.markdown(historico_atual)
    else:
        st.caption("Nenhum histórico registrado ainda.")

    st.divider()
    st.markdown("#### ⚙️ Nova Interação")
    status_atual = row.get('status', 'Pendente')

    if status_atual in ["Finalizado", "Cancelado"]:
        st.warning(f"Chamado encerrado como: **{status_atual.upper()}**")
        if st.button("🔄 Reabrir Chamado", key=f"btn_reopen_{row['id']}", type="primary"):
            ts = agora_utc_iso()
            user_email = st.session_state.user.email
            dt_fmt = agora_br().strftime("%d/%m/%Y às %H:%M")
            log = f"\n\n--- 🔄 **REABERTO** por {user_email} em {dt_fmt} ---\nMotivo: Reabertura solicitada."
            upd = {"status": "Pendente", "resolucao": historico_atual + log, "ultima_atualizacao": ts}
            atualizar_chamado_interno(row['id'], upd)
            st.success("Chamado reaberto!")
            time.sleep(1.5)
            st.rerun()
    else:
        with st.form(key=f"form_int_{row['id']}"):
            opcoes = ["Pendente", "Em Andamento", "Finalizado", "Cancelado"]
            idx = opcoes.index(status_atual) if status_atual in opcoes else 0
            n_status = st.selectbox("Atualizar Status", opcoes, index=idx)
            nova_msg = st.text_area("Adicionar Nova Resposta", height=100, placeholder="Digite a atualização...")
            
            if st.form_submit_button("💾 Enviar Atualização", use_container_width=True):
                if nova_msg or n_status != status_atual:
                    ts = agora_utc_iso()
                    user_email = st.session_state.user.email
                    dt_fmt = agora_br().strftime("%d/%m/%Y às %H:%M")
                    novo_bloco = ""
                    if nova_msg: novo_bloco = f"\n\n**[{dt_fmt}] {user_email} escreveu:**\n{nova_msg}\n___"
                    if n_status != status_atual: novo_bloco += f"\n\n*ℹ️ Status alterado de {status_atual} para {n_status} por {user_email} em {dt_fmt}*"

                    upd = {"status": n_status, "resolucao": historico_atual + novo_bloco, "ultima_atualizacao": ts}
                    atualizar_chamado_interno(row['id'], upd)
                    st.success("Registrado!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Nada alterado.")

        st.write("")
        with st.expander("🔒 Editar/Corrigir Histórico Completo (Requer Senha)"):
            senha_int = st.text_input("Senha de Administrador", type="password", key=f"pass_int_{row['id']}")
            if senha_int == os.getenv("UNLOCK_PASSWORD"):
                st.warning("⚠️ Modo de Edição Completa.")
                texto_full = st.text_area("Histórico Completo", value=historico_atual, height=300, key=f"full_edit_int_{row['id']}")
                if st.button("💾 Salvar Correção", key=f"save_full_int_{row['id']}"):
                    ts = agora_utc_iso()
                    upd = {"resolucao": texto_full, "ultima_atualizacao": ts}
                    atualizar_chamado_interno(row['id'], upd)
                    st.success("Histórico corrigido!")
                    time.sleep(1)
                    st.rerun()
            elif senha_int: st.error("Senha incorreta.")

# -------------------------------------------------------
# LOGIN
# -------------------------------------------------------
if "user" not in st.session_state: st.session_state.user = None

if not st.session_state.user:
    st.title("🔐 Login do Sistema")
    c1, _ = st.columns([1, 2])
    with c1:
        with st.form("form_login"):
            email = st.text_input("E-mail corporativo")
            senha = st.text_input("Senha", type="password")
            btn_login = st.form_submit_button("Entrar", use_container_width=True)

        if btn_login:
            if not email or not senha:
                st.warning("Preencha e-mail e senha.")
            else:
                try:
                    res = auth_login(email, senha)
                    st.session_state.user = res.user
                    st.rerun()
                except Exception:
                    st.error("Erro de acesso. Verifique suas credenciais.")
    st.stop()

USER_EMAIL = st.session_state.user.email
IS_ADMIN = USER_EMAIL in ADMINS

# -------------------------------------------------------
# SIDEBAR
# -------------------------------------------------------
if "pagina" not in st.session_state: st.session_state.pagina = "Novo Atendimento"

with st.sidebar:
    if os.path.exists("image_12.png"): st.image("image_12.png", width=200)
    else: st.markdown(f"**{USER_EMAIL}**")
    
    st.divider()
    st.caption("ATENDIMENTO GERAL")
    if st.button("📝 Novo Atendimento", use_container_width=True): st.session_state.pagina = "Novo Atendimento"
    if st.button("📋 Listar Chamados", use_container_width=True): st.session_state.pagina = "Listar Chamados"
    if st.button("📊 Dashboard", use_container_width=True): st.session_state.pagina = "Dashboard"
    
    st.divider()
    st.caption("CHAMADOS INTERNOS")
    if st.button("🏢 Novo Chamado Interno", use_container_width=True): st.session_state.pagina = "Interno_Novo"
    if st.button("🗂️ Listar Internos", use_container_width=True): st.session_state.pagina = "Interno_Lista"
    
    st.divider()
    if st.button("Sair", use_container_width=True):
        auth_logout()
        st.session_state.user = None
        st.rerun()

# =================================================================================
# PÁGINA: NOVO ATENDIMENTO (GERAL) - CAMPOS VAZIOS POR PADRÃO
# =================================================================================
if st.session_state.pagina == "Novo Atendimento":
    st.header("📝 Registrar Atendimento")
    if 'ticket_atual' not in st.session_state: st.session_state.ticket_atual = gerar_ticket("ATD")
    st.info(f"🎫 **Chamado:** `{st.session_state.ticket_atual}`")

    with st.form("form_novo", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            func = st.text_input("Funcionário Atendido *")
            cpf_input = st.text_input("CPF (Opcional - Apenas números)", max_chars=11, help="Digite apenas os 11 números.")
            # INDEX=NONE FAZ O SELECT COMEÇAR VAZIO
            meio = st.selectbox("Meio de Contato *", ["WhatsApp", "Telefone", "E-mail", "Presencial"], index=None, placeholder="Selecione o meio...")
            atend = st.text_input("Atendente", value=USER_EMAIL)
            
            st.write("") # Espaçamento
            # --- NOVO CHECKBOX SOLICITADO ---
            is_recepcao = st.checkbox("📍 Atendimento via Recepção?")

        with c2:
            assunto = st.selectbox("Assunto *", ["Salário", "Benefícios", "Férias", "Ponto", "Outros"], index=None, placeholder="Selecione o assunto...")
            tel_input = st.text_input("Telefone (Opcional)", help="Digite apenas números com DDD.")
            motivo = st.text_area("Motivo Detalhado *", height=135)
        
        if st.form_submit_button("💾 Salvar"):
            # VALIDAÇÃO REFORÇADA PARA OS CAMPOS QUE AGORA PODEM SER NONE
            if func and motivo and assunto and meio:
                ts = agora_utc_iso()
                cpf_limpo = limpar_apenas_numeros(cpf_input)
                tel_limpo = limpar_apenas_numeros(tel_input)
                payload = {
                    "user_id": st.session_state.user.id, "criado_por": USER_EMAIL,
                    "data_atendimento": ts, "ultima_atualizacao": ts,
                    "quem_realizou": atend, "funcionario_atendido": func,
                    "cpf": cpf_limpo, "telefone": tel_limpo,
                    "motivo_contato": motivo, "meio_atendimento": meio,
                    "assunto": assunto, "numero_chamado": st.session_state.ticket_atual,
                    "andamento": "Aguardando",
                    # --- ENVIANDO O NOVO CAMPO ---
                    "recepcao": is_recepcao 
                }
                criar_atendimento(payload)
                st.success("Registrado!")
                st.session_state.ticket_atual = gerar_ticket("ATD")
                time.sleep(1)
                st.rerun()
            else: st.error("Preencha Funcionário, Meio, Assunto e Motivo.")

# =================================================================================
# PÁGINA: LISTAR CHAMADOS (GERAL)
# =================================================================================
elif st.session_state.pagina == "Listar Chamados":
    
    col_tit, col_btn = st.columns([3, 1])
    with col_tit: st.header("📋 Atendimentos Gerais")
    with col_btn:
        st.write("")
        if st.button("🔄 Atualizar Lista", use_container_width=True, key="refresh_geral"): st.rerun()

    res = listar_atendimentos(st.session_state.user.id, admin=IS_ADMIN)
    dados = res.data if res and res.data else []
    
    if not dados: st.info("Sem dados.")
    else:
        with st.expander("🔍 Filtros", expanded=True):
            # ADICIONADO COLUNA F5 PARA O FILTRO DE RECEPÇÃO
            f1, f2, f3, f4, f5 = st.columns([2,1,1,1, 1]) 
            busca = f1.text_input("Buscar")
            d_ini = f2.date_input("Início", value=None)
            d_fim = f3.date_input("Fim", value=None)
            st_sel = f4.multiselect("Status", ["Aguardando", "Concluído"], default=["Aguardando", "Concluído"])
            
            # --- FILTRO NOVO ---
            f5.write("") # Espaçador para alinhar
            f5.write("")
            filtro_recepcao = f5.toggle("Só Recepção") # Toggle para filtrar

        filtrados = []
        for r in dados:
            try:
                data_str = str(r['data_atendimento'])
                if data_str.endswith('Z'): data_str = data_str.replace('Z', '+00:00')
                try: dt_r = datetime.fromisoformat(data_str)
                except ValueError: 
                    if "." in data_str: data_str = data_str.split(".")[0] + "+00:00"
                    dt_r = datetime.fromisoformat(data_str)
                
                if dt_r.tzinfo is None: dt_r = dt_r.replace(tzinfo=timezone.utc)
                dt_br = dt_r.astimezone(TZ_BR).date()
            except: continue

            # LÓGICA DE FILTRAGEM
            # 1. Busca textual
            if (busca and busca.lower() not in str(r).lower()): continue
            # 2. Status
            if (st_sel and r['andamento'] not in st_sel): continue
            # 3. Datas
            if (d_ini and dt_br < d_ini): continue
            if (d_fim and dt_br > d_fim): continue
            # 4. Recepção (NOVO)
            if filtro_recepcao and not r.get('recepcao'): continue

            filtrados.append(r)

        if 'pagina_atual_lista' not in st.session_state: st.session_state.pagina_atual_lista = 1
        itens = 10
        total_pags = math.ceil(len(filtrados)/itens)
        if st.session_state.pagina_atual_lista > total_pags: st.session_state.pagina_atual_lista = total_pags
        if st.session_state.pagina_atual_lista < 1: st.session_state.pagina_atual_lista = 1
        idx_ini = (st.session_state.pagina_atual_lista - 1) * itens
        
        for row in filtrados[idx_ini : idx_ini + itens]:
            status = row['andamento']
            if status == "Concluído": cor, bg = "#28a745", "#A5D6A7"
            elif status == "Excluído": cor, bg = "#d32f2f", "#EF9A9A"
            else: cor, bg = "#0288d1", "#90CAF9"

            raw_text = row.get('tratativa') or ''
            texto_limpo = raw_text.replace('\n', ' ').replace('\r', '')
            if len(texto_limpo) > 100: tratativa_preview = texto_limpo[:100] + "..."
            else: tratativa_preview = texto_limpo if texto_limpo else "..."

            # Verifica se é recepção para mostrar no card
            origem_tag = ""
            if row.get('recepcao'):
                origem_tag = '<span style="background:#FF9800; color:white; padding:3px 8px; border-radius:12px; font-size:0.75em; font-weight:bold; margin-left:5px;">📍 RECEPÇÃO</span>'

            card_html = f"""<div style="border-left:6px solid {cor}; background:{bg}; padding:15px; border-radius:8px; margin-bottom:10px; color:black;">
            <div style="display:flex; justify-content:space-between;"><span style="font-weight:600;">{row['numero_chamado']} | {row['funcionario_atendido']}</span><div>{origem_tag}<span style="background:{cor}; color:white; padding:3px 8px; border-radius:12px; font-size:0.75em; font-weight:bold; margin-left:5px;">{status.upper()}</span></div></div>
            <div style="font-size:0.85em; margin-top:5px; border-bottom:1px solid rgba(0,0,0,0.1); padding-bottom:5px;">📅 {formatar_data_br(row['data_atendimento'])} | 📂 {row['assunto']}</div>
            <div style="margin-top:8px; font-size:0.9em;"><strong>💬 Motivo:</strong> {row['motivo_contato']}</div>
            <div style="margin-top:5px; font-size: 0.9em; background: rgba(255,255,255,0.5); padding: 8px; border-radius: 4px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">
            <strong>🔧 Tratativa (Prévia):</strong> {tratativa_preview}
            </div>
            </div>"""
            st.markdown(card_html, unsafe_allow_html=True)
            if st.button("👁️ Ver Detalhes / Editar", key=f"bt_{row['id']}"): modal_editar(row)

        if total_pags > 1:
            st.divider()
            c_pg = st.columns([1, 2, 1])[1]
            c_pg.number_input("Página", 1, total_pags, key="pagina_atual_lista")

# =================================================================================
# PÁGINA: DASHBOARD (ATUALIZADO COM QUIOSQUE LIMITADO E GRÁFICO COLORIDO)
# =================================================================================
elif st.session_state.pagina == "Dashboard":
    c_head, c_date, c_ctrl = st.columns([2, 2, 2])
    with c_head:
        if os.path.exists("image_12.png"): st.image("image_12.png", width=250)
        else: st.subheader("Dashboard")
        st.caption(f"Carga: {agora_br().strftime('%H:%M:%S')}")
    
    with c_date:
        rng = st.date_input("Período", (agora_br().date()-timedelta(30), agora_br().date()), key="dash_range")
    
    with c_ctrl:
        st.write("")
        c_t1, c_t2 = st.columns(2)
        live = c_t1.toggle("🔴 Ao Vivo")
        som = c_t2.toggle("🔊 Som")
    
    st.markdown("---")
    
    res = listar_atendimentos(st.session_state.user.id, admin=IS_ADMIN)
    raw = pd.DataFrame(res.data) if res and res.data else pd.DataFrame()
    if not raw.empty:
        raw['dt'] = pd.to_datetime(raw['data_atendimento'], utc=True).dt.tz_convert(TZ_BR).dt.date
        df = raw.copy()
        
        # Filtro de data
        if rng:
            if len(rng)==2: df = df[(df['dt']>=rng[0]) & (df['dt']<=rng[1])]
            elif len(rng)==1: df = df[df['dt']==rng[0]]
        
        if df.empty: st.warning("Sem dados para o período.")
        else:
            tot = len(df)
            ab = len(df[df['andamento']=='Aguardando'])
            co = len(df[df['andamento']=='Concluído'])
            
            # Som de notificação
            if 'lt' not in st.session_state: st.session_state.lt = tot
            if tot > st.session_state.lt and som:
                reproduzir_bip()
                st.toast("Novo chamado!", icon="🔔")
            st.session_state.lt = tot
            
            # --- CARDS DE MÉTRICAS ---
            def card(tit, val, per_val, cor, bg="#1e1e1e", show_per=True):
                if show_per: per_html = f'<p style="margin:0; font-size:0.8em; font-weight:bold; color:{cor};">{per_val:.1f}% do total</p>'
                else: per_html = '<p style="margin:0; font-size:0.8em; color:transparent;">.</p>'
                return f"""<div style="background:{bg}; border-left:5px solid {cor}; padding:20px; border-radius:8px; box-shadow:2px 2px 5px rgba(0,0,0,0.2);">
                <p style="margin:0; font-size:0.9em; color:#ccc;">{tit}</p><h2 style="margin:5px 0; color:white;">{val}</h2>{per_html}</div>"""
            
            c1, c2, c3 = st.columns(3)
            c1.markdown(card("TOTAL", tot, 0, "white", "#262730", show_per=False), unsafe_allow_html=True)
            c2.markdown(card("EM ABERTO", ab, (ab/tot)*100 if tot>0 else 0, "#007bff", "#262730", show_per=True), unsafe_allow_html=True)
            c3.markdown(card("CONCLUÍDOS", co, (co/tot)*100 if tot>0 else 0, "#28a745", "#262730", show_per=True), unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # --- DIVISÃO: GRÁFICO (ESQ) | QUIOSQUE (DIR) ---
            c_chart, c_kiosk = st.columns([1.8, 1.2])

            with c_chart:
                st.subheader("📊 Volumetria por Assunto")
                # Gráfico com COR adicionada
                chart = alt.Chart(df['assunto'].value_counts().reset_index().set_axis(['Assunto','Qtd'], axis=1)).mark_bar().encode(
                    x='Qtd', 
                    y=alt.Y('Assunto', sort='-x'),
                    color=alt.Color('Assunto', legend=None), # Adiciona cor por categoria
                    tooltip=['Assunto','Qtd']
                ).properties(height=450)
                st.altair_chart(chart, use_container_width=True)

            with c_kiosk:
                st.subheader("🛑 Últimas Ocorrências")
                
                # LIMITADO A 4 REGISTROS
                recentes = df.sort_values(by='data_atendimento', ascending=False).head(4)
                
                if recentes.empty:
                    st.info("Nenhuma ocorrência recente.")
                else:
                    for i, row in recentes.iterrows():
                        status = row['andamento']
                        if status == "Concluído": cor_st = "#28a745"
                        elif status == "Excluído": cor_st = "#d32f2f"
                        else: cor_st = "#0288d1"
                        
                        data_fmt = formatar_data_br(row['data_atendimento'])
                        # Cria um card minimalista escuro
                        kiosk_html = f"""
                        <div style="border-left: 4px solid {cor_st}; background-color: #262730; padding: 10px; margin-bottom: 8px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.3);">
                            <div style="font-weight: bold; font-size: 0.95em; color: white; display:flex; justify-content:space-between;">
                                <span>{row['numero_chamado']}</span>
                                <span style="font-size:0.75em; background:{cor_st}; padding: 1px 6px; border-radius:4px;">{status}</span>
                            </div>
                            <div style="font-size: 0.9em; color: #ddd; margin-top:2px;">{row['funcionario_atendido']}</div>
                            <div style="font-size: 0.8em; color: #aaa; display: flex; justify-content: space-between; margin-top: 4px;">
                                <span>📂 {row['assunto']}</span>
                            </div>
                            <div style="font-size: 0.75em; color: #888; margin-top: 4px; text-align: right;">
                                🕒 {data_fmt}
                            </div>
                        </div>
                        """
                        st.markdown(kiosk_html, unsafe_allow_html=True)
            
    if live:
        time.sleep(2) # Atualização a cada 2s no modo Live
        st.rerun()

# =================================================================================
# PÁGINA: NOVO CHAMADO INTERNO - CAMPO VAZIO POR PADRÃO
# =================================================================================
elif st.session_state.pagina == "Interno_Novo":
    st.header("🏢 Novo Chamado Interno")
    if 'ticket_int' not in st.session_state: st.session_state.ticket_int = gerar_ticket("INT")
    st.info(f"🎫 **Ticket Interno:** `{st.session_state.ticket_int}`")

    with st.form("form_interno", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nome = st.text_input("Nome do Solicitante")
            # INDEX=NONE AQUI TAMBÉM
            setor = st.selectbox("Setor", ["RH", "Financeiro", "Jurídico", "TI", "Suprimentos", "Controladoria", "Planejamento", "Operacional"], index=None, placeholder="Selecione o setor...")
        with c2:
            mail = st.text_input("E-mail para Contato")
            tel = st.text_input("Telefone")
        
        desc = st.text_area("Descrição da Solicitação")

        if st.form_submit_button("🚀 Abrir Chamado"):
            # VALIDAÇÃO DO SETOR
            if nome and desc and mail and setor:
                ts = agora_utc_iso()
                payload = {
                    "numero_ticket": st.session_state.ticket_int,
                    "user_id": st.session_state.user.id,
                    "solicitante": nome, "setor": setor, "email": mail, "telefone": tel,
                    "descricao": desc, "status": "Pendente", "created_at": ts, "ultima_atualizacao": ts
                }
                criar_chamado_interno(payload)
                st.success("Chamado aberto!")
                st.session_state.ticket_int = gerar_ticket("INT")
                time.sleep(1.5)
                st.rerun()
            else: st.error("Preencha Nome, E-mail, Setor e Descrição.")

# =================================================================================
# PÁGINA: LISTAR INTERNOS
# =================================================================================
elif st.session_state.pagina == "Interno_Lista":
    
    col_tit, col_btn = st.columns([3, 1])
    with col_tit: st.header("🗂️ Registros de Chamados Internos")
    with col_btn:
        st.write("")
        if st.button("🔄 Atualizar Lista", use_container_width=True, key="refresh_interno"): st.rerun()

    res = listar_chamados_internos(user_id=st.session_state.user.id, admin=IS_ADMIN)
    dados = res.data if res and res.data else []

    if not dados:
        st.info("Nenhum chamado interno.")
    else:
        with st.expander("🔍 Filtros", expanded=True):
            f1, f2, f3 = st.columns([2, 1, 1])
            busca = f1.text_input("Buscar")
            filtro_setor = f2.multiselect("Setor", sorted(list(set(d['setor'] for d in dados))))
            filtro_status = f3.multiselect("Status", ["Pendente", "Em Andamento", "Finalizado", "Cancelado"], default=["Pendente", "Em Andamento"])

        filtrados = [r for r in dados if (not busca or busca.lower() in str(r).lower()) and (not filtro_setor or r['setor'] in filtro_setor) and (not filtro_status or r.get('status','Pendente') in filtro_status)]
        
        st.write(f"Mostrando **{len(filtrados)}** chamados.")

        for row in filtrados:
            status = row.get('status', 'Pendente')
            if status == "Finalizado": cor, bg = "#2E7D32", "#E8F5E9"
            elif status == "Cancelado": cor, bg = "#C62828", "#FFEBEE"
            elif status == "Em Andamento": cor, bg = "#F9A825", "#FFFDE7"
            else: cor, bg = "#6A1B9A", "#F3E5F5"

            dt_criacao = formatar_data_br(row['created_at'])

            raw_text = row.get('resolucao') or ''
            texto_limpo = raw_text.replace('\n', ' ').replace('\r', '')
            if len(texto_limpo) > 100: resolucao_preview = texto_limpo[:100] + "..."
            else: resolucao_preview = texto_limpo if texto_limpo else "..."

            card_html = f"""
<div style="border-left: 6px solid {cor}; background-color: {bg}; padding: 15px; border-radius: 8px; margin-bottom: 12px; color: black; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
<div style="display: flex; justify-content: space-between; align-items: center;">
<span style="font-size: 1.1em; font-weight: bold; color: #333;">{row['numero_ticket']} | {row['setor']}</span>
<span style="background:{cor}; color:white; padding:3px 10px; border-radius:12px; font-size:0.75em; font-weight: bold;">{status.upper()}</span>
</div>
<div style="font-size: 0.85em; color: #555; margin-top: 5px; border-bottom: 1px solid rgba(0,0,0,0.1); padding-bottom: 5px;">
📅 <b>Aberto em:</b> {dt_criacao} &nbsp;|&nbsp; 👤 <b>Solicitante:</b> {row['solicitante']}
</div>
<div style="margin-top:8px; font-size: 0.95em; color: #111;"><strong>📝 Descrição:</strong> {row['descricao']}</div>
<div style="margin-top:5px; font-size: 0.85em; color: #444;">📞 {row['telefone']} | 📧 {row['email']}</div>
<div style="margin-top:5px; font-size: 0.9em; background: rgba(255,255,255,0.5); padding: 8px; border-radius: 4px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">
<strong>🔧 Resolução/Histórico (Prévia):</strong> {resolucao_preview}
</div>
</div>
"""
            st.markdown(card_html, unsafe_allow_html=True)
            if st.button("👁️ Ver Detalhes / Gerenciar", key=f"btn_int_{row['id']}"):
                modal_interno(row)