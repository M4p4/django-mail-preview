/* Behaviour of the mail preview pages: light or dark, tabs, the frame's width,
   the drawer on a phone, folding preview groups, confirmations, copy buttons,
   the keyboard and the live list. The links and forms work without it; this
   makes them instant. */
(() => {
  document.documentElement.classList.add("js");

  // Light or dark: the button beside the wordmark flips the scheme, and the
  // choice is kept per browser. theme.js applied it before the first paint;
  // without a stored choice the page follows the system. The glyph and the
  // label name what a click gives, in every copy of the button.
  const THEME_KEY = "mail-preview-theme";
  const prefersDark = matchMedia("(prefers-color-scheme: dark)");
  const themeButtons = document.querySelectorAll(".theme");
  const theme = () =>
    document.documentElement.dataset.theme || (prefersDark.matches ? "dark" : "light");
  const syncTheme = () => {
    const next = theme() === "dark" ? "light" : "dark";
    themeButtons.forEach((button) => {
      button.setAttribute("aria-label", `Switch to ${next} mode`);
      button.title = `Switch to ${next} mode`;
      button.querySelector(".sun").toggleAttribute("hidden", next !== "light");
      button.querySelector(".moon").toggleAttribute("hidden", next !== "dark");
    });
  };
  const setTheme = (value) => {
    document.documentElement.dataset.theme = value;
    syncTheme();
  };
  themeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const next = theme() === "dark" ? "light" : "dark";
      setTheme(next);
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch {
        // Storage may be unavailable; the choice then lasts for this page only.
      }
    });
  });
  prefersDark.addEventListener("change", syncTheme);
  addEventListener("storage", (event) => {
    const value = event.newValue;
    if (event.key === THEME_KEY && (value === "light" || value === "dark")) setTheme(value);
  });
  syncTheme();

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

  // The frame's width: a preset, a number typed in, or full, remembered across
  // pages. The field doubles as the readout and always shows what the frame
  // measures, so "full" and a width the pane cannot fit read as what they are.
  const frame = document.querySelector('.tab[data-tab="html"] iframe');
  const presets = document.querySelectorAll(".width button[data-width]");
  const field = document.querySelector(".width input");
  const WIDTH_KEY = "mail-preview-width";
  let width = "full";
  const clamp = (n) => Math.min(Math.max(n, Number(field.min)), Number(field.max));
  const readout = () => {
    if (document.activeElement !== field) field.value = frame.clientWidth;
  };
  const setWidth = (next) => {
    width = next;
    frame.style.width = next === "full" ? "" : `${next}px`;
    presets.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.width === next));
    });
    readout();
    try {
      localStorage.setItem(WIDTH_KEY, next);
    } catch {
      // Storage may be unavailable; the choice then lasts for this page only.
    }
  };
  if (frame) {
    let saved = NaN;
    try {
      saved = Number(localStorage.getItem(WIDTH_KEY));
    } catch {
      // See above.
    }
    setWidth(Number.isInteger(saved) && saved > 0 ? String(clamp(saved)) : "full");
    presets.forEach((button) => {
      button.addEventListener("click", () => setWidth(button.dataset.width));
    });
    field.addEventListener("change", () => {
      const typed = Math.round(field.valueAsNumber);
      field.blur();
      setWidth(Number.isNaN(typed) ? "full" : String(clamp(typed)));
    });
    new ResizeObserver(readout).observe(frame);
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

  // The open message or preview stays in view in the sidebar: each page load
  // scrolls the list it is in, so walking the mail with the header's links or
  // with j and k keeps the selection in the middle of the list. Only the lists
  // scroll, never the window.
  for (let item = document.querySelector('.sidebar li[aria-current="page"]'); item; ) {
    let box = item.parentElement;
    while (box && !/auto|scroll/.test(getComputedStyle(box).overflowY)) box = box.parentElement;
    if (!box) break;
    const offset = item.getBoundingClientRect().top - box.getBoundingClientRect().top;
    if (offset < 0 || offset + item.offsetHeight > box.clientHeight) {
      box.scrollTop += offset - (box.clientHeight - item.offsetHeight) / 2;
    }
    item = box;
  }

  // Delete and Clear all ask first.
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  // Copy on the Plain text and Source tabs. Without the clipboard API (a plain
  // http:// origin other than localhost) the text is selected and copied the
  // old way, or stays selected for the user to copy.
  document.querySelectorAll(".copy").forEach((button) => {
    const pre = button.parentElement.querySelector("pre");
    const label = button.querySelector("span");
    const original = label.textContent;
    let revert = null;
    const copy = async () => {
      try {
        await navigator.clipboard.writeText(pre.textContent);
        return "Copied";
      } catch {
        getSelection().selectAllChildren(pre);
        return document.execCommand("copy") ? "Copied" : "Selected";
      }
    };
    button.addEventListener("click", async () => {
      label.textContent = await copy();
      clearTimeout(revert);
      revert = setTimeout(() => (label.textContent = original), 1500);
    });
  });

  // j and k walk the captured mail. On a message page they open the older and
  // the newer message through the header's links; on the start page they move
  // focus down and up the inbox table, where Enter opens the focused row. Keys
  // typed into a field, and shortcuts with a modifier, are left alone.
  document.addEventListener("keydown", (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key !== "j" && event.key !== "k") return;
    if (event.target.closest("input, textarea, select, [contenteditable]")) return;
    const down = event.key === "j";
    const link = document.querySelector(down ? '.nav a[rel="next"]' : '.nav a[rel="prev"]');
    if (link) {
      location.assign(link.href);
      return;
    }
    const rows = [...document.querySelectorAll(".inbox tbody a")];
    const at = rows.indexOf(document.activeElement);
    const next = at < 0 ? rows[down ? 0 : rows.length - 1] : rows[at + (down ? 1 : -1)];
    if (next) next.focus();
  });

  // New mail since the page loaded: the count goes in the title and onto the
  // favicon, the wordmark's tile with a red badge drawn on a canvas.
  const icon = document.querySelector('link[rel="icon"]');
  const title = document.title;
  const favicon = (count) => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 64;
    const ctx = canvas.getContext("2d");
    ctx.scale(2, 2);
    ctx.fillStyle = "#0f766e";
    ctx.beginPath();
    ctx.roundRect(0, 0, 32, 32, 8);
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 3.5;
    ctx.lineCap = ctx.lineJoin = "round";
    ctx.stroke(new Path2D("M8 23V9l8 9 8-9v14"));
    ctx.beginPath();
    ctx.arc(22, 10, 10, 0, 2 * Math.PI);
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "#dc2626";
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.font = "bold 13px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(count > 9 ? "9+" : String(count), 22, 10.5);
    return canvas.toDataURL("image/png");
  };
  const announce = (count) => {
    document.title = `(${count}) ${title}`;
    try {
      icon.href = favicon(count);
    } catch {
      // No canvas, or no icon link: the title still carries the count.
    }
  };

  // The live list: poll for new mail while the tab is visible. The start page
  // reloads; an open message shows a badge and the count instead, so it isn't
  // pulled away. The count is what arrived since this page loaded.
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
        if (body.dataset.page === "index") {
          location.reload();
          return;
        }
        if (badge) badge.hidden = false;
        const fresh = data.count - Number(body.dataset.count);
        if (fresh > 0) announce(fresh);
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
