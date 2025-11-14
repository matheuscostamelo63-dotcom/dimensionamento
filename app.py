# --------------------------------------------------------------
# app.py – VERSÃO PARA PRODUÇÃO (RENDER) - COM BASE DE MATERIAIS
# --------------------------------------------------------------

# ⚠️ IMPORTANTE: Configurar matplotlib ANTES de importar pyplot
import matplotlib
matplotlib.use('Agg')  # Backend sem GUI para servidor

import os
import uuid
from datetime import datetime
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from supabase import create_client
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import matplotlib.pyplot as plt
import shutil

# Config
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "dimensionamento")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# Inicializa Supabase apenas se as credenciais estiverem disponíveis
supabase_client = None
if SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL != "http://localhost:54321":
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"⚠️ Aviso: Não foi possível conectar ao Supabase: {e}")
        print("→ Rodando em modo LOCAL (sem upload)")

# ============== BASE DE DADOS DE MATERIAIS ==============
MATERIAIS_TUBULACAO = {
    # Plásticos
    "pvc": {
        "nome": "PVC (Policloreto de Vinila)",
        "rugosidade_mm": 0.0015,
        "pressao_max_bar": 16,
        "aplicacao": "Água fria, esgoto, irrigação",
        "categoria": "Plásticos"
    },
    "pead": {
        "nome": "PEAD (Polietileno Alta Densidade)",
        "rugosidade_mm": 0.002,
        "pressao_max_bar": 16,
        "aplicacao": "Água, gás, saneamento",
        "categoria": "Plásticos"
    },
    "ppr": {
        "nome": "PPR (Polipropileno Copolímero Random)",
        "rugosidade_mm": 0.0015,
        "pressao_max_bar": 25,
        "aplicacao": "Água quente/fria, aquecimento",
        "categoria": "Plásticos"
    },
    
    # Aços
    "aco_carbono_novo": {
        "nome": "Aço Carbono Novo",
        "rugosidade_mm": 0.045,
        "pressao_max_bar": 150,
        "aplicacao": "Industrial, alta pressão",
        "categoria": "Aços"
    },
    "aco_carbono_usado": {
        "nome": "Aço Carbono Usado",
        "rugosidade_mm": 0.15,
        "pressao_max_bar": 100,
        "aplicacao": "Industrial (instalações antigas)",
        "categoria": "Aços"
    },
    "aco_comercial": {
        "nome": "Aço Comercial",
        "rugosidade_mm": 0.046,
        "pressao_max_bar": 120,
        "aplicacao": "Uso geral industrial",
        "categoria": "Aços"
    },
    "aco_galvanizado_novo": {
        "nome": "Aço Galvanizado Novo",
        "rugosidade_mm": 0.15,
        "pressao_max_bar": 100,
        "aplicacao": "Água potável, proteção contra corrosão",
        "categoria": "Aços"
    },
    "aco_galvanizado_usado": {
        "nome": "Aço Galvanizado Usado",
        "rugosidade_mm": 0.40,
        "pressao_max_bar": 80,
        "aplicacao": "Instalações antigas",
        "categoria": "Aços"
    },
    "aco_inox": {
        "nome": "Aço Inoxidável",
        "rugosidade_mm": 0.015,
        "pressao_max_bar": 200,
        "aplicacao": "Alimentos, químicos, alta higiene",
        "categoria": "Aços"
    },
    
    # Ferros
    "ferro_fundido_novo": {
        "nome": "Ferro Fundido Novo",
        "rugosidade_mm": 0.26,
        "pressao_max_bar": 25,
        "aplicacao": "Água, esgoto, adutoras",
        "categoria": "Ferros"
    },
    "ferro_fundido_usado": {
        "nome": "Ferro Fundido Usado",
        "rugosidade_mm": 0.50,
        "pressao_max_bar": 20,
        "aplicacao": "Sistemas antigos",
        "categoria": "Ferros"
    },
    "ferro_galvanizado": {
        "nome": "Ferro Galvanizado",
        "rugosidade_mm": 0.15,
        "pressao_max_bar": 25,
        "aplicacao": "Água potável (antigo)",
        "categoria": "Ferros"
    },
    
    # Outros Materiais
    "cobre": {
        "nome": "Cobre",
        "rugosidade_mm": 0.0015,
        "pressao_max_bar": 50,
        "aplicacao": "Água quente/fria, gás, refrigeração",
        "categoria": "Não-Ferrosos"
    },
    "concreto_liso": {
        "nome": "Concreto Liso",
        "rugosidade_mm": 0.30,
        "pressao_max_bar": 10,
        "aplicacao": "Adutoras, grandes vazões",
        "categoria": "Concreto"
    },
    "concreto_comum": {
        "nome": "Concreto Comum",
        "rugosidade_mm": 1.00,
        "pressao_max_bar": 8,
        "aplicacao": "Drenagem, esgoto",
        "categoria": "Concreto"
    },
    "fibrocimento": {
        "nome": "Fibrocimento",
        "rugosidade_mm": 0.025,
        "pressao_max_bar": 6,
        "aplicacao": "Água (uso descontinuado)",
        "categoria": "Outros"
    },
    "vidro": {
        "nome": "Vidro",
        "rugosidade_mm": 0.0015,
        "pressao_max_bar": 10,
        "aplicacao": "Laboratórios, processos especiais",
        "categoria": "Outros"
    }
}

