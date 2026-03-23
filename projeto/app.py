import os
import json
import hashlib
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, session
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder=".")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-fallback")

# ── Groq client ────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY não encontrada. Crie um arquivo .env com a chave.")
client = Groq(api_key=GROQ_API_KEY)
MODEL = "llama-3.1-8b-instant"

DB_FILE = "vitaai_db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def get_user(username):
    db = load_db()
    return db["users"].get(username)

def current_user():
    return session.get("username")

DISCLAIMER = (
    "⚠️ AVISO: Esta análise é informativa e NÃO substitui consulta médica. "
    "Sempre consulte um profissional de saúde habilitado para diagnóstico e tratamento. "
    "Em emergências, ligue 192 (SAMU) ou vá ao pronto-socorro mais próximo."
)

# ══════════════════════════════════════════════════════════════
# FRONTEND
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

# ══════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = (data.get("password") or "").strip()
    name     = (data.get("name") or "").strip()
    age      = data.get("age", "")
    gender   = data.get("gender", "")

    if not username or not password or not name:
        return jsonify({"error": "Preencha todos os campos obrigatórios."}), 400
    if len(username) < 3:
        return jsonify({"error": "Usuário deve ter ao menos 3 caracteres."}), 400
    if len(password) < 6:
        return jsonify({"error": "Senha deve ter ao menos 6 caracteres."}), 400

    db = load_db()
    if username in db["users"]:
        return jsonify({"error": "Nome de usuário já existe."}), 409

    db["users"][username] = {
        "username": username,
        "password": hash_password(password),
        "name": name,
        "age": age,
        "gender": gender,
        "created_at": datetime.now().isoformat(),
        "diary": [],
        "medications": [],
        "symptom_history": [],
        "measurements": []
    }
    save_db(db)
    session["username"] = username
    return jsonify({"ok": True, "name": name})

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = (data.get("password") or "").strip()
    user = get_user(username)
    if not user or user["password"] != hash_password(password):
        return jsonify({"error": "Usuário ou senha incorretos."}), 401
    session["username"] = username
    return jsonify({"ok": True, "name": user["name"]})

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/auth/me", methods=["GET"])
def me():
    username = current_user()
    if not username:
        return jsonify({"error": "Não autenticado."}), 401
    user = get_user(username)
    return jsonify({
        "username": user["username"],
        "name": user["name"],
        "age": user.get("age", ""),
        "gender": user.get("gender", "")
    })

# ══════════════════════════════════════════════════════════════
# DIARY
# ══════════════════════════════════════════════════════════════

@app.route("/api/diary", methods=["GET"])
def diary_list():
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401
    db = load_db()
    entries = db["users"][username].get("diary", [])
    return jsonify(sorted(entries, key=lambda x: x["date"], reverse=True))

@app.route("/api/diary", methods=["POST"])
def diary_add():
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    mood = data.get("mood", 3)
    pain = data.get("pain", 0)
    if not text:
        return jsonify({"error": "Texto vazio."}), 400
    entry = {
        "id": str(uuid.uuid4())[:8],
        "date": datetime.now().isoformat(),
        "text": text,
        "mood": mood,
        "pain": pain
    }
    db = load_db()
    db["users"][username]["diary"].append(entry)
    save_db(db)
    return jsonify(entry)

@app.route("/api/diary/<entry_id>", methods=["DELETE"])
def diary_delete(entry_id):
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401
    db = load_db()
    db["users"][username]["diary"] = [
        e for e in db["users"][username]["diary"] if e["id"] != entry_id
    ]
    save_db(db)
    return jsonify({"ok": True})

# ══════════════════════════════════════════════════════════════
# MEDICATIONS
# ══════════════════════════════════════════════════════════════

@app.route("/api/medications", methods=["GET"])
def meds_list():
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401
    db = load_db()
    return jsonify(db["users"][username].get("medications", []))

