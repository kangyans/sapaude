// Book reader (The Enchiridion) — see "Book reader" in style.css.
// - Reading bar: appears once the contents scroll away; shows the title, the
//   current chapter (XII / LII), a progress line, and a link back to Contents.
// - Resume: remembers the last chapter read (this browser only) and offers
//   "繼續閱讀" above the contents.
// - Keyboard: ← / → jump to the previous / next chapter.
(function () {
  var book = document.querySelector('.book');
  if (!book) return;
  var chapters = [].slice.call(book.querySelectorAll('.chapter'));
  if (!chapters.length) return;
  var total = chapters.length;
  var last = chapters[total - 1].getAttribute('data-no');
  var KEY = 'book:' + location.pathname;

  function store(v) { try { localStorage.setItem(KEY, v); } catch (e) {} }
  function recall() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }

  // ---- reading bar ----
  var bar = document.createElement('div');
  bar.className = 'book-bar';
  bar.setAttribute('aria-hidden', 'true');
  bar.innerHTML =
    '<div class="book-bar-inner">' +
      '<a class="book-bar-toc" href="#contents">Contents</a>' +
      '<span class="book-bar-title">The Enchiridion</span>' +
      '<span class="book-bar-no"></span>' +
    '</div>' +
    '<div class="book-bar-progress"><span></span></div>';
  document.body.appendChild(bar);
  var noEl = bar.querySelector('.book-bar-no');
  var fill = bar.querySelector('.book-bar-progress span');
  var text = book.querySelector('.book-text');
  var toc = book.querySelector('.book-toc');

  function current() {
    var line = window.innerHeight * 0.3, cur = 0;
    for (var i = 0; i < total; i++) {
      if (chapters[i].getBoundingClientRect().top <= line) cur = i; else break;
    }
    return cur;
  }

  var saved = -1;
  function update() {
    var r = text.getBoundingClientRect();
    var span = r.height - window.innerHeight;
    var p = span > 0 ? Math.min(1, Math.max(0, -r.top / span)) : 1;
    fill.style.transform = 'scaleX(' + p + ')';
    bar.classList.toggle('is-shown', toc.getBoundingClientRect().bottom < 0);
    var c = current();
    noEl.textContent = chapters[c].getAttribute('data-no') + ' / ' + last;
    if (r.top < 0 && c !== saved) { saved = c; store(String(c + 1)); }
  }

  var ticking = false;
  window.addEventListener('scroll', function () {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () { ticking = false; update(); });
  }, { passive: true });
  window.addEventListener('resize', update);
  update();

  // ---- resume ----
  var n = parseInt(recall(), 10);
  var resume = book.querySelector('.book-resume');
  if (resume && n > 1 && n <= total && !location.hash) {
    var ch = chapters[n - 1];
    resume.innerHTML = '繼續閱讀：<a href="#' + ch.id + '">' + ch.getAttribute('data-no') + '</a>';
    resume.hidden = false;
  }

  // ---- keyboard ----
  document.addEventListener('keydown', function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey || /input|textarea|select/i.test(e.target.tagName)) return;
    var dir = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!dir) return;
    var r = text.getBoundingClientRect();
    if (r.top > window.innerHeight || r.bottom < 0) return;   // only while reading
    var target = chapters[Math.max(0, Math.min(total - 1, current() + dir))];
    e.preventDefault();
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    history.replaceState(null, '', '#' + target.id);
  });
})();
