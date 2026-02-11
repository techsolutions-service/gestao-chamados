import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Erro: SUPABASE_URL ou SUPABASE_KEY não encontradas no arquivo .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- AUTENTICAÇÃO ---
def auth_login(email, password):
    return supabase.auth.sign_in_with_password({"email": email, "password": password})

def auth_logout():
    return supabase.auth.sign_out()

# --- MÓDULO GERAL ---
def criar_atendimento(data: dict):
    try:
        return supabase.table("atendimentos").insert(data).execute()
    except Exception as e:
        print(f"Erro ao criar atendimento: {e}")
        return None

def listar_atendimentos(user_id=None, admin=False):
    try:
        query = supabase.table("atendimentos").select("*")
        if not admin:
            query = query.eq("user_id", user_id)
        return query.order("data_atendimento", desc=True).execute()
    except Exception as e:
        print(f"Erro ao listar atendimentos: {e}")
        return None

def atualizar_atendimento(id_atendimento, dados: dict):
    try:
        return supabase.table("atendimentos").update(dados).eq("id", id_atendimento).execute()
    except Exception as e:
        print(f"Erro ao atualizar atendimento: {e}")
        return None

# --- MÓDULO INTERNO (ATUALIZADO COM FILTRO DE USUÁRIO) ---
def criar_chamado_interno(data: dict):
    try:
        return supabase.table("chamados_internos").insert(data).execute()
    except Exception as e:
        print(f"Erro ao criar chamado interno: {e}")
        return None

def listar_chamados_internos(user_id=None, admin=False):
    try:
        query = supabase.table("chamados_internos").select("*")
        # Se não for admin, filtra apenas os chamados do usuário logado
        if not admin:
            query = query.eq("user_id", user_id)
        return query.order("created_at", desc=True).execute()
    except Exception as e:
        print(f"Erro ao listar chamados internos: {e}")
        return None

def atualizar_chamado_interno(id_chamado, dados: dict):
    try:
        return supabase.table("chamados_internos").update(dados).eq("id", id_chamado).execute()
    except Exception as e:
        print(f"Erro ao atualizar chamado interno: {e}")
        return None