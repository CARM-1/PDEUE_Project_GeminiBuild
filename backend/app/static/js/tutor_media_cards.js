/* PDEUE Local-First Visual Media, Playbook Step Checklist & Citation Renderer (Zero-CDN) */
(function () {
  var _mediaStore = [];

  function _esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[c];
    });
  }

  function _isSafeLocalMediaPath(path) {
    return (
      typeof path === 'string' &&
      path.indexOf('/static/media/playbooks/') === 0 &&
      path.indexOf('://') === -1 &&
      path.indexOf('..') === -1
    );
  }

  function _ensureLightbox() {
    var existing = document.getElementById('pdeueMediaLightbox');
    if (existing) return existing;
    var overlay = document.createElement('div');
    overlay.id = 'pdeueMediaLightbox';
    overlay.className = 'pdeue-media-lightbox';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'pdeueMediaLightboxTitle');
    overlay.hidden = true;
    overlay.innerHTML =
      '<div class="pdeue-media-lightbox-panel">' +
      '  <div class="pdeue-media-lightbox-head">' +
      '    <h3 id="pdeueMediaLightboxTitle">Annotated Playbook Reference</h3>' +
      '    <button type="button" id="pdeueMediaLightboxCloseBtn" class="pdeue-media-lightbox-close" aria-label="Close enlarged playbook screenshot">Close Preview</button>' +
      '  </div>' +
      '  <img id="pdeueMediaLightboxImg" class="pdeue-media-lightbox-img" src="" alt="">' +
      '  <p id="pdeueMediaLightboxCaption" class="tutor-media-caption"></p>' +
      '  <ol id="pdeueMediaLightboxLegend" class="tutor-callout-legend" style="margin-top:10px;"></ol>' +
      '</div>';
    document.body.appendChild(overlay);

    var closeBtn = document.getElementById('pdeueMediaLightboxCloseBtn');
    if (closeBtn) {
      closeBtn.addEventListener('click', closeMediaModal);
    }
    overlay.addEventListener('click', function (ev) {
      if (ev.target === overlay) closeMediaModal();
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && !overlay.hidden) closeMediaModal();
    });
    return overlay;
  }

  function openMediaModal(storeIndex) {
    var item = _mediaStore[storeIndex];
    if (!item || !_isSafeLocalMediaPath(item.path)) return;
    var overlay = _ensureLightbox();
    var titleEl = document.getElementById('pdeueMediaLightboxTitle');
    var imgEl = document.getElementById('pdeueMediaLightboxImg');
    var capEl = document.getElementById('pdeueMediaLightboxCaption');
    var legEl = document.getElementById('pdeueMediaLightboxLegend');
    if (titleEl) titleEl.textContent = item.title || 'Annotated Playbook Screenshot';
    if (imgEl) {
      imgEl.src = item.path;
      imgEl.alt = item.caption || item.title || 'PDEUE Annotated Screenshot';
    }
    if (capEl) capEl.textContent = item.caption || '';
    if (legEl) {
      var legend = Array.isArray(item.callout_legend) ? item.callout_legend : [];
      legEl.innerHTML = legend
        .map(function (c, idx) {
          var num = c && c.badge != null ? c.badge : idx + 1;
          var label = (c && c.label) || '';
          var note = (c && c.note) || '';
          return (
            '<li class="tutor-callout-item">' +
            '<span class="tutor-callout-num">' + _esc(num) + '</span>' +
            '<span><strong>' + _esc(label) + '</strong>' + (note ? ' — ' + _esc(note) : '') + '</span>' +
            '</li>'
          );
        })
        .join('');
    }
    overlay.hidden = false;
    var closeBtn = document.getElementById('pdeueMediaLightboxCloseBtn');
    if (closeBtn) closeBtn.focus();
  }

  function closeMediaModal() {
    var overlay = document.getElementById('pdeueMediaLightbox');
    if (overlay) overlay.hidden = true;
  }

  function renderLocalBadge(data) {
    if (!data || data.answered_locally !== true) return '';
    return '<span class="tutor-local-badge" data-answered-locally="true">Local Library · Zero Internet</span>';
  }

  function renderVisualAidBlock(data) {
    if (!data || typeof data !== 'object') return '';
    var mediaRefs = Array.isArray(data.media_refs)
      ? data.media_refs.filter(function (m) {
          return m && _isSafeLocalMediaPath(m.path);
        })
      : [];
    var steps = Array.isArray(data.playbook_steps)
      ? data.playbook_steps.filter(function (s) {
          return typeof s === 'string' && s.trim().length > 0;
        })
      : [];
    var cites = Array.isArray(data.manual_citations)
      ? data.manual_citations.filter(function (c) {
          return c && c.manual_file;
        })
      : [];

    if (!mediaRefs.length && !steps.length && !cites.length) {
      return '';
    }

    var parts = ['<div class="tutor-visual-aid-stack" data-visual-aid="true">'];

    if (mediaRefs.length) {
      parts.push('<div class="tutor-media-grid">');
      mediaRefs.forEach(function (ref) {
        var idx = _mediaStore.push(ref) - 1;
        var legend = Array.isArray(ref.callout_legend) ? ref.callout_legend : [];
        var typeLabel = String(ref.media_type || 'annotated_screenshot').replace(/_/g, ' ');
        var legendHtml = legend
          .map(function (c, cIdx) {
            var num = c && c.badge != null ? c.badge : cIdx + 1;
            var label = (c && c.label) || '';
            var note = (c && c.note) || '';
            return (
              '<li class="tutor-callout-item">' +
              '<span class="tutor-callout-num">' + _esc(num) + '</span>' +
              '<span><strong>' + _esc(label) + '</strong>' + (note ? ' — ' + _esc(note) : '') + '</span>' +
              '</li>'
            );
          })
          .join('');
        parts.push(
          '<article class="tutor-media-card" data-playbook-id="' + _esc(ref.playbook_id || '') + '">' +
            '<div class="tutor-media-card-head">' +
              '<strong style="font-size:0.84rem;color:#F8FAFC;">' + _esc(ref.title || 'Visual Walkthrough') + '</strong>' +
              '<span class="tutor-media-type-pill">' + _esc(typeLabel) + '</span>' +
            '</div>' +
            '<button type="button" class="tutor-media-thumb-btn" onclick="window.PDEUEVisualTutor.openMediaModal(' + idx + ')" aria-label="Enlarge annotated screenshot: ' + _esc(ref.caption || ref.title || 'Playbook visual') + '">' +
              '<img class="tutor-media-thumb" src="' + _esc(ref.path) + '" alt="' + _esc(ref.caption || ref.title || 'Annotated UI screenshot') + '" loading="lazy">' +
              '<span class="tutor-media-zoom-hint">Click to enlarge visual guide &amp; callout legend</span>' +
            '</button>' +
            '<p class="tutor-media-caption">' + _esc(ref.caption || '') + '</p>' +
            (legendHtml ? '<ol class="tutor-callout-legend">' + legendHtml + '</ol>' : '') +
          '</article>'
        );
      });
      parts.push('</div>');
    }

    if (steps.length) {
      var stepsHtml = steps
        .map(function (step) {
          var cleanStep = String(step).replace(/^\d+\.\s*/, '');
          return '<li>' + _esc(cleanStep) + '</li>';
        })
        .join('');
      parts.push(
        '<section class="tutor-steps-card" aria-label="Playbook step checklist">' +
          '<div class="tutor-steps-title">Ordered Cause-and-Effect Steps</div>' +
          '<ol class="tutor-steps-list">' + stepsHtml + '</ol>' +
        '</section>'
      );
    }

    if (cites.length) {
      var citesHtml = cites
        .map(function (c) {
          return (
            '<span class="tutor-manual-cite-badge" title="' + _esc(c.excerpt || '') + '">' +
              '<strong>' + _esc(c.manual_file) + '</strong>' +
              (c.section_title ? ' · ' + _esc(c.section_title) : '') +
            '</span>'
          );
        })
        .join('');
      parts.push(
        '<div class="tutor-manual-cites-bar" aria-label="Canonical manual citations">' +
          citesHtml +
        '</div>'
      );
    }

    parts.push('</div>');
    return parts.join('');
  }

  window.PDEUEVisualTutor = {
    openMediaModal: openMediaModal,
    closeMediaModal: closeMediaModal,
    renderLocalBadge: renderLocalBadge,
    renderVisualAidBlock: renderVisualAidBlock
  };
})();
