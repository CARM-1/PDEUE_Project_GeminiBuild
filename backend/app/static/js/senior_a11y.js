/* PDEUE PR #82 — Site-Wide Senior Accessibility (A | A+ | A++), Plane Links & Family Alerts */
(function () {
  'use strict';

  var STORAGE_KEY = 'pdeue_text_scale';
  var VALID_SCALES = { standard: true, large: true, xlarge: true };

  function readStoredScale() {
    try {
      var saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved && VALID_SCALES[saved]) {
        return saved;
      }
    } catch (_err) {
      /* localStorage unavailable in restricted contexts */
    }
    return 'standard';
  }

  function applyScale(scale) {
    var chosen = VALID_SCALES[scale] ? scale : 'standard';
    document.documentElement.setAttribute('data-text-scale', chosen);
    try {
      window.localStorage.setItem(STORAGE_KEY, chosen);
    } catch (_err) {
      /* ignore storage errors */
    }
    var buttons = document.querySelectorAll('#textScaleGroup button[data-scale], .text-scale-btn[data-scale]');
    for (var i = 0; i < buttons.length; i++) {
      var btn = buttons[i];
      var isCurrent = btn.getAttribute('data-scale') === chosen;
      btn.setAttribute('aria-pressed', isCurrent ? 'true' : 'false');
      if (isCurrent) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    }
    return chosen;
  }

  function resolveDoorwayHref(currentHref, targetUrl) {
    if (!targetUrl) return currentHref || '';
    try {
      var baseOrigin = (window.location && window.location.origin && window.location.origin !== 'null')
        ? window.location.origin
        : 'http://localhost';
      var parsedTarget = new URL(targetUrl, baseOrigin);
      if (currentHref) {
        var parsedCurrent = new URL(currentHref, baseOrigin);
        if (parsedCurrent.search) {
          if (!parsedTarget.search) {
            parsedTarget.search = parsedCurrent.search;
          } else {
            var merged = new URLSearchParams(parsedTarget.search);
            var incoming = new URLSearchParams(parsedCurrent.search);
            incoming.forEach(function (val, key) {
              merged.set(key, val);
            });
            parsedTarget.search = '?' + merged.toString();
          }
        }
        if (parsedCurrent.hash) {
          parsedTarget.hash = parsedCurrent.hash;
        }
      }
      return parsedTarget.toString();
    } catch (_err) {
      return targetUrl;
    }
  }

  function lookupDoorwayTarget(doorways, key) {
    if (!doorways || !key) return '';
    if (doorways[key]) return doorways[key];
    if (key === 'admin_tech' && doorways.tech) return doorways.tech;
    if (key === 'tech' && doorways.admin_tech) return doorways.admin_tech;
    return '';
  }

  function applyPlaneDoorways(data) {
    if (!data || !data.doorways) return;
    window.PDEUEPlaneConfig = data;
    if (data.routing_mode === 'multi_domain_air_gapped') {
      var links = document.querySelectorAll('a[data-plane-doorway]');
      for (var i = 0; i < links.length; i++) {
        var el = links[i];
        var key = el.getAttribute('data-plane-doorway');
        var targetUrl = lookupDoorwayTarget(data.doorways, key);
        if (targetUrl) {
          var currentHref = el.getAttribute('href') || '';
          el.setAttribute('href', resolveDoorwayHref(currentHref, targetUrl));
        }
      }
    }
    var ifasBtn = document.getElementById('ifasHandoffBtn');
    var ifasHost = document.getElementById('ifasPortalHost');
    if (ifasHost && data.doorways.ifas_configured && data.doorways.ifas) {
      ifasHost.textContent = data.doorways.ifas;
    }
    if (ifasBtn) {
      ifasBtn.setAttribute('data-ifas-url', data.doorways.ifas || '');
      ifasBtn.setAttribute('data-ifas-target', data.doorways.ifas_production_target || 'https://narratixai.net');
    }
  }

  function resolveDoorwayUrl(key, fallbackHref) {
    var cfg = window.PDEUEPlaneConfig;
    if (cfg && cfg.routing_mode === 'multi_domain_air_gapped' && cfg.doorways) {
      var targetUrl = lookupDoorwayTarget(cfg.doorways, key);
      if (targetUrl) {
        return resolveDoorwayHref(fallbackHref || '', targetUrl);
      }
    }
    return fallbackHref || '';
  }

  function hydratePlaneLinks() {
    if (typeof window.fetch !== 'function') return;
    window.fetch('/api/v1/portal/planes')
      .then(function (resp) { return resp.ok ? resp.json() : null; })
      .then(function (data) { applyPlaneDoorways(data); })
      .catch(function () { /* keep relative defaults cleanly */ });
  }

  function renderNotificationsList(items) {
    var listEl = document.getElementById('familyAlertsList');
    var badgeEl = document.getElementById('familyAlertsCount');
    if (badgeEl) {
      badgeEl.textContent = String(items.length);
    }
    if (!listEl) return;
    listEl.textContent = '';
    if (!items.length) {
      var empty = document.createElement('p');
      empty.textContent = 'No family alerts right now. Check back soon!';
      listEl.appendChild(empty);
      return;
    }
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var card = document.createElement('article');
      card.className = 'family-alert-item';

      var metaTop = document.createElement('div');
      metaTop.className = 'family-alert-meta';
      var tag = document.createElement('span');
      tag.className = 'family-alert-tag';
      tag.textContent = item.category || 'ANNOUNCEMENT';
      var scope = document.createElement('span');
      scope.textContent = item.target_scope || 'ALL_FAMILY';
      metaTop.appendChild(tag);
      metaTop.appendChild(scope);

      var heading = document.createElement('h4');
      heading.textContent = item.title || 'Family Update';

      var body = document.createElement('p');
      body.textContent = item.message || '';

      var metaFoot = document.createElement('div');
      metaFoot.className = 'family-alert-meta';
      var ts = document.createElement('span');
      ts.textContent = (item.created_at_utc || '').slice(0, 10);
      metaFoot.appendChild(ts);

      if (item.action_url && item.action_url.charAt(0) === '/') {
        var link = document.createElement('a');
        link.className = 'family-alert-link';
        link.setAttribute('href', item.action_url);
        link.textContent = 'Open in Family Hub →';
        metaFoot.appendChild(link);
      }

      card.appendChild(metaTop);
      card.appendChild(heading);
      card.appendChild(body);
      card.appendChild(metaFoot);
      listEl.appendChild(card);
    }
  }

  function loadFamilyAlerts() {
    var hasDrawer = document.getElementById('familyAlertsDrawer') || document.getElementById('familyAlertsCount');
    if (!hasDrawer || typeof window.fetch !== 'function') return;
    window.fetch('/api/v1/portal/community/notifications')
      .then(function (resp) { return resp.ok ? resp.json() : null; })
      .then(function (data) {
        if (data && Array.isArray(data.notifications)) {
          renderNotificationsList(data.notifications);
        }
      })
      .catch(function () { /* fail silent; never break portal */ });
  }

  function toggleFamilyAlerts(forceOpen) {
    var drawer = document.getElementById('familyAlertsDrawer');
    var btn = document.getElementById('familyAlertsBtn');
    if (!drawer) return;
    var shouldOpen = typeof forceOpen === 'boolean' ? forceOpen : drawer.hasAttribute('hidden');
    if (shouldOpen) {
      drawer.removeAttribute('hidden');
      if (btn) btn.setAttribute('aria-expanded', 'true');
      loadFamilyAlerts();
    } else {
      drawer.setAttribute('hidden', '');
      if (btn) {
        btn.setAttribute('aria-expanded', 'false');
        btn.focus();
      }
    }
  }

  window.PDEUESeniorA11y = {
    setScale: applyScale,
    getScale: readStoredScale,
    toggleAlerts: toggleFamilyAlerts,
    refreshAlerts: loadFamilyAlerts,
    hydratePlaneLinks: hydratePlaneLinks,
    applyPlaneDoorways: applyPlaneDoorways,
    resolveDoorwayUrl: resolveDoorwayUrl
  };

  // Apply persisted text scale immediately to avoid layout flicker
  applyScale(readStoredScale());

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      applyScale(readStoredScale());
      hydratePlaneLinks();
      loadFamilyAlerts();
    });
  } else {
    hydratePlaneLinks();
    loadFamilyAlerts();
  }
})();