# ============== TABELA DE PRESSÃO DE VAPOR ==============
PRESSAO_VAPOR_AGUA = {
    0: 611, 5: 872, 10: 1228, 15: 1705, 20: 2338,
    25: 3169, 30: 4246, 35: 5628, 40: 7384, 45: 9593,
    50: 12349, 55: 15758, 60: 19946, 65: 25043, 70: 31201,
    75: 38595, 80: 47414, 85: 57867, 90: 70182, 95: 84608,
    100: 101325
}

def get_pressao_vapor(temp):
    """Interpola pressão de vapor da água em Pa"""
    if temp <= 0:
        return 611
    if temp >= 100:
        return 101325
    
    temps = sorted(PRESSAO_VAPOR_AGUA.keys())
    for i in range(len(temps)-1):
        if temps[i] <= temp <= temps[i+1]:
            t1, t2 = temps[i], temps[i+1]
            p1, p2 = PRESSAO_VAPOR_AGUA[t1], PRESSAO_VAPOR_AGUA[t2]
            return p1 + (p2-p1)*(temp-t1)/(t2-t1)
    return 2338

# ============== FUNÇÕES HIDRÁULICAS ==============
def velocity(Q, D):
    """Calcula velocidade do fluido"""
    return Q / (np.pi * (D ** 2) / 4) if D > 0 else 0

def reynolds(rho, v, D, mu):
    """Calcula número de Reynolds"""
    return rho * v * D / mu if mu > 0 else 0

def friction_factor(Re, D, material=None, rugosidade_mm=None):
    """
    Calcula fator de atrito de Darcy-Weisbach
    
    Args:
        Re: Número de Reynolds
        D: Diâmetro interno (m)
        material: ID do material da base de dados (ex: "pvc")
        rugosidade_mm: Rugosidade customizada em mm (opcional)
    
    Returns:
        float: Fator de atrito f
    """
    # Regime laminar
    if Re < 2000:
        return 64 / max(Re, 1e-12)
    
    # Determina rugosidade
    if rugosidade_mm is not None:
        # Rugosidade customizada fornecida
        e = rugosidade_mm / 1000  # Converte mm para m
    elif material and material in MATERIAIS_TUBULACAO:
        # Usa base de dados
        e = MATERIAIS_TUBULACAO[material]["rugosidade_mm"] / 1000
    else:
        # Default: aço comercial
        e = 0.045 / 1000
    
    # Fórmula de Colebrook-White (aproximação de Swamee-Jain)
    rugosidade_relativa = e / D
    termo1 = rugosidade_relativa / 3.7
    termo2 = 5.74 / (Re ** 0.9)
    
    return (-2 * np.log10(termo1 + termo2)) ** (-2)

def hf_distributed(L, D, v, f):
    """Calcula perda de carga distribuída"""
    return f * (L/D) * (v**2)/(2*9.81)

def hf_local(K, v):
    """Calcula perda de carga localizada"""
    return K * (v**2)/(2*9.81)

