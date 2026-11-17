(function () {
  'use strict';

  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));

  /* ---------------------------------------------------------------------
     Sidebar (mobile / tablet)
     --------------------------------------------------------------------- */
  const sidebar = $('[data-staff-sidebar]');
  const scrim = $('.staff-scrim');
  const openButtons = $$('[data-staff-open]');
  const closeButtons = $$('[data-staff-close]');
  const menuToggle = openButtons[0];
  const desktopQuery = window.matchMedia('(min-width: 1025px)');

  function focusables(container) {
    return $$(
      'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      container
    ).filter((el) => el.offsetWidth > 0 && el.offsetHeight > 0);
  }

  function isSidebarOpen() {
    return sidebar && sidebar.classList.contains('is-open');
  }

  function setSidebar(open, restoreFocus) {
    if (!sidebar) return;
    sidebar.classList.toggle('is-open', open);
    if (scrim) scrim.classList.toggle('is-open', open);
    document.body.classList.toggle('staff-no-scroll', open);

    openButtons.forEach((button) => {
      if (button.hasAttribute('aria-expanded')) {
        button.setAttribute('aria-expanded', String(open));
      }
    });

    if (open) {
      const firstLink = focusables(sidebar)[0];
      if (firstLink) {
        window.setTimeout(() => firstLink.focus(), 60);
      }
    } else if (restoreFocus && menuToggle) {
      menuToggle.focus();
    }
  }

  openButtons.forEach((button) => {
    button.addEventListener('click', () => setSidebar(true, false));
  });

  closeButtons.forEach((button) => {
    button.addEventListener('click', () => setSidebar(false, true));
  });

  document.addEventListener('keydown', (event) => {
    if (!isSidebarOpen()) return;

    if (event.key === 'Escape') {
      event.preventDefault();
      setSidebar(false, true);
      return;
    }

    if (event.key === 'Tab' && sidebar) {
      const items = focusables(sidebar);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  function handleDesktopChange(event) {
    if (event.matches) {
      setSidebar(false, false);
    }
  }

  if (desktopQuery.addEventListener) {
    desktopQuery.addEventListener('change', handleDesktopChange);
  } else if (desktopQuery.addListener) {
    desktopQuery.addListener(handleDesktopChange);
  }

  /* ---------------------------------------------------------------------
     Destructive action confirmation
     --------------------------------------------------------------------- */
  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-confirm]');
    if (!trigger) return;
    if (trigger.dataset.confirmed === 'true') {
      delete trigger.dataset.confirmed;
      return;
    }
    const message = trigger.getAttribute('data-confirm') || 'Are you sure?';
    if (!window.confirm(message)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    trigger.dataset.confirmed = 'true';
  }, true);

  /* ---------------------------------------------------------------------
     Flash messages
     --------------------------------------------------------------------- */
  $$('[data-dismiss-flash]').forEach((button) => {
    button.addEventListener('click', () => {
      const flash = button.closest('.staff-flash');
      if (!flash) return;
      flash.style.transition = 'opacity 0.18s ease, transform 0.18s ease';
      flash.style.opacity = '0';
      flash.style.transform = 'translateY(-4px)';
      window.setTimeout(() => flash.remove(), 200);
    });
  });

  $$('.staff-flash').forEach((flash) => {
    window.setTimeout(() => {
      if (!flash.isConnected) return;
      flash.style.transition = 'opacity 0.25s ease, transform 0.25s ease';
      flash.style.opacity = '0';
      flash.style.transform = 'translateY(-4px)';
      window.setTimeout(() => flash.remove(), 260);
    }, 9000);
  });

  /* ---------------------------------------------------------------------
     Password reveal
     --------------------------------------------------------------------- */
  $$('[data-password-toggle]').forEach((button) => {
    const targetSelector = button.getAttribute('data-password-toggle');
    const input = targetSelector ? $(targetSelector) : null;
    if (!input) return;

    button.addEventListener('click', () => {
      const showing = input.getAttribute('type') === 'text';
      input.setAttribute('type', showing ? 'password' : 'text');
      button.textContent = showing ? 'Show' : 'Hide';
      button.setAttribute('aria-pressed', String(!showing));
      input.focus();
    });
  });

  /* ---------------------------------------------------------------------
     Confirm before leaving an edited staff form
     --------------------------------------------------------------------- */
  $$('.staff-form-stack').forEach((form) => {
    let dirty = false;
    const markDirty = () => {
      dirty = true;
    };

    form.addEventListener('input', markDirty, { passive: true });
    form.addEventListener('change', markDirty, { passive: true });

    form.addEventListener('submit', () => {
      dirty = false;
    });

    window.addEventListener('beforeunload', (event) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = '';
    });
  });

  /* ---------------------------------------------------------------------
     Keep status select and save button reachable on tall pages
     --------------------------------------------------------------------- */
  const stickyCard = $('.staff-sticky-card');
  if (stickyCard && window.matchMedia('(max-width: 1180px)').matches) {
    stickyCard.classList.remove('staff-sticky-card');
  }

  /* ---------------------------------------------------------------------
     Copy the reorder list to the clipboard
     --------------------------------------------------------------------- */
  $$('[data-copy-target]').forEach((button) => {
    const original = button.innerHTML;
    button.addEventListener('click', async () => {
      const target = document.getElementById(button.getAttribute('data-copy-target'));
      if (!target) return;
      const text = target.textContent.trim();
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
        } else {
          const helper = document.createElement('textarea');
          helper.value = text;
          helper.setAttribute('readonly', '');
          helper.style.position = 'fixed';
          helper.style.opacity = '0';
          document.body.appendChild(helper);
          helper.select();
          document.execCommand('copy');
          helper.remove();
        }
        button.textContent = 'Copied';
        window.setTimeout(() => {
          button.innerHTML = original;
        }, 1800);
      } catch (error) {
        button.textContent = 'Copy failed';
        window.setTimeout(() => {
          button.innerHTML = original;
        }, 2200);
      }
    });
  });
})();
