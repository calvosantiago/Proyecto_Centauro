(() => {
  const BRAND_NAME = "Centauro";
  const TAB_TITLE = "Centauro | Asistente IA";
  const LOGO_SRC = "/public/obs-logo.png";

  const ensureHeaderLogo = () => {
    // Buscar el header principal (barra superior de ~60px)
    const header = [...document.querySelectorAll("*")].find((el) => {
      const r = el.getBoundingClientRect();
      return r.top < 5 && r.height > 40 && r.height < 80 && r.width > 500;
    });

    if (!header) return;
    if (header.querySelector(".centauro-brand-logo")) return;

    // El div central del header está absolutamente posicionado y vacío
    const center = [...header.children].find((c) =>
      c.className.includes("absolute")
    );
    const target = center || header;

    const logo = document.createElement("img");
    logo.className = "centauro-brand-logo";
    logo.src = LOGO_SRC;
    logo.alt = "OBS Logo";
    logo.loading = "eager";
    target.appendChild(logo);
  };

  const applyBrand = () => {
    if (document.title !== TAB_TITLE) {
      document.title = TAB_TITLE;
    }

    const possibleTitles = document.querySelectorAll("h1, h2, [data-testid='chat-title']");
    possibleTitles.forEach((node) => {
      if (node.textContent && node.textContent.trim() === "Assistant") {
        node.textContent = BRAND_NAME;
      }
    });

    ensureHeaderLogo();
  };

  const runOnce = () => {
    applyBrand();

    const observer = new MutationObserver(() => applyBrand());
    observer.observe(document.body, { childList: true, subtree: true });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", runOnce, { once: true });
  } else {
    runOnce();
  }
})();