def npsha(Patm, Pvap, rho, g, P_suc, hs, hf_suc, v):
    """Calcula NPSH disponível"""
    return (P_suc/(rho*g) - Pvap/(rho*g) + hs - hf_suc - v**2/(2*g))

def calculate_hmt_for_scenario(q_val, data, fluido, nivel_suc, nivel_rec, destino_idx=0):
    """Calcula Hmt para um cenário específico de níveis"""
    if q_val <= 0:
        return 0
    
    rho = float(fluido.get("densidade", 1000))
    mu = float(fluido.get("viscosidade", 0.001))
    suc = data.get("suc", {})
    
    # Determina pressão de sucção
    tipo_res_suc = suc.get("tipo_reservatorio", "aberto")
    if tipo_res_suc == "pressurizado":
        P_suc = 101325 + float(suc.get("pressao_manometrica", 0))
    else:
        P_suc = 101325
    
    # Calcula perdas na sucção
    hf_suc_g, hl_suc_g = 0.0, 0.0
    for t in suc.get("trechos", []):
        L = float(t.get("L", 0))
        D = float(t.get("D", 0.1))
        mat = t.get("material")
        rug_custom = t.get("rugosidade_mm")
        conn = int(t.get("conexoes", 0))
        v_g = velocity(q_val, D)
        Re_g = reynolds(rho, v_g, D, mu)
        f_g = friction_factor(Re_g, D, material=mat, rugosidade_mm=rug_custom)
        hf_suc_g += hf_distributed(L, D, v_g, f_g)
        hl_suc_g += hf_local(0.5*conn, v_g)
    
    # Recalque (pode ser múltiplo)
    recalques = data.get("recalque", [])
    if not isinstance(recalques, list):
        recalques = [recalques]
    
    rec = recalques[destino_idx] if destino_idx < len(recalques) else recalques[0]
    
    # Determina pressão de recalque
    tipo_res_rec = rec.get("tipo_reservatorio", "aberto")
    if tipo_res_rec == "pressurizado":
        P_rec = 101325 + float(rec.get("pressao_manometrica", 0))
    else:
        P_rec = 101325
    
    # Calcula perdas no recalque
    hf_rec_g, hl_rec_g = 0.0, 0.0
    for t in rec.get("trechos", []):
        L = float(t.get("L", 0))
        D = float(t.get("D", 0.1))
        mat = t.get("material")
        rug_custom = t.get("rugosidade_mm")
        conn = int(t.get("conexoes", 0))
        v_g = velocity(q_val, D)
        Re_g = reynolds(rho, v_g, D, mu)
        f_g = friction_factor(Re_g, D, material=mat, rugosidade_mm=rug_custom)
        hf_rec_g += hf_distributed(L, D, v_g, f_g)
        hl_rec_g += hf_local(0.5*conn, v_g)
    
    # Hmt = diferença de pressão + diferença geométrica + perdas
    delta_P = (P_rec - P_suc) / (rho * 9.81)
    delta_h = nivel_rec - nivel_suc
    perdas = hf_suc_g + hl_suc_g + hf_rec_g + hl_rec_g
    
    return delta_P + delta_h + perdas

# ============== FLASK APP ==============
app = Flask(__name__)
CORS(app)  # Habilita CORS para todas as rotas

# ============== ENDPOINT: LISTAR MATERIAIS ==============
@app.route("/api/materiais", methods=["GET"])
def api_materiais():
    """
    Retorna lista de materiais disponíveis na base de dados
    
    GET /api/materiais
    
    Resposta:
    [
        {
            "id": "pvc",
            "nome": "PVC (Policloreto de Vinila)",
            "rugosidade_mm": 0.0015,
            "pressao_max_bar": 16,
            "aplicacao": "Água fria, esgoto, irrigação",
            "categoria": "Plásticos"
        },
        ...
    ]
    """
    materiais_lista = []
    
    for material_id, dados in MATERIAIS_TUBULACAO.items():
        materiais_lista.append({
            "id": material_id,
            "nome": dados["nome"],
            "rugosidade_mm": dados["rugosidade_mm"],
            "pressao_max_bar": dados["pressao_max_bar"],
            "aplicacao": dados["aplicacao"],
            "categoria": dados["categoria"]
        })
    
    # Ordena por categoria e depois por nome
    materiais_lista.sort(key=lambda x: (x["categoria"], x["nome"]))
    
    return jsonify({
        "status": "ok",
        "total": len(materiais_lista),
        "materiais": materiais_lista
    })

