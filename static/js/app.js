(function () {
  'use strict';

  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const FOCUSABLE = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled]):not([type="hidden"])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])'
  ].join(',');

  function visibleFocusables(container) {
    return $$(FOCUSABLE, container).filter((el) => {
      return !el.hasAttribute('hidden') && el.offsetWidth > 0 && el.offsetHeight > 0;
    });
  }

  function trapFocus(event, container) {
    if (event.key !== 'Tab') return;
    const items = visibleFocusables(container);
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

  function setPageLock(locked) {
    document.body.classList.toggle('no-scroll', locked);
  }

  // Move focus into a layer once its open styles have applied. Retries cover
  // the frame where visibility is still being recalculated after opening.
  function focusIntoLayer(layer, target) {
    if (!layer || !target) return;
    const focusTarget = () => {
      if (!layer.classList.contains('is-open')) return;
      const active = document.activeElement;
      if (!layer.contains(active) || active === document.body) {
        target.focus({ preventScroll: true });
      }
    };
    focusTarget();
    window.requestAnimationFrame(focusTarget);
    window.setTimeout(focusTarget, 140);
  }

  function isLayerOpen(layer) {
    return layer && layer.classList.contains('is-open');
  }

  function debounce(fn, wait) {
    let timer;
    return function (...args) {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => fn.apply(this, args), wait);
    };
  }

  /* ------------------------------------------------------------------
     First-party analytics
     Records page views and meaningful interactions against the Django
     endpoint. No third-party script, no advertising profile.
  ------------------------------------------------------------------ */
  const analyticsEndpoint = '/analytics/event/';
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const analyticsDisabled = navigator.doNotTrack === '1';

  function trackEvent(name, metadata) {
    if (analyticsDisabled || !analyticsEndpoint) return;
    const payload = {
      name: name,
      path: window.location.pathname + window.location.search,
      title: document.title,
      referrer: document.referrer || '',
      metadata: metadata || {}
    };
    const headers = { 'Content-Type': 'application/json' };
    if (csrfMeta && csrfMeta.content) headers['X-CSRFToken'] = csrfMeta.content;
    try {
      fetch(analyticsEndpoint, {
        method: 'POST',
        headers: headers,
        credentials: 'same-origin',
        keepalive: true,
        body: JSON.stringify(payload)
      }).catch(() => {});
    } catch (error) {
      /* Analytics should never interrupt the page. */
    }
  }

  trackEvent('page_view');

  // Service and tool landing pages use the same first-party endpoint.
  (function trackLandingView() {
    const match = window.location.pathname.match(/^\/(services|tools)\/([^/]+)\/$/);
    if (!match) return;
    trackEvent(match[1] === 'services' ? 'service_view' : 'tool_view', { slug: match[2], location: 'page' });
  })();

  document.addEventListener('click', (event) => {
    const target = event.target.closest('[data-analytics], [data-callback-open], a[href^="tel:"]');
    if (!target) return;
    if (target.matches('a[href^="tel:"]')) {
      trackEvent('phone_click', { location: 'link' });
      return;
    }
    if (target.hasAttribute('data-callback-open')) {
      trackEvent('callback_open', { service: target.getAttribute('data-service') || '' });
      return;
    }
    const explicit = target.getAttribute('data-analytics');
    const label = target.getAttribute('data-analytics-label') || '';
    if (explicit === 'tool_card') {
      trackEvent('tool_view', { tool: label });
    } else {
      trackEvent('cta_click', { label: label || explicit || '' });
    }
  });


  /* ------------------------------------------------------------------
     Toast
  ------------------------------------------------------------------ */
  const toastRegion = $('#toast-region');
  function showToast(message, type = 'success') {
    if (!toastRegion || !message) return;
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    const icon = document.createElement('span');
    icon.className = 'material-symbols-outlined';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = type === 'error' ? 'error' : type === 'info' ? 'info' : 'check_circle';
    const text = document.createElement('span');
    text.textContent = message;
    toast.append(icon, text);
    toastRegion.appendChild(toast);
    window.setTimeout(() => {
      toast.classList.add('is-leaving');
      window.setTimeout(() => toast.remove(), 250);
    }, 3200);
  }

  /* ------------------------------------------------------------------
     Header: scroll progress + compact state
  ------------------------------------------------------------------ */
  const header = $('[data-header]');
  const progress = $('#scroll-progress');
  let pageScrollMax = 0;
  let measureTick = false;

  function measurePageScroll() {
    pageScrollMax = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
  }

  function onScroll() {
    const y = window.scrollY || window.pageYOffset;
    if (header) {
      const scrolled = y > 8;
      if (header.classList.contains('is-scrolled') !== scrolled) {
        header.classList.toggle('is-scrolled', scrolled);
      }
    }

    if (progress) {
      const value = pageScrollMax > 0 ? Math.min(1, Math.max(0, y / pageScrollMax)) : 0;
      progress.style.transform = 'scaleX(' + value + ')';
    }
  }

  function schedulePageMeasure() {
    if (measureTick) return;
    measureTick = true;
    window.requestAnimationFrame(() => {
      measureTick = false;
      measurePageScroll();
      onScroll();
    });
  }

  let scrollTick = false;
  window.addEventListener('scroll', () => {
    if (scrollTick) return;
    scrollTick = true;
    window.requestAnimationFrame(() => {
      onScroll();
      scrollTick = false;
    });
  }, { passive: true });
  window.addEventListener('resize', schedulePageMeasure, { passive: true });
  window.addEventListener('load', schedulePageMeasure);
  if ('ResizeObserver' in window) {
    try {
      new ResizeObserver(schedulePageMeasure).observe(document.body);
    } catch (error) {
      /* Layout measurement is an optimisation. */
    }
  }
  measurePageScroll();
  onScroll();

  /* ------------------------------------------------------------------
     Hero cinema: scrub the shop film from the scroll position
     - The film is delivered as a WebP frame sequence, so scrubbing never
       waits on a video seek or a decoder chain.
     - Frames load in order behind the poster; scrolling simply paints the
       matching frame to the canvas.
  ------------------------------------------------------------------ */
  const heroSection = $('[data-hero-cinema]');
  const heroStage = $('[data-hero-stage]', heroSection || document);
  const heroMedia = $('.hero-cinema-media', heroSection || document);
  const heroCanvas = $('[data-hero-canvas]', heroSection || document);
  const heroPoster = $('[data-hero-poster]', heroSection || document);
  const heroProgressEl = $('[data-hero-progress]', heroSection || document);
  const heroCountEl = $('[data-hero-count]', heroSection || document);
  const heroContent = $('.hero-cinema-content', heroSection || document);
  const heroTimecodeEl = $('[data-hero-timecode]', heroSection || document);
  const heroFrameEl = $('[data-hero-frame]', heroSection || document);
  const heroTotalEl = $('[data-hero-total]', heroSection || document);
  const heroLoadEl = $('[data-hero-load]', heroSection || document);
  const heroLoadBarEl = $('[data-hero-load-bar]', heroSection || document);
  const heroScrub = $('[data-hero-scrub]', heroSection || document);
  const heroTorch = $('[data-hero-torch]', heroSection || document);
  const heroFinePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const saveData = navigator.connection && navigator.connection.saveData;
  const heroMobile = window.matchMedia('(max-width: 767px)').matches;

  if (heroPoster && heroMobile) {
    const mobilePoster = heroPoster.getAttribute('data-src-mobile');
    if (mobilePoster) heroPoster.src = mobilePoster;
  }

  if (heroSection && (reduceMotion || saveData)) {
    heroSection.classList.add('is-static');
  }

  if (heroSection && heroStage && heroCanvas && !reduceMotion && !saveData) {
    const heroContext = heroCanvas.getContext('2d');
    const heroFrameCount = parseInt(heroCanvas.getAttribute('data-frame-count'), 10) || 0;
    const heroFrameBase = heroMobile
      ? heroCanvas.getAttribute('data-frame-base-mobile')
      : heroCanvas.getAttribute('data-frame-base');
    const heroFrameVersion = heroCanvas.getAttribute('data-frame-version') || '1';
    const heroFrames = new Array(heroFrameCount);

    let heroTarget = 0;
    let heroCurrent = 0;
    let heroFrame = 0;
    let heroLastDrawn = -1;
    let heroLastTextIndex = -1;
    let heroLastProgress = -1;
    let heroLastPercent = -1;
    let heroLastWhole = -1;
    let heroLastTenths = -1;
    let heroLastContentY = NaN;
    let heroLastOpacity = NaN;
    let heroLastZoom = NaN;
    let heroDrawn = false;
    let heroLoaded = 0;
    let heroTop = 0;
    let heroRange = 0;
    let heroLastTime = 0;
    let heroMeasureTick = false;
    let heroInView = true;
    let heroLoadPaused = false;

    if (heroTotalEl) heroTotalEl.textContent = String(heroFrameCount).padStart(3, '0');
    if (heroScrub) heroScrub.setAttribute('aria-valuemax', String(heroFrameCount));

    const clamp01 = (value) => Math.min(1, Math.max(0, value));
    const heroFrameUrl = (index) =>
      heroFrameBase + '/frame-' + String(index + 1).padStart(3, '0') + '.webp?v=' + heroFrameVersion;

    function updateHeroLoad() {
      const ratio = heroFrameCount ? Math.min(1, heroLoaded / heroFrameCount) : 0;
      if (heroLoadBarEl) heroLoadBarEl.style.transform = 'scaleX(' + ratio.toFixed(3) + ')';
      if (heroLoadEl) heroLoadEl.textContent = 'Film ' + Math.round(ratio * 100) + '% loaded';
      if (heroCanvas) heroCanvas.classList.toggle('is-loaded', ratio >= 1);
    }

    function sizeHeroCanvas(image) {
      if (heroCanvas.width !== image.naturalWidth || heroCanvas.height !== image.naturalHeight) {
        heroCanvas.width = image.naturalWidth;
        heroCanvas.height = image.naturalHeight;
      }
    }

    function drawHeroFrame(index) {
      const image = heroFrames[index];
      if (!image || !image.complete || !image.naturalWidth) return false;
      sizeHeroCanvas(image);
      heroContext.drawImage(image, 0, 0, heroCanvas.width, heroCanvas.height);
      heroDrawn = true;
      heroLastDrawn = index;
      return true;
    }

    function drawNearestHeroFrame(index) {
      // On a fast flick the exact frame may still be in flight. Paint the
      // closest available one instead of jumping to a distant frame.
      for (let offset = 1; offset <= 8; offset += 1) {
        if (drawHeroFrame(index - offset)) return true;
        if (drawHeroFrame(index + offset)) return true;
      }
      return false;
    }

    // Warm the decoder a few frames ahead so the next scroll step is instant.
    function primeHeroFrames(index) {
      for (let i = index + 1; i <= Math.min(index + 6, heroFrameCount - 1); i += 1) {
        const image = heroFrames[i];
        if (image && image.complete && image.decode) image.decode().catch(() => {});
      }
    }

    for (let i = 0; i < heroFrameCount; i += 1) {
      heroFrames[i] = null;
    }

    // Load every fourth frame first so any scroll position has a nearby
    // frame early, then fill the gaps.
    const heroLoadOrder = [];
    for (let i = 0; i < heroFrameCount; i += 4) heroLoadOrder.push(i);
    for (let i = 0; i < heroFrameCount; i += 1) {
      if (i % 4 !== 0) heroLoadOrder.push(i);
    }

    let heroLoadIndex = 0;
    let heroLoadActive = 0;

    function pumpHeroFrames() {
      if (heroLoadPaused) return;
      while (heroLoadActive < 6 && heroLoadIndex < heroLoadOrder.length) {
        const index = heroLoadOrder[heroLoadIndex];
        heroLoadIndex += 1;
        heroLoadActive += 1;

        const image = new Image();
        image.decoding = 'async';
        image.addEventListener('load', () => {
          heroLoadActive -= 1;
          heroLoaded += 1;
          if (index === 0) sizeHeroCanvas(image);
          updateHeroLoad();
          queueHeroUpdate();
          pumpHeroFrames();
        });
        image.addEventListener('error', () => {
          heroLoadActive -= 1;
          heroLoaded += 1;
          updateHeroLoad();
          pumpHeroFrames();
        });
        image.src = heroFrameUrl(index);
        heroFrames[index] = image;
      }
    }

    pumpHeroFrames();
    updateHeroLoad();

    function measureHero() {
      const rect = heroSection.getBoundingClientRect();
      heroTop = rect.top + window.scrollY;
      heroRange = Math.max(0, rect.height - heroStage.offsetHeight);
    }

    function readHeroProgress() {
      if (heroRange <= 0) return 0;
      return clamp01((window.scrollY - heroTop) / heroRange);
    }

    function paintHero(progress) {
      const index = Math.round(progress * (heroFrameCount - 1));
      const frameNumber = index + 1;
      const seconds = progress * 5;
      const whole = Math.floor(seconds);
      const tenths = Math.floor((seconds - whole) * 10);

      if (Math.abs(progress - heroLastProgress) > 0.00005) {
        heroLastProgress = progress;
        if (heroProgressEl) {
          heroProgressEl.style.transform = 'scaleX(' + progress.toFixed(4) + ')';
        }
        const progressHost = heroScrub || heroSection;
        if (progressHost) progressHost.style.setProperty('--hero-progress', progress.toFixed(4));
        if (!heroMobile) {
          const zoom = 1.02 + progress * 0.04;
          if (Math.abs(zoom - heroLastZoom) > 0.0002) {
            heroLastZoom = zoom;
            const zoomHost = heroMedia || heroSection;
            if (zoomHost) zoomHost.style.setProperty('--hero-zoom', zoom.toFixed(4));
          }
        }
        if (heroContent) {
          const contentY = -progress * 22;
          if (Math.abs(contentY - heroLastContentY) > 0.02) {
            heroLastContentY = contentY;
            heroContent.style.transform = 'translate3d(0,' + contentY.toFixed(2) + 'px,0)';
          }
          const opacity = 1 - progress * 0.18;
          if (Math.abs(opacity - heroLastOpacity) > 0.002) {
            heroLastOpacity = opacity;
            heroContent.style.opacity = opacity.toFixed(3);
          }
        }
      }

      const percent = Math.round(progress * 100);
      if (percent !== heroLastPercent) {
        heroLastPercent = percent;
        if (heroCountEl) heroCountEl.textContent = String(percent).padStart(2, '0');
      }

      if (index !== heroLastTextIndex) {
        heroLastTextIndex = index;
        if (heroFrameEl) heroFrameEl.textContent = String(frameNumber).padStart(3, '0');
        if (heroTimecodeEl) heroTimecodeEl.textContent = '0:' + String(whole).padStart(2, '0') + '.' + tenths;
        if (heroScrub) {
          heroScrub.setAttribute('aria-valuenow', String(frameNumber));
          heroScrub.setAttribute(
            'aria-valuetext',
            'Frame ' + frameNumber + ' of ' + heroFrameCount + ', time 0:' + String(whole).padStart(2, '0') + '.' + tenths
          );
        }
      }

      if (index === heroLastDrawn) return;
      if (!drawHeroFrame(index)) {
        if (!heroDrawn) drawHeroFrame(0);
        else drawNearestHeroFrame(index);
      }
      primeHeroFrames(index);
    }

    function tickHero(now) {
      heroFrame = 0;
      if (!heroLastTime) heroLastTime = now;
      /* Time-based easing keeps the film at the same perceived speed on
         60 Hz, 90 Hz and 120 Hz displays. */
      const dt = Math.min(64, Math.max(8, now - heroLastTime));
      heroLastTime = now;
      const diff = heroTarget - heroCurrent;
      if (Math.abs(diff) < 0.0004) {
        heroCurrent = heroTarget;
      } else {
        const ease = 1 - Math.exp(-16 * (dt / 1000));
        heroCurrent += diff * ease;
      }
      paintHero(heroCurrent);
      if (heroCurrent !== heroTarget) {
        heroFrame = window.requestAnimationFrame(tickHero);
      } else {
        heroLastTime = 0;
      }
    }

    function queueHeroUpdate() {
      if (!heroInView) return;
      heroTarget = readHeroProgress();
      if (!heroFrame) heroFrame = window.requestAnimationFrame(tickHero);
    }

    function scheduleHeroMeasure() {
      if (heroMeasureTick) return;
      heroMeasureTick = true;
      window.requestAnimationFrame(() => {
        heroMeasureTick = false;
        measureHero();
        queueHeroUpdate();
      });
    }

    function scrollToHeroProgress(progress) {
      if (heroRange <= 0) return;
      const top = heroTop + clamp01(progress) * heroRange;
      try {
        /* "instant" jumps immediately even though the document opts into
           CSS smooth scrolling. Older engines reject the value, so fall
           back to a synchronous jump with smooth behaviour suspended. */
        window.scrollTo({ top, behavior: 'instant' });
      } catch (error) {
        const root = document.documentElement;
        const previous = root.style.scrollBehavior;
        root.style.scrollBehavior = 'auto';
        window.scrollTo(0, top);
        root.style.scrollBehavior = previous;
      }
    }

    // Draggable / keyboard scrub rail. It writes to the scroll position so
    // the sticky film and the rest of the page stay in sync.
    if (heroScrub) {
      let dragging = false;

      const progressFromEvent = (event) => {
        const rect = heroScrub.getBoundingClientRect();
        if (!rect.width) return 0;
        return clamp01((event.clientX - rect.left) / rect.width);
      };

      heroScrub.addEventListener('pointerdown', (event) => {
        dragging = true;
        heroScrub.classList.add('is-dragging');
        if (heroScrub.setPointerCapture) heroScrub.setPointerCapture(event.pointerId);
        scrollToHeroProgress(progressFromEvent(event));
        event.preventDefault();
      });

      heroScrub.addEventListener('pointermove', (event) => {
        if (!dragging) return;
        scrollToHeroProgress(progressFromEvent(event));
      });

      const stopDragging = (event) => {
        if (!dragging) return;
        dragging = false;
        heroScrub.classList.remove('is-dragging');
        if (heroScrub.releasePointerCapture && event.pointerId !== undefined) {
          try { heroScrub.releasePointerCapture(event.pointerId); } catch (error) { /* ignore */ }
        }
      };

      heroScrub.addEventListener('pointerup', stopDragging);
      heroScrub.addEventListener('pointercancel', stopDragging);

      heroScrub.addEventListener('keydown', (event) => {
        const step = 1 / Math.max(1, heroFrameCount - 1);
        let next = null;
        if (event.key === 'ArrowRight' || event.key === 'ArrowUp') next = readHeroProgress() + step;
        if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') next = readHeroProgress() - step;
        if (event.key === 'PageUp') next = readHeroProgress() + step * 10;
        if (event.key === 'PageDown') next = readHeroProgress() - step * 10;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = 1;
        if (next === null) return;
        event.preventDefault();
        scrollToHeroProgress(next);
      });
    }

    // Pointer headlight: a warm inspection lamp follows the cursor over the
    // desktop film. Purely decorative, and skipped for touch/reduced motion.
    if (heroTorch && heroStage && heroFinePointer) {
      let torchFrame = 0;
      let tx = 0;
      let ty = 0;

      const paintTorch = () => {
        torchFrame = 0;
        heroSection.style.setProperty('--torch-x', tx.toFixed(1) + 'px');
        heroSection.style.setProperty('--torch-y', ty.toFixed(1) + 'px');
      };

      heroStage.addEventListener('pointerenter', () => {
        heroSection.classList.add('is-torching');
      });
      heroStage.addEventListener('pointermove', (event) => {
        const rect = heroStage.getBoundingClientRect();
        tx = event.clientX - rect.left;
        ty = event.clientY - rect.top;
        if (!torchFrame) torchFrame = window.requestAnimationFrame(paintTorch);
      });
      heroStage.addEventListener('pointerleave', () => {
        heroSection.classList.remove('is-torching');
      });
    }

    window.addEventListener('scroll', queueHeroUpdate, { passive: true });
    window.addEventListener('resize', scheduleHeroMeasure, { passive: true });
    window.addEventListener('load', scheduleHeroMeasure);
    if ('ResizeObserver' in window) {
      try {
        const heroObserver = new ResizeObserver(scheduleHeroMeasure);
        heroObserver.observe(heroSection);
        heroObserver.observe(document.body);
      } catch (error) {
        /* Measurement will still refresh on resize. */
      }
    }
    if ('IntersectionObserver' in window) {
      try {
        const heroViewObserver = new IntersectionObserver((entries) => {
          const entry = entries[0];
          heroInView = entry.isIntersecting;
          heroLoadPaused = !entry.isIntersecting;
          if (entry.isIntersecting) {
            scheduleHeroMeasure();
            pumpHeroFrames();
          } else {
            heroLoadPaused = true;
            if (heroFrame) {
              window.cancelAnimationFrame(heroFrame);
              heroFrame = 0;
            }
            heroLastTime = 0;
          }
        }, { rootMargin: '160px 0px' });
        heroViewObserver.observe(heroSection);
      } catch (error) {
        /* The film still plays without visibility pausing. */
      }
    }
    document.addEventListener('visibilitychange', () => {
      heroLoadPaused = document.hidden || !heroInView;
      if (!heroLoadPaused) pumpHeroFrames();
    });
    measureHero();
    queueHeroUpdate();
  }

  /* ------------------------------------------------------------------
     Shop open / closed status (Winnipeg time)
  ------------------------------------------------------------------ */
  const DAY_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const DAY_LONG = {
    Sun: 'Sunday', Mon: 'Monday', Tue: 'Tuesday', Wed: 'Wednesday',
    Thu: 'Thursday', Fri: 'Friday', Sat: 'Saturday'
  };

  function getWinnipegTime() {
    try {
      const parts = new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/Winnipeg',
        weekday: 'short',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23'
      }).formatToParts(new Date());
      const values = {};
      parts.forEach((part) => { values[part.type] = part.value; });
      return {
        day: values.weekday,
        hour: parseInt(values.hour, 10) % 24,
        minute: parseInt(values.minute, 10)
      };
    } catch (error) {
      const now = new Date();
      return {
        day: DAY_SHORT[now.getDay()],
        hour: now.getHours(),
        minute: now.getMinutes()
      };
    }
  }

  function shopState() {
    const time = getWinnipegTime();
    const dayIndex = DAY_SHORT.indexOf(time.day);
    const minutes = time.hour * 60 + time.minute;
    const opens = 9 * 60;
    const closes = 18 * 60;
    const weekday = dayIndex >= 1 && dayIndex <= 6;

    if (weekday && minutes >= opens && minutes < closes) {
      return { open: true, day: time.day, text: 'Open now · closes 6:00 PM' };
    }
    if (weekday && minutes < opens) {
      return { open: false, day: time.day, text: 'Closed · opens 9:00 AM today' };
    }

    let nextIndex = (dayIndex + 1) % 7;
    if (nextIndex === 0) nextIndex = 1;
    return {
      open: false,
      day: time.day,
      text: 'Closed · opens ' + DAY_LONG[DAY_SHORT[nextIndex]] + ' 9:00 AM'
    };
  }

  function updateShopStatus() {
    const state = shopState();
    $$('[data-shop-status]').forEach((el) => {
      el.textContent = state.text;
      const dot = el.parentElement ? el.parentElement.querySelector('.status-dot') : null;
      if (dot) dot.classList.toggle('is-closed', !state.open);
    });

    $$('[data-day-row]').forEach((row) => {
      row.classList.toggle('is-today', row.getAttribute('data-day-row') === state.day);
    });
  }

  updateShopStatus();
  window.setInterval(updateShopStatus, 60000);

  /* ------------------------------------------------------------------
     Mobile navigation
  ------------------------------------------------------------------ */
  const mobileLayer = $('[data-mobile-layer]');
  const mobilePanel = $('[data-mobile-panel]');
  const mobileOpenBtn = $('[data-mobile-open]');
  let mobileReturnFocus = null;

  function openMobileMenu() {
    if (!mobileLayer) return;
    mobileReturnFocus = document.activeElement;
    mobileLayer.classList.add('is-open');
    mobileLayer.setAttribute('aria-hidden', 'false');
    if (mobileOpenBtn) mobileOpenBtn.setAttribute('aria-expanded', 'true');
    setPageLock(true);
    const closeBtn = $('[data-mobile-close]', mobilePanel);
    focusIntoLayer(mobileLayer, closeBtn);
  }

  function closeMobileMenu(restoreFocus = true) {
    if (!mobileLayer || !mobileLayer.classList.contains('is-open')) return;
    mobileLayer.classList.remove('is-open');
    mobileLayer.setAttribute('aria-hidden', 'true');
    if (mobileOpenBtn) {
      mobileOpenBtn.setAttribute('aria-expanded', 'false');
      if (restoreFocus && mobileReturnFocus) mobileOpenBtn.focus();
    }
    setPageLock(false);
  }

  if (mobileOpenBtn) {
    mobileOpenBtn.addEventListener('click', openMobileMenu);
  }

  $$('[data-mobile-close]').forEach((el) => {
    el.addEventListener('click', () => closeMobileMenu());
  });

  if (mobileLayer) {
    mobileLayer.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeMobileMenu();
      } else {
        trapFocus(event, mobilePanel);
      }
    });
    $$('a', mobilePanel).forEach((link) => {
      link.addEventListener('click', () => closeMobileMenu(false));
    });
  }

  /* ------------------------------------------------------------------
     Services mega menu
  ------------------------------------------------------------------ */
  const dropdown = $('[data-dropdown]');
  const dropdownToggle = $('[data-dropdown-toggle]');
  const dropdownPanel = $('[data-dropdown-panel]');
  let dropdownTimer = null;

  function openDropdown() {
    if (!dropdown || !dropdownPanel || !dropdownToggle) return;
    window.clearTimeout(dropdownTimer);
    dropdownPanel.classList.add('is-active');
    dropdownToggle.setAttribute('aria-expanded', 'true');
    const chevron = $('#services-chevron');
    if (chevron) chevron.style.transform = 'rotate(180deg)';
  }

  function closeDropdown() {
    if (!dropdown || !dropdownPanel || !dropdownToggle) return;
    dropdownPanel.classList.remove('is-active');
    dropdownToggle.setAttribute('aria-expanded', 'false');
    const chevron = $('#services-chevron');
    if (chevron) chevron.style.transform = 'rotate(0deg)';
  }

  function scheduleCloseDropdown() {
    window.clearTimeout(dropdownTimer);
    dropdownTimer = window.setTimeout(closeDropdown, 140);
  }

  if (dropdown && dropdownToggle && dropdownPanel) {
    dropdownToggle.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (dropdownPanel.classList.contains('is-active')) {
        closeDropdown();
      } else {
        openDropdown();
      }
    });

    dropdown.addEventListener('mouseenter', openDropdown);
    dropdown.addEventListener('mouseleave', scheduleCloseDropdown);

    dropdown.addEventListener('focusout', (event) => {
      if (!dropdown.contains(event.relatedTarget)) closeDropdown();
    });

    document.addEventListener('click', (event) => {
      if (!dropdown.contains(event.target)) closeDropdown();
    });

    $$('a', dropdownPanel).forEach((link) => {
      link.addEventListener('click', closeDropdown);
    });
  }

  /* ------------------------------------------------------------------
     Callback modal
  ------------------------------------------------------------------ */
  const callbackModal = $('[data-callback-modal]');
  const callbackForm = $('[data-callback-form]');
  const callbackSuccess = $('[data-callback-success]');
  const callbackServiceInput = $('#callback-service');
  const callbackNotesInput = $('#callback-notes');
  let callbackReturnFocus = null;

  function resetCallbackErrors() {
    if (!callbackForm) return;
    $$('[data-error-for]', callbackForm).forEach((el) => {
      el.hidden = true;
      el.textContent = '';
    });
    $$('[aria-invalid="true"]', callbackForm).forEach((el) => el.removeAttribute('aria-invalid'));
    const alert = $('[data-callback-error]', callbackModal);
    if (alert) {
      alert.hidden = true;
      alert.textContent = '';
    }
  }

  function openCallbackModal(service, note) {
    if (!callbackModal || !callbackForm || !callbackSuccess) return;
    const fromDrawer = Boolean(mobileLayer && mobileLayer.classList.contains('is-open'));
    callbackReturnFocus = fromDrawer && mobileOpenBtn ? mobileOpenBtn : document.activeElement;
    if (fromDrawer) closeMobileMenu(false);

    if (callbackModal.getAttribute('data-completed') === 'true') {
      callbackForm.reset();
      callbackModal.removeAttribute('data-completed');
    }
    resetCallbackErrors();
    callbackForm.hidden = false;
    callbackSuccess.hidden = true;

    if (callbackServiceInput) {
      callbackServiceInput.value = service || '';
    }
    if (callbackNotesInput && typeof note === 'string' && note) {
      callbackNotesInput.value = note;
    }

    callbackModal.classList.add('is-open');
    callbackModal.setAttribute('aria-hidden', 'false');
    setPageLock(true);
    focusIntoLayer(callbackModal, $('#callback-name'));
  }

  function closeCallbackModal() {
    if (!callbackModal || !callbackModal.classList.contains('is-open')) return;
    callbackModal.classList.remove('is-open');
    callbackModal.setAttribute('aria-hidden', 'true');
    setPageLock(false);
    if (callbackReturnFocus && typeof callbackReturnFocus.focus === 'function') {
      callbackReturnFocus.focus();
    }
  }

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-callback-open]');
    if (!trigger) return;
    event.preventDefault();
    openCallbackModal(
      trigger.getAttribute('data-service') || '',
      trigger.getAttribute('data-callback-note')
    );
  });

  $$('[data-callback-close]').forEach((el) => {
    el.addEventListener('click', closeCallbackModal);
  });

  if (callbackModal) {
    callbackModal.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeCallbackModal();
      } else {
        trapFocus(event, callbackModal);
      }
    });
  }

  function setSubmitState(form, loading) {
    const button = $('[data-submit]', form);
    const label = $('[data-submit-label]', form);
    const spinner = $('[data-spinner]', form);
    if (button) button.disabled = loading;
    if (spinner) spinner.hidden = !loading;
    if (label) {
      if (loading) {
        label.setAttribute('data-original', label.textContent);
        label.textContent = 'Sending…';
      } else if (label.getAttribute('data-original')) {
        label.textContent = label.getAttribute('data-original');
        label.removeAttribute('data-original');
      }
    }
  }

  function showFormErrors(form, errors, summaryTarget) {
    if (!form) return;
    const keys = Object.keys(errors || {});
    keys.forEach((key) => {
      const errorEl = $('[data-error-for="' + key + '"]', form);
      if (errorEl) {
        errorEl.textContent = errors[key];
        errorEl.hidden = false;
      }
      const input = form.querySelector('[name="' + key + '"]');
      if (input) input.setAttribute('aria-invalid', 'true');
    });
    if (summaryTarget) {
      summaryTarget.textContent = keys.length ? 'Please fix the highlighted fields and try again.' : 'Something went wrong. Please try again.';
      summaryTarget.hidden = false;
    }
  }

  function clearErrorFor(input) {
    if (!input) return;
    const form = input.form;
    if (!form) return;
    const el = $('[data-error-for="' + input.name + '"]', form);
    if (el) {
      el.hidden = true;
      el.textContent = '';
    }
    input.removeAttribute('aria-invalid');
  }

  function validateBasics(form) {
    const errors = {};
    const name = form.querySelector('[name="full_name"]');
    const phone = form.querySelector('[name="phone_number"]');
    if (name && !name.value.trim()) {
      errors.full_name = 'Please tell us your name.';
    }
    if (phone) {
      const value = phone.value.trim();
      if (!value) {
        errors.phone_number = 'Please add a phone number so we can call you back.';
      } else if (value.replace(/\D/g, '').length < 7) {
        errors.phone_number = 'That phone number looks too short. Please check it.';
      }
    }
    return errors;
  }

  async function submitAjaxForm(form) {
    const formData = new FormData(form);
    const csrfInput = form.querySelector('[name="csrfmiddlewaretoken"]');
    const headers = { 'X-Requested-With': 'XMLHttpRequest' };
    if (csrfInput) headers['X-CSRFToken'] = csrfInput.value;

    const response = await fetch(form.action, {
      method: 'POST',
      body: formData,
      headers,
      credentials: 'same-origin'
    });

    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      data = {};
    }
    if (!response.ok) {
      const requestError = new Error(data.message || 'Something went wrong.');
      requestError.payload = data;
      throw requestError;
    }
    return data;
  }

  if (callbackForm) {
    callbackForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      resetCallbackErrors();
      const errors = validateBasics(callbackForm);
      if (Object.keys(errors).length) {
        showFormErrors(callbackForm, errors, $('[data-callback-error]', callbackModal));
        const firstKey = Object.keys(errors)[0];
        const firstInput = callbackForm.querySelector('[name="' + firstKey + '"]');
        if (firstInput) firstInput.focus();
        return;
      }

      setSubmitState(callbackForm, true);
      try {
        const data = await submitAjaxForm(callbackForm);
        callbackForm.hidden = true;
        callbackSuccess.hidden = false;
        callbackModal.setAttribute('data-completed', 'true');
        const message = $('[data-callback-success-message]', callbackModal);
        if (message) message.textContent = data.message || 'We will call you back during shop hours.';
        showToast('Callback request sent.', 'success');
        trackEvent('callback_submit', { reference: data.reference || '' });
        const heading = $('h3', callbackSuccess);
        if (heading) {
          heading.setAttribute('tabindex', '-1');
          heading.focus();
        }
      } catch (error) {
        const payload = error.payload || {};
        showFormErrors(callbackForm, payload.errors || {}, $('[data-callback-error]', callbackModal));
        if (!payload.errors) showToast(error.message || 'Could not send the request.', 'error');
      } finally {
        setSubmitState(callbackForm, false);
      }
    });

    $$('input, select, textarea', callbackForm).forEach((input) => {
      input.addEventListener('input', () => clearErrorFor(input));
    });
  }

  /* ------------------------------------------------------------------
     Lightbox
  ------------------------------------------------------------------ */
  const lightbox = $('[data-lightbox-modal]');
  const lightboxImage = $('[data-lightbox-image]');
  const lightboxCaption = $('[data-lightbox-caption]');
  const lightboxSub = $('[data-lightbox-sub]');
  const lightboxCounter = $('[data-lightbox-counter]');
  let galleryTriggers = [];
  let lightboxIndex = 0;
  let lightboxReturnFocus = null;
  let touchStartX = null;

  function collectGallery() {
    galleryTriggers = $$('[data-lightbox]');
  }

  function updateLightbox() {
    if (!galleryTriggers.length) return;
    const trigger = galleryTriggers[lightboxIndex];
    const src = trigger.getAttribute('data-src');
    const title = trigger.getAttribute('data-title') || 'Workshop photo';
    const sub = trigger.getAttribute('data-sub') || '';
    const alt = $('img', trigger) ? $('img', trigger).getAttribute('alt') : title;

    if (lightboxImage) {
      lightboxImage.style.opacity = reduceMotion ? '1' : '0.25';
      const swap = () => {
        lightboxImage.src = src;
        lightboxImage.alt = alt;
        window.requestAnimationFrame(() => { lightboxImage.style.opacity = '1'; });
      };
      if (reduceMotion) swap();
      else window.setTimeout(swap, 100);
    }
    if (lightboxCaption) lightboxCaption.textContent = title;
    if (lightboxSub) lightboxSub.textContent = sub;
    if (lightboxCounter) lightboxCounter.textContent = (lightboxIndex + 1) + ' / ' + galleryTriggers.length;
  }

  function openLightbox(trigger) {
    if (!lightbox) return;
    collectGallery();
    lightboxIndex = Math.max(0, galleryTriggers.indexOf(trigger));
    lightboxReturnFocus = document.activeElement;
    updateLightbox();
    lightbox.classList.add('is-open');
    lightbox.setAttribute('aria-hidden', 'false');
    setPageLock(true);
    trackEvent('gallery_view', { title: trigger.getAttribute('data-title') || '' });
    focusIntoLayer(lightbox, $('[data-lightbox-close]', lightbox));
  }

  function closeLightbox() {
    if (!lightbox || !lightbox.classList.contains('is-open')) return;
    lightbox.classList.remove('is-open');
    lightbox.setAttribute('aria-hidden', 'true');
    setPageLock(false);
    if (lightboxReturnFocus && typeof lightboxReturnFocus.focus === 'function') {
      lightboxReturnFocus.focus();
    }
  }

  function nextLightbox() {
    if (!galleryTriggers.length) return;
    lightboxIndex = (lightboxIndex + 1) % galleryTriggers.length;
    updateLightbox();
  }

  function prevLightbox() {
    if (!galleryTriggers.length) return;
    lightboxIndex = (lightboxIndex - 1 + galleryTriggers.length) % galleryTriggers.length;
    updateLightbox();
  }

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-lightbox]');
    if (trigger) {
      event.preventDefault();
      openLightbox(trigger);
      return;
    }
    if (event.target.closest('[data-lightbox-close]')) closeLightbox();
    if (event.target.closest('[data-lightbox-next]')) nextLightbox();
    if (event.target.closest('[data-lightbox-prev]')) prevLightbox();
  });

  if (lightbox) {
    lightbox.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeLightbox();
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        nextLightbox();
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        prevLightbox();
      } else {
        trapFocus(event, lightbox);
      }
    });

    const stage = $('.lightbox-stage', lightbox);
    if (stage) {
      stage.addEventListener('touchstart', (event) => {
        touchStartX = event.changedTouches[0].clientX;
      }, { passive: true });
      stage.addEventListener('touchend', (event) => {
        if (touchStartX === null) return;
        const delta = event.changedTouches[0].clientX - touchStartX;
        if (Math.abs(delta) > 45) {
          if (delta < 0) nextLightbox();
          else prevLightbox();
        }
        touchStartX = null;
      }, { passive: true });
    }
  }

  /* ------------------------------------------------------------------
     Repair triage
  ------------------------------------------------------------------ */
  const TRIAGE_CATALOG = {
    windshield: {
      icon: 'car_repair',
      title: 'Windshield repair & replacement',
      desc: 'Stone-chip resin repair or a full glass replacement, sealed to factory spec. MPI direct billing is available on eligible claims.',
      time: '30 min chip · 2–3 hr replacement',
      mpi: 'MPI direct repair eligible',
      service: 'Windshield repair or replacement'
    },
    collision: {
      icon: 'car_crash',
      title: 'Collision & body repair',
      desc: 'Panel repair, bumper restoration and structural alignment. We check for hidden damage before the estimate is finalised.',
      time: '2–5 business days typical',
      mpi: 'MPI Direct Repair shop',
      service: 'Collision estimate'
    },
    diagnostics: {
      icon: 'settings_input_component',
      title: 'Check-engine & computer diagnostics',
      desc: 'OBD-II scanning, live data and electrical checks. We explain the cause before any parts are ordered.',
      time: '45–60 minutes',
      mpi: 'Private mechanical work',
      service: 'Computerized diagnostics'
    },
    brakes: {
      icon: 'disc_full',
      title: 'Brake inspection & service',
      desc: 'Pad and rotor measurement, caliper and line checks, and brake fluid service to chase down noise or a soft pedal.',
      time: '1–2 hours per axle',
      mpi: 'Wear item · private rates',
      service: 'Brake service'
    },
    maintenance: {
      icon: 'oil_barrel',
      title: 'Maintenance & safety inspection',
      desc: 'Oil and filter service, fluid checks, MPI safety inspections and wheel balancing to keep the vehicle road-ready.',
      time: '30 min to same-day',
      mpi: 'Safety certificates provided',
      service: 'Maintenance or safety inspection'
    }
  };

  $$('[data-triage]').forEach((widget) => {
    const state = { vehicle: 'Car / Sedan', issue: 'windshield' };
    const vehicleButtons = $$('[data-vehicle]', widget);
    const issueButtons = $$('[data-issue]', widget);
    const cta = $('[data-triage-cta]', widget);

    function setPressed(buttons, activeButton) {
      buttons.forEach((button) => {
        const isActive = button === activeButton;
        button.classList.toggle('is-active', isActive);
        button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      });
    }

    function updateTriage() {
      const item = TRIAGE_CATALOG[state.issue];
      if (!item) return;
      const icon = $('[data-triage-field="icon"]', widget);
      const title = $('[data-triage-field="title"]', widget);
      const desc = $('[data-triage-field="desc"]', widget);
      const time = $('[data-triage-field="time"]', widget);
      const mpi = $('[data-triage-field="mpi"]', widget);

      if (icon) icon.textContent = item.icon;
      if (title) title.textContent = item.title;
      if (desc) desc.textContent = item.desc;
      if (time) time.textContent = item.time;
      if (mpi) mpi.textContent = item.mpi;
      if (cta) {
        cta.setAttribute('data-service', item.service + ' — ' + state.vehicle);
        const label = $('[data-triage-cta-label]', widget);
        if (label) label.textContent = 'Pre-fill a callback';
      }

      const result = $('.triage-result', widget);
      if (result && !reduceMotion) {
        result.classList.remove('is-updating');
        void result.offsetWidth;
        result.classList.add('is-updating');
      }
    }

    vehicleButtons.forEach((button) => {
      button.addEventListener('click', () => {
        state.vehicle = button.getAttribute('data-vehicle') || state.vehicle;
        setPressed(vehicleButtons, button);
        updateTriage();
      });
    });

    issueButtons.forEach((button) => {
      button.addEventListener('click', () => {
        state.issue = button.getAttribute('data-issue') || state.issue;
        setPressed(issueButtons, button);
        updateTriage();
      });
    });

    updateTriage();
  });

  /* ------------------------------------------------------------------
     FAQ accordions
  ------------------------------------------------------------------ */
  $$('[data-accordion]').forEach((group) => {
    const toggles = $$('.faq-toggle', group);
    const toggleAll = $('[data-faq-toggle-all]', group);

    function setOpen(button, open) {
      const wrapper = button.nextElementSibling;
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (wrapper) {
        wrapper.classList.toggle('is-open', open);
        wrapper.setAttribute('aria-hidden', open ? 'false' : 'true');
        wrapper.inert = !open;
      }
    }

    toggles.forEach((button) => {
      setOpen(button, button.getAttribute('aria-expanded') === 'true');
      button.addEventListener('click', () => {
        const willOpen = button.getAttribute('aria-expanded') !== 'true';
        toggles.forEach((other) => {
          if (other !== button) setOpen(other, false);
        });
        setOpen(button, willOpen);
        if (toggleAll) {
          const allOpen = toggles.every((toggle) => toggle.getAttribute('aria-expanded') === 'true');
          toggleAll.textContent = allOpen ? 'Collapse all' : 'Expand all';
        }
      });
    });

    if (toggleAll) {
      toggleAll.addEventListener('click', () => {
        const shouldOpen = toggles.some((button) => button.getAttribute('aria-expanded') !== 'true');
        toggles.forEach((button) => setOpen(button, shouldOpen));
        toggleAll.textContent = shouldOpen ? 'Collapse all' : 'Expand all';
      });
    }
  });

  /* ------------------------------------------------------------------
     Service directory: search, filter, expand, deep links
  ------------------------------------------------------------------ */
  const serviceRoot = $('[data-service-filter]');
  if (serviceRoot) {
    const cards = $$('[data-service][data-category]', serviceRoot);
    const chips = $$('[data-service-cat]', serviceRoot);
    const searchInput = $('[data-service-search]', serviceRoot);
    const clearSearch = $('[data-service-clear]', serviceRoot);
    const countEl = $('[data-service-count]', serviceRoot);
    const emptyEl = $('[data-service-empty]', serviceRoot);
    const capStatus = $('[data-cap-status]');
    const resetButtons = $$('[data-service-reset]', serviceRoot);
    const state = { category: 'all', query: '' };

    function applyServiceFilters() {
      let shown = 0;
      const query = state.query.trim().toLowerCase();
      cards.forEach((card) => {
        const categoryMatch = state.category === 'all' || card.getAttribute('data-category') === state.category;
        const haystack = (card.getAttribute('data-search') || '') + ' ' + card.textContent.toLowerCase();
        const queryMatch = !query || haystack.indexOf(query) !== -1;
        const show = categoryMatch && queryMatch;
        card.hidden = !show;
        if (show) shown += 1;
      });

      if (countEl) countEl.textContent = 'Showing ' + shown + ' of ' + cards.length + ' services';
      if (capStatus) {
        const activeChip = chips.find((chip) => chip.getAttribute('data-service-cat') === state.category);
        const label = state.category === 'all' || !activeChip ? 'All services' : activeChip.textContent.trim();
        capStatus.textContent = 'Showing ' + shown + ' of ' + cards.length + ' · ' + label;
      }
      if (emptyEl) emptyEl.hidden = shown !== 0;
      if (clearSearch) clearSearch.hidden = !state.query;
      const filtered = state.category !== 'all' || Boolean(state.query);
      resetButtons.forEach((button) => { button.hidden = !filtered; });
    }

    function setCategory(category) {
      state.category = category;
      chips.forEach((chip) => {
        const active = chip.getAttribute('data-service-cat') === category;
        chip.classList.toggle('is-active', active);
        chip.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      syncCapBoard(category);
      applyServiceFilters();
    }

    const capRows = $$('[data-cap-filter]');
    function syncCapBoard(category) {
      capRows.forEach((row) => {
        const active = row.getAttribute('data-cap-filter') === category;
        row.classList.toggle('is-active', active);
        row.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
    }
    capRows.forEach((row) => {
      row.addEventListener('click', () => {
        const category = row.getAttribute('data-cap-filter');
        setCategory(state.category === category ? 'all' : category);
      });
    });

    chips.forEach((chip) => {
      chip.addEventListener('click', () => setCategory(chip.getAttribute('data-service-cat')));
    });

    if (searchInput) {
      searchInput.addEventListener('input', debounce(() => {
        state.query = searchInput.value;
        applyServiceFilters();
      }, 120));
    }

    if (clearSearch) {
      clearSearch.addEventListener('click', () => {
        if (searchInput) {
          searchInput.value = '';
          searchInput.focus();
        }
        state.query = '';
        applyServiceFilters();
      });
    }

    function resetServiceFilters() {
      if (searchInput) searchInput.value = '';
      state.query = '';
      setCategory('all');
    }

    resetButtons.forEach((button) => {
      button.addEventListener('click', resetServiceFilters);
    });

    function expandServiceCard(card, shouldScroll) {
      const toggle = $('[data-service-toggle]', card);
      const details = $('[data-service-details]', card);
      if (!toggle || !details) return;
      toggle.setAttribute('aria-expanded', 'true');
      details.classList.add('is-open');
      const label = toggle.querySelector('span');
      if (label) label.textContent = 'Hide details';
      card.classList.add('is-highlighted');
      if (shouldScroll) {
        window.setTimeout(() => {
          const top = card.getBoundingClientRect().top + window.scrollY - 110;
          window.scrollTo({ top, behavior: reduceMotion ? 'auto' : 'smooth' });
          toggle.focus({ preventScroll: true });
        }, 30);
      }
      window.setTimeout(() => card.classList.remove('is-highlighted'), 1800);
    }

    $$('[data-service-toggle]').forEach((toggle) => {
      toggle.addEventListener('click', () => {
        const card = toggle.closest('[data-service]');
        const details = $('[data-service-details]', card);
        const open = toggle.getAttribute('aria-expanded') === 'true';
        toggle.setAttribute('aria-expanded', open ? 'false' : 'true');
        if (details) details.classList.toggle('is-open', !open);
        const label = toggle.querySelector('span');
        if (label) label.textContent = open ? "What's involved" : 'Hide details';
      });
    });

    $$('[data-jump-to]', serviceRoot).forEach((button) => {
      button.addEventListener('click', () => {
        const selector = button.getAttribute('data-jump-to');
        const target = selector ? $(selector) : null;
        if (!target) return;
        resetServiceFilters();
        expandServiceCard(target, true);
      });
    });

    function handleServiceHash() {
      const hash = window.location.hash;
      if (!hash || hash.length < 2) return;
      const target = document.getElementById(hash.slice(1));
      if (!target || !target.matches('[data-service]')) return;
      resetServiceFilters();
      expandServiceCard(target, true);
    }

    applyServiceFilters();
    window.setTimeout(handleServiceHash, 120);
    window.addEventListener('hashchange', handleServiceHash);
  }

  /* ------------------------------------------------------------------
     Tabs
  ------------------------------------------------------------------ */
  $$('[data-tabs]').forEach((root) => {
    const tabs = $$('[data-tab]', root);
    const panels = $$('[data-tab-panel]', root);
    if (!tabs.length) return;

    function activate(tab, focus) {
      const value = tab.getAttribute('data-tab');
      tabs.forEach((item) => {
        const active = item === tab;
        item.classList.toggle('is-active', active);
        item.setAttribute('aria-selected', active ? 'true' : 'false');
        item.setAttribute('tabindex', active ? '0' : '-1');
      });
      panels.forEach((panel) => {
        const active = panel.getAttribute('data-tab-panel') === value;
        panel.classList.toggle('is-active', active);
        panel.hidden = !active;
      });
      if (focus) tab.focus();
    }

    tabs.forEach((tab) => {
      tab.addEventListener('click', () => activate(tab));
      tab.addEventListener('keydown', (event) => {
        const index = tabs.indexOf(tab);
        let nextIndex = null;
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') nextIndex = (index + 1) % tabs.length;
        if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') nextIndex = (index - 1 + tabs.length) % tabs.length;
        if (event.key === 'Home') nextIndex = 0;
        if (event.key === 'End') nextIndex = tabs.length - 1;
        if (nextIndex !== null) {
          event.preventDefault();
          activate(tabs[nextIndex], true);
        }
      });
    });
  });

  /* ------------------------------------------------------------------
     Review filters
  ------------------------------------------------------------------ */
  $$('[data-review-filter]').forEach((root) => {
    const buttons = $$('[data-review-cat]', root);
    const reviews = $$('[data-review]', root);
    const empty = $('[data-review-empty]', root);

    function filter(category) {
      let shown = 0;
      reviews.forEach((review) => {
        const show = category === 'all' || review.getAttribute('data-cat') === category;
        review.hidden = !show;
        if (show) shown += 1;
      });
      buttons.forEach((button) => {
        const active = button.getAttribute('data-review-cat') === category;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      if (empty) empty.hidden = shown !== 0;
    }

    buttons.forEach((button) => {
      button.addEventListener('click', () => {
        const category = button.getAttribute('data-review-cat');
        filter(category);
        trackEvent('review_filter', { category: category });
      });
    });
  });

  /* ------------------------------------------------------------------
     Claim checklist (saved locally)
  ------------------------------------------------------------------ */
  $$('[data-claim-checklist]').forEach((root) => {
    const key = root.getAttribute('data-claim-key') || 'mla-claim';
    const inputs = $$('[data-claim-item]', root);
    const progress = $('[data-claim-progress]', root);
    const bar = $('[data-claim-bar]', root);
    const dial = $('[data-claim-dial]', root);
    const ring = $('[data-claim-ring]', root);
    const dialCount = $('[data-claim-dial-count]', root);
    const reset = $('[data-claim-reset]', root);

    function readState() {
      try {
        const value = window.localStorage.getItem(key);
        return value ? JSON.parse(value) : [];
      } catch (error) {
        return [];
      }
    }

    function saveState() {
      try {
        window.localStorage.setItem(key, JSON.stringify(inputs.map((input) => input.checked)));
      } catch (error) {
        /* Storage can be unavailable; progress still works for this visit. */
      }
    }

    function updateProgress() {
      const checked = inputs.filter((input) => input.checked).length;
      const ratio = inputs.length ? checked / inputs.length : 0;
      if (progress) progress.textContent = checked + ' of ' + inputs.length + ' ready';
      if (bar) bar.style.width = ratio * 100 + '%';
      if (ring) {
        const radius = ring.r && ring.r.baseVal ? ring.r.baseVal.value : 21;
        ring.style.strokeDashoffset = String(2 * Math.PI * radius * (1 - ratio));
      }
      if (dialCount) dialCount.textContent = checked + '/' + inputs.length;
      if (dial) dial.classList.toggle('is-complete', inputs.length > 0 && checked === inputs.length);
    }

    const saved = readState();
    inputs.forEach((input, index) => {
      input.checked = Boolean(saved[index]);
      input.addEventListener('change', () => {
        saveState();
        updateProgress();
      });
    });
    updateProgress();

    if (reset) {
      reset.addEventListener('click', () => {
        inputs.forEach((input) => { input.checked = false; });
        saveState();
        updateProgress();
        showToast('Checklist reset.', 'info');
      });
    }
  });

  /* ------------------------------------------------------------------
     Copy to clipboard
  ------------------------------------------------------------------ */
  async function copyText(value) {
    if (!value) return false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(value);
        return true;
      }
    } catch (error) {
      /* Fall back below. */
    }
    try {
      const textarea = document.createElement('textarea');
      textarea.value = value;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      const ok = document.execCommand('copy');
      textarea.remove();
      return ok;
    } catch (error) {
      return false;
    }
  }

  $$('[data-copy]').forEach((button) => {
    button.addEventListener('click', async () => {
      const value = button.getAttribute('data-copy');
      const message = button.getAttribute('data-copy-message') || 'Copied';
      const ok = await copyText(value);
      showToast(ok ? message : 'Could not copy — please select it manually.', ok ? 'success' : 'error');
    });
  });

  /* ------------------------------------------------------------------
     Contact form: live summary + AJAX submit
  ------------------------------------------------------------------ */
  const contactForm = $('[data-contact-form]');
  const contactSuccess = $('[data-contact-success]');
  const contactCard = $('.form-card');

  function updateContactSummary() {
    if (!contactForm) return;
    const nameInput = $('[data-summary-source="name"]', contactForm);
    const phoneInput = $('[data-summary-source="phone"]', contactForm);
    const serviceInput = $('#service-needed', contactForm);
    const timeInput = contactForm.querySelector('input[name="preferred_time"]:checked');
    const nameEl = $('[data-summary-name]', contactForm);
    const phoneEl = $('[data-summary-phone]', contactForm);
    const serviceEl = $('[data-summary-service]', contactForm);
    const timeEl = $('[data-summary-time]', contactForm);

    if (nameEl) nameEl.textContent = nameInput && nameInput.value.trim() ? nameInput.value.trim() : 'you';
    if (phoneEl) phoneEl.textContent = phoneInput && phoneInput.value.trim() ? phoneInput.value.trim() : 'your number';
    if (serviceEl) serviceEl.textContent = serviceInput && serviceInput.value ? serviceInput.value : 'a general enquiry';
    if (timeEl) timeEl.textContent = timeInput ? timeInput.value.charAt(0).toLowerCase() + timeInput.value.slice(1) : 'anytime today';
  }

  if (contactForm) {
    $$('[data-service-choice]').forEach((button) => {
      button.addEventListener('click', () => {
        const value = button.getAttribute('data-service-choice');
        const hidden = $('#service-needed', contactForm);
        if (hidden) hidden.value = value;
        $$('[data-service-choice]', contactForm).forEach((chip) => {
          const active = chip === button;
          chip.classList.toggle('is-active', active);
          chip.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        updateContactSummary();
      });
    });

    $$('[data-summary-source]', contactForm).forEach((input) => {
      input.addEventListener('input', updateContactSummary);
    });

    $$('input[name="preferred_time"]', contactForm).forEach((input) => {
      input.addEventListener('change', updateContactSummary);
    });

    const charInput = $('[data-char-input]', contactForm);
    const charCount = $('[data-char-count]', contactForm);
    if (charInput && charCount) {
      const updateCount = () => {
        charCount.textContent = charInput.value.length + ' / ' + charInput.maxLength;
      };
      charInput.addEventListener('input', updateCount);
      updateCount();
    }

    $$('input, textarea, select', contactForm).forEach((input) => {
      input.addEventListener('input', () => clearErrorFor(input));
    });

    const phoneInput = $('[name="phone_number"]', contactForm);
    if (phoneInput) {
      phoneInput.addEventListener('blur', () => {
        const digits = phoneInput.value.replace(/\D/g, '');
        if (digits.length === 10) {
          phoneInput.value = '(' + digits.slice(0, 3) + ') ' + digits.slice(3, 6) + '-' + digits.slice(6);
          updateContactSummary();
        }
      });
    }

    updateContactSummary();

    contactForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const alertEl = $('[data-form-alert]');
      if (alertEl) alertEl.hidden = true;
      $$('[data-error-for]', contactForm).forEach((el) => {
        el.hidden = true;
        el.textContent = '';
      });
      $$('[aria-invalid="true"]', contactForm).forEach((el) => el.removeAttribute('aria-invalid'));

      const errors = validateBasics(contactForm);
      if (Object.keys(errors).length) {
        showFormErrors(contactForm, errors, alertEl);
        const firstKey = Object.keys(errors)[0];
        const firstInput = contactForm.querySelector('[name="' + firstKey + '"]');
        if (firstInput) firstInput.focus();
        return;
      }

      setSubmitState(contactForm, true);
      try {
        const data = await submitAjaxForm(contactForm);
        contactForm.hidden = true;
        if (contactSuccess) {
          contactSuccess.hidden = false;
          const message = $('[data-contact-success-message]', contactSuccess);
          if (message) message.textContent = data.message || "We'll call you back during shop hours.";
          const heading = $('h2', contactSuccess);
          if (heading) {
            heading.setAttribute('tabindex', '-1');
            heading.focus({ preventScroll: true });
          }
          if (contactCard) {
            const top = contactCard.getBoundingClientRect().top + window.scrollY - 110;
            window.scrollTo({ top, behavior: reduceMotion ? 'auto' : 'smooth' });
          }
        }
        showToast('Callback request sent.', 'success');
        trackEvent('callback_submit', { reference: data.reference || '' });
      } catch (error) {
        const payload = error.payload || {};
        showFormErrors(contactForm, payload.errors || {}, alertEl);
        if (!payload.errors) showToast(error.message || 'Could not send the request. Please call the shop.', 'error');
      } finally {
        setSubmitState(contactForm, false);
      }
    });

    const resetContact = $('[data-contact-reset]');
    if (resetContact) {
      resetContact.addEventListener('click', () => {
        contactForm.reset();
        contactForm.hidden = false;
        if (contactSuccess) contactSuccess.hidden = true;
        const hidden = $('#service-needed', contactForm);
        if (hidden) hidden.value = 'General enquiry';
        $$('[data-service-choice]', contactForm).forEach((chip) => {
          const active = chip.getAttribute('data-service-choice') === 'General enquiry';
          chip.classList.toggle('is-active', active);
          chip.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        const alertEl = $('[data-form-alert]');
        if (alertEl) alertEl.hidden = true;
        updateContactSummary();
        if (charInput && charCount) charCount.textContent = '0 / ' + charInput.maxLength;
        const nameField = $('#contact-name');
        if (nameField) nameField.focus();
      });
    }
  }

  /* ------------------------------------------------------------------
     MPI claim navigator
     A four-question wizard that produces a plain-language next step.
     It never claims to approve coverage.
  ------------------------------------------------------------------ */
  const claimRoot = $('[data-claim-navigator]');
  if (claimRoot && claimRoot.getAttribute('data-completed') !== 'true') {
    const claimSteps = $$('[data-claim-step]', claimRoot);
    const claimHeading = $('[data-claim-heading]', claimRoot);
    const claimCount = $('[data-claim-step-count]', claimRoot);
    const claimProgress = $('[data-claim-progress]', claimRoot);
    const claimWizard = $('[data-claim-wizard]', claimRoot);
    const claimResult = $('[data-claim-result]', claimRoot);
    const claimLead = $('[data-claim-lead]', claimRoot);
    const claimResultTitle = $('[data-claim-result-title]', claimRoot);
    const claimResultCopy = $('[data-claim-result-copy]', claimRoot);
    const claimResultList = $('[data-claim-result-list]', claimRoot);
    const claimResultIcon = $('[data-claim-result-icon]', claimRoot);
    const claimForm = $('[data-claim-form]', claimRoot);
    const claimBack = $('[data-claim-back]', claimRoot);
    const claimQuestions = [
      'Was anyone injured?',
      'Do you have an MPI claim number?',
      'Is the vehicle drivable?',
      'Are you the registered owner?'
    ];
    const claimAnswers = {};
    const claimKeys = ['anyone_injured', 'has_claim', 'vehicle_drivable', 'registered_owner'];

    function claimSyncButtons() {
      $$('[data-claim-answer]', claimRoot).forEach((button) => {
        const key = button.getAttribute('data-claim-answer');
        button.setAttribute('aria-pressed', claimAnswers[key] === button.getAttribute('data-value') ? 'true' : 'false');
      });
    }

    function claimSyncHidden() {
      if (!claimForm) return;
      claimKeys.forEach((key) => {
        const input = claimForm.querySelector('[name="' + key + '"]');
        if (input) input.value = claimAnswers[key] || '';
      });
      const summary = claimForm.querySelector('[name="result_summary"]');
      if (summary) {
        const answered = claimKeys.filter((key) => claimAnswers[key]);
        const title = (claimResultTitle ? claimResultTitle.textContent : '').replace(/\.+$/, '');
        summary.value = answered.length
          ? 'Navigator answers — ' + answered.map((key) => key.replace(/_/g, ' ') + ': ' + claimAnswers[key]).join('; ') + '. Suggested next step: ' + title + '.'
          : '';
      }
    }

    function claimSetFocus(el) {
      if (!el) return;
      el.setAttribute('tabindex', '-1');
      el.focus({ preventScroll: true });
    }

    function claimShowStep(index) {
      if (!claimSteps.length) return;
      const safeIndex = Math.max(0, Math.min(index, claimSteps.length - 1));
      claimSteps.forEach((step, stepIndex) => {
        step.hidden = stepIndex !== safeIndex;
      });
      claimAnswers.current = safeIndex;
      if (claimWizard) claimWizard.hidden = false;
      if (claimResult) claimResult.hidden = true;
      if (claimLead) claimLead.hidden = true;
      if (claimHeading) claimHeading.textContent = claimQuestions[safeIndex];
      if (claimCount) claimCount.textContent = 'Step ' + (safeIndex + 1) + ' of ' + claimSteps.length;
      if (claimProgress) claimProgress.style.width = (safeIndex / claimSteps.length) * 100 + '%';
      if (claimBack) claimBack.hidden = safeIndex === 0;
      claimSyncButtons();
      claimSetFocus(claimHeading);
    }

    function claimShowResult() {
      if (!claimResult) return;
      const injured = claimAnswers.anyone_injured === 'yes';
      const noClaim = claimAnswers.has_claim === 'no';
      const unsureClaim = claimAnswers.has_claim === 'unsure';
      const notDrivable = claimAnswers.vehicle_drivable === 'no';
      const notOwner = claimAnswers.registered_owner === 'no';
      let title = 'Book an estimate at Maple Leaf.';
      let copy = 'Bring the vehicle when you are ready. We will inspect the damage, explain the repair options and confirm the next step.';
      let icon = 'verified_user';
      let items = [
        'Bring the vehicle registration and your driver\'s licence.',
        'If you have an MPI claim number, bring that paperwork too.',
        'Request a preferred drop-off window or call the shop.'
      ];

      if (injured) {
        title = 'Get medical care first, then call MPI.';
        copy = 'If anyone was hurt, medical care comes before the repair decision. Once everyone is safe, MPI can guide the claim.';
        icon = 'emergency';
        items = [
          'Call 911 if anyone needs urgent medical help.',
          'Tell MPI about the injury when you open or update the claim.',
          'Call the shop when the vehicle is ready to be assessed.'
        ];
      } else if (notDrivable) {
        title = 'Call the shop before you arrange a tow.';
        copy = 'If the vehicle is not safe to drive, do not move it on the road. We can talk through intake, towing and what to bring before it arrives.';
        icon = 'car_crash';
        items = [
          'Do not drive if the vehicle is unsafe or leaking fluid.',
          'Call the shop to confirm intake and towing arrangements.',
          'Have the registration, driver\'s licence and claim number ready.'
        ];
      } else if (noClaim) {
        title = 'Start with MPI, then book an estimate.';
        copy = 'You can have the repair looked at, but the claim starts with MPI. Opening the claim first keeps the paperwork and the repair plan moving together.';
        icon = 'add_card';
        items = [
          'Call MPI to open a claim and get a claim number.',
          'Bring the claim number, registration and driver\'s licence.',
          'Request a drop-off window when you are ready for the estimate.'
        ];
      } else if (unsureClaim) {
        title = 'Check with MPI, then book an estimate.';
        copy = 'If you are not sure whether a claim is open, check with MPI before the visit. We can still look at the repair side, but MPI decides what a claim covers.';
        icon = 'help';
        items = [
          'Call MPI or check your online account for the claim status.',
          'Write down the claim number if one exists.',
          'Bring the registration and driver\'s licence to the shop.'
        ];
      } else if (notOwner) {
        title = 'Bring the registered owner\'s paperwork.';
        copy = 'The repair paperwork usually needs to match the registered owner. Ask the owner what authorisation the shop will need before the vehicle is dropped off.';
        icon = 'group';
        items = [
          'Confirm who the registered owner is.',
          'Ask about a signed authorisation if the owner is not coming.',
          'Bring the registration, driver\'s licence and claim number.'
        ];
      }

      if (claimResultTitle) claimResultTitle.textContent = title;
      if (claimResultCopy) claimResultCopy.textContent = copy;
      if (claimResultIcon) claimResultIcon.textContent = icon;
      if (claimResultList) {
        claimResultList.innerHTML = '';
        items.forEach((item) => {
          const li = document.createElement('li');
          li.textContent = item;
          claimResultList.appendChild(li);
        });
      }
      claimAnswers.completed = true;
      if (claimWizard) claimWizard.hidden = true;
      claimResult.hidden = false;
      if (claimLead) claimLead.hidden = true;
      if (claimBack) claimBack.hidden = true;
      if (claimCount) claimCount.textContent = 'Result';
      if (claimProgress) claimProgress.style.width = '100%';
      claimSyncHidden();
      trackEvent('claim_navigator_complete', { injured: injured, drivable: !notDrivable, has_claim: claimAnswers.has_claim || '' });
      claimSetFocus(claimResultTitle);
    }

    $$('[data-claim-answer]', claimRoot).forEach((button) => {
      button.addEventListener('click', () => {
        const key = button.getAttribute('data-claim-answer');
        claimAnswers[key] = button.getAttribute('data-value');
        claimSyncButtons();
        if (!claimRoot.getAttribute('data-started')) {
          claimRoot.setAttribute('data-started', 'true');
          trackEvent('claim_navigator_start', { first_answer: key });
        }
        if (key === 'anyone_injured' && claimAnswers[key] === 'yes') {
          claimShowResult();
          return;
        }
        const next = (claimAnswers.current || 0) + 1;
        if (next >= claimSteps.length) {
          claimShowResult();
        } else {
          claimShowStep(next);
        }
      });
    });

    if (claimBack) {
      claimBack.addEventListener('click', () => {
        claimShowStep((claimAnswers.current || 0) - 1);
      });
    }

    $$('[data-claim-restart]', claimRoot).forEach((button) => {
      button.addEventListener('click', () => {
        ['anyone_injured', 'has_claim', 'vehicle_drivable', 'registered_owner'].forEach((key) => delete claimAnswers[key]);
        claimAnswers.completed = false;
        claimSyncHidden();
        claimShowStep(0);
      });
    });

    const claimOpenForm = $('[data-claim-open-form]', claimRoot);
    if (claimOpenForm) {
      claimOpenForm.addEventListener('click', () => {
        if (claimWizard) claimWizard.hidden = true;
        if (claimResult) claimResult.hidden = true;
        if (claimLead) claimLead.hidden = false;
        claimSyncHidden();
        const nameInput = claimLead && claimLead.querySelector('[name="full_name"]');
        if (nameInput) nameInput.focus({ preventScroll: true });
      });
    }

    if (claimForm) {
      claimForm.addEventListener('submit', () => {
        claimSyncHidden();
        trackEvent('claim_navigator_submit', { injured: claimAnswers.anyone_injured || '' });
      });
    }

    if (claimRoot.getAttribute('data-form-open') === 'true') {
      if (claimWizard) claimWizard.hidden = true;
      if (claimResult) claimResult.hidden = true;
      if (claimLead) claimLead.hidden = false;
      if (claimCount) claimCount.textContent = 'Details';
    } else {
      claimShowStep(0);
    }
  }

  /* ------------------------------------------------------------------
     Windshield chip checker
  ------------------------------------------------------------------ */
  const chipRoot = $('[data-chip-checker]');
  if (chipRoot) {
    const chipResult = $('[data-chip-result]', chipRoot);
    const chipTitle = $('[data-chip-result-title]', chipRoot);
    const chipCopy = $('[data-chip-result-copy]', chipRoot);
    const chipList = $('[data-chip-result-list]', chipRoot);
    const chipIcon = $('[data-chip-result-icon]', chipRoot);
    const chipProgress = $('[data-chip-progress-label]', chipRoot);
    const chipState = {};

    function chipUpdateProgress() {
      const answered = ['type', 'size', 'location'].filter((key) => chipState[key]).length;
      if (chipProgress) chipProgress.textContent = answered + ' of 3 answered';
      return answered;
    }

    function chipShowResult() {
      const replace = chipState.size === 'large' || chipState.location === 'edge';
      const assess = !replace && (chipState.type === 'crack' || chipState.location === 'driver' || chipState.size === 'medium');
      let title = 'A resin repair may be possible.';
      let copy = 'Small, round chips away from the driver\'s line of sight are often good candidates for resin repair. The shop confirms after looking at the glass.';
      let icon = 'build_circle';
      let items = [
        'Keep the chip clean and avoid pressing on it.',
        'Avoid temperature shocks, car washes and slamming doors.',
        'Have the glass checked before the damage spreads.'
      ];

      if (replace) {
        title = 'Plan for a replacement assessment.';
        copy = 'Large damage, a crack or damage near the edge is usually beyond a resin repair. A replacement is confirmed after the glass is inspected.';
        icon = 'car_repair';
        items = [
          'Do not wait if the crack is growing or the vehicle is unsafe.',
          'Ask about MPI direct billing if this is an eligible claim.',
          'Call the shop to confirm glass availability for your vehicle.'
        ];
      } else if (assess) {
        title = 'Have the glass inspected before deciding.';
        copy = 'The size, depth and position matter — especially in the driver\'s line of sight. This guide cannot confirm whether a repair will hold.';
        icon = 'search';
        items = [
          'Do not assume a chip is safe because it looks small.',
          'Bring the vehicle in for an in-person glass assessment.',
          'Ask about repair first; replacement is used when repair will not hold.'
        ];
      }

      if (chipTitle) chipTitle.textContent = title;
      if (chipCopy) chipCopy.textContent = copy;
      if (chipIcon) chipIcon.textContent = icon;
      if (chipList) {
        chipList.innerHTML = '';
        items.forEach((item) => {
          const li = document.createElement('li');
          li.textContent = item;
          chipList.appendChild(li);
        });
      }
      if (chipResult) chipResult.hidden = false;
      trackEvent('chip_checker_result', { type: chipState.type || '', size: chipState.size || '', location: chipState.location || '', recommendation: replace ? 'replace' : assess ? 'assess' : 'repair' });
      if (chipTitle) {
        chipTitle.setAttribute('tabindex', '-1');
        chipTitle.focus({ preventScroll: true });
      }
    }

    const chipGroups = [
      { key: 'type', attr: 'data-chip-type' },
      { key: 'size', attr: 'data-chip-size' },
      { key: 'location', attr: 'data-chip-location' }
    ];
    chipGroups.forEach((group) => {
      $$('[' + group.attr + ']', chipRoot).forEach((button) => {
        button.addEventListener('click', () => {
          chipState[group.key] = button.getAttribute(group.attr);
          $$('[' + group.attr + ']', chipRoot).forEach((item) => {
            item.setAttribute('aria-pressed', item === button ? 'true' : 'false');
          });
          if (chipUpdateProgress() === 3) chipShowResult();
        });
      });
    });
    chipUpdateProgress();
  }

  /* ------------------------------------------------------------------
     Repair vs replace comparison
  ------------------------------------------------------------------ */
  const compareRoot = $('[data-repair-compare]');
  if (compareRoot) {
    const compareResult = $('[data-compare-result]', compareRoot);
    const compareTitle = $('[data-compare-result-title]', compareRoot);
    const compareCopy = $('[data-compare-result-copy]', compareRoot);
    const compareRepairList = $('[data-compare-repair-list]', compareRoot);
    const compareReplaceList = $('[data-compare-replace-list]', compareRoot);
    const compareIcon = $('[data-compare-result-icon]', compareRoot);
    const compareProgress = $('[data-repair-progress-label]', compareRoot);
    const compareState = {};
    let compareTracked = false;

    function compareUpdateProgress() {
      const answered = ['damage', 'age', 'payment'].filter((key) => compareState[key]).length;
      if (compareProgress) compareProgress.textContent = answered + ' of 3 answered';
      return answered;
    }

    function fillCompareList(target, items) {
      if (!target) return;
      target.innerHTML = '';
      items.forEach((item) => {
        const li = document.createElement('li');
        li.textContent = item;
        target.appendChild(li);
      });
    }

    function compareShowResult() {
      const damage = compareState.damage;
      const age = compareState.age;
      const payment = compareState.payment;
      let title = 'The shop confirms the scope after inspection.';
      let copy = 'Repair and replacement both depend on what is found when the vehicle is inspected. Hidden damage or parts availability can change the recommendation.';
      let icon = 'balance';
      let repairItems = [
        'The part can be safely straightened, refinished or sealed.',
        'The structure and safety systems are intact.',
        'A repair restores safe operation without hidden compromise.'
      ];
      let replaceItems = [
        'The part is cracked, crushed or structurally compromised.',
        'A repair would not restore safe operation.',
        'The claim or warranty requires a new part.'
      ];

      if (damage === 'cosmetic') {
        title = 'Repair is often the first option for cosmetic damage.';
        copy = 'Dents, scratches and paint damage are usually repaired rather than replaced. The exception is a panel that cannot be straightened or finished properly.';
        icon = 'format_paint';
      } else if (damage === 'structural') {
        title = 'A structural inspection sets the scope.';
        copy = 'Collision damage can hide behind the panel. The shop inspects the structure and safety systems before saying whether repair or replacement is the right route.';
        icon = 'car_crash';
        replaceItems = [
          'The structure is bent or crushed beyond a safe repair.',
          'Safety systems or mounting points are compromised.',
          'The claim or manufacturer guidance calls for replacement.'
        ];
      } else if (damage === 'glass') {
        title = 'Glass damage is assessed in person.';
        copy = 'A small chip away from the driver\'s view may be repairable. Cracks, edge damage and driver-line damage usually point toward replacement.';
        icon = 'car_repair';
        repairItems = [
          'The chip is small and away from the driver\'s line of sight.',
          'The damage has not spread into a crack.',
          'A resin repair can restore the glass without replacing it.'
        ];
        replaceItems = [
          'The damage is a crack or reaches the edge of the glass.',
          'The chip sits in the driver\'s critical viewing area.',
          'A repair would not restore a safe, clear windshield.'
        ];
      } else if (damage === 'mechanical') {
        title = 'Diagnosis comes before the repair-or-replace call.';
        copy = 'A mechanical fault needs to be isolated first. Replacing parts before testing is how a repair bill grows without solving the problem.';
        icon = 'build';
      }

      if (age === 'old') {
        replaceItems = replaceItems.concat('The vehicle\'s age or parts availability makes a replacement the more practical route.');
      } else if (age === 'new') {
        repairItems = repairItems.concat('Keeping the original factory panels and finish has value on a newer vehicle.');
      }

      if (payment === 'mpi') {
        copy += ' Because this is an MPI claim, the adjuster\'s decision and the shop\'s repair plan both matter. MPI decides coverage; the shop confirms the repair scope.';
      } else if (payment === 'private') {
        copy += ' On a private repair, you approve the scope before work starts. Ask for the options in writing.';
      }

      if (compareTitle) compareTitle.textContent = title;
      if (compareCopy) compareCopy.textContent = copy;
      if (compareIcon) compareIcon.textContent = icon;
      fillCompareList(compareRepairList, repairItems);
      fillCompareList(compareReplaceList, replaceItems);
      if (compareResult) compareResult.hidden = false;
      if (!compareTracked) {
        compareTracked = true;
        trackEvent('repair_replace_result', { damage: damage || '', age: age || '', payment: payment || '' });
      }
      if (compareTitle) {
        compareTitle.setAttribute('tabindex', '-1');
        compareTitle.focus({ preventScroll: true });
      }
    }

    const compareGroups = [
      { key: 'damage', attr: 'data-compare-damage' },
      { key: 'age', attr: 'data-compare-age' },
      { key: 'payment', attr: 'data-compare-payment' }
    ];
    compareGroups.forEach((group) => {
      $$('[' + group.attr + ']', compareRoot).forEach((button) => {
        button.addEventListener('click', () => {
          compareState[group.key] = button.getAttribute(group.attr);
          $$('[' + group.attr + ']', compareRoot).forEach((item) => {
            item.setAttribute('aria-pressed', item === button ? 'true' : 'false');
          });
          if (compareUpdateProgress() === 3) compareShowResult();
        });
      });
    });
    compareUpdateProgress();
  }

  /* ------------------------------------------------------------------
     Damage photo preview
  ------------------------------------------------------------------ */
  const photoForm = $('[data-photo-form]');
  if (photoForm) {
    const photoInput = $('input[type="file"][name="photos"]', photoForm);
    const photoPreview = $('[data-photo-preview]', photoForm);
    const photoDrop = $('[data-photo-drop]', photoForm);
    const photoMaxFiles = parseInt(photoForm.getAttribute('data-photo-max-files'), 10) || 4;
    const photoMaxBytes = parseInt(photoForm.getAttribute('data-photo-max-bytes'), 10) || 6 * 1024 * 1024;
    const photoMaxMb = Math.round(photoMaxBytes / (1024 * 1024));
    const photoTypes = ['image/jpeg', 'image/png', 'image/webp'];
    let photoObjectUrls = [];
    let photoStarted = false;

    function photoFiles() {
      return photoInput && photoInput.files ? Array.from(photoInput.files) : [];
    }

    function setPhotoFiles(files) {
      if (!photoInput) return;
      const transfer = new DataTransfer();
      files.slice(0, photoMaxFiles).forEach((file) => transfer.items.add(file));
      photoInput.files = transfer.files;
      renderPhotoPreviews();
    }

    function renderPhotoPreviews() {
      if (!photoPreview) return;
      photoObjectUrls.forEach((url) => URL.revokeObjectURL(url));
      photoObjectUrls = [];
      photoPreview.innerHTML = '';
      const files = photoFiles();
      files.forEach((file, index) => {
        const figure = document.createElement('figure');
        figure.className = 'photo-preview-item';
        const image = document.createElement('img');
        const url = URL.createObjectURL(file);
        photoObjectUrls.push(url);
        image.src = url;
        image.alt = 'Selected damage photo ' + (index + 1);
        const caption = document.createElement('figcaption');
        caption.textContent = file.name;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'photo-preview-remove';
        remove.setAttribute('aria-label', 'Remove ' + file.name);
        remove.textContent = '×';
        remove.addEventListener('click', () => {
          setPhotoFiles(photoFiles().filter((item, itemIndex) => itemIndex !== index));
        });
        figure.append(image, caption, remove);
        photoPreview.appendChild(figure);
      });
      if (files.length && !photoStarted) {
        photoStarted = true;
        trackEvent('photo_request_start', { photos: files.length });
      }
    }

    if (photoInput) {
      photoInput.addEventListener('change', () => {
        let files = photoFiles();
        const valid = [];
        files.forEach((file) => {
          if (file.size > photoMaxBytes) {
            showToast(file.name + ' is larger than ' + photoMaxMb + ' MB.', 'error');
            return;
          }
          if (file.type && photoTypes.indexOf(file.type.toLowerCase()) === -1) {
            showToast(file.name + ' is not a supported image type.', 'error');
            return;
          }
          valid.push(file);
        });
        if (valid.length > photoMaxFiles) {
          showToast('Please choose up to ' + photoMaxFiles + ' photos.', 'info');
        }
        if (valid.length !== files.length) {
          setPhotoFiles(valid);
        } else {
          renderPhotoPreviews();
        }
      });
    }

    if (photoDrop) {
      ['dragenter', 'dragover'].forEach((name) => {
        photoDrop.addEventListener(name, (event) => {
          event.preventDefault();
          photoDrop.classList.add('is-dragover');
        });
      });
      ['dragleave', 'drop'].forEach((name) => {
        photoDrop.addEventListener(name, (event) => {
          event.preventDefault();
          photoDrop.classList.remove('is-dragover');
        });
      });
      photoDrop.addEventListener('drop', (event) => {
        const dropped = event.dataTransfer && event.dataTransfer.files
          ? Array.from(event.dataTransfer.files)
          : [];
        if (dropped.length) setPhotoFiles(photoFiles().concat(dropped));
      });
    }

    window.addEventListener('pagehide', () => {
      photoObjectUrls.forEach((url) => URL.revokeObjectURL(url));
    });

    photoForm.addEventListener('submit', () => {
      trackEvent('photo_request_submit', { photos: photoFiles().length });
    });
  }

  /* ------------------------------------------------------------------
     Booking form analytics
  ------------------------------------------------------------------ */
  const bookingForm = $('[data-booking-form]');
  if (bookingForm) {
    let bookingStarted = false;
    bookingForm.addEventListener('focusin', () => {
      if (bookingStarted) return;
      bookingStarted = true;
      trackEvent('booking_start');
    });
    bookingForm.addEventListener('submit', () => {
      trackEvent('booking_submit', { service: (bookingForm.querySelector('[name="service"]') || {}).value || '' });
    });
  }

  /* ------------------------------------------------------------------
     Reveal on scroll: line draw, photo wipe, scan and step rise
  ------------------------------------------------------------------ */
  const revealEls = $$('[data-reveal]');
  document.documentElement.setAttribute('data-js-ready', 'true');
  if (revealEls.length) {
    const revealNow = (el) => el.classList.add('is-revealed');
    if (reduceMotion || !('IntersectionObserver' in window)) {
      revealEls.forEach(revealNow);
    } else {
      const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          revealNow(entry.target);
          revealObserver.unobserve(entry.target);
        });
      }, { threshold: 0.01, rootMargin: '0px 0px 12% 0px' });

      revealEls.forEach((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.top < window.innerHeight * 0.98 && rect.bottom > 0) {
          revealNow(el);
        } else {
          revealObserver.observe(el);
        }
      });
    }
  }

  /* ------------------------------------------------------------------
     Back to top
  ------------------------------------------------------------------ */
  $$('[data-back-to-top]').forEach((button) => {
    button.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
    });
  });

  /* ------------------------------------------------------------------
     Global keyboard handling
  ------------------------------------------------------------------ */
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (isLayerOpen(lightbox)) {
      closeLightbox();
      return;
    }
    if (isLayerOpen(callbackModal)) {
      closeCallbackModal();
      return;
    }
    if (isLayerOpen(mobileLayer)) {
      closeMobileMenu();
      return;
    }
    closeDropdown();
  });
})();