@app.route("/api/medications", methods=["POST"])
def meds_add():
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401
    data = request.get_json(silent=True) or {}
    name     = (data.get("name") or "").strip()
    dose     = (data.get("dose") or "").strip()
    schedule = (data.get("schedule") or "").strip()
    notes    = (data.get("notes") or "").strip()
    if not name or not dose:
        return jsonify({"error": "Nome e dose são obrigatórios."}), 400
    med = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "dose": dose,
        "schedule": schedule,
        "notes": notes,
        "created_at": datetime.now().isoformat()
    }
    db = load_db()
    db["users"][username]["medications"].append(med)
    save_db(db)
    return jsonify(med)

@app.route("/api/medications/<med_id>", methods=["DELETE"])
def meds_delete(med_id):
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401
    db = load_db()
    db["users"][username]["medications"] = [
        m for m in db["users"][username]["medications"] if m["id"] != med_id
    ]
    save_db(db)
    return jsonify({"ok": True})

# ══════════════════════════════════════════════════════════════
# MEASUREMENTS (pressão, glicemia, peso)
# ══════════════════════════════════════════════════════════════

# Referências clínicas para alertas automáticos
MEASURE_REFS = {
    "pressao_sistolica": {"min": 90,  "max": 139, "unit": "mmHg"},
    "pressao_diastolica":{"min": 60,  "max": 89,  "unit": "mmHg"},
    "glicemia":          {"min": 70,  "max": 99,  "unit": "mg/dL"},
    "peso":              {"min": None,"max": None, "unit": "kg"},
    "frequencia":        {"min": 60,  "max": 100, "unit": "bpm"},
    "saturacao":         {"min": 95,  "max": 100, "unit": "%"},
    "temperatura":       {"min": 36.0,"max": 37.5,"unit": "°C"},
}

def measure_status(key, value):
    ref = MEASURE_REFS.get(key)
    if not ref or ref["min"] is None:
        return "normal"
    try:
        v = float(value)
        if ref["min"] is not None and v < ref["min"]: return "baixo"
        if ref["max"] is not None and v > ref["max"]: return "alto"
        return "normal"
    except:
        return "normal"

@app.route("/api/measurements", methods=["GET"])
def measurements_list():
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401
    db = load_db()
    # garante campo existe em usuários antigos
    if "measurements" not in db["users"][username]:
        db["users"][username]["measurements"] = []
        save_db(db)
    data = db["users"][username]["measurements"]
    return jsonify(sorted(data, key=lambda x: x["date"], reverse=True))

@app.route("/api/measurements", methods=["POST"])
def measurements_add():
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401
    data = request.get_json(silent=True) or {}

    # Coleta somente os campos enviados
    fields = ["pressao_sistolica","pressao_diastolica","glicemia","peso","frequencia","saturacao","temperatura"]
    values = {}
    alerts = []

    for f in fields:
        v = data.get(f, "").strip() if isinstance(data.get(f), str) else str(data.get(f, ""))
        if v:
            values[f] = v
            st = measure_status(f, v)
            if st != "normal":
                ref = MEASURE_REFS[f]
                alerts.append({
                    "field": f,
                    "value": v,
                    "status": st,
                    "unit": ref["unit"]
                })

    if not values:
        return jsonify({"error": "Informe ao menos uma medição."}), 400

    entry = {
        "id": str(uuid.uuid4())[:8],
        "date": datetime.now().isoformat(),
        "values": values,
        "alerts": alerts,
        "notes": (data.get("notes") or "").strip()
    }

    db = load_db()
    if "measurements" not in db["users"][username]:
        db["users"][username]["measurements"] = []
    db["users"][username]["measurements"].append(entry)
    save_db(db)
    return jsonify(entry)

@app.route("/api/measurements/<entry_id>", methods=["DELETE"])
def measurements_delete(entry_id):
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401
    db = load_db()
    db["users"][username]["measurements"] = [
        m for m in db["users"][username].get("measurements", []) if m["id"] != entry_id
    ]
    save_db(db)
    return jsonify({"ok": True})

