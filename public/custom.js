// Fuerza el color #444444 en toda la caja de escritura de Chainlit
(function aplicarEstilosCaja() {
  function pintarCaja() {
    // Buscar el textarea o contenteditable
    const inputs = document.querySelectorAll(
      'textarea, [contenteditable="true"], input[type="text"]'
    );

    inputs.forEach(function (el) {
      // Subir por los ancestros y pintar todos hasta llegar a <main> o <body>
      let nodo = el;
      for (let i = 0; i < 8; i++) {
        if (!nodo || nodo === document.body || nodo.tagName === 'MAIN') break;
        nodo.style.setProperty('background-color', '#444444', 'important');
        nodo.style.setProperty('border-color', '#555555', 'important');
        nodo = nodo.parentElement;
      }

      // El propio input
      el.style.setProperty('background-color', '#444444', 'important');
      el.style.setProperty('color', '#ffffff', 'important');
    });
  }

  // Ejecutar al cargar y cada vez que Chainlit renderice algo nuevo
  pintarCaja();
  const observer = new MutationObserver(pintarCaja);
  observer.observe(document.body, { childList: true, subtree: true });
})();
