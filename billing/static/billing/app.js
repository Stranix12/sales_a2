/* ============================================================================
   Sales System — JS propio (reemplaza el bundle de Bootstrap)
   Implementa el comportamiento de los mismos atributos data-bs-* que ya traían
   las plantillas: dropdown, modal, collapse (navbar móvil) y dismiss.
   Además: toasts auto-descartables y resaltado de la sección activa del menú.
   ========================================================================== */
(function () {
  'use strict';

  /* ---------------------------- DROPDOWNS -------------------------------- */
  function closeAllDropdowns(except) {
    document.querySelectorAll('.dropdown-menu.show').forEach(function (m) {
      if (m !== except) m.classList.remove('show');
    });
  }
  document.querySelectorAll('[data-bs-toggle="dropdown"]').forEach(function (toggle) {
    toggle.addEventListener('click', function (e) {
      e.preventDefault();
      var menu = toggle.parentElement.querySelector('.dropdown-menu');
      if (!menu) return;
      var isOpen = menu.classList.contains('show');
      closeAllDropdowns(isOpen ? null : menu);
      menu.classList.toggle('show', !isOpen);
    });
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.dropdown')) closeAllDropdowns(null);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAllDropdowns(null);
  });

  /* ------------------------------ MODALS --------------------------------- */
  function openModal(modal) {
    if (!modal || modal.classList.contains('show')) return;
    modal.classList.add('show');
    document.body.classList.add('modal-open');
    var focusable = modal.querySelector('input, select, textarea, button');
    if (focusable) setTimeout(function () { focusable.focus(); }, 60);
  }
  function closeModal(modal) {
    if (!modal || !modal.classList.contains('show')) return;
    modal.classList.remove('show');
    if (!document.querySelector('.modal.show')) document.body.classList.remove('modal-open');
  }
  document.querySelectorAll('[data-bs-toggle="modal"]').forEach(function (trigger) {
    trigger.addEventListener('click', function (e) {
      e.preventDefault();
      var sel = trigger.getAttribute('data-bs-target');
      var modal = sel && document.querySelector(sel);
      openModal(modal);
    });
  });
  // Cerrar al hacer clic en la zona opaca alrededor del diálogo. El contenedor
  // .modal queda por encima del backdrop, así que el clic llega aquí (no al
  // backdrop): cerramos solo si el clic fue directamente sobre el contenedor.
  document.querySelectorAll('.modal').forEach(function (modal) {
    modal.addEventListener('click', function (e) {
      if (e.target === modal) closeModal(modal);
    });
  });
  document.querySelectorAll('[data-bs-dismiss="modal"]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      closeModal(btn.closest('.modal'));
    });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      var open = document.querySelector('.modal.show');
      if (open) closeModal(open);
    }
  });

  /* ------------------------ COLLAPSE (navbar móvil) ---------------------- */
  document.querySelectorAll('[data-bs-toggle="collapse"]').forEach(function (toggle) {
    toggle.addEventListener('click', function (e) {
      e.preventDefault();
      var sel = toggle.getAttribute('data-bs-target');
      var target = sel && document.querySelector(sel);
      if (target) target.classList.toggle('show');
    });
  });

  /* --------------------------- DISMISS (alertas) ------------------------- */
  document.querySelectorAll('[data-bs-dismiss="alert"]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var alert = btn.closest('.alert');
      if (alert) alert.remove();
    });
  });

  /* ------------------------------ TOASTS --------------------------------- */
  function dismissToast(toast) {
    if (toast.classList.contains('is-leaving')) return;
    toast.classList.add('is-leaving');
    toast.addEventListener('animationend', function (ev) {
      if (ev.animationName === 'toastOut') toast.remove();
    });
  }
  document.querySelectorAll('.app-toast').forEach(function (toast) {
    var bar = toast.querySelector('.app-toast-bar');
    var close = toast.querySelector('.app-toast-close');
    if (bar) bar.addEventListener('animationend', function () { dismissToast(toast); });
    if (close) close.addEventListener('click', function () { dismissToast(toast); });
  });

  /* --------------------- CONTEO ANIMADO (KPIs del dash) ------------------ */
  document.querySelectorAll('.js-count').forEach(function (el) {
    var target = parseFloat(el.getAttribute('data-count') || '0');
    var money = el.getAttribute('data-money') === '1';
    var dur = 900, start = null;
    function fmt(v) {
      if (money) return '$' + v.toLocaleString('es-EC', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      return Math.round(v).toLocaleString('es-EC');
    }
    function step(ts) {
      if (!start) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(target * eased);
      if (p < 1) requestAnimationFrame(step); else el.textContent = fmt(target);
    }
    requestAnimationFrame(step);
  });

  /* ---------------------- RESALTADO DE SECCIÓN ACTIVA -------------------- */
  var path = location.pathname;
  var best = null;
  document.querySelectorAll('.app-navbar .nav-link[href], .app-navbar .dropdown-item[href]').forEach(function (a) {
    var href = a.getAttribute('href');
    if (!href || href === '#') return;
    if (href === '/') { if (path === '/') best = a; return; }
    if (path.indexOf(href) === 0 && (!best || href.length > best.getAttribute('href').length)) best = a;
  });
  if (best) {
    best.classList.add('active');
    var dd = best.closest('.dropdown');
    if (dd) {
      var toggle = dd.querySelector('.nav-link.dropdown-toggle');
      if (toggle) toggle.classList.add('active');
    }
  }
})();