# ══════════════════════════════════════════════════════════════
# DASHBOARD INTELIGENTE
# ══════════════════════════════════════════════════════════════

@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401

    user = get_user(username)
    now  = datetime.now()

    diary        = user.get("diary", [])
    medications  = user.get("medications", [])
    symptom_hist = user.get("symptom_history", [])
    measurements = user.get("measurements", [])

    insights = []

    # ── 1. Último registro no diário ──────────────────────
    if not diary:
        insights.append({
            "type": "info",
            "icon": "📓",
            "title": "Comece seu diário de saúde",
            "text": "Registrar como você se sente diariamente ajuda a identificar padrões.",
            "action": "diary",
            "action_label": "Fazer primeiro registro"
        })
    else:
        last_diary = max(diary, key=lambda x: x["date"])
        days_ago = (now - datetime.fromisoformat(last_diary["date"])).days
        if days_ago >= 3:
            insights.append({
                "type": "warn",
                "icon": "📓",
                "title": f"Diário sem registro há {days_ago} dias",
                "text": "Manter o diário atualizado ajuda a monitorar sua saúde ao longo do tempo.",
                "action": "diary",
                "action_label": "Registrar agora"
            })

    # ── 2. Medicamentos sem horário ────────────────────────
    meds_sem_horario = [m for m in medications if not m.get("schedule","").strip()]
    if meds_sem_horario:
        nomes = ", ".join(m["name"] for m in meds_sem_horario[:2])
        insights.append({
            "type": "warn",
            "icon": "💊",
            "title": "Medicamentos sem horário definido",
            "text": f"{nomes} não têm horário cadastrado. Tomar no horário certo é essencial.",
            "action": "medications",
            "action_label": "Revisar medicamentos"
        })

    # ── 3. Triagem urgente recente sem follow-up ───────────
    if symptom_hist:
        recentes = sorted(symptom_hist, key=lambda x: x["date"], reverse=True)
        ultima = recentes[0]
        dias = (now - datetime.fromisoformat(ultima["date"])).days
        if ultima.get("urgency") in ("urgente", "emergencia") and dias <= 7:
            insights.append({
                "type": "danger",
                "icon": "🚨",
                "title": "Triagem recente com urgência elevada",
                "text": f"Sua última triagem ({dias} dia(s) atrás) indicou nível '{ultima.get('urgency_label','')}'. Você consultou um médico?",
                "action": "triage",
                "action_label": "Ver triagem"
            })
        elif ultima.get("urgency") == "moderado" and dias >= 5:
            insights.append({
                "type": "warn",
                "icon": "🩺",
                "title": "Retorno da triagem pendente",
                "text": f"Há {dias} dias você teve sintomas de urgência moderada. Como está se sentindo agora?",
                "action": "triage",
                "action_label": "Nova triagem"
            })

    # ── 4. Alertas de medições fora do normal ──────────────
    if measurements:
        ultima_med = max(measurements, key=lambda x: x["date"])
        alertas = ultima_med.get("alerts", [])
        if alertas:
            nomes_map = {
                "pressao_sistolica": "Pressão sistólica",
                "pressao_diastolica": "Pressão diastólica",
                "glicemia": "Glicemia",
                "frequencia": "Frequência cardíaca",
                "saturacao": "Saturação O₂",
                "temperatura": "Temperatura"
            }
            for al in alertas[:2]:
                nome = nomes_map.get(al["field"], al["field"])
                insights.append({
                    "type": "danger" if al["status"] == "alto" else "warn",
                    "icon": "📊",
                    "title": f"{nome} {al['status']} na última medição",
                    "text": f"Valor registrado: {al['value']} {al['unit']}. Monitore e consulte seu médico se persistir.",
                    "action": "measurements",
                    "action_label": "Ver medições"
                })

    # ── 5. Sem medições recentes (para usuários com histórico) ─
    if measurements:
        ultima_m = max(measurements, key=lambda x: x["date"])
        dias_m = (now - datetime.fromisoformat(ultima_m["date"])).days
        if dias_m >= 7:
            insights.append({
                "type": "info",
                "icon": "📊",
                "title": f"Sem medições há {dias_m} dias",
                "text": "Registrar pressão, glicemia e peso regularmente é fundamental para quem monitora saúde crônica.",
                "action": "measurements",
                "action_label": "Registrar medição"
            })
    elif not measurements and (diary or medications):
        # usuário já usa o app mas nunca mediu
        insights.append({
            "type": "info",
            "icon": "📊",
            "title": "Registre suas medições de saúde",
            "text": "Acompanhe pressão arterial, glicemia, peso e outros indicadores em um só lugar.",
            "action": "measurements",
            "action_label": "Primeira medição"
        })

    # ── 6. Tudo bem ────────────────────────────────────────
    if not insights:
        insights.append({
            "type": "success",
            "icon": "✅",
            "title": "Tudo em dia!",
            "text": "Seus registros estão atualizados e não há alertas pendentes. Continue assim!",
            "action": None,
            "action_label": None
        })

    # ── Stats ──────────────────────────────────────────────
    stats = {
        "diary_count":       len(diary),
        "med_count":         len(medications),
        "triage_count":      len(symptom_hist),
        "measurement_count": len(measurements),
    }

    # Última medição para o dashboard
    last_measure = None
    if measurements:
        lm = max(measurements, key=lambda x: x["date"])
        last_measure = {
            "date": lm["date"],
            "values": lm["values"],
            "alerts": lm["alerts"]
        }

    return jsonify({
        "insights": insights,
        "stats": stats,
        "last_measure": last_measure
    })

