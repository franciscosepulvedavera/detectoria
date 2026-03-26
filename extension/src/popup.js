// ============================================================
// DetectorIA — popup.js  (Groq API)
// ============================================================

const $ = id => document.getElementById(id);

let selectedFile = null;

// ---- Opciones ----
$('openOptions').addEventListener('click', () => chrome.runtime.openOptionsPage());
$('bannerOpenOptions').addEventListener('click', () => chrome.runtime.openOptionsPage());

// ---- Verificar configuración al abrir el popup ----
// El banner se muestra solo si no hay ni API key de Groq ni URL de servidor.
chrome.storage.sync.get({ groqApiKey: '', backendUrl: '' }, ({ groqApiKey, backendUrl }) => {
  if (!groqApiKey && !backendUrl) showApiKeyBanner();
});

// ---- Dropzone ----
const dropzone  = $('dropzone');
const fileInput = $('fileInput');

dropzone.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });
dropzone.addEventListener('dragover',  e => { e.preventDefault(); dropzone.classList.add('drag'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('drag');
  handleFile(e.dataTransfer?.files?.[0]);
});
fileInput.addEventListener('change', () => handleFile(fileInput.files?.[0]));

const ALLOWED = ['.txt', '.pdf', '.docx', '.png', '.jpg', '.jpeg'];

function handleFile(file) {
  if (!file) return;
  const ext = getExt(file.name);
  if (!ALLOWED.includes(ext)) {
    showStatus('Formato no soportado. Usa PDF, DOCX, TXT, PNG o JPG.', 'error');
    return;
  }
  if (file.size > 15 * 1024 * 1024) {
    showStatus('El archivo supera 15 MB. Usa un documento más pequeño.', 'error');
    return;
  }
  selectedFile = file;
  $('fileMeta').hidden = false;
  $('fileMeta').textContent = `${file.name}  (${fmtSize(file.size)})`;
  $('analyzeBtn').disabled = false;
  $('results').hidden = true;
  hideStatus();
}

// ---- Analizar ----
$('analyzeBtn').addEventListener('click', analyze);

async function analyze() {
  if (!selectedFile) return;

  const { groqApiKey, groqModel, backendUrl } = await new Promise(resolve =>
    chrome.storage.sync.get(
      { groqApiKey: '', groqModel: 'llama-3.3-70b-versatile', backendUrl: '' },
      resolve
    )
  );

  if (!groqApiKey && !backendUrl) {
    showApiKeyBanner();
    return;
  }

  hideApiKeyBanner();
  const level       = $('level').value;
  const usingServer = !!backendUrl;
  setLoading(true);
  showStatus(
    usingServer ? 'Analizando con Gemini (servidor)…' : 'Analizando con Groq (local)…',
    'loading'
  );

  try {
    let result;
    if (usingServer) {
      const raw = await callBackend(selectedFile, level, backendUrl);
      result = normalizeBackendResult(raw);
    } else {
      result = await analyzeFile(selectedFile, level, groqApiKey, groqModel);
    }
    renderResults(result);
    showStatus(
      usingServer ? '✓ Analizado con Gemini (servidor)' : '✓ Analizado con Groq (local)',
      'info'
    );
  } catch (err) {
    showStatus('Error: ' + err.message, 'error');
  } finally {
    setLoading(false);
  }
}

// ---- Extracción de texto según tipo de archivo ----
async function analyzeFile(file, level, apiKey, model) {
  const ext = getExt(file.name);
  let text = '';

  if (ext === '.txt') {
    text = await readText(file);

  } else if (ext === '.docx') {
    text = await extractDocx(file);
    if (!text) throw new Error('No se pudo leer el DOCX. Prueba convertirlo a TXT o PDF.');

  } else if (ext === '.pdf') {
    text = await extractPdfText(file);
    if (!text || text.length < 30) throw new Error('No se pudo extraer texto del PDF. Prueba con un PDF generado desde Word o Google Docs (no escaneado).');

  } else if (['.png', '.jpg', '.jpeg'].includes(ext)) {
    // Imágenes: usar modelo de visión de Groq
    return await callGroqVision(file, level, apiKey);
  }

  if (!text || text.trim().length < 20) {
    throw new Error('El archivo parece estar vacío o no tiene texto legible.');
  }

  return await callGroq(text, level, apiKey, model);
}

// ---- Llamada a Groq (texto) ----
async function callGroq(text, level, apiKey, model) {
  const resp = await fetch('https://api.groq.com/openai/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: 'system', content: buildPrompt(level) },
        { role: 'user',   content: 'TEXTO DEL ESTUDIANTE:\n' + text.slice(0, 12000) }
      ],
      temperature: 0.1,
      max_tokens: 1024,
      response_format: { type: 'json_object' }
    })
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.error?.message || `Error HTTP ${resp.status}`);
  }

  const data    = await resp.json();
  const rawText = data?.choices?.[0]?.message?.content || '';
  try {
    return JSON.parse(rawText);
  } catch {
    throw new Error('Respuesta inesperada de la IA. Intenta de nuevo.');
  }
}

// ---- Llamada a Groq (visión para imágenes) ----
async function callGroqVision(file, level, apiKey) {
  const b64      = await readBase64(file);
  const mimeType = mimeFor(getExt(file.name));

  const resp = await fetch('https://api.groq.com/openai/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      model: 'llama-3.2-11b-vision-preview',
      messages: [{
        role: 'user',
        content: [
          { type: 'image_url', image_url: { url: `data:${mimeType};base64,${b64}` } },
          { type: 'text', text: buildPrompt(level) + '\n\nAnaliza el documento de la imagen y responde con el JSON indicado.' }
        ]
      }],
      temperature: 0.1,
      max_tokens: 1024
    })
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.error?.message || `Error HTTP ${resp.status}`);
  }

  const data    = await resp.json();
  const rawText = data?.choices?.[0]?.message?.content || '';
  const cleaned = rawText.replace(/```json\s*/g, '').replace(/```\s*/g, '').trim();
  try {
    return JSON.parse(cleaned);
  } catch {
    throw new Error('Respuesta inesperada de la IA. Intenta de nuevo.');
  }
}

// ---- Prompt ----
function buildPrompt(level) {
  const ctx = level
    ? `El estudiante cursa: ${level}. Un vocabulario o estructura demasiado sofisticada para ese nivel es una señal clara de IA.`
    : 'El nivel educativo no fue especificado.';

  return `Eres un experto en detección de contenido generado por IA en trabajos académicos de estudiantes chilenos.

${ctx}

Analiza el texto y determina si fue escrito por un humano o generado total o parcialmente por IA.

Señales de IA: estructura perfecta, conectores académicos excesivos ("en conclusión", "cabe destacar", "resulta pertinente"), párrafos homogéneos, ausencia de errores naturales, vocabulario sofisticado atípico para el nivel.

Responde ÚNICAMENTE con este JSON (sin texto adicional):
{
  "is_ai": boolean,
  "score": número entre 0.0 y 1.0 (0 = humano seguro, 1 = IA seguro),
  "nivel_adecuacion": "alta" | "media" | "baja",
  "observaciones": "2 o 3 oraciones explicando el análisis",
  "fragmentos_sospechosos": [
    { "fragmento": "cita textual breve", "motivo": "explicación" }
  ]
}

Incluye hasta 3 fragmentos sospechosos si los hay. Si no hay, deja el arreglo vacío.`;
}

// ---- Lectores de archivo ----
function readText(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload  = e => res(e.target.result);
    r.onerror = () => rej(new Error('Error leyendo el archivo'));
    r.readAsText(file, 'UTF-8');
  });
}

function readBase64(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload  = e => res(e.target.result.split(',')[1]);
    r.onerror = () => rej(new Error('Error leyendo el archivo'));
    r.readAsDataURL(file);
  });
}

// ---- Parser DOCX (sin dependencias, usa DecompressionStream nativo) ----
async function extractDocx(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let offset  = 0;

  while (offset < bytes.length - 30) {
    if (bytes[offset] !== 0x50 || bytes[offset+1] !== 0x4B ||
        bytes[offset+2] !== 0x03 || bytes[offset+3] !== 0x04) { offset++; continue; }

    const compression = bytes[offset+8]  | (bytes[offset+9]  << 8);
    const compSize    = bytes[offset+18] | (bytes[offset+19] << 8) | (bytes[offset+20] << 16) | (bytes[offset+21] << 24);
    const fnLen       = bytes[offset+26] | (bytes[offset+27] << 8);
    const exLen       = bytes[offset+28] | (bytes[offset+29] << 8);
    const dataStart   = offset + 30 + fnLen + exLen;
    const filename    = new TextDecoder().decode(bytes.slice(offset + 30, offset + 30 + fnLen));

    if (filename === 'word/document.xml') {
      const comp = bytes.slice(dataStart, dataStart + compSize);
      let xmlBytes;
      if (compression === 0) {
        xmlBytes = comp;
      } else if (compression === 8) {
        try {
          const ds = new DecompressionStream('deflate-raw');
          const w  = ds.writable.getWriter();
          w.write(comp); w.close();
          xmlBytes = new Uint8Array(await new Response(ds.readable).arrayBuffer());
        } catch { return ''; }
      } else { return ''; }

      const xml   = new TextDecoder('utf-8').decode(xmlBytes);
      const doc   = new DOMParser().parseFromString(xml, 'text/xml');
      const ns    = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';
      let nodes   = doc.getElementsByTagNameNS(ns, 't');
      if (!nodes.length) nodes = doc.getElementsByTagName('w:t');
      if (!nodes.length) nodes = doc.getElementsByTagName('t');
      return Array.from(nodes).map(n => n.textContent).join(' ').trim();
    }

    const next = dataStart + compSize;
    offset = next > offset ? next : offset + 1;
  }
  return '';
}

// ---- Parser PDF básico (PDFs de texto generados desde Word/Google Docs) ----
async function extractPdfText(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const raw   = new TextDecoder('latin1').decode(bytes);
  const texts = [];

  // Busca todos los streams en el PDF
  const streamRe = /stream\r?\n([\s\S]*?)\r?\nendstream/g;
  let m;
  while ((m = streamRe.exec(raw)) !== null) {
    const chunk = m[1];

    // Prueba sin compresión
    if (chunk.includes('BT') && chunk.includes('ET')) {
      texts.push(...parsePdfOps(chunk));
      continue;
    }

    // Prueba FlateDecode (deflate / deflate-raw)
    const streamBytes = Uint8Array.from(chunk, c => c.charCodeAt(0));
    for (const algo of ['deflate', 'deflate-raw']) {
      try {
        const ds = new DecompressionStream(algo);
        const w  = ds.writable.getWriter();
        w.write(streamBytes); w.close();
        const dec = new TextDecoder('latin1').decode(await new Response(ds.readable).arrayBuffer());
        if (dec.includes('BT') && dec.includes('ET')) {
          texts.push(...parsePdfOps(dec));
          break;
        }
      } catch { /* sigue */ }
    }
  }

  return texts.join(' ').replace(/\s+/g, ' ').trim();
}

function parsePdfOps(stream) {
  const out    = [];
  const blocks = stream.match(/BT[\s\S]*?ET/g) || [];
  for (const blk of blocks) {
    // Tj
    for (const tj of (blk.match(/\(([^)\\]*(?:\\.[^)\\]*)*)\)\s*Tj/g) || [])) {
      const t = tj.match(/\(([\s\S]*)\)\s*Tj$/)?.[1];
      if (t) out.push(decodePdfStr(t));
    }
    // TJ
    for (const arr of (blk.match(/\[[\s\S]*?\]\s*TJ/g) || [])) {
      for (const p of (arr.match(/\(([^)\\]*(?:\\.[^)\\]*)*)\)/g) || [])) {
        out.push(decodePdfStr(p.slice(1, -1)));
      }
    }
  }
  return out.filter(Boolean);
}

function decodePdfStr(s) {
  return s
    .replace(/\\n/g, '\n').replace(/\\r/g, '').replace(/\\t/g, ' ')
    .replace(/\\\(/g, '(').replace(/\\\)/g, ')').replace(/\\\\/g, '\\')
    .replace(/\\(\d{3})/g, (_, o) => String.fromCharCode(parseInt(o, 8)));
}

// ---- Mapeo de niveles: selector → formato del backend Flask ----
const NIVEL_MAP = {
  '1° Básico': 'basica-1-4', '2° Básico': 'basica-1-4',
  '3° Básico': 'basica-1-4', '4° Básico': 'basica-1-4',
  '5° Básico': 'basica-5-8', '6° Básico': 'basica-5-8',
  '7° Básico': 'basica-5-8', '8° Básico': 'basica-5-8',
  '1° Medio':  'medio-1-2',  '2° Medio':  'medio-1-2',
  '3° Medio':  'medio-3-4',  '4° Medio':  'medio-3-4',
  'CFT Centro de Formación Técnica': 'superior',
  'IP Instituto Profesional':        'superior',
  'Universitario':                   'superior',
};

// ---- Llamada al backend Flask (/analizar) ----
async function callBackend(file, level, backendUrl) {
  const form = new FormData();
  form.append('file', file);
  form.append('nivel', NIVEL_MAP[level] || 'medio-3-4');

  const resp = await fetch(backendUrl + '/analizar', { method: 'POST', body: form });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.error || `Error HTTP ${resp.status} del servidor`);
  }
  return resp.json();
}

// ---- Normaliza la respuesta del backend al formato que usa renderResults ----
// Backend devuelve: { porcentaje, color, label, indicadores, preguntas, ... }
// renderResults espera: { is_ai, score, nivel_adecuacion, observaciones, fragmentos_sospechosos }
function normalizeBackendResult(data) {
  const score      = Math.max(0, Math.min(100, data.porcentaje || 0)) / 100;
  const adecuacion = score < 0.35 ? 'baja' : score < 0.7 ? 'media' : 'alta';
  const obs        = (data.indicadores || []).join(' · ') || data.error_info || 'Análisis completado.';
  return {
    is_ai:                 score >= 0.5,
    score,
    nivel_adecuacion:      adecuacion,
    observaciones:         obs,
    fragmentos_sospechosos: []
  };
}

// ---- Render resultados ----
function renderResults(data) {
  const score = Math.max(0, Math.min(1, Number(data.score) || 0));
  const pct   = Math.round(score * 100);
  const box   = $('scoreBox');

  $('scoreNumber').textContent = pct + '%';

  let cls, riskText;
  if (pct >= 70)      { cls = 'risk-high'; riskText = 'Alto riesgo de IA'; }
  else if (pct >= 35) { cls = 'risk-med';  riskText = 'Riesgo moderado'; }
  else                { cls = 'risk-low';  riskText = 'Bajo riesgo'; }

  box.className = 'score-box ' + cls;
  $('riskLabel').textContent = riskText;
  $('isAiLabel').textContent = data.is_ai
    ? '🤖 Posiblemente generado por IA'
    : '✍️ Aparenta ser escrito por el estudiante';

  let html = '';

  if (data.observaciones) {
    html += `<div class="card"><div class="card-title">Observaciones</div><p>${esc(data.observaciones)}</p></div>`;
  }

  if (data.nivel_adecuacion) {
    const labels = { alta: 'Alta ✓', media: 'Media ≈', baja: 'Baja ⚠️' };
    html += `<div class="meta-row">
      <span class="meta-key">Adecuación al nivel</span>
      <span class="meta-val">${esc(labels[data.nivel_adecuacion] || data.nivel_adecuacion)}</span>
    </div>`;
  }

  const frags = data.fragmentos_sospechosos || [];
  if (frags.length) {
    html += `<div class="card"><div class="card-title">Fragmentos sospechosos</div></div>`;
    frags.forEach((f, i) => {
      html += `<div class="fragment">
        <span class="frag-num">${i + 1}</span>
        <div class="frag-body">
          <span class="frag-text">"${esc(f.fragmento)}"</span>
          <span class="frag-reason">↳ ${esc(f.motivo)}</span>
        </div>
      </div>`;
    });
  }

  $('details').innerHTML = html;
  $('results').hidden = false;
}

// ---- Helpers ----
function getExt(name) { return (name.toLowerCase().match(/\.[^.]+$/) || [''])[0]; }
function mimeFor(ext) {
  return { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg' }[ext] || 'application/octet-stream';
}
function fmtSize(b) {
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
  return (b / 1048576).toFixed(1) + ' MB';
}
function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function setLoading(on) {
  $('analyzeBtn').disabled    = on;
  $('analyzeBtn').textContent = on ? 'Analizando…' : 'Analizar documento';
}
function showStatus(msg, type = '') {
  const el = $('status');
  el.textContent = msg;
  el.className   = 'status ' + type;
  el.hidden      = false;
}
function hideStatus() { $('status').hidden = true; }
function showApiKeyBanner() { $('apiKeyBanner').hidden = false; }
function hideApiKeyBanner() { $('apiKeyBanner').hidden = true; }
