/* Behaviour of the mail preview pages: tabs, width toggle, confirmations and the
   live list. The links and forms work without it; this makes them instant. */
(() => {
  document.documentElement.classList.add("js");

  // Tabs switch in place when their pane is on the page. The Source pane is
  // only rendered when it was asked for, so its link navigates instead.
  const tabs = document.querySelectorAll(".tabs a[data-tab]");
  const panes = document.querySelectorAll(".tab[data-tab]");
  tabs.forEach((link) => {
    link.addEventListener("click", (event) => {
      const target = document.querySelector(`.tab[data-tab="${link.dataset.tab}"]`);
      if (!target) return;
      event.preventDefault();
      panes.forEach((pane) => (pane.hidden = pane !== target));
      tabs.forEach((other) => other.removeAttribute("aria-current"));
      link.setAttribute("aria-current", "page");
      history.replaceState(null, "", link.href);
    });
  });

  // The frame's width: 375, 600 or full, remembered across pages.
  const frame = document.querySelector('.tab[data-tab="html"]');
  const widths = document.querySelectorAll(".width button[data-width]");
  const WIDTH_KEY = "mail-preview-width";
  const setWidth = (width) => {
    frame.dataset.width = width;
    widths.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.width === width));
    });
    try {
      localStorage.setItem(WIDTH_KEY, width);
    } catch {
      // Storage may be unavailable; the choice then lasts for this page only.
    }
  };
  if (frame && widths.length) {
    let saved = null;
    try {
      saved = localStorage.getItem(WIDTH_KEY);
    } catch {
      // See above.
    }
    setWidth(document.querySelector(`.width [data-width="${saved}"]`) ? saved : "full");
    widths.forEach((button) => {
      button.addEventListener("click", () => setWidth(button.dataset.width));
    });
  }

  // Delete and Clear all ask first.
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  // The live list: poll for new mail while the tab is visible. The start page
  // reloads; an open message shows a badge instead, so it isn't pulled away.
  const body = document.body;
  const badge = document.querySelector(".badge");
  let timer = null;
  const poll = () => {
    fetch(body.dataset.latestUrl, { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!data) return;
        const unchanged =
          String(data.count) === body.dataset.count &&
          (data.latest || "") === body.dataset.latest;
        if (unchanged) return;
        if (body.dataset.page === "index") location.reload();
        else if (badge) badge.hidden = false;
      })
      .catch(() => {
        // The server is restarting; the next poll will find it.
      });
  };
  const schedule = () => {
    clearInterval(timer);
    timer = document.visibilityState === "visible" ? setInterval(poll, 3000) : null;
  };
  if (badge) badge.addEventListener("click", () => location.reload());
  document.addEventListener("visibilitychange", schedule);
  schedule();
})();
