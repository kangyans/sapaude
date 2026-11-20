// Vertical text (直排) bands — see "Vertical text" in style.css.
// Each .vertical box is a vertical-rl multi-column container whose columns
// are full-width horizontal bands. Its height starts at one band; the text
// that does not fit spills into overflow bands below, which scrollHeight
// measures. Setting the height to that extent makes every band a real
// column, so the box grows to fit its text and never needs a scrollbar.
(function () {
  var boxes = [].slice.call(document.querySelectorAll('.post-body .vertical'))
    .filter(function (el) { return !el.closest('.box'); });   // covers size themselves
  if (!boxes.length) return;

  function fit() {
    boxes.forEach(function (el) {
      el.style.height = '';                     // back to one band (CSS)
      var extent = el.scrollHeight;             // all bands, incl. overflow ones
      el.style.height = (extent + 2) + 'px';    // +2px guards against rounding
    });
  }

  var timer;
  function refit() { clearTimeout(timer); timer = setTimeout(fit, 120); }

  fit();
  window.addEventListener('load', fit);
  window.addEventListener('resize', refit);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
})();
