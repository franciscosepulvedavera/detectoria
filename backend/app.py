import os
import logging
import tempfile
import json
import shutil
from flask import Flask, render_template, request, flash, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import docx
import pdfplumber
import google.generativeai as genai

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# Cargar variables de entorno
load_dotenv()

# Configurar Gemini
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    logging.warning("GOOGLE_API_KEY no está configurada — el análisis usará el modo fallback")
else:
    genai.configure(api_key=api_key)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-key-change-in-production")
CORS(app, origins=["chrome-extension://*"])

# Configuración
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.txt', '.docx', '.pdf',
                      '.jpg', '.jpeg', '.png', '.bmp', '.tiff'}

# -------- Funciones auxiliares -------- #


def allowed_file(filename):
    """Verifica si la extensión del archivo está permitida"""
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)


def extraer_texto(file_path):
    """Extrae el texto de un archivo TXT, DOCX, PDF o imagen"""
    texto = ""
    try:
        extension = file_path.lower()

        if extension.endswith(".txt"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                texto = f.read()
        elif extension.endswith(".docx"):
            doc = docx.Document(file_path)
            texto = "\n".join([p.text for p in doc.paragraphs])
        elif extension.endswith(".pdf"):
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    texto += page.extract_text() + "\n"
        elif extension.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tiff')):
            texto = extraer_texto_imagen(file_path)
        else:
            logging.warning(f"Formato no soportado: {extension}")

        return texto.strip()
    except Exception as e:
        logging.error(f"Error extrayendo texto: {e}")
        return ""


def extraer_texto_imagen(file_path):
    """Extrae texto de una imagen usando OCR (pytesseract)"""
    try:
        import pytesseract
        from PIL import Image
        logging.info(f"Procesando imagen con OCR: {file_path}")
        img = Image.open(file_path)
        texto = pytesseract.image_to_string(img, lang='spa+eng')
        logging.info(f"OCR completado: {len(texto)} caracteres extraídos")
        return texto
    except ImportError:
        logging.warning("pytesseract o Pillow no está instalado. OCR no disponible.")
        return "OCR no disponible - Instala pytesseract para procesar imágenes"
    except Exception as e:
        logging.error(f"Error en OCR: {e}")
        return ""


def diagnosticar_error_gemini(error):
    """Diagnostica el tipo de error de Gemini"""
    error_str = str(error).lower()

    if "quota" in error_str or "limit" in error_str:
        return "Cuota de API alcanzada - Has excedido el límite de requests"
    elif "invalid" in error_str and "key" in error_str:
        return "API Key inválida - Verifica tu clave de Google AI"
    elif "unauthorized" in error_str or "401" in error_str:
        return "No autorizado - API Key incorrecta o expirada"
    elif "rate" in error_str and "limit" in error_str:
        return "Límite de velocidad alcanzado - Demasiadas requests por minuto"
    elif "network" in error_str or "connection" in error_str:
        return "Error de conexión - Problema de red o internet"
    elif "timeout" in error_str:
        return "Timeout - La request tardó demasiado en responder"
    elif "json" in error_str:
        return "Error de formato JSON - Respuesta malformada de Gemini"
    elif "model" in error_str:
        return "Modelo no disponible - Error con el modelo de IA"
    else:
        return f"Error desconocido: {error}"


def limpiar_respuesta_gemini(response_text):
    """Limpia la respuesta de Gemini removiendo markdown y caracteres extra"""
    if not response_text:
        return ""

    # Remover markdown si existe
    if response_text.startswith('```json'):
        response_text = response_text.replace('```json', '').replace('```', '')

    # Remover espacios y saltos de línea al inicio y final
    response_text = response_text.strip()

    # Remover caracteres de escape si existen
    response_text = response_text.replace('\\n', '\n').replace('\\t', '\t')

    return response_text


def transformar_respuesta_gemini(respuesta_gemini, texto, nivel_educativo):
    """
    Transforma la respuesta simple de Gemini al formato completo requerido
    """
    try:
        # Parsear la respuesta simple de Gemini
        data = json.loads(respuesta_gemini)

        # Extraer datos básicos
        porcentaje = data.get("porcentaje", 50)
        indicadores = data.get("indicadores", [])
        preguntas = data.get("preguntas", [])

        # Determinar color y label basado en porcentaje
        if porcentaje < 50:
            color = "green"
            label = "Bajo"
        elif porcentaje < 75:
            color = "yellow"
            label = "Medio"
        else:
            color = "red"
            label = "Alto"

        # Crear respuesta completa
        resultado_completo = {
            "porcentaje": porcentaje,
            "color": color,
            "label": label,
            "indicadores": indicadores,
            "preguntas": preguntas,
            "filename": "",
            "analizado_con_ia": True,
            "nivel_educativo": nivel_educativo,
            "error_info": "Análisis exitoso con IA",
            "longitud_texto": len(texto),
            "palabras_unicas": len(set(texto.split())),
            "densidad_vocabulario": round((len(set(texto.split())) / len(texto.split()) * 100), 1) if texto.split() else 0
        }

        return json.dumps(resultado_completo), True, "Análisis exitoso con IA"

    except Exception as e:
        logging.error(f"Error transformando respuesta: {e}")
        return json.dumps(analisis_fallback(texto, nivel_educativo)), False, f"Error transformando respuesta: {str(e)}"


def analizar_con_gemini(texto, nivel_educativo):
    """
    Envía el texto a Gemini y obtiene el análisis en JSON.
    Retorna (resultado_json, analizado_con_ia: bool, error_info: str)
    """
    if not texto.strip():
        return json.dumps(analisis_fallback(texto, nivel_educativo)), False, "Texto vacío"

    # Mapear niveles a descripciones
    niveles = {
        "basica-1-4": "Educación Básica 1°-4° (7-10 años)",
        "basica-5-8": "Educación Básica 5°-8° (11-14 años)",
        "medio-1-2": "Educación Media 1°-2° (15-16 años)",
        "medio-3-4": "Educación Media 3°-4° (17-18 años)",
        "superior": "Educación Superior (18+ años)"
    }

    nivel_desc = niveles.get(nivel_educativo, "Nivel no especificado")

    # PROMPT SIMPLE - Solo datos esenciales
    prompt = f"""
    Analiza este texto de un estudiante de {nivel_desc} para detectar si fue creado con IA.

    Devuelve SOLO un JSON simple con esta estructura:
    {{
        "porcentaje": [0-100, donde 0=humano, 100=IA],
        "indicadores": ["indicador1", "indicador2", "indicador3"],
        "preguntas": ["pregunta1", "pregunta2", "pregunta3"]
    }}

    Indicadores de IA a buscar:
    - Vocabulario muy avanzado para la edad
    - Estructura demasiado perfecta
    - Falta de errores típicos de la edad
    - Repetición de patrones
    - Complejidad sintáctica inusual

    Indicadores de escritura humana:
    - Errores gramaticales típicos de la edad
    - Vocabulario apropiado para el nivel
    - Expresiones personales
    - Inconsistencias naturales

    Preguntas según nivel {nivel_desc}:
    - "¿Puedes explicar con tus propias palabras?"
    - "Dame un ejemplo relacionado con tu experiencia"
    - "¿Qué opinión personal tienes?"

    Texto: {texto[:1500]}

    JSON:
    """

    try:
        logging.info(f"Conectando con Gemini — texto: {len(texto)} chars, nivel: {nivel_desc}")

        # Verificar API key
        if not api_key or api_key == "tu_api_key_aqui":
            logging.error("API Key no configurada")
            return json.dumps(analisis_fallback(texto, nivel_educativo)), False, "API Key no configurada"

        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)

        if response is None:
            logging.error("Gemini devolvió respuesta None")
            return json.dumps(analisis_fallback(texto, nivel_educativo)), False, "Gemini devolvió respuesta vacía"

        if not hasattr(response, 'text'):
            logging.error("Respuesta de Gemini sin atributo 'text'")
            return json.dumps(analisis_fallback(texto, nivel_educativo)), False, "Respuesta de Gemini no tiene texto"

        response_text = response.text
        if not response_text or response_text.strip() == "":
            logging.error("Respuesta de Gemini está vacía")
            return json.dumps(analisis_fallback(texto, nivel_educativo)), False, "Gemini devolvió respuesta vacía"

        logging.info(f"Respuesta de Gemini recibida: {len(response_text)} chars")
        response_text_limpia = limpiar_respuesta_gemini(response_text)
        return transformar_respuesta_gemini(response_text_limpia, texto, nivel_educativo)

    except Exception as e:
        error_diagnostico = diagnosticar_error_gemini(e)
        logging.error(f"Error con Gemini [{type(e).__name__}]: {e} — {error_diagnostico}")
        return json.dumps(analisis_fallback(texto, nivel_educativo)), False, error_diagnostico


