# DetectorIA

Herramienta para profesores chilenos que detecta si un trabajo de estudiante fue generado con IA. Combina un backend Flask (análisis con Google Gemini) y una extensión de Chrome (análisis local con Groq), ambos con soporte para PDF, DOCX, TXT e imágenes.

---

## Qué es DetectorIA

DetectorIA analiza textos de estudiantes y estima la probabilidad de que hayan sido generados por IA, contextualizando el análisis según el nivel educativo del estudiante (1° Básico hasta universitario). Puede usarse de dos formas:

- **Extensión Chrome** — sin servidor, analiza directamente en el navegador usando la API de Groq (Llama, Gemma).
- **Backend Flask** — servidor propio desplegado en Render.com, analiza usando Google Gemini con fallback heurístico.
- **Modo híbrido** — la extensión puede conectarse al backend si se configura la URL del servidor.

---

## Estructura del proyecto

```
detectoria/
├── .gitignore
├── .env.example
├── README.md
├── Procfile                  ← arranque para Render.com
├── render.yaml               ← configuración de deploy
├── requirements.txt          ← dependencias Python
│
├── backend/                  ← servidor Flask
│   ├── app.py
│   └── templates/
│       ├── index.html
│       └── result.html
│
└── extension/                ← extensión Chrome
    ├── manifest.json
    ├── assets/               ← íconos
    └── src/
        ├── popup.html / popup.js
        ├── options.html / options.js
        ├── background.js
        └── styles.css
```

---

## Cómo correr el backend (Flask)

### Requisitos
- Python 3.11+
- Tesseract instalado en el sistema (opcional, para OCR de imágenes)

### Instalación local

```bash
# 1. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Edita .env y agrega tu GOOGLE_API_KEY

# 4. Correr el servidor
python backend/app.py
# → http://127.0.0.1:5000
```

### Endpoints disponibles

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/` | Interfaz web |
| `GET` | `/health` | Health check → `{"status":"ok","version":"1.0"}` |
| `POST` | `/analizar` | Recibe `file` + `nivel`, devuelve JSON de análisis |

### Ejemplo con curl

```bash
curl -X POST \
  -F "file=@trabajo.docx" \
  -F "nivel=medio-3-4" \
  http://127.0.0.1:5000/analizar | jq .
```

Valores para `nivel`: `basica-1-4` · `basica-5-8` · `medio-1-2` · `medio-3-4` · `superior`

### Deploy en Render.com

1. Sube el proyecto a GitHub
2. En Render → **New Web Service** → conecta el repo
3. Render detecta `render.yaml` automáticamente
4. En **Environment Variables** agrega `GOOGLE_API_KEY` con tu valor real
5. Deploy — la URL resultante es la que configuras en la extensión

---

## Cómo instalar la extensión Chrome

1. Abre Chrome y ve a `chrome://extensions`
2. Activa **Modo desarrollador** (esquina superior derecha)
3. Haz clic en **Cargar descomprimida**
4. Selecciona la carpeta `extension/` de este proyecto
5. La extensión aparece en la barra de herramientas

### Configuración inicial

Al instalar por primera vez se abre automáticamente la página de opciones. Ahí configuras:

- **API Key de Groq** — para análisis local sin servidor. Obtén tu clave gratuita en [console.groq.com/keys](https://console.groq.com/keys)
- **URL del servidor (opcional)** — si tienes el backend Flask desplegado, pega la URL aquí (ej: `https://detectoria-backend.onrender.com`). Si se configura, el análisis usará Gemini vía servidor en vez de Groq.

### Formatos soportados por la extensión

PDF · DOCX · TXT · PNG · JPG · JPEG

---

## Variables de entorno necesarias

Copia `.env.example` a `.env` y completa los valores:

```bash
cp .env.example .env
```

| Variable | Descripción | Requerida |
|----------|-------------|-----------|
| `GOOGLE_API_KEY` | API key de Google AI (Gemini) | Sí, para el backend |
| `SECRET_KEY` | Clave secreta de Flask (sesiones) | Recomendada en producción |

La extensión Chrome **no usa** estas variables de entorno — su API key de Groq se guarda en `chrome.storage.sync` a través de la página de opciones.

---

## Licencia

Proyecto educativo. Ajusta la licencia según tus necesidades.
