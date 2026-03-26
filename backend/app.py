import os
import logging
import tempfile
import json
import shutil
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import docx
import pdfplumber
from groq import Groq

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

load_dotenv()

# Configurar cliente Groq
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logging.warning("GROQ_API_KEY no está configurada — el análisis usará el modo fallback")
    groq_client = None
else:
    groq_client = Groq(api_key=api_key)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-key-change-in-production")
CORS(app, origins=["chrome-extension://*"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.txt', '.docx', '.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.tiff'}

NIVELES = {
    "basica-1-4": "Educación Básica 1°-4° (7-10 años)",
    "basica-5-8": "Educación Básica 5°-8° (11-14 años)",
    "medio-1-2":  "Educación Media 1°-2° (15-16 años)",
    "medio-3-4":  "Educación Media 3°-4° (17-18 años)",
    "superior":   "Educación Superior (18+ años)"
}

# -------- Funciones auxiliares -------- #

def allowed_file(filename):
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)


def extraer_texto(file_path):
    texto = ""
    try:
        ext = file_path.lower()
        if ext.endswith(".txt"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                texto = f.read()
        elif ext.endswith(".docx"):
            doc = docx.Document(file_path)
            texto = "\n".join([p.text for p in doc.paragraphs])
        elif ext.endswith(".pdf"):
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        texto += page_text + "\n"
        elif ext.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tiff')):
            texto = extraer_texto_imagen(file_path)
        else:
            logging.warning(f"Formato no soportado: {ext}")
        return texto.strip()
    except Exception as e:
        logging.error(f"Error extrayendo texto: {e}")
        return ""


def extraer_texto_imagen(file_path):
    try:
        import pytesseract
        from PIL import Image
        logging.info(f"Procesando imagen con OCR: {file_path}")
        img = Image.open(file_path)
        texto = pytesseract.image_to_string(img, lang='spa+eng')
        logging.info(f"OCR completado: {len(texto)} caracteres extraídos")
        return texto
    except ImportError:
        logging.warning("pytesseract no está disponible. OCR no disponible.")
        return "OCR no disponible"
    except Exception as e:
        logging.error(f"Error en OCR: {e}")
        return ""


def analizar_con_groq(texto, nivel_educativo):
    """Envía el texto a Groq (Llama) y retorna (resultado_json, analizado_con_ia, error_info)"""
    if not texto.strip():
        return json.dumps(analisis_fallback(texto, nivel_educativo)), False, "Texto vacío"

    if not groq_client:
        return json.dumps(analisis_fallback(texto, nivel_educativo)), False, "GROQ_API_KEY no configurada"

    nivel_desc = NIVELES.get(nivel_educativo, nivel_educativo)

    prompt_sistema = f"""Eres un experto en detección de contenido generado por IA en trabajos académicos de estudiantes chilenos.
El estudiante cursa: {nivel_desc}. Un vocabulario o estructura demasiado sofisticada para ese nivel es una señal clara de IA.

Analiza el texto y determina si fue escrito por un humano o generado total o parcialmente por IA.

Señales de IA: estructura perfecta, conectores académicos excesivos ("en conclusión", "cabe destacar", "resulta pertinente"), párrafos homogéneos, ausencia de errores naturales, vocabulario sofisticado atípico para el nivel.

Señales humanas: errores gramaticales típicos de la edad, vocabulario apropiado al nivel, expresiones personales, inconsistencias naturales.

Responde ÚNICAMENTE con este JSON (sin texto adicional):
{{
    "porcentaje": número entre 0 y 100 (0=humano seguro, 100=IA seguro),
    "indicadores": ["indicador1", "indicador2", "indicador3"],
    "preguntas": ["pregunta de validación 1", "pregunta 2", "pregunta 3"]
}}"""

    try:
        logging.info(f"Conectando con Groq — {len(texto)} chars, nivel: {nivel_desc}")

        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user",   "content": f"TEXTO DEL ESTUDIANTE:\n{texto[:12000]}"}
            ],
            temperature=0.1,
            max_tokens=1024,
            response_format={"type": "json_object"}
        )

        raw = completion.choices[0].message.content
        logging.info(f"Respuesta de Groq recibida: {len(raw)} chars")

        data = json.loads(raw)
        porcentaje = max(0, min(100, int(data.get("porcentaje", 50))))

        if porcentaje < 50:
            color, label = "green", "Bajo"
        elif porcentaje < 75:
            color, label = "yellow", "Medio"
        else:
            color, label = "red", "Alto"

        resultado = {
            "porcentaje": porcentaje,
            "color": color,
            "label": label,
            "indicadores": data.get("indicadores", []),
            "preguntas": data.get("preguntas", []),
            "filename": "",
            "analizado_con_ia": True,
            "nivel_educativo": nivel_educativo,
            "error_info": "Análisis exitoso con IA (Groq)",
            "longitud_texto": len(texto),
            "palabras_unicas": len(set(texto.split())),
            "densidad_vocabulario": round(len(set(texto.split())) / len(texto.split()) * 100, 1) if texto.split() else 0
        }

        return json.dumps(resultado), True, "Análisis exitoso con IA"

    except Exception as e:
        logging.error(f"Error con Groq [{type(e).__name__}]: {e}")
        return json.dumps(analisis_fallback(texto, nivel_educativo)), False, str(e)


