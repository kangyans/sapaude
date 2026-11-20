// 影冊 rows: Netflix-style horizontal rows. Each .row-viewport scrolls
// sideways (touch / trackpad / keyboard); this adds ‹ › buttons that page by
// one viewport and hide at either end. Without JS the rows still scroll.
(function () {
  [].forEach.call(document.querySelectorAll('.row-viewport'), function (vp) {
    var track = vp.querySelector('.row-track');
    if (!track) return;

    function button(dir, label, glyph) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'row-btn row-btn-' + dir;
      b.setAttribute('aria-label', label);
      b.textContent = glyph;
      b.addEventListener('click', function () {
        var step = track.clientWidth * 0.9 * (dir === 'next' ? 1 : -1);
        track.scrollBy({ left: step, behavior: 'smooth' });
      });
      vp.appendChild(b);
      return b;
    }
    var prev = button('prev', '上一組', '‹');
    var next = button('next', '下一組', '›');

    function update() {
      var max = track.scrollWidth - track.clientWidth - 2;
      prev.hidden = track.scrollLeft <= 2;
      next.hidden = track.scrollLeft >= max;
      vp.classList.toggle('at-start', prev.hidden);
      vp.classList.toggle('at-end', next.hidden);
    }
    track.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    window.addEventListener('load', update);
    update();
  });
})();
