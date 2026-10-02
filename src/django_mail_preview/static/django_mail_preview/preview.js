/* Behaviour of the mail preview pages: tabs, width toggle, the drawer on a
   phone, folding preview groups, confirmations and the live list. The links and
   forms work without it; this makes them instant. */
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

  // On a phone the sidebar is a drawer behind the Menu button: the scrim and
  // Escape close it, focus goes in on open and back to the button on close,
  // and Tab stays inside while it is open. Closed, the drawer is inert, so
  // neither the keyboard nor a screen reader lands in it.
  const layout = document.querySelector(".layout");
  const menu = document.querySelector(".menu");
  const scrim = document.querySelector(".scrim");
  const sidebar = document.getElementById("sidebar");
  const narrow = matchMedia("(max-width: 48rem)");
  const focusable = () => sidebar.querySelectorAll("a[href], button:not([hidden]), summary");
  const isOpen = () => layout.classList.contains("nav-open");
  const syncNav = () => {
    sidebar.inert = narrow.matches && !isOpen();
  };
  const setNav = (open) => {
    layout.classList.toggle("nav-open", open);
    menu.setAttribute("aria-expanded", String(open));
    scrim.hidden = !open;
    syncNav();
    (open ? focusable()[0] : menu).focus();
  };
  narrow.addEventListener("change", syncNav);
  syncNav();
  menu.addEventListener("click", () => setNav(!isOpen()));
  scrim.addEventListener("click", () => setNav(false));
  document.addEventListener("keydown", (event) => {
    if (!isOpen()) return;
    if (event.key === "Escape") setNav(false);
    if (event.key !== "Tab") return;
    const items = focusable();
    const edge = event.shiftKey ? items[0] : items[items.length - 1];
    if (document.activeElement !== edge) return;
    event.preventDefault();
    (event.shiftKey ? items[items.length - 1] : items[0]).focus();
  });

  // Preview groups fold. Closed ones are remembered; the group of the open
  // preview never starts closed.
  const GROUPS_KEY = "mail-preview-closed-groups";
  let closed = [];
  try {
    const stored = JSON.parse(localStorage.getItem(GROUPS_KEY));
    if (Array.isArray(stored)) closed = stored;
  } catch {
    // Storage may be unavailable; every group then starts open.
  }
  document.querySelectorAll(".sidebar details[data-group]").forEach((group) => {
    const name = group.dataset.group;
    if (closed.includes(name) && !group.querySelector("[aria-current]")) group.open = false;
    group.addEventListener("toggle", () => {
      closed = closed.filter((other) => other !== name);
      if (!group.open) closed.push(name);
      try {
        localStorage.setItem(GROUPS_KEY, JSON.stringify(closed));
      } catch {
        // See above.
      }
    });
  });

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
