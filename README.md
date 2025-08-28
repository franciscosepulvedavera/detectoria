## Detector de IA para trabajos de estudiantes

Aplicación web en Flask que analiza documentos de estudiantes y estima el nivel de probabilidad de que hayan sido generados con IA. Usa la API de Google Gemini cuando hay clave configurada y, en caso de error o falta de clave, realiza un análisis automático de respaldo (fallback).

### Características
- **Subida de archivos** por arrastre o selección manual.
- **Formatos soportados**: `.txt`, `.docx`, `.pdf`, `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`.
- **Selector de nivel educativo** para contextualizar el análisis (básica, media, superior).
- **Análisis con IA (Gemini)** cuando hay `GOOGLE_API_KEY` válida.
- **Fallback automático** si falla la IA (reglas simples sobre longitud, puntuación, repetición, vocabulario).
- **Resultados en tiempo real** vía endpoint JSON: porcentaje, color/label, indicadores, preguntas de validación y métricas básicas.

### Requisitos
- Python 3.11
- Dependencias listadas en `requirements.txt`

### Instalación
1. Crear y activar un entorno virtual (opcional pero recomendado):
```bash
python3 -m venv venv
source venv/bin/activate
```
2. Instalar dependencias:
```bash
pip install -r requirements.txt
```

### Variables de entorno
Crear un archivo `.env` en la raíz del proyecto con:
```
GOOGLE_API_KEY=tu_api_key_de_google_ai
SECRET_KEY=una_clave_secreta_para_flask
```
- `GOOGLE_API_KEY`: Necesaria para usar Gemini. Si falta o es inválida, la app usa el análisis de fallback.
- `SECRET_KEY`: Para sesiones/flash en Flask; en producción usar un valor robusto.

### Ejecutar la aplicación
```bash
python app.py
```
Luego abrir en el navegador: `http://127.0.0.1:5000/`

Rutas principales:
- `GET /` — Interfaz web para subir y analizar documentos.
- `GET /test` — Prueba de salud del servidor: devuelve `{ "message": "Servidor funcionando correctamente" }`.
- `POST /analizar` — Endpoint AJAX que recibe archivo y nivel educativo, y devuelve JSON con el análisis.

### Uso desde la interfaz
1. Abrir la página principal.
2. Arrastrar o seleccionar un archivo soportado.
3. Elegir el nivel educativo.
4. Pulsar "Analizar Documento" y esperar el resultado.

### Uso del endpoint `/analizar` con curl
```bash
curl -X POST \
  -F "file=@/ruta/a/tu_archivo.docx" \
  -F "nivel=medio-3-4" \
  http://127.0.0.1:5000/analizar | jq .
```

Valores permitidos para `nivel`:
- `basica-1-4`
- `basica-5-8`
- `medio-1-2`
- `medio-3-4`
- `superior`

Respuesta JSON (ejemplo):
```json
{
  "porcentaje": 72,
  "color": "yellow",
  "label": "Medio",
  "indicadores": ["Vocabulario avanzado para la edad", "Estructura muy regular"],
  "preguntas": ["¿Puedes explicar con tus propias palabras?"],
  "filename": "trabajo.pdf",
  "analizado_con_ia": true,
  "nivel_educativo": "medio-3-4",
  "error_info": "Análisis exitoso con IA",
  "longitud_texto": 2450,
  "palabras_unicas": 620,
  "densidad_vocabulario": 25.3
}
```

### Notas sobre OCR (imágenes)
- La función de OCR está stub/placeholder en `app.py` y devuelve un mensaje indicando que no está disponible.
- Para OCR real, instalar y configurar:
  - `opencv-python` y `pytesseract` (ya listados en `requirements.txt`).
  - Tesseract en el sistema operativo y su ruta accesible por `pytesseract`.

### Límites y validaciones
- Tamaño máximo de archivo: 10 MB.
- Validación de extensiones y tamaño antes de procesar.
- Si no se puede extraer texto, se retorna un JSON con `error` o indicadores informando el problema.

### Estructura del proyecto
```
app.py
templates/
  ├─ index.html     # Interfaz principal (drag & drop, selector de nivel, resultados)
  └─ result.html    # Plantilla alternativa de resultados
requirements.txt
README.md
```

### Despliegue
- Configurar variables de entorno en el servidor (incluida `GOOGLE_API_KEY`).
- Ejecutar con un WSGI como `gunicorn` detrás de un servidor web (Nginx/Apache) para producción.
- Desactivar `debug=True` en producción.

### Solución de problemas
- "GOOGLE_API_KEY no está configurada": crear `.env` con la clave válida.
- Errores 401/403/limites de cuota: revisar el panel de Google AI y la facturación.
- PDFs escaneados sin texto: requieren OCR; ver sección de OCR.
- Respuestas inesperadas de Gemini: la app limpia y transforma la salida, y hace fallback si el JSON no es parseable.

### Licencia
Este proyecto se distribuye con fines educativos. Ajusta la licencia según tus necesidades.
