import os
import io
import math
import uuid
import json
import datetime
from typing import List, Dict, Any
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
# Determina o caminho absoluto do arquivo .env
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'

print(f"[DEBUG] Pasta do app.py: {BASE_DIR}")
print(f"[DEBUG] Procurando .env em: {env_path}")
print(f"[DEBUG] Arquivo .env existe? {env_path.exists()}")

# Carrega o .env
load_dotenv(dotenv_path=env_path)

# Verifica se carregou
print(f"[DEBUG] SUPABASE_URL carregado: {os.environ.get('SUPABASE_URL')}")
print(f"[DEBUG] SUPABASE_KEY carregado: {'***' if os.environ.get('SUPABASE_KEY') else 'None'}")

# libs científicas e de geração de arquivos
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from supabase import create_client, Client
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------
# Config / Supabase client
# ---------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "projects")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("\n[ERRO] Variáveis de ambiente não encontradas!")
    print(f"[ERRO] Certifique-se de que o arquivo .env existe em: {env_path}")
    print(f"[ERRO] E contém as linhas:")
    print(f"[ERRO] SUPABASE_URL=sua-url-aqui")
    print(f"[ERRO] SUPABASE_KEY=sua-chave-aqui")
    raise EnvironmentError("Você deve definir SUPABASE_URL e SUPABASE_KEY no arquivo .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Flask app
app = Flask(__name__)
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

g_const = 9.81

# -------------------- Helper: Hydraulic functions --------------------
def area_from_d(D: float) -> float:
    return math.pi * D**2 / 4.0

def velocity(Q: float, D: float) -> float:
    A = area_from_d(D)
    return Q / A if A > 0 else 0.0

def reynolds(rho: float, Q: float, D: float, mu: float) -> float:
    v = velocity(Q, D)
    if mu == 0 or D == 0:
        return 0.0
    return rho * v * D / mu

def colebrook_white(Re: float, eps: float, D: float, f0=0.02, tol=1e-8, maxiter=200) -> float:
    if Re <= 2300:
        return 64.0 / max(Re, 1e-12)
    f = f0
    for _ in range(maxiter):
        rhs = -2.0 * math.log10((eps / (3.7 * D)) + (2.51 / (Re * math.sqrt(f))))
        f_new = 1.0 / (rhs * rhs)
        if abs(f_new - f) < tol:
            return f_new
        f = f_new
    return swamee_jain(Re, eps, D)

def swamee_jain(Re: float, eps: float, D: float) -> float:
    if Re <= 0:
        return 0.03
    return 0.25 / (math.log10((eps/(3.7*D)) + (5.74 / (Re**0.9)))**2)

def compute_f_safe(Re: float, eps: float, D: float) -> float:
    try:
        if Re is None or Re <= 0:
            return 0.04
        if Re <= 2300:
            return 64.0 / max(Re,1e-12)
        return colebrook_white(Re, eps, D)
    except Exception:
        return swamee_jain(Re, eps, D)

def hf_distributed(f: float, L: float, D: float, Q: float) -> float:
    v = velocity(Q, D)
    return f * (L / D) * (v**2) / (2.0 * g_const)

def hf_local_by_K(K: float, Q: float, D: float) -> float:
    v = velocity(Q, D)
    return K * (v**2) / (2.0 * g_const)

DEFAULT_K_PER_CONNECTION = 0.5

# -------------------- Process list of trechos (sucção/recalque) --------------------
def process_trechos(Q: float, trechos: List[Dict[str, Any]], rho: float, mu: float) -> Dict[str, Any]:
    details = []
    hf_sum = 0.0
    hl_sum = 0.0
    reynolds_list = []
    f_list = []
    for t in trechos:
        L = float(t.get('L', 0.0))
        D = float(t.get('D', 0.0))
        eps = float(t.get('rug', 0.000045))
        conexoes = int(t.get('conexoes', 0))
        Kpc = t.get('K_por_conexao')
        if Kpc is None:
            Kpc = DEFAULT_K_PER_CONNECTION
        Re = reynolds(rho, Q, D, mu)
        f = compute_f_safe(Re, eps, D)
        hf = hf_distributed(f, L, D, Q)
        K_total = conexoes * float(Kpc)
        hl = hf_local_by_K(K_total, Q, D)
        hf_sum += hf
        hl_sum += hl
        reynolds_list.append(Re)
        f_list.append(f)
        details.append({"L":L,"D":D,"eps":eps,"conexoes":conexoes,"K_por_conexao":Kpc,"Re":Re,"f":f,"hf":hf,"hl":hl})
    return {"details":details,"hf_sum":hf_sum,"hl_sum":hl_sum,"reynolds":reynolds_list,"f_list":f_list}

# -------------------- NPSH calculation --------------------
def compute_NPSHa(Patm_pa: float, Pvap_pa: float, rho: float, g: float, hs: float, hf_suc: float, v_suc: float)-> float:
    term_atm = Patm_pa / (rho * g)
    term_v = (v_suc**2) / (2*g)
    term_vapor = Pvap_pa / (rho * g)
    return term_atm + term_v + hs - term_vapor - hf_suc

# -------------------- Supabase helpers --------------------
def supabase_get_user(access_token: str):
    """
    Get user info from Supabase using access_token.
    Returns dict with user info or None.
    """
    try:
        # supabase.auth.get_user expects an access token (session access_token)
        user_resp = supabase.auth.get_user(access_token)
        # the returned object structure depends on supabase-py version
        # try common shapes:
        if hasattr(user_resp, "user") and user_resp.user:
            return user_resp.user
        # else maybe .data
        if isinstance(user_resp, dict) and user_resp.get("data"):
            return user_resp["data"].get("user") or user_resp["data"]
        return None
    except Exception:
        return None

def supabase_upload_file(local_path: str, remote_path: str) -> str:
    """
    Upload local_path to Supabase storage (bucket SUPABASE_STORAGE_BUCKET).
    Returns public URL on success.
    """
    with open(local_path, "rb") as f:
        data = f.read()
    # remote_path should be unique, e.g. f"projects/{case_id}/plot.png"
    try:
        res = supabase.storage.from_(SUPABASE_STORAGE_BUCKET).upload(remote_path, data, {"cacheControl":"3600", "upsert": True})
        # get public url
        public_url_resp = supabase.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(remote_path)
        if isinstance(public_url_resp, dict):
            # supabase-py may return {'publicUrl': '...'} or {'data': {'publicUrl':...}}
            if public_url_resp.get('publicUrl'):
                return public_url_resp['publicUrl']
            if public_url_resp.get('data') and public_url_resp['data'].get('publicUrl'):
                return public_url_resp['data']['publicUrl']
        # fallback: construct url (works if set)
        return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}/{remote_path}"
    except Exception as e:
        print("Upload failed:", e)
        return ""

# -------------------- Auth endpoints (use Supabase Auth) --------------------
@app.route('/api/cadastrar', methods=['POST'])
def api_cadastrar():
    """
    Body: { email, senha }
    This endpoint proxies to Supabase Auth sign_up.
    """
    try:
        data = request.get_json(force=True)
        email = data.get('email')
        senha = data.get('senha')
        if not email or not senha:
            return jsonify({"status":"error","message":"email e senha obrigatórios"}), 400
        # sign up user (Supabase returns user/session)
        resp = supabase.auth.sign_up({"email": email, "password": senha})
        # resp may contain 'data' and 'error'
        return jsonify({"status":"ok","data": resp}), 201
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}), 500

@app.route('/api/login', methods=['POST'])
def api_login():
    """
    Body: { email, senha } -> proxies to Supabase sign_in_with_password
    Returns session object (contains access_token) that the frontend should store.
    """
    try:
        data = request.get_json(force=True)
        email = data.get('email')
        senha = data.get('senha')
        if not email or not senha:
            return jsonify({"status":"error","message":"email e senha obrigatórios"}), 400
        resp = supabase.auth.sign_in_with_password({"email": email, "password": senha})
        return jsonify({"status":"ok","data": resp})
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}), 401

# -------------------- Core compute endpoint --------------------
@app.route('/api/calcular', methods=['POST'])
def api_calcular():
    """
    Payload (JSON):
    {
      "fluido": {"nome": "...","densidade":1000,"viscosidade":0.001,"pressao_atm":101325,"pressao_vapor":2338},
      "Q": 0.025,
      "sucção": {"hs": 2.0, "trechos":[{L,D,rug,conexoes, K_por_conexao?}]},
      "recalque": {"hr": 20.0, "trechos":[...]},
      "usuario": "email",    # opcional
      "opcoes": {"margem_npsh":0.5}
    }
    """
    try:
        data = request.get_json(force=True)
        fluido = data.get('fluido', {})
        Q = float(data.get('Q', 0.0))
        suc = data.get('sucção') or data.get('suc') or data.get('suction') or {}
        rec = data.get('recalque') or data.get('rec') or {}
        usuario = data.get('usuario', "")
        opcoes = data.get('opcoes', {})
        margem_npsh = float(opcoes.get('margem_npsh', 0.5))
        rho = float(fluido.get('densidade', 1000.0))
        mu = float(fluido.get('viscosidade', 0.001))
        Patm = float(fluido.get('pressao_atm', 101325.0))
        Pvap = float(fluido.get('pressao_vapor', 2338.0))
        hs = float(suc.get('hs', 0.0))
        hr = float(rec.get('hr', 0.0))
        trechos_suc = suc.get('trechos', [])
        trechos_rec = rec.get('trechos', [])
        # ensure trechos have default values
        for t in trechos_suc: t.setdefault('rug', 0.000045)
        for t in trechos_rec: t.setdefault('rug', 0.000045)
        # process
        suc_res = process_trechos(Q, trechos_suc, rho, mu)
        rec_res = process_trechos(Q, trechos_rec, rho, mu)
        hf_suc = suc_res['hf_sum']; hl_suc = suc_res['hl_sum']
        hf_rec = rec_res['hf_sum']; hl_rec = rec_res['hl_sum']
        hf_total = hf_suc + hf_rec
        hl_total = hl_suc + hl_rec
        Hmt = hr + hs + hf_total + hl_total
        P_hid_W = rho * g_const * Q * Hmt
        # NPSHa - use suction first trecho diameter for velocity if present
        if trechos_suc and len(trechos_suc) > 0:
            D_for_v = float(trechos_suc[0].get('D', 0.05))
        else:
            # fallback: use first rec trecho or default
            D_for_v = float(trechos_rec[0].get('D', 0.05)) if trechos_rec else 0.05
        v_suc = velocity(Q, D_for_v)
        NPSHa = compute_NPSHa(Patm, Pvap, rho, g_const, hs, hf_suc, v_suc)
        NPSHr_user = float(data.get('NPSHr', 0.0)) if data.get('NPSHr') is not None else None
        cav_ok = None
        if NPSHr_user:
            cav_ok = (NPSHa >= (NPSHr_user + margem_npsh))
        # Build a small plot and pdf and upload to Supabase Storage
        case_id = uuid.uuid4().hex
        # Plot system curve
        Qgrid = np.linspace(max(1e-6, Q*0.1), max(Q*3, Q+1e-6), 200)
        Hsys = []
        for qg in Qgrid:
            sres = process_trechos(qg, trechos_suc, rho, mu)
            rres = process_trechos(qg, trechos_rec, rho, mu)
            Hsys.append( (hs + sres['hf_sum'] + sres['hl_sum']) + (hr + rres['hf_sum'] + rres['hl_sum']) )
        Hsys = np.array(Hsys)
        H0 = max(Hsys)*1.1 + 1.0
        Qmax = Qgrid.max()
        Hpump = H0*(1 - (Qgrid/Qmax)**2)
        fig, ax = plt.subplots(figsize=(8,5))
        ax.plot(Qgrid*3600, Hsys, label='Curva do Sistema')
        ax.plot(Qgrid*3600, Hpump, label='Curva Exemplo da Bomba')
        op_point = ((Q*3600), ((hs + hf_suc + hl_suc) + (hr + hf_rec + hl_rec)))
        ax.scatter([op_point[0]],[op_point[1]], color='red', label='Ponto de operação')
        ax.set_xlabel('Vazão (m³/h)')
        ax.set_ylabel('Altura (m)')
        ax.legend(); ax.grid(True)
        img_local = os.path.join(UPLOAD_DIR, f"{case_id}.png")
        fig.tight_layout(); plt.savefig(img_local); plt.close(fig)
        # Create PDF
        pdf_local = os.path.join(UPLOAD_DIR, f"{case_id}.pdf")
        with PdfPages(pdf_local) as pdf:
            fig_txt = plt.figure(figsize=(8.27,11.69))
            fig_txt.text(0.02,0.98,"Relatório - Dimensionamento de Bomba Centrífuga", fontsize=14, weight='bold', va='top')
            y=0.95
            lines = [
                f"Data: {datetime.datetime.utcnow().isoformat()}",
                f"Usuario: {usuario}",
                f"Q (m3/s): {Q}",
                f"hs (m): {hs}",
                f"hr (m): {hr}",
                f"hf_suc (m): {hf_suc:.4f}",
                f"hl_suc (m): {hl_suc:.4f}",
                f"hf_rec (m): {hf_rec:.4f}",
                f"hl_rec (m): {hl_rec:.4f}",
                f"Hmt (m): {Hmt:.4f}",
                f"NPSHa (m): {NPSHa:.4f}",
                f"NPSHr (m): {NPSHr_user if NPSHr_user else 'not provided'}"
            ]
            for ln in lines:
                fig_txt.text(0.02,y,ln,fontsize=10); y -= 0.03
            pdf.savefig(fig_txt); plt.close(fig_txt)
            fig2 = plt.figure(figsize=(8.27,6))
            img = plt.imread(img_local)
            plt.imshow(img); plt.axis('off'); pdf.savefig(fig2); plt.close(fig2)
        # Upload files to Supabase storage
        remote_img_path = f"{case_id}/plot.png"
        remote_pdf_path = f"{case_id}/report.pdf"
        img_url = supabase_upload_file(img_local, remote_img_path)
        pdf_url = supabase_upload_file(pdf_local, remote_pdf_path)
        # Insert project metadata in Supabase table 'projects'
        project_row = {
            "id": case_id,
            "user_id": usuario or "",
            "email": usuario or "",
            "name": data.get('name') or f"Projeto {case_id[:6]}",
            "summary": f"Q={Q}, Hmt={Hmt:.3f}",
            "payload": data,
            "img_path": remote_img_path,
            "pdf_path": remote_pdf_path,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        # Insert
        try:
            resp = supabase.table("projects").insert(project_row).execute()
        except Exception as e:
            # If insert fails, still return results but warn
            print("Supabase insert failed:", e)
        # Build response
        resp_json = {
            "status":"ok",
            "case_id": case_id,
            "hf_suc": hf_suc,
            "hl_suc": hl_suc,
            "hf_rec": hf_rec,
            "hl_rec": hl_rec,
            "hf_total": hf_total,
            "hl_total": hl_total,
            "H_mt": Hmt,
            "P_hid_W": P_hid_W,
            "NPSHa": NPSHa,
            "NPSHr": NPSHr_user,
            "reynolds": {"suc": suc_res['reynolds'], "rec": rec_res['reynolds']},
            "f": {"suc": suc_res['f_list'], "rec": rec_res['f_list']},
            "img_url": img_url,
            "pdf_url": pdf_url
        }
        if cav_ok is not None:
            resp_json['cavitation_ok'] = cav_ok
        return jsonify(resp_json)
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}), 400

# -------------------- Save project (override metadata) --------------------
@app.route('/api/salvar_projeto', methods=['POST'])
def api_salvar_projeto():
    """
    Body: { "email": "...", "case_id": "...", "name": "...", "summary": "...", "payload": {..} }
    Requires auth via Authorization header Bearer <access_token> OR provide email.
    """
    try:
        data = request.get_json(force=True)
        email = data.get('email')
        case_id = data.get('case_id')
        name = data.get('name', f"Projeto {case_id[:6]}" if case_id else "Projeto")
        summary = data.get('summary', '')
        payload = data.get('payload', {})
        if not email or not case_id:
            return jsonify({"status":"error","message":"email e case_id obrigatorios"}), 400
        row = {
            "id": case_id,
            "user_id": email,
            "email": email,
            "name": name,
            "summary": summary,
            "payload": payload,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        resp = supabase.table("projects").upsert(row).execute()
        return jsonify({"status":"ok","message":"project saved","data": resp.data})
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}), 500

# -------------------- List projects --------------------
@app.route('/api/listar_projetos', methods=['GET'])
def api_listar_projetos():
    email = request.args.get('email')
    if not email:
        return jsonify({"status":"error","message":"email required"}), 400
    try:
        resp = supabase.table("projects").select("*").eq("email", email).execute()
        return jsonify({"status":"ok","projects": resp.data})
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}), 500

