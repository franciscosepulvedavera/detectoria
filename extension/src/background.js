// ============================================================
// DetectorIA — background.js (Service Worker)
// ============================================================

// Al instalar la extensión por primera vez, abrir opciones para
// que el usuario configure su API Key de Groq.
chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === chrome.runtime.OnInstalledReason.INSTALL) {
    chrome.runtime.openOptionsPage();
  }
});