def analisis_fallback(texto, nivel_educativo):
    """Análisis básico cuando Gemini falla"""
    indicadores = []
    porcentaje = 50

    # Análisis básico del texto
    if len(texto) < 100:
        indicadores.append("Texto muy corto")
        porcentaje += 20

    if texto.count(".") < 3:
        indicadores.append("Pocos puntos (posible copia)")
        porcentaje += 15

    if len(set(texto.split())) < 15:
        indicadores.append("Vocabulario limitado")
        porcentaje += 15

    # Detectar texto repetitivo
    palabras = texto.split()
    if len(palabras) > 10:
        palabras_unicas = len(set(palabras))
        ratio = palabras_unicas / len(palabras)
        if ratio < 0.6:
            indicadores.append("Mucha repetición de palabras")
            porcentaje += 20

    # Ajustar según nivel educativo
    if nivel_educativo in ["basica-1-4", "basica-5-8"]:
        indicadores.append(f"Análisis básico para nivel {nivel_educativo}")
    elif nivel_educativo in ["medio-1-2", "medio-3-4"]:
        indicadores.append(f"Análisis para educación media")
    else:
        indicadores.append("Análisis automático básico")

    nivel = "bajo" if porcentaje < 50 else "medio" if porcentaje < 75 else "alto"
    color = "green" if nivel == "bajo" else "yellow" if nivel == "medio" else "red"

    return {
        "porcentaje": min(porcentaje, 100),
        "color": color,
        "label": nivel.capitalize(),
        "indicadores": indicadores if indicadores else ["Análisis automático básico"],
        "preguntas": [
            "¿Puedes explicar el tema principal con tus propias palabras?",
            "Dame un ejemplo relacionado con tu entorno.",
            "¿Qué parte te costó más entender de este trabajo?"
        ],
        "filename": "",
        "analizado_con_ia": False,
        "nivel_educativo": nivel_educativo,
        "error_info": "Análisis automático (fallback)",
        "longitud_texto": len(texto),
        "palabras_unicas": len(set(texto.split())),
        "densidad_vocabulario": round((len(set(texto.split())) / len(texto.split()) * 100), 1) if texto.split() else 0
    }

