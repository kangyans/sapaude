// 影冊 rows: Netflix-style horizontal rows.
// - ‹ › buttons glide the row by whole posters with an ease-in-out animation
//   (scroll-snap is paused while gliding so it doesn't fight the motion),
//   and hide at either end. Touch devices swipe; without JS rows still scroll.
// - Marks the first/last fully visible card so its hover magnify grows inward.
(function () {
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }

  [].forEach.call(document.querySelectorAll('.row-viewport'), function (vp) {
    var track = vp.querySelector('.row-track');
    if (!track) return;
    var cards = [].slice.call(track.children);
    var anim = null;

    function stride() {
      if (cards.length < 2) return track.clientWidth;
      return cards[1].offsetLeft - cards[0].offsetLeft;       // card width + gap
    }

    function glide(dir) {
      var s = stride();
      var perView = Math.max(1, Math.floor((track.clientWidth + 1) / s));
      var max = track.scrollWidth - track.clientWidth;
      var from = track.scrollLeft;
      // land on a card boundary, one "page" of whole cards away
      var target = Math.round(from / s + dir * perView) * s;
      target = Math.max(0, Math.min(max, target));
      if (reduce) { track.scrollLeft = target; return; }

      if (anim) cancelAnimationFrame(anim);
      track.classList.add('is-gliding');
      var start = null, dur = 650;
      function step(ts) {
        if (start === null) start = ts;
        var t = Math.min(1, (ts - start) / dur);
        track.scrollLeft = from + (target - from) * ease(t);
        if (t < 1) { anim = requestAnimationFrame(step); }
        else { anim = null; track.classList.remove('is-gliding'); update(); }
      }
      anim = requestAnimationFrame(step);
    }

    function button(dir, label, glyph) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'row-btn row-btn-' + (dir > 0 ? 'next' : 'prev');
      b.setAttribute('aria-label', label);
      b.textContent = glyph;
      b.addEventListener('click', function () { glide(dir); });
      vp.appendChild(b);
      return b;
    }
    var prev = button(-1, '上一組', '‹');
    var next = button(1, '下一組', '›');

    function markEdges() {
      var left = track.scrollLeft, right = left + track.clientWidth;
      var first = null, last = null;
      cards.forEach(function (c) {
        c.classList.remove('edge-start', 'edge-end');
        var a = c.offsetLeft, b = a + c.offsetWidth;
        if (a >= left - 2 && b <= right + 2) { if (!first) first = c; last = c; }
      });
      if (first) first.classList.add('edge-start');
      if (last) last.classList.add('edge-end');
    }

    function update() {
      var max = track.scrollWidth - track.clientWidth - 2;
      prev.hidden = track.scrollLeft <= 2;
      next.hidden = track.scrollLeft >= max;
      vp.classList.toggle('at-start', prev.hidden);
      vp.classList.toggle('at-end', next.hidden);
      markEdges();
    }

    var raf = null;
    track.addEventListener('scroll', function () {
      if (raf) return;
      raf = requestAnimationFrame(function () { raf = null; update(); });
    }, { passive: true });
    window.addEventListener('resize', update);
    window.addEventListener('load', update);
    update();
  });
})();