# ══════════════════════════════════════════════════════════════
# AI ROUTES
# ══════════════════════════════════════════════════════════════

def groq_call(system, user_msg, max_tokens=800):
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg}
        ],
        temperature=0.3,
        max_tokens=max_tokens,
    )
    return completion.choices[0].message.content.strip()

def extract_json(raw):
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("JSON não encontrado")
    return json.loads(raw[start:end])

# ── Triagem de Sintomas ────────────────────────────────────

@app.route("/api/ai/triage", methods=["POST"])
def ai_triage():
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401

    data = request.get_json(silent=True) or {}
    symptoms = (data.get("symptoms") or "").strip()
    if not symptoms:
        return jsonify({"error": "Descreva seus sintomas."}), 400
    if len(symptoms) > 800:
        return jsonify({"error": "Descrição muito longa (máx. 800 caracteres)."}), 400

    user = get_user(username)
    ctx = f"Paciente: {user['name']}, {user.get('age','?')} anos, sexo {user.get('gender','?')}."

    system = """Você é um assistente de triagem de saúde. Analise os sintomas e retorne SOMENTE JSON válido, sem texto extra.

Estrutura obrigatória:
{"urgency":"emergencia|urgente|moderado|leve","urgency_label":"Emergência|Urgente|Moderado|Leve","summary":"resumo claro em 1-2 frases","possible_causes":["causa1","causa2","causa3"],"recommendations":["recomendação1","recomendação2","recomendação3"],"when_to_seek_care":"instrução clara sobre quando buscar atendimento","disclaimer":"SEMPRE consulte um médico. Esta análise não é diagnóstico médico."}

urgency: emergencia (risco de vida), urgente (buscar UPA em horas), moderado (consultar médico em dias), leve (cuidados em casa).
Nunca forneça diagnóstico definitivo."""

    try:
        raw = groq_call(system, f"{ctx}\nSintomas: {symptoms}", max_tokens=700)
        result = extract_json(raw)
        result["disclaimer"] = DISCLAIMER

        db = load_db()
        db["users"][username]["symptom_history"].append({
            "id": str(uuid.uuid4())[:8],
            "date": datetime.now().isoformat(),
            "symptoms": symptoms,
            "urgency": result.get("urgency", "moderado"),
            "urgency_label": result.get("urgency_label", "Moderado"),
            "summary": result.get("summary", "")
        })
        save_db(db)
        return jsonify(result)
    except Exception as e:
        print(f"Triage error: {e}")
        return jsonify({"error": "Erro ao processar. Tente novamente."}), 500

