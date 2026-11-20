// Vertical text (直排) — see "Vertical text" in style.css.
//
// 1. 縱中橫: wrap runs of 1–2 ASCII digits so they sit upright in one
//    character cell; 3–4 digit runs (years) stack upright digit by digit.
// 2. Bands: each .vertical box is a vertical-rl multi-column container whose
//    columns are full-width horizontal bands. CSS gives it one band of height;
//    text that does not fit spills into overflow bands below. We count those
//    bands and set the height to exactly n bands + gaps, so the box fits its
//    text and never needs a scrollbar. Re-fits on resize and once fonts load.
(function () {
  var boxes = [].slice.call(document.querySelectorAll('.post-body .vertical'));
  if (!boxes.length) return;

  // ---- 1. upright numbers ----
  var NUM = /(^|[^0-9A-Za-z.])([0-9]{1,4})(?![0-9A-Za-z.])/g;
  function uprightNumbers(root) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        var p = n.parentNode;
        if (!/[0-9]/.test(n.nodeValue) || p.closest('script, style, a, .tcy, .num-upright')) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function (node) {
      var text = node.nodeValue, frag = document.createDocumentFragment(), last = 0, m;
      NUM.lastIndex = 0;
      while ((m = NUM.exec(text))) {
        var start = m.index + m[1].length;
        frag.appendChild(document.createTextNode(text.slice(last, start)));
        var span = document.createElement('span');
        span.className = m[2].length <= 2 ? 'tcy' : 'num-upright';
        span.textContent = m[2];
        frag.appendChild(span);
        last = start + m[2].length;
      }
      if (last === 0) return;
      frag.appendChild(document.createTextNode(text.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
  }

  // ---- 2. fit bands ----
  function px(v) { return parseFloat(v) || 0; }
  function fit() {
    boxes.forEach(function (el) {
      el.style.height = '';                              // one band (CSS)
      var cs = getComputedStyle(el);
      var padTop = px(cs.paddingTop);
      var band = px(cs.columnWidth) || (el.clientHeight - padTop - px(cs.paddingBottom));
      var gap = px(cs.columnGap);
      // scrollHeight = padding-top + every band, including overflow bands
      var extent = el.scrollHeight - padTop;
      var n = Math.max(1, Math.round((extent + gap) / (band + gap)));
      el.style.height = (n * band + (n - 1) * gap + 1) + 'px';
      // safety: if anything still overflows (rounding, late layout), take one more band
      if (el.scrollHeight > el.clientHeight + 2) {
        n += 1;
        el.style.height = (n * band + (n - 1) * gap + 1) + 'px';
      }
    });
  }

  boxes.forEach(uprightNumbers);
  fit();

  var timer;
  function refit() { clearTimeout(timer); timer = setTimeout(fit, 120); }
  window.addEventListener('load', fit);
  window.addEventListener('resize', refit);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
})();