def analisis_fallback(texto, nivel_educativo):
    """Análisis heurístico básico cuando la IA no está disponible"""
    indicadores = []
    porcentaje = 50

    if len(texto) < 100:
        indicadores.append("Texto muy corto")
        porcentaje += 20
    if texto.count(".") < 3:
        indicadores.append("Pocos puntos (posible copia)")
        porcentaje += 15
    if len(set(texto.split())) < 15:
        indicadores.append("Vocabulario limitado")
        porcentaje += 15

    palabras = texto.split()
    if len(palabras) > 10 and (len(set(palabras)) / len(palabras)) < 0.6:
        indicadores.append("Mucha repetición de palabras")
        porcentaje += 20

    indicadores.append("Análisis automático (sin IA)")

    porcentaje = min(porcentaje, 100)
    color = "green" if porcentaje < 50 else "yellow" if porcentaje < 75 else "red"
    label = "Bajo" if porcentaje < 50 else "Medio" if porcentaje < 75 else "Alto"

    return {
        "porcentaje": porcentaje,
        "color": color,
        "label": label,
        "indicadores": indicadores,
        "preguntas": [
            "¿Puedes explicar el tema principal con tus propias palabras?",
            "Dame un ejemplo relacionado con tu entorno.",
            "¿Qué parte te costó más entender de este trabajo?"
        ],
        "filename": "",
        "analizado_con_ia": False,
        "nivel_educativo": nivel_educativo,
        "error_info": "Análisis automático (fallback — GROQ_API_KEY no configurada)",
        "longitud_texto": len(texto),
        "palabras_unicas": len(set(texto.split())),
        "densidad_vocabulario": round(len(set(texto.split())) / len(texto.split()) * 100, 1) if texto.split() else 0
    }


# -------- Rutas de Flask -------- #

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "version": "1.0",
        "ia_disponible": groq_client is not None
    })


@app.route("/analizar", methods=["POST"])
def analizar():
    logging.info(f"Inicio de análisis — {request.method} {request.url}")
    try:
        file  = request.files.get("file")
        nivel = request.form.get("nivel")

        logging.info(f"Archivo: {file.filename if file else 'None'}, nivel: {nivel}")

        if not file or file.filename == "":
            return jsonify({"error": "No se seleccionó ningún archivo"}), 400
        if not nivel:
            return jsonify({"error": "Por favor selecciona un nivel educativo"}), 400
        if not allowed_file(file.filename):
            return jsonify({"error": "Tipo de archivo no permitido. Use .txt, .docx, .pdf, .jpg, .png"}), 400

        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        if file_size > MAX_FILE_SIZE:
            return jsonify({"error": "Archivo demasiado grande. Máximo 10MB"}), 400

        temp_file = None
        try:
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=os.path.splitext(file.filename)[1])
            file.save(temp_file.name)

            texto = extraer_texto(temp_file.name)
            logging.info(f"Texto extraído: {len(texto)} caracteres")

            if not texto:
                return jsonify({
                    "porcentaje": 0, "color": "gray", "label": "No detectado",
                    "indicadores": ["No se pudo extraer texto del documento"],
                    "preguntas": [], "filename": file.filename,
                    "analizado_con_ia": False,
                    "error_info": "No se pudo extraer texto del documento"
                })

            resultado, analizado_con_ia, error_info = analizar_con_groq(texto, nivel)
            logging.info(f"Análisis completado — IA: {analizado_con_ia}, info: {error_info}")

            try:
                data = json.loads(resultado)
            except json.JSONDecodeError:
                data = analisis_fallback(texto, nivel)
                analizado_con_ia = False
                error_info = "Error parseando respuesta de IA"

            return jsonify({
                "porcentaje":          data.get("porcentaje", 50),
                "color":               data.get("color", "gray"),
                "label":               data.get("label", "Medio"),
                "indicadores":         data.get("indicadores", []),
                "preguntas":           data.get("preguntas", []),
                "filename":            file.filename,
                "analizado_con_ia":    analizado_con_ia,
                "nivel_educativo":     nivel,
                "error_info":          error_info,
                "longitud_texto":      data.get("longitud_texto", 0),
                "palabras_unicas":     data.get("palabras_unicas", 0),
                "densidad_vocabulario": data.get("densidad_vocabulario", 0)
            })

        except Exception as e:
            logging.error(f"Error procesando archivo: {e}")
            return jsonify({"error": f"Error procesando archivo: {str(e)}"}), 500
        finally:
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)

    except Exception as e:
        logging.error(f"Error inesperado: {e}")
        return jsonify({"error": f"Error inesperado: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
