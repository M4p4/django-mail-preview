/* The stored colour scheme goes on <html> before anything paints, so a page
   chosen dark never flashes light. Loaded in <head> without defer on purpose:
   it is tiny, and blocking is what prevents the flash. The button that stores
   the choice lives in preview.js; without a choice the page follows the
   system. */
(() => {
  try {
    const theme = localStorage.getItem("mail-preview-theme");
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  } catch {
    // Storage may be unavailable; the page then follows the system.
  }
})();