# -------------------- Serve public file URLs (optional) --------------------
@app.route('/api/plot/<case_id>', methods=['GET'])
def api_plot(case_id):
    try:
        # generate public URL if exists
        remote_img_path = f"{case_id}/plot.png"
        public_url_resp = supabase.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(remote_img_path)
        if isinstance(public_url_resp, dict):
            # structure varies
            url = public_url_resp.get('publicUrl') or (public_url_resp.get('data') or {}).get('publicUrl')
        else:
            url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}/{remote_img_path}"
        return jsonify({"status":"ok","img_url": url})
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}), 404

@app.route('/api/report/<case_id>', methods=['GET'])
def api_report(case_id):
    try:
        remote_pdf_path = f"{case_id}/report.pdf"
        public_url_resp = supabase.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(remote_pdf_path)
        if isinstance(public_url_resp, dict):
            url = public_url_resp.get('publicUrl') or (public_url_resp.get('data') or {}).get('publicUrl')
        else:
            url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}/{remote_pdf_path}"
        return jsonify({"status":"ok","pdf_url": url})
    except Exception as e:
        return jsonify({"status":"error","message":str(e)}), 404

# -------------------- Run server --------------------
if __name__ == '__main__':
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 5000))
    print("Starting Flask + Supabase backend on", host, port)
    app.run(host=host, port=port, debug=True)