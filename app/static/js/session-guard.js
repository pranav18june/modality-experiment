/**
 * session-guard.js
 * Detects idle timeout (12 minutes) and shows a warning banner.
 */
document.addEventListener('DOMContentLoaded', () => {
  const IDLE_TIMEOUT_MS = 12 * 60 * 1000; // 12 minutes
  const WARNING_MS = 3 * 60 * 1000;       // show warning 3 mins before
  
  let idleTimer;
  let warningTimer;
  
  const banner = document.getElementById('session-banner');
  const extendBtn = document.getElementById('extend-session-btn');
  
  function resetTimers() {
    clearTimeout(idleTimer);
    clearTimeout(warningTimer);
    if (banner) banner.classList.remove('visible');
    
    // Set timer to show warning
    warningTimer = setTimeout(() => {
      if (banner) banner.classList.add('visible');
    }, IDLE_TIMEOUT_MS - WARNING_MS);
    
    // Set timer for actual idle timeout
    idleTimer = setTimeout(() => {
      if (banner) banner.classList.remove('visible');
      alert("Your session has timed out due to inactivity. Please refresh the page.");
    }, IDLE_TIMEOUT_MS);
  }
  
  // Listen for activity
  ['mousemove', 'keydown', 'scroll', 'touchstart', 'click'].forEach(evt => {
    window.addEventListener(evt, resetTimers, { passive: true });
  });
  
  if (extendBtn) {
    extendBtn.addEventListener('click', (e) => {
      e.preventDefault();
      resetTimers();
      // small visual feedback
      const origText = extendBtn.innerText;
      extendBtn.innerText = "Extended!";
      setTimeout(() => extendBtn.innerText = origText, 2000);
    });
  }
  
  // Start
  resetTimers();
});