# ── Analisador de Exames ───────────────────────────────────

@app.route("/api/ai/exam", methods=["POST"])
def ai_exam():
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401

    data = request.get_json(silent=True) or {}
    exam_text = (data.get("exam_text") or "").strip()
    if not exam_text:
        return jsonify({"error": "Cole o texto do exame."}), 400
    if len(exam_text) > 1200:
        return jsonify({"error": "Texto muito longo (máx. 1200 caracteres)."}), 400

    system = """Analise o resultado do exame e retorne SOMENTE JSON valido, sem texto extra, sem markdown.

Formato exato:
{"exam_type":"nome do exame","overall":"normal","overall_label":"Normal","explanation":"resumo em 2 frases","items":[{"name":"item","value":"valor","reference":"referencia","status":"normal","interpretation":"significado breve"}],"recommendations":["rec1","rec2"]}

IMPORTANTE: overall e status so podem ser: normal, atencao ou alterado. Maximo 10 itens. Sem campos extras."""

    try:
        raw = groq_call(system, f"Exame:\n{exam_text}", max_tokens=1400)
        result = extract_json(raw)
        result["disclaimer"] = DISCLAIMER
        return jsonify(result)
    except Exception as e:
        print(f"Exam error: {e}")
        return jsonify({"error": "Erro ao processar. Tente novamente."}), 500

# ── Chat de Saúde ──────────────────────────────────────────

@app.route("/api/ai/chat", methods=["POST"])
def ai_chat():
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401

    data = request.get_json(silent=True) or {}
    message  = (data.get("message") or "").strip()
    history  = data.get("history", [])

    if not message:
        return jsonify({"error": "Mensagem vazia."}), 400
    if len(message) > 600:
        return jsonify({"error": "Mensagem muito longa (máx. 600 caracteres)."}), 400

    user = get_user(username)
    system = f"""Você é VitaAI, assistente de saúde virtual empático e responsável.
Paciente: {user['name']}, {user.get('age','?')} anos, sexo {user.get('gender','?')}.

REGRAS OBRIGATÓRIAS:
- Responda em português, de forma clara e acolhedora.
- NUNCA forneça diagnósticos definitivos.
- NUNCA indique dosagens específicas de medicamentos.
- Sempre recomende consulta médica para questões sérias.
- Em emergências, instrua a ligar 192 (SAMU) imediatamente.
- Seja conciso (máx. 3 parágrafos).
- Ao final de respostas sobre sintomas ou doenças, adicione: "💡 Lembre-se: esta informação não substitui consulta médica."
"""

    messages = [{"role": "system", "content": system}]
    for h in history[-6:]:
        if h.get("role") in ("user", "assistant"):
            messages.append({"role": h["role"], "content": h["content"][:400]})
    messages.append({"role": "user", "content": message})

    try:
        completion = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=0.5, max_tokens=600,
        )
        reply = completion.choices[0].message.content.strip()
        return jsonify({"reply": reply})
    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({"error": "Erro ao processar. Tente novamente."}), 500

# ── Histórico de Sintomas ──────────────────────────────────

@app.route("/api/symptom-history", methods=["GET"])
def symptom_history():
    username = current_user()
    if not username: return jsonify({"error": "Não autenticado."}), 401
    db = load_db()
    history = db["users"][username].get("symptom_history", [])
    return jsonify(sorted(history, key=lambda x: x["date"], reverse=True)[:20])

# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app.run(debug=True, port=5000)