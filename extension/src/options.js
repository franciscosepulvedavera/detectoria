const $ = id => document.getElementById(id);

// ---- Cargar configuración guardada ----
(async () => {
  const { groqApiKey, groqModel, backendUrl } = await chrome.storage.sync.get({
    groqApiKey: '',
    groqModel:  'llama-3.3-70b-versatile',
    backendUrl: ''
  });
  $('groqApiKey').value = groqApiKey;
  $('groqModel').value  = groqModel;
  $('backendUrl').value = backendUrl;
})();

// ---- Guardar configuración ----
$('saveBtn').addEventListener('click', async () => {
  const groqApiKey = $('groqApiKey').value.trim();
  const groqModel  = $('groqModel').value;
  const backendUrl = $('backendUrl').value.trim().replace(/\/$/, ''); // sin trailing slash

  await chrome.storage.sync.set({ groqApiKey, groqModel, backendUrl });

  const msg = $('savedMsg');
  msg.style.display = 'block';
  setTimeout(() => { msg.style.display = 'none'; }, 2500);
});
