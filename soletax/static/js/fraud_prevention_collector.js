/**
 * HMRC Fraud Prevention — browser-side data collector.
 *
 * Collects the subset of HMRC's required fraud-prevention header data
 * that can ONLY be observed from inside the browser (screen, timezone as
 * JS sees it, installed plugins, local network IPs, window size). This
 * data is POSTed to Django before any action that triggers an HMRC API
 * submission (e.g. clicking "Submit Quarterly Update"), where it's merged
 * server-side with vendor/device headers in fraud_prevention.py.
 *
 * IMPORTANT — local IP collection via WebRTC:
 * Modern browsers increasingly restrict or disable WebRTC's ability to
 * enumerate local IPs for privacy reasons (especially Firefox by default,
 * and Chrome behind certain flags/extensions). If `local_ips` comes back
 * empty, that's an expected "missing data" case HMRC's spec explicitly
 * allows for — do not block the user, just submit without that field and
 * let server-side validation log the gap.
 *
 * This file deliberately has ZERO external dependencies so it can be
 * served as a static asset without a build step.
 */

(function (window) {
  'use strict';

  function getTimezone() {
    // Returns 'UTC+01:00' style string, which is what HMRC expects —
    // NOT an IANA name like 'Europe/London'.
    var offsetMinutes = -new Date().getTimezoneOffset(); // JS gives inverted sign
    var sign = offsetMinutes >= 0 ? '+' : '-';
    var abs = Math.abs(offsetMinutes);
    var hh = String(Math.floor(abs / 60)).padStart(2, '0');
    var mm = String(abs % 60).padStart(2, '0');
    return 'UTC' + sign + hh + ':' + mm;
  }

  function getScreens() {
    // Most setups only have one observable screen from a single browser
    // tab. Multi-monitor detail beyond what `window.screen` exposes isn't
    // reliably available from web JS — this submits what's actually
    // observable rather than guessing.
    var s = window.screen || {};
    return [{
      width: s.width || null,
      height: s.height || null,
      scaling_factor: window.devicePixelRatio || 1,
      colour_depth: s.colorDepth || null,
    }];
  }

  function getWindowSize() {
    return {
      width: window.innerWidth || document.documentElement.clientWidth || null,
      height: window.innerHeight || document.documentElement.clientHeight || null,
    };
  }

  function getBrowserPlugins() {
    try {
      if (!navigator.plugins || navigator.plugins.length === 0) return [];
      var names = [];
      for (var i = 0; i < navigator.plugins.length; i++) {
        names.push(navigator.plugins[i].name);
      }
      return names;
    } catch (e) {
      return [];
    }
  }

  function getDoNotTrack() {
    var dnt = navigator.doNotTrack || window.doNotTrack || navigator.msDoNotTrack;
    return dnt === '1' || dnt === 'yes';
  }

  function getUserAgent() {
    return navigator.userAgent || '';
  }

  /**
   * Attempts to enumerate local IPs via WebRTC ICE candidates.
   * Returns a Promise that resolves to an array of IP strings (possibly
   * empty if the browser blocks this, which is increasingly the norm).
   * Has a hard timeout so this never hangs form submission indefinitely.
   */
  function getLocalIPs(timeoutMs) {
    timeoutMs = timeoutMs || 800;
    return new Promise(function (resolve) {
      var RTCPeerConnection = window.RTCPeerConnection ||
        window.mozRTCPeerConnection || window.webkitRTCPeerConnection;
      if (!RTCPeerConnection) {
        resolve([]);
        return;
      }

      var ips = new Set();
      var pc;
      var settled = false;

      function finish() {
        if (settled) return;
        settled = true;
        try { pc && pc.close(); } catch (e) {}
        resolve(Array.from(ips));
      }

      try {
        pc = new RTCPeerConnection({ iceServers: [] });
        pc.createDataChannel('');
        pc.onicecandidate = function (event) {
          if (!event || !event.candidate || !event.candidate.candidate) {
            finish();
            return;
          }
          var match = /([0-9]{1,3}(\.[0-9]{1,3}){3}|[a-f0-9:]+:[a-f0-9:]+)/.exec(
            event.candidate.candidate
          );
          if (match) ips.add(match[1]);
        };
        pc.createOffer().then(function (offer) {
          return pc.setLocalDescription(offer);
        }).catch(finish);
        setTimeout(finish, timeoutMs);
      } catch (e) {
        finish();
      }
    });
  }

  /**
   * Main entry point. Returns a Promise resolving to the full client_data
   * object expected by core.fraud_prevention.build_full_headers().
   */
  function collect() {
    return getLocalIPs().then(function (localIps) {
      var windowSize = getWindowSize();
      return {
        timezone: getTimezone(),
        screens: getScreens(),
        window_width: windowSize.width,
        window_height: windowSize.height,
        browser_plugins: getBrowserPlugins(),
        do_not_track: getDoNotTrack(),
        user_agent_browser_js: getUserAgent(),
        local_ips: localIps,
        local_ips_timestamp: new Date().toISOString().replace(/(\.\d{3})\d*Z$/, '$1Z'),
      };
    });
  }

  /**
   * Convenience helper: collects fraud-prevention data and stores it as a
   * hidden JSON field in the given form before submit, so it travels to
   * Django alongside the rest of the form POST without a separate AJAX
   * round-trip. Call this on a form's submit handler and call
   * event.preventDefault() / re-submit after the promise resolves.
   *
   * Usage:
   *   form.addEventListener('submit', function (e) {
   *     if (form.dataset.fpAttached === '1') return; // already collected, let it submit
   *     e.preventDefault();
   *     SoleTaxFraudPrevention.attachToForm(form).then(function () {
   *       form.dataset.fpAttached = '1';
   *       form.submit();
   *     });
   *   });
   */
  function attachToForm(formEl, fieldName) {
    fieldName = fieldName || 'fraud_prevention_data';
    return collect().then(function (data) {
      var existing = formEl.querySelector('input[name="' + fieldName + '"]');
      if (!existing) {
        existing = document.createElement('input');
        existing.type = 'hidden';
        existing.name = fieldName;
        formEl.appendChild(existing);
      }
      existing.value = JSON.stringify(data);
      return data;
    });
  }

  window.SoleTaxFraudPrevention = {
    collect: collect,
    attachToForm: attachToForm,
  };

})(window);
