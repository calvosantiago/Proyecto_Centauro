(() => {
  const BRAND_NAME = "Centauro";
  const TAB_TITLE = "Centauro | Asistente IA";

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
  };

  const runOnce = () => {
    applyBrand();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", runOnce, { once: true });
  } else {
    runOnce();
  }
})();