# -------- Rutas de Flask -------- #


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "1.0"})


@app.route("/test", methods=["GET"])
def test():
    """Ruta de prueba para verificar que el servidor funciona"""
    return jsonify({"message": "Servidor funcionando correctamente"})


@app.route("/analizar", methods=["POST"])
def analizar():
    """Endpoint AJAX para análisis de archivos"""
    logging.info(f"Inicio de análisis — {request.method} {request.url}")

    try:
        file = request.files.get("file")
        nivel = request.form.get("nivel")

        logging.info(f"Archivo: {file.filename if file else 'None'}, nivel: {nivel}")

        if not file or file.filename == "":
            return jsonify({"error": "No se seleccionó ningún archivo"}), 400

        if not nivel:
            return jsonify({"error": "Por favor selecciona un nivel educativo"}), 400

        if not allowed_file(file.filename):
            return jsonify({"error": "Tipo de archivo no permitido. Use .txt, .docx, .pdf, .jpg, .png"}), 400

        # Verificar tamaño del archivo
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        logging.info(f"Tamaño del archivo: {file_size} bytes")

        if file_size > MAX_FILE_SIZE:
            return jsonify({"error": "Archivo demasiado grande. Máximo 10MB"}), 400

        # Procesar archivo
        temp_file = None
        try:
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=os.path.splitext(file.filename)[1])
            file.save(temp_file.name)

            texto = extraer_texto(temp_file.name)
            logging.info(f"Texto extraído: {len(texto)} caracteres")

            if not texto:
                logging.warning("No se pudo extraer texto del documento")
                return jsonify({
                    "porcentaje": 0,
                    "color": "gray",
                    "label": "No detectado",
                    "indicadores": ["No se pudo extraer texto del documento"],
                    "preguntas": [],
                    "filename": file.filename,
                    "analizado_con_ia": False,
                    "error_info": "No se pudo extraer texto del documento"
                })

            resultado, analizado_con_ia, error_info = analizar_con_gemini(texto, nivel)
            logging.info(f"Análisis completado — IA: {analizado_con_ia}, info: {error_info}")

            try:
                data = json.loads(resultado)
            except json.JSONDecodeError:
                logging.error("Error parseando JSON de Gemini, usando fallback")
                data = analisis_fallback(texto, nivel)
                analizado_con_ia = False
                error_info = "Error parseando respuesta de IA"

            porcentaje = data.get("porcentaje", 50)
            label = data.get("label", "medio")
            color = data.get("color", "gray")

            resultado_final = {
                "porcentaje": porcentaje,
                "color": color,
                "label": label.capitalize(),
                "indicadores": data.get("indicadores", []),
                "preguntas": data.get("preguntas", []),
                "filename": file.filename,
                "analizado_con_ia": analizado_con_ia,
                "nivel_educativo": nivel,
                "error_info": error_info,
                "longitud_texto": data.get("longitud_texto", 0),
                "palabras_unicas": data.get("palabras_unicas", 0),
                "densidad_vocabulario": data.get("densidad_vocabulario", 0)
            }

            return jsonify(resultado_final)

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
