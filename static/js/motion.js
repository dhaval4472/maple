/*
  Maple Leaf — motion layer
  ----------------------------------------------------------------------
  A dependency-free interaction layer that adds the workshop's
  "instrumented" feel: section rail, scroll instruments, stagger
  reveals, coverage hotspots, photo inspection, magnetic CTAs and a
  claim-completion moment.

  Everything is progressive. If this file fails, the site still works;
  if the visitor prefers reduced motion, nothing moves on its own.
*/
(function () {
  'use strict';

  const doc = document.documentElement;
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));

  doc.classList.add('motion-ready');

  const scrollSubs = [];
  const refreshSubs = [];
  let scrollQueued = false;
  let refreshQueued = false;
  let viewportHeight = window.innerHeight;
  let scrollMax = 0;

  function measureViewport() {
    viewportHeight = window.innerHeight;
    scrollMax = Math.max(0, document.documentElement.scrollHeight - viewportHeight);
  }

  function runScrollSubs() {
    scrollQueued = false;
    for (let i = 0; i < scrollSubs.length; i += 1) {
      try {
        scrollSubs[i]();
      } catch (error) {
        /* One instrument failing must not stop the rest. */
      }
    }
  }

  function onScroll() {
    if (scrollQueued) return;
    scrollQueued = true;
    window.requestAnimationFrame(runScrollSubs);
  }

  /* Geometry is measured in one batch on resize rather than on every scroll
     frame. Reading layout inside the scroll loop forces the browser to flush
     style and layout repeatedly, which is the main cause of judder. */
  function refreshGeometry() {
    refreshQueued = false;
    measureViewport();
    for (let i = 0; i < refreshSubs.length; i += 1) {
      try {
        refreshSubs[i](viewportHeight);
      } catch (error) {
        /* Keep the remaining instruments alive. */
      }
    }
    runScrollSubs();
  }

  function queueRefresh() {
    if (refreshQueued) return;
    refreshQueued = true;
    window.requestAnimationFrame(refreshGeometry);
  }

  function addScroll(fn) {
    scrollSubs.push(fn);
  }

  function addRefresh(fn) {
    refreshSubs.push(fn);
    fn(viewportHeight);
  }

  measureViewport();
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', queueRefresh, { passive: true });
  window.addEventListener('load', queueRefresh);
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(queueRefresh).catch(() => {});
  }
  if ('ResizeObserver' in window) {
    try {
      const layoutObserver = new ResizeObserver(queueRefresh);
      layoutObserver.observe(document.body);
    } catch (error) {
      /* ResizeObserver is an optimisation, not a requirement. */
    }
  }

  /* ------------------------------------------------------------------
     1. Section rail — a quiet index down the right edge
  ------------------------------------------------------------------ */
  try {
    const rail = $('[data-section-rail]');
    const sections = $$('[data-rail-label]');
    if (rail && sections.length > 1) {
      const links = [];

      sections.forEach((section, index) => {
        if (!section.id) section.id = 'section-' + (index + 1);
        const label = section.getAttribute('data-rail-label') || section.id;

        const link = document.createElement('a');
        link.className = 'section-rail-link';
        link.href = '#' + section.id;
        link.setAttribute('aria-label', 'Jump to ' + label);
        link.innerHTML =
          '<span class="section-rail-mark" aria-hidden="true"></span>' +
          '<span class="section-rail-text">' + label + '</span>';
        rail.appendChild(link);
        links.push({ link, section });
      });

      function setRailActive() {
        const anchor = window.scrollY + viewportHeight * 0.38;
        let currentIndex = -1;
        for (let i = 0; i < railRanges.length; i += 1) {
          const range = railRanges[i];
          if (range.top <= anchor && range.bottom > anchor) {
            currentIndex = i;
            break;
          }
        }
        if (currentIndex === -1) {
          currentIndex = railRanges.findIndex((range) => range.bottom > anchor);
          if (currentIndex === -1) currentIndex = links.length - 1;
        }
        links.forEach((item, index) => {
          const active = index === currentIndex;
          if (item.link.classList.contains('is-active') !== active) {
            item.link.classList.toggle('is-active', active);
          }
          if (active) item.link.setAttribute('aria-current', 'true');
          else item.link.removeAttribute('aria-current');
        });
      }

      let railRanges = [];
      addRefresh(() => {
        railRanges = links.map((item) => {
          const rect = item.section.getBoundingClientRect();
          const top = rect.top + window.scrollY;
          return { top, bottom: top + rect.height };
        });
      });
      addScroll(setRailActive);
      setRailActive();
      rail.classList.add('is-ready');
    }
  } catch (error) {
    /* Section rail is optional. */
  }

  /* ------------------------------------------------------------------
     2. Scroll instrument — progress ring + back to top
  ------------------------------------------------------------------ */
  try {
    const topButton = $('[data-scroll-top]');
    const ring = $('[data-scroll-top-ring]');
    if (topButton) {
      let lastRingOffset = null;
      function updateScrollInstrument() {
        const value = scrollMax > 0 ? Math.min(1, Math.max(0, window.scrollY / scrollMax)) : 0;
        if (ring) {
          const offset = (100 - value * 100).toFixed(1);
          if (offset !== lastRingOffset) {
            lastRingOffset = offset;
            ring.style.strokeDashoffset = offset;
          }
        }
        const visible = window.scrollY > viewportHeight * 0.55;
        if (topButton.classList.contains('is-visible') !== visible) {
          topButton.classList.toggle('is-visible', visible);
        }
      }

      topButton.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
      });

      addScroll(updateScrollInstrument);
      addRefresh(updateScrollInstrument);
      updateScrollInstrument();
    }
  } catch (error) {
    /* Scroll instrument is optional. */
  }

  /* ------------------------------------------------------------------
     3. Stagger reveal groups
  ------------------------------------------------------------------ */
  try {
    const groups = $$('[data-stagger]');
    if (groups.length) {
      groups.forEach((group) => {
        const kids = Array.from(group.children).filter((el) => el.nodeType === 1);
        kids.forEach((el, index) => {
          el.style.setProperty('--stagger-i', Math.min(index, 12));
        });
        group.classList.add('stagger-ready');
      });

      if (reduceMotion || !('IntersectionObserver' in window)) {
        groups.forEach((group) => group.classList.add('is-revealed'));
      } else {
        const staggerObserver = new IntersectionObserver((entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            entry.target.classList.add('is-revealed');
            staggerObserver.unobserve(entry.target);
          });
        }, { threshold: 0.01, rootMargin: '0px 0px 12% 0px' });

        groups.forEach((group) => {
          const rect = group.getBoundingClientRect();
          if (rect.top < window.innerHeight * 0.98 && rect.bottom > 0) {
            group.classList.add('is-revealed');
          } else {
            staggerObserver.observe(group);
          }
        });
      }
    }
  } catch (error) {
    $$('[data-stagger]').forEach((group) => group.classList.add('is-revealed'));
  }

  /* ------------------------------------------------------------------
     4. Pointer spotlight on workshop cards
  ------------------------------------------------------------------ */
  if (finePointer && !reduceMotion) {
    try {
      const hosts = $$('.service-card, .triage-card, .contact-card, .form-card, .review-card, .rail-card, .rail-dark, .info-block, [data-spotlight]');
      hosts.forEach((host) => {
        if (host.classList.contains('spotlight-host')) return;
        host.classList.add('spotlight-host');
        const glow = document.createElement('span');
        glow.className = 'spotlight-glow';
        glow.setAttribute('aria-hidden', 'true');
        host.appendChild(glow);

        let frame = 0;
        let px = 50;
        let py = 50;
        host.addEventListener('pointerenter', () => {
          host.classList.add('is-spotlit');
          if (!frame) frame = window.requestAnimationFrame(paint);
        });
        host.addEventListener('pointermove', (event) => {
          const rect = host.getBoundingClientRect();
          px = ((event.clientX - rect.left) / rect.width) * 100;
          py = ((event.clientY - rect.top) / rect.height) * 100;
          if (!frame) frame = window.requestAnimationFrame(paint);
        });
        host.addEventListener('pointerleave', () => {
          host.classList.remove('is-spotlit');
        });

        function paint() {
          frame = 0;
          host.style.setProperty('--spot-x', px.toFixed(1) + '%');
          host.style.setProperty('--spot-y', py.toFixed(1) + '%');
        }
      });
    } catch (error) {
      /* Decorative only. */
    }
  }

  /* ------------------------------------------------------------------
     5. Photo inspection cursor
  ------------------------------------------------------------------ */
  if (finePointer && !reduceMotion) {
    try {
      const photoSelectors = '.photo-reveal, .process-photo, .floor-photo, [data-inspect]';
      const photos = $$(photoSelectors);
      photos.forEach((photo) => {
        const image = photo.querySelector('img');
        if (!image || photo.classList.contains('inspect-ready')) return;
        photo.classList.add('inspect-ready');

        const cursor = document.createElement('span');
        cursor.className = 'inspect-cursor';
        cursor.setAttribute('aria-hidden', 'true');
        cursor.innerHTML =
          '<span class="inspect-cursor-h"></span>' +
          '<span class="inspect-cursor-v"></span>' +
          '<span class="inspect-cursor-ring"></span>' +
          '<span class="inspect-cursor-read">X 00 · Y 00</span>';
        photo.appendChild(cursor);
        const read = $('.inspect-cursor-read', cursor);

        let frame = 0;
        let x = 50;
        let y = 50;
        photo.addEventListener('pointerenter', () => photo.classList.add('is-inspecting'));
        photo.addEventListener('pointerleave', () => photo.classList.remove('is-inspecting'));
        photo.addEventListener('pointermove', (event) => {
          const rect = photo.getBoundingClientRect();
          x = Math.min(100, Math.max(0, ((event.clientX - rect.left) / rect.width) * 100));
          y = Math.min(100, Math.max(0, ((event.clientY - rect.top) / rect.height) * 100));
          if (!frame) frame = window.requestAnimationFrame(paint);
        });

        function paint() {
          frame = 0;
          cursor.style.setProperty('--ix', x.toFixed(2) + '%');
          cursor.style.setProperty('--iy', y.toFixed(2) + '%');
          if (read) {
            read.textContent =
              'X ' + String(Math.round(x)).padStart(2, '0') +
              ' · Y ' + String(Math.round(y)).padStart(2, '0');
          }
        }
      });
    } catch (error) {
      /* Decorative only. */
    }
  }

  /* ------------------------------------------------------------------
     6. Gallery tilt + glare
  ------------------------------------------------------------------ */
  if (finePointer && !reduceMotion) {
    try {
      $$('.gallery-item').forEach((item) => {
        if (item.classList.contains('tilt-ready')) return;
        item.classList.add('tilt-ready');
        let frame = 0;
        let rx = 0;
        let ry = 0;
        let gx = 50;
        let gy = 50;

        item.addEventListener('pointerenter', () => item.classList.add('is-tilting'));
        item.addEventListener('pointermove', (event) => {
          const rect = item.getBoundingClientRect();
          const nx = (event.clientX - rect.left) / rect.width;
          const ny = (event.clientY - rect.top) / rect.height;
          gx = nx * 100;
          gy = ny * 100;
          ry = (nx - 0.5) * 5.5;
          rx = (0.5 - ny) * 4.5;
          if (!frame) frame = window.requestAnimationFrame(paint);
        });
        item.addEventListener('pointerleave', () => {
          item.classList.remove('is-tilting');
          rx = 0;
          ry = 0;
          if (!frame) frame = window.requestAnimationFrame(paint);
        });

        function paint() {
          frame = 0;
          item.style.setProperty('--tilt-x', rx.toFixed(2) + 'deg');
          item.style.setProperty('--tilt-y', ry.toFixed(2) + 'deg');
          item.style.setProperty('--glare-x', gx.toFixed(1) + '%');
          item.style.setProperty('--glare-y', gy.toFixed(1) + '%');
        }
      });
    } catch (error) {
      /* Decorative only. */
    }
  }

  /* ------------------------------------------------------------------
     7. Magnetic buttons
  ------------------------------------------------------------------ */
  if (finePointer && !reduceMotion) {
    try {
      $$('[data-magnetic]').forEach((el) => {
        if (el.classList.contains('magnetic-ready')) return;
        el.classList.add('magnetic-ready');
        const strength = parseFloat(el.getAttribute('data-magnetic')) || 5;
        let frame = 0;
        let tx = 0;
        let ty = 0;

        el.addEventListener('pointermove', (event) => {
          const rect = el.getBoundingClientRect();
          const nx = (event.clientX - (rect.left + rect.width / 2)) / (rect.width / 2);
          const ny = (event.clientY - (rect.top + rect.height / 2)) / (rect.height / 2);
          tx = Math.max(-1, Math.min(1, nx)) * strength;
          ty = Math.max(-1, Math.min(1, ny)) * strength;
          el.classList.add('is-magnetic');
          if (!frame) frame = window.requestAnimationFrame(paint);
        });
        el.addEventListener('pointerleave', () => {
          tx = 0;
          ty = 0;
          if (!frame) frame = window.requestAnimationFrame(paint);
        });
        el.addEventListener('blur', () => {
          tx = 0;
          ty = 0;
          if (!frame) frame = window.requestAnimationFrame(paint);
        });

        function paint() {
          frame = 0;
          el.style.setProperty('--mag-x', tx.toFixed(2) + 'px');
          el.style.setProperty('--mag-y', ty.toFixed(2) + 'px');
          if (!tx && !ty) el.classList.remove('is-magnetic');
        }
      });
    } catch (error) {
      /* Decorative only. */
    }
  }

  /* ------------------------------------------------------------------
     8. CTA band glow that follows the pointer
  ------------------------------------------------------------------ */
  if (finePointer && !reduceMotion) {
    try {
      $$('.cta-band, .cta-dark').forEach((band) => {
        if (band.classList.contains('glow-ready')) return;
        band.classList.add('glow-ready');
        const glow = document.createElement('span');
        glow.className = 'cta-glow';
        glow.setAttribute('aria-hidden', 'true');
        band.appendChild(glow);
        let frame = 0;
        let x = 50;
        let y = 50;

        band.addEventListener('pointerenter', () => band.classList.add('is-glowing'));
        band.addEventListener('pointerleave', () => band.classList.remove('is-glowing'));
        band.addEventListener('pointermove', (event) => {
          const rect = band.getBoundingClientRect();
          x = ((event.clientX - rect.left) / rect.width) * 100;
          y = ((event.clientY - rect.top) / rect.height) * 100;
          if (!frame) frame = window.requestAnimationFrame(paint);
        });

        function paint() {
          frame = 0;
          glow.style.setProperty('--glow-x', x.toFixed(1) + '%');
          glow.style.setProperty('--glow-y', y.toFixed(1) + '%');
        }
      });
    } catch (error) {
      /* Decorative only. */
    }
  }

  /* ------------------------------------------------------------------
     9. Parallax decor (CTA leaf, certification plate)
  ------------------------------------------------------------------ */
  try {
    const layers = $$('[data-parallax]');
    if (layers.length) {
      const parallaxItems = [];
      function paintParallax() {
        const viewCenter = window.scrollY + viewportHeight / 2;
        parallaxItems.forEach((item) => {
          if (Math.abs(item.center - viewCenter) > viewportHeight * 1.8) return;
          const offset = (item.center - viewCenter) * -item.speed;
          const next = offset.toFixed(1);
          if (next === item.last) return;
          item.last = next;
          item.layer.style.setProperty('--parallax-y', next + 'px');
        });
      }
      function measureParallax() {
        parallaxItems.length = 0;
        layers.forEach((layer) => {
          const rect = layer.getBoundingClientRect();
          parallaxItems.push({
            layer,
            speed: parseFloat(layer.getAttribute('data-parallax')) || 0.06,
            center: rect.top + window.scrollY + rect.height / 2,
            last: null
          });
        });
      }
      if (!reduceMotion) {
        addRefresh(measureParallax);
        addScroll(paintParallax);
        paintParallax();
      }
    }
  } catch (error) {
    /* Decorative only. */
  }

  /* ------------------------------------------------------------------
     10. Coverage schematic hotspots
  ------------------------------------------------------------------ */
  try {
    $$('[data-coverage]').forEach((root) => {
      const points = $$('[data-coverage-point]', root);
      if (!points.length) return;
      const titleEl = $('[data-coverage-title]', root);
      const copyEl = $('[data-coverage-copy]', root);
      const metaEl = $('[data-coverage-meta]', root);
      const iconEl = $('[data-coverage-icon]', root);
      const detail = $('[data-coverage-detail]', root);
      let scanTimer = 0;

      function select(point) {
        points.forEach((item) => {
          const active = item === point;
          item.classList.toggle('is-active', active);
          item.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        if (titleEl) titleEl.textContent = point.getAttribute('data-title') || '';
        if (copyEl) copyEl.textContent = point.getAttribute('data-copy') || '';
        if (metaEl) metaEl.textContent = point.getAttribute('data-meta') || '';
        if (iconEl) iconEl.textContent = point.getAttribute('data-icon') || 'build_circle';

        root.classList.remove('is-scanning');
        if (detail) detail.classList.remove('is-updating');
        // Force the animation to restart on every selection.
        void root.offsetWidth;
        root.classList.add('is-scanning');
        if (detail) detail.classList.add('is-updating');
        window.clearTimeout(scanTimer);
        scanTimer = window.setTimeout(() => {
          root.classList.remove('is-scanning');
          if (detail) detail.classList.remove('is-updating');
        }, 1500);
      }

      points.forEach((point) => {
        point.addEventListener('click', () => select(point));
        point.addEventListener('focus', () => select(point));
      });

      select(points[0]);
    });
  } catch (error) {
    /* Coverage map still reads as a static schematic. */
  }

  /* ------------------------------------------------------------------
     11. Claim checklist completion moment
  ------------------------------------------------------------------ */
  try {
    $$('[data-claim-checklist]').forEach((root) => {
      const inputs = $$('[data-claim-item]', root);
      if (!inputs.length) return;
      const badge = $('[data-claim-complete]', root);
      const reset = $('[data-claim-reset]', root);
      let wasComplete = inputs.every((input) => input.checked);

      function renderComplete(celebrate) {
        const complete = inputs.every((input) => input.checked);
        root.classList.toggle('is-claim-complete', complete);
        if (badge) {
          badge.hidden = !complete;
          // Keep the badge visible whenever the checklist is done, including
          // on a return visit where it is already complete at load time.
          if (complete && celebrate && !wasComplete) {
            badge.classList.remove('is-on');
            void badge.offsetWidth;
            badge.classList.add('is-on');
          } else if (complete) {
            badge.classList.add('is-on');
          } else {
            badge.classList.remove('is-on');
          }
        }
        if (complete && celebrate && !wasComplete) {
          burstLeaves(root);
          if (navigator.vibrate && !reduceMotion) {
            try { navigator.vibrate([10, 26, 14]); } catch (error) { /* ignore */ }
          }
        }
        wasComplete = complete;
      }

      function burstLeaves(scope) {
        if (reduceMotion) return;
        const panel = $('.claim-head', scope) || scope;
        const burst = document.createElement('span');
        burst.className = 'claim-burst';
        burst.setAttribute('aria-hidden', 'true');
        for (let i = 0; i < 12; i += 1) {
          const leaf = document.createElement('span');
          leaf.className = 'claim-leaf';
          const angle = (Math.PI * 2 * i) / 12 + Math.random() * 0.35;
          const distance = 46 + Math.random() * 58;
          leaf.style.setProperty('--dx', Math.cos(angle) * distance + 'px');
          leaf.style.setProperty('--dy', Math.sin(angle) * distance + 'px');
          leaf.style.setProperty('--rot', Math.round(Math.random() * 220 - 110) + 'deg');
          leaf.style.setProperty('--delay', Math.round(Math.random() * 90) + 'ms');
          burst.appendChild(leaf);
        }
        panel.appendChild(burst);
        window.setTimeout(() => burst.remove(), 1600);
      }

      inputs.forEach((input) => input.addEventListener('change', () => renderComplete(true)));
      if (reset) reset.addEventListener('click', () => window.setTimeout(() => renderComplete(false), 0));
      renderComplete(false);
    });
  } catch (error) {
    /* Checklist still works without the celebration. */
  }

  /* ------------------------------------------------------------------
     12. Contact form readiness meter
  ------------------------------------------------------------------ */
  try {
    $$('[data-form-readiness]').forEach((meter) => {
      const form = meter.closest('form');
      if (!form) return;
      const bar = $('[data-form-readiness-bar]', meter);
      const label = $('[data-form-readiness-label]', meter);
      const track = $('[data-form-readiness-track]', meter);
      const nameField = $('[name="full_name"]', form);
      const phoneField = $('[name="phone_number"]', form);
      const noteField = $('[name="vehicle_description"]', form);

      function update() {
        const name = nameField && nameField.value.trim();
        const phone = phoneField && phoneField.value.trim();
        const notes = noteField && noteField.value.trim();
        let score = 0;
        if (name) score += 35;
        if (phone) score += 45;
        if (notes) score += 20;
        const ready = Boolean(name && phone);

        if (bar) bar.style.transform = 'scaleX(' + (score / 100).toFixed(3) + ')';
        if (track) track.setAttribute('aria-valuenow', String(score));
        if (label) {
          label.textContent = !name
            ? 'Start with your name'
            : (!phone ? 'Add a contact number' : (notes ? 'Ready to send' : 'Add vehicle details (optional)'));
        }
        meter.classList.toggle('is-ready', ready);
        meter.classList.toggle('is-complete', ready && Boolean(notes));
      }

      ['input', 'change'].forEach((eventName) => form.addEventListener(eventName, update));
      update();
    });
  } catch (error) {
    /* Meter is optional. */
  }

  /* Keep instruments honest after bfcache restores or late font reflow. */
  window.addEventListener('pageshow', onScroll);
  window.addEventListener('load', onScroll);
  doc.setAttribute('data-motion-ready', 'true');
})();
