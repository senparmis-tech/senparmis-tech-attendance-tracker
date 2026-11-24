/* Small motion helpers: count-up numbers, roll-call card slide, theme toggle spin. */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Dashboard: stagger index for the stat cards, then count each number up once.
  var grid = document.querySelector('.stats-overview-grid');
  if (grid) {
    Array.prototype.forEach.call(grid.children, function (card, i) { card.style.setProperty('--i', i); });
    if (!reduce) {
      Array.prototype.forEach.call(grid.querySelectorAll('.stat-metric-value'), function (el, i) {
        var text = el.textContent.trim();
        if (!/^\d+$/.test(text)) return;
        var target = parseInt(text, 10);
        if (target < 2) return;
        var start = null, delay = 80 + i * 70, dur = 700;
        el.textContent = '0';
        function tick(now) {
          if (start === null) start = now + delay;
          var t = Math.min(1, Math.max(0, (now - start) / dur));
          el.textContent = String(Math.round(target * (1 - Math.pow(1 - t, 3))));
          if (t < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
      });
    }
  }

  // Roll call (attendance and scores): slide the card in when the student changes.
  function watch(nameId, cardId) {
    var name = document.getElementById(nameId), card = document.getElementById(cardId);
    if (!name || !card || reduce || !window.MutationObserver) return;
    new MutationObserver(function () {
      card.classList.remove('swap');
      void card.offsetWidth;
      card.classList.add('swap');
    }).observe(name, { childList: true, characterData: true, subtree: true });
  }
  watch('rcStudentName', 'rollCardMain');
  watch('rcName', 'rcMain');

  // Theme toggle: one spin per click.
  var tbtn = document.getElementById('themeToggleBtn');
  if (tbtn && !reduce) {
    tbtn.addEventListener('click', function () {
      tbtn.classList.remove('spin');
      void tbtn.offsetWidth;
      tbtn.classList.add('spin');
    });
  }
})();