# ============== ENDPOINT: SERVIR ARQUIVOS ESTÁTICOS ==============
@app.route('/static/<filename>')
def serve_static(filename):
    """Serve arquivos estáticos (PDFs gerados localmente)"""
    return send_from_directory(STATIC_DIR, filename)

# ============== ENDPOINT: CALCULAR ==============
@app.route("/api/calcular", methods=["POST"])
def api_calcular():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "JSON inválido"}), 400
        
        # ===== EXTRAÇÃO DE DADOS =====
        fluido = data.get("fluido", {})
        rho = float(fluido.get("densidade", 1000))
        mu = float(fluido.get("viscosidade", 0.001))
        mu_cp = mu * 1000
        temp = float(fluido.get("temperatura", 20))
        Pvap = get_pressao_vapor(temp)
        Patm = float(fluido.get("pressao_atm", 101325))
        
        Q = float(data.get("Q", 0))
        if Q <= 0:
            return jsonify({"status": "error", "message": "Vazão deve ser > 0"}), 400
        
        suc = data.get("suc", {})
        recalques = data.get("recalque", [])
        if not isinstance(recalques, list):
            recalques = [recalques]
        
        NPSHr_user = float(data.get("NPSHr", 3.0))
        name = data.get("name", "Projeto")
        usuario = data.get("usuario", "email@exemplo.com")
        config_sistema = data.get("configuracao_sistema", "simples")
        g = 9.81
        
        warnings = []
        errors = []
        recomendacoes = []
        
        # ===== VALIDAÇÕES =====
        
        # Viscosidade
        if mu_cp > 10:
            warnings.append({
                "nivel": "ALERTA",
                "categoria": "Viscosidade",
                "mensagem": f"Viscosidade de {mu_cp:.1f} cP detectada",
                "impacto": "Bomba centrifuga tera BAIXA EFICIENCIA",
                "acao": ["Recomendado: Bomba de deslocamento positivo"]
            })
        
        if mu_cp > 100:
            errors.append({
                "nivel": "IMPEDITIVO",
                "categoria": "Viscosidade",
                "mensagem": f"Viscosidade {mu_cp:.1f} cP PROIBITIVA",
                "impacto": "Centrifuga nao funciona adequadamente",
                "acao": ["NAO USE CENTRIFUGA!", "Use bomba de deslocamento positivo"]
            })
        
        # Pressão de sucção
        tipo_res_suc = suc.get("tipo_reservatorio", "aberto")
        if tipo_res_suc == "pressurizado":
            P_suc = Patm + float(suc.get("pressao_manometrica", 0))
        else:
            P_suc = Patm
        
        # Níveis
        nivel_suc_nom = float(suc.get("nivel_nominal", suc.get("hs", 0)))
        nivel_suc_min = float(suc.get("nivel_min", nivel_suc_nom))
        nivel_suc_max = float(suc.get("nivel_max", nivel_suc_nom))
        
        # Perdas na sucção
        hf_suc, hl_suc = 0.0, 0.0
        v_suc_max = 0
        for t in suc.get("trechos", []):
            L = float(t.get("L", 0))
            D = float(t.get("D", 0.1))
            mat = t.get("material")
            rug_custom = t.get("rugosidade_mm")
            conn = int(t.get("conexoes", 0))
            v = velocity(Q, D)
            v_suc_max = max(v_suc_max, v)
            Re = reynolds(rho, v, D, mu)
            f = friction_factor(Re, D, material=mat, rugosidade_mm=rug_custom)
            hf_suc += hf_distributed(L, D, v, f)
            hl_suc += hf_local(0.5*conn, v)
        
        # Validação velocidade sucção
        if v_suc_max < 0.5:
            warnings.append({
                "nivel": "ATENCAO",
                "categoria": "Velocidade",
                "mensagem": f"Velocidade succao baixa: {v_suc_max:.2f} m/s",
                "impacto": "Risco de sedimentacao",
                "acao": ["Reduzir diametro da tubulacao"]
            })
        
        if v_suc_max > 3.0:
            warnings.append({
                "nivel": "CRITICO",
                "categoria": "Velocidade",
                "mensagem": f"Velocidade succao ALTA: {v_suc_max:.2f} m/s",
                "impacto": "RISCO DE CAVITACAO",
                "acao": ["Aumentar diametro da tubulacao"]
            })
        
        # ===== CÁLCULO PARA CADA DESTINO =====
        resultados_destinos = []
        Hmt_max = 0
        
        for idx, rec in enumerate(recalques):
            destino_id = rec.get("destino_id", f"Destino_{idx+1}")
            
            nivel_rec_nom = float(rec.get("nivel_nominal", rec.get("hr", 0)))
            nivel_rec_min = float(rec.get("nivel_min", nivel_rec_nom))
            nivel_rec_max = float(rec.get("nivel_max", nivel_rec_nom))
            
            tipo_res_rec = rec.get("tipo_reservatorio", "aberto")
            if tipo_res_rec == "pressurizado":
                P_rec = Patm + float(rec.get("pressao_manometrica", 0))
            else:
                P_rec = Patm
            
            hf_rec, hl_rec = 0.0, 0.0
            v_rec_max = 0
            for t in rec.get("trechos", []):
                L = float(t.get("L", 0))
                D = float(t.get("D", 0.1))
                mat = t.get("material")
                rug_custom = t.get("rugosidade_mm")
                conn = int(t.get("conexoes", 0))
                v = velocity(Q, D)
                v_rec_max = max(v_rec_max, v)
                Re = reynolds(rho, v, D, mu)
                f = friction_factor(Re, D, material=mat, rugosidade_mm=rug_custom)
                hf_rec += hf_distributed(L, D, v, f)
                hl_rec += hf_local(0.5*conn, v)
            
            if v_rec_max > 5.0:
                warnings.append({
                    "nivel": "ALERTA",
                    "categoria": "Velocidade",
                    "mensagem": f"Velocidade recalque {destino_id} ALTA: {v_rec_max:.2f} m/s",
                    "impacto": "Risco de erosao",
                    "acao": ["Aumentar diametro"]
                })
            
            Hmt_pior = calculate_hmt_for_scenario(Q, data, fluido, nivel_suc_min, nivel_rec_max, idx)
            Hmt_nom = calculate_hmt_for_scenario(Q, data, fluido, nivel_suc_nom, nivel_rec_nom, idx)
            Hmt_melhor = calculate_hmt_for_scenario(Q, data, fluido, nivel_suc_max, nivel_rec_min, idx)
            
            Hmt_max = max(Hmt_max, Hmt_pior)
            
            D_suc = float(suc.get("trechos", [{}])[0].get("D", 0.1))
            v_suc = velocity(Q, D_suc)
            NPSHa_val = npsha(Patm, Pvap, rho, g, P_suc, nivel_suc_min, hf_suc, v_suc)
            cav_ok = bool(float(NPSHa_val) > float(NPSHr_user + 0.5))
            
            resultados_destinos.append({
                "destino_id": destino_id,
                "Hmt_pior": float(round(Hmt_pior, 2)),
                "Hmt_nominal": float(round(Hmt_nom, 2)),
                "Hmt_melhor": float(round(Hmt_melhor, 2)),
                "hf_rec": float(round(hf_rec, 4)),
                "hl_rec": float(round(hl_rec, 4)),
                "v_rec_max": float(round(v_rec_max, 2)),
                "NPSHa": float(round(NPSHa_val, 2)),
                "cavitation_ok": cav_ok
            })
        
        Hmt = Hmt_max
        P_hid_W = rho * g * Q * Hmt
        P_bar = Hmt * 0.0981
        
        # Validações adicionais
        if Hmt > 200:
            warnings.append({
                "nivel": "CRITICO",
                "categoria": "Pressao",
                "mensagem": f"Pressao {Hmt:.1f} mCA ({P_bar:.1f} bar) EXTREMA!",
                "impacto": "Componentes comuns nao suportam",
                "acao": ["Tubulacao Schedule 80", "Valvulas 150# minimo"]
            })
        
        if Hmt > 300:
            errors.append({
                "nivel": "IMPEDITIVO",
                "categoria": "Pressao",
                "mensagem": "Pressao > 300 mCA - centrifuga NAO RECOMENDADA",
                "impacto": "Risco estrutural",
                "acao": ["OBRIGATORIO: bomba multistagio"]
            })
        
        if not all(r["cavitation_ok"] for r in resultados_destinos):
            warnings.append({
                "nivel": "CRITICO",
                "categoria": "Cavitacao",
                "mensagem": "RISCO DE CAVITACAO!",
                "impacto": "Danos ao rotor",
                "acao": ["Reduzir perdas na succao", "Aumentar diametro succao"]
            })
        
        if len(recalques) > 1:
            warnings.append({
                "nivel": "OBRIGATORIO",
                "categoria": "Sistema",
                "mensagem": f"Sistema com {len(recalques)} destinos",
                "impacto": "Vazao pode nao se distribuir",
                "acao": ["Instalar valvulas reguladoras"]
            })
        
        # Recomendações
        recomendacoes.append(f"Bomba com Hmt >= {Hmt:.2f} m na vazao {Q*3600:.2f} m³/h")
        recomendacoes.append("Verificar curva do fabricante")
        recomendacoes.append(f"NPSHr da bomba <= {min(r['NPSHa'] for r in resultados_destinos)-0.5:.2f} m")
        
        case_id = str(uuid.uuid4())
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        
        # ===== GRÁFICO =====
        graph_path = os.path.join(UPLOAD_DIR, f"{case_id}_graph.png")
        
        q_range_m3h = np.linspace(0, Q * 3600 * 1.5, 100)
        q_range_m3s = q_range_m3h / 3600
        
        h_pior = [calculate_hmt_for_scenario(q, data, fluido, nivel_suc_min,
                   recalques[0].get("nivel_max", recalques[0].get("nivel_nominal", recalques[0].get("hr", 0)))) for q in q_range_m3s]
        h_nominal = [calculate_hmt_for_scenario(q, data, fluido, nivel_suc_nom,
                      recalques[0].get("nivel_nominal", recalques[0].get("hr", 0))) for q in q_range_m3s]
        h_melhor = [calculate_hmt_for_scenario(q, data, fluido, nivel_suc_max,
                     recalques[0].get("nivel_min", recalques[0].get("nivel_nominal", recalques[0].get("hr", 0)))) for q in q_range_m3s]
        
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(14, 8))
        
        ax.fill_between(q_range_m3h, h_melhor, h_pior, alpha=0.2, color='#1E40AF',
                        label='Faixa de Operacao')
        
        ax.plot(q_range_m3h, h_pior, '--', color='#DC2626', linewidth=2, label='Pior Caso')
        ax.plot(q_range_m3h, h_nominal, color='#1E40AF', linewidth=3, label='Nominal')
        ax.plot(q_range_m3h, h_melhor, '--', color='#059669', linewidth=2, label='Melhor Caso')
        
        ax.plot(Q * 3600, Hmt, 'o', markersize=12, color='#D97706',
                markeredgecolor='black', markeredgewidth=2,
                label=f'Operacao ({Q*3600:.1f} m³/h, {Hmt:.1f} m)')
        
        ax.set_title('Curva do Sistema - Variacao de Niveis', fontsize=18, fontweight='bold', pad=20)
        ax.set_xlabel('Vazao (m³/h)', fontsize=14, fontweight='bold')
        ax.set_ylabel('Altura Manometrica (m)', fontsize=14, fontweight='bold')
        ax.legend(fontsize=11, loc='upper left')
        ax.grid(True, alpha=0.3)
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
        
        fig.tight_layout()
        plt.savefig(graph_path, dpi=200, bbox_inches='tight')
        plt.close(fig)
        
        # ===== PDF =====
        pdf_path = os.path.join(UPLOAD_DIR, f"{case_id}.pdf")
        width = 2480
        height = 9000
        img = Image.new('RGB', (width, height), color='#FFFFFF')
        draw = ImageDraw.Draw(img)
        
        # ✅ FONTES COM FALLBACK PARA LINUX
        try:
            font_title = ImageFont.truetype("arialbd.ttf", 140)
            font_subtitle = ImageFont.truetype("arial.ttf", 65)
            font_header = ImageFont.truetype("arialbd.ttf", 70)
            font_text = ImageFont.truetype("arial.ttf", 52)
            font_small = ImageFont.truetype("arial.ttf", 46)
        except:
            try:
                font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 140)
                font_subtitle = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 65)
                font_header = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 70)
                font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 52)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 46)
            except:
                font_title = font_subtitle = font_header = font_text = font_small = ImageFont.load_default()
        
        # Cabeçalho
        for y in range(0, 450):
            ratio = y / 450
            r = int(30 + (100-30) * ratio)
            g = int(64 + (150-64) * ratio)
            b = int(175 + (220-175) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        
        draw.text((width//2, 150), "RELATORIO DE", fill="#FFFFFF", font=font_title, anchor="mm")
        draw.text((width//2, 260), "DIMENSIONAMENTO", fill="#FFFFFF", font=font_title, anchor="mm")
        draw.text((width//2, 350), "Bomba Centrifuga - Analise Completa", fill="#E0E7FF", font=font_subtitle, anchor="mm")
        
        y_pos = 520
        
        def add_section_header(title):
            nonlocal y_pos
            y_pos += 15
            draw.rectangle([(100, y_pos), (2380, y_pos+90)], fill="#1E40AF")
            draw.text((140, y_pos+45), title, fill="white", font=font_header, anchor="lm")
            y_pos += 105
        
        def add_alert_box(message, alert_type="warning"):
            nonlocal y_pos
            colors = {
                "warning": ("#FEF3C7", "#F59E0B", "#92400E"),
                "success": ("#D1FAE5", "#10B981", "#065F46"),
                "error": ("#FEE2E2", "#EF4444", "#991B1B")
            }
            bg, border, text = colors.get(alert_type, colors["warning"])
            box_height = 90
            draw.rectangle([(100, y_pos), (2380, y_pos+box_height)], fill=bg, outline=border, width=4)
            draw.text((140, y_pos+45), message, fill=text, font=font_text, anchor="lm")
            y_pos += box_height + 15
        
        def add_bullet_list(items):
            nonlocal y_pos
            for item in items:
                draw.text((140, y_pos), f"- {item}", fill="#374151", font=font_small, anchor="lm")
                y_pos += 55
            y_pos += 20
        
        # Conteúdo
        add_section_header("INFORMACOES")
        draw.text((140, y_pos), f"Projeto: {name}", fill="#000000", font=font_small, anchor="lm")
        y_pos += 55
        draw.text((140, y_pos), f"Data: {now}", fill="#374151", font=font_small, anchor="lm")
        y_pos += 55
        
        add_section_header("STATUS")
        if errors:
            add_alert_box(f"{len(errors)} ERRO(S) ENCONTRADO(S)", "error")
        elif warnings:
            add_alert_box(f"{len(warnings)} ALERTA(S)", "warning")
        else:
            add_alert_box("Sistema OK", "success")
        
        add_section_header("RESULTADOS")
        draw.text((140, y_pos), f"Vazao: {Q*3600:.2f} m³/h", fill="#000000", font=font_small, anchor="lm")
        y_pos += 55
        draw.text((140, y_pos), f"Hmt: {Hmt:.2f} m", fill="#000000", font=font_small, anchor="lm")
        y_pos += 55
        draw.text((140, y_pos), f"Potencia: {P_hid_W/1000:.2f} kW", fill="#000000", font=font_small, anchor="lm")
        y_pos += 55
        draw.text((140, y_pos), f"Temperatura: {temp:.0f} C", fill="#000000", font=font_small, anchor="lm")
        y_pos += 55
        draw.text((140, y_pos), f"Viscosidade: {mu_cp:.1f} cP", fill="#000000", font=font_small, anchor="lm")
        y_pos += 55
        
        add_section_header("GRAFICO")
        try:
            with Image.open(graph_path) as graph_img:
                new_width = 2000
                new_height = int(2000 * graph_img.height / graph_img.width)
                graph_img = graph_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                img.paste(graph_img, (240, y_pos))
                y_pos += new_height + 30
        except:
            pass
        
        if warnings:
            add_section_header("ALERTAS")
            for warn in warnings:
                add_alert_box(f"{warn['categoria']}: {warn['mensagem']}", "warning")
                if 'impacto' in warn:
                    draw.text((160, y_pos), f"Impacto: {warn['impacto']}",
                             fill="#6B7280", font=font_small, anchor="lm")
                    y_pos += 50
                add_bullet_list(warn['acao'])
        
        if errors:
            add_section_header("ERROS IMPEDITIVOS")
            for err in errors:
                add_alert_box(f"{err['categoria']}: {err['mensagem']}", "error")
                if 'impacto' in err:
                    draw.text((160, y_pos), f"Impacto: {err['impacto']}",
                             fill="#6B7280", font=font_small, anchor="lm")
                    y_pos += 50
                add_bullet_list(err['acao'])
        
        add_section_header("RECOMENDACOES")
        add_bullet_list(recomendacoes)
        
        img.save(pdf_path, "PDF", resolution=300.0)
        
        # ===== UPLOAD OU MODO LOCAL =====
        pdf_url = None
        modo_local = os.getenv("TEST_MODE_LOCAL", "false").lower() == "true" or supabase_client is None
        
        if modo_local:
            # Modo local: copia PDF para pasta static
            print("🔧 Modo LOCAL: salvando PDF em static/")
            static_pdf_path = os.path.join(STATIC_DIR, f"{case_id}.pdf")
            shutil.copy2(pdf_path, static_pdf_path)
            pdf_url = f"http://localhost:{os.environ.get('PORT', 5000)}/static/{case_id}.pdf"
        else:
            # Modo produção: upload para Supabase
            try:
                print("☁️ Modo PRODUÇÃO: fazendo upload para Supabase...")
                with open(pdf_path, "rb") as f:
                    file_data = f.read()
                remote_path = f"{case_id}/relatorio.pdf"
                supabase_client.storage.from_(SUPABASE_BUCKET).upload(
                    path=remote_path,
                    file=file_data,
                    file_options={"content-type": "application/pdf"}
                )
                pdf_url = supabase_client.storage.from_(SUPABASE_BUCKET).get_public_url(remote_path)
                print(f"✅ Upload concluído: {pdf_url}")
            except Exception as e:
                print(f"❌ Erro no upload: {e}")
                warnings.append({
                    "nivel": "ALERTA",
                    "categoria": "Upload",
                    "mensagem": f"Falha no upload do PDF: {str(e)}",
                    "impacto": "Relatório não disponível online",
                    "acao": ["Verificar conexão Supabase", "Configurar variáveis .env"]
                })
                # Fallback para modo local
                static_pdf_path = os.path.join(STATIC_DIR, f"{case_id}.pdf")
                shutil.copy2(pdf_path, static_pdf_path)
                pdf_url = f"/static/{case_id}.pdf"
        
        # Cleanup (remove arquivos temporários)
        try:
            if not os.getenv("KEEP_FILES", "false").lower() == "true":
                os.remove(pdf_path)
                os.remove(graph_path)
        except Exception as e:
            print(f"⚠️ Aviso: não foi possível remover arquivos temporários: {e}")
        
        return jsonify({
            "status": "ok" if not errors else "warning",
            "case_id": case_id,
            "pdf_url": str(pdf_url),
            "modo_local": modo_local,
            "temperatura": temp,
            "viscosidade_cp": mu_cp,
            "H_mt_nominal": float(round(Hmt, 2)),
            "pressao_bar": float(round(P_bar, 2)),
            "P_hid_kW": float(round(P_hid_W/1000, 2)),
            "velocidade_succao": float(round(v_suc_max, 2)),
            "resultados_destinos": resultados_destinos,
            "warnings": warnings,
            "errors": errors,
            "recomendacoes": recomendacoes
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

# ✅ PRODUÇÃO: Porta dinâmica + Debug=False
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("🚀 SERVIDOR FLASK INICIADO")
    print("=" * 60)
    if supabase_client:
        print("☁️  Modo: PRODUÇÃO (Supabase conectado)")
    else:
        print("🔧 Modo: LOCAL (sem Supabase)")
    print(f"🌐 Endereço: http://localhost:{port}")
    print(f"📊 Endpoint materiais: http://localhost:{port}/api/materiais")
    print(f"⚙️  Endpoint calcular: http://localhost:{port}/api/calcular")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)