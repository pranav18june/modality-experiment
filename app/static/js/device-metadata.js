/**
 * device-metadata.js
 * Captures device metadata and populates hidden fields in the consent form.
 */
document.addEventListener('DOMContentLoaded', () => {
  const ua = navigator.userAgent;
  
  // Basic device type detection
  let deviceType = 'desktop';
  if (/Mobi|Android/i.test(ua)) deviceType = 'mobile';
  if (/Tablet|iPad/i.test(ua)) deviceType = 'tablet';
  
  // Basic OS detection
  let os = 'unknown';
  if (ua.indexOf("Win") !== -1) os = "Windows";
  if (ua.indexOf("Mac") !== -1) os = "MacOS";
  if (ua.indexOf("Linux") !== -1) os = "Linux";
  if (ua.indexOf("Android") !== -1) os = "Android";
  if (ua.indexOf("like Mac") !== -1) os = "iOS";

  // Populating hidden fields if they exist
  const fields = {
    'meta-device': deviceType,
    'meta-os': os,
    'meta-browser': navigator.userAgent.substring(0, 50), // Trucated for space
    'meta-screen': `${window.screen.width}x${window.screen.height} (@${window.devicePixelRatio}x)`,
    'meta-tz': Intl.DateTimeFormat().resolvedOptions().timeZone,
    'meta-lang': navigator.language
  };

  for (const [id, value] of Object.entries(fields)) {
    const el = document.getElementById(id);
    if (el) el.value = value;
  }
});
