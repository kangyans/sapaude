// Book reader — see "Book reader" in style.css.
//
// Three kinds of book page share one reading bar (title, position, progress):
//   .book with .chapter sections   one-page book in chapters (The Enchiridion):
//                                  bar shows the current chapter; ← / → move
//                                  between chapters; resume to last chapter.
//   .book-page                     a series chapter (人間詞話 卷二 …) or a
//                                  one-page book (報任安書): bar shows its label;
//                                  series chapters are remembered for resume.
//   .book-cover                    a series' cover + contents: offers 繼續閱讀
//                                  to the chapter last read.
// Positions are remembered in this browser only (localStorage).
(function () {
  function store(k, v) { try { localStorage.setItem('book:' + k, v); } catch (e) {} }
  function recall(k) { try { return localStorage.getItem('book:' + k); } catch (e) { return null; } }

  var root = document.querySelector('.book, .book-page');
  if (!root) return;
  var id = root.getAttribute('data-book') || location.pathname;
  var zh = root.classList.contains('book-zh');

  // ---- series cover: resume link only ----
  if (root.classList.contains('book-cover')) {
    var last = recall(id), resume = root.querySelector('.book-resume');
    if (last && resume) {
      var link = root.querySelector('.toc-list a[href="' + last + '"]');
      if (link) {
        var label = link.querySelector('.toc-no');
        resume.innerHTML = '繼續閱讀：<a href="' + last + '">' + (label ? label.textContent : '') + '</a>';
        resume.hidden = false;
      }
    }
    return;
  }

  // ---- reading bar ----
  var bar = document.createElement('div');
  bar.className = 'book-bar' + (zh ? ' book-bar-zh' : '');
  bar.setAttribute('aria-hidden', 'true');
  var tocHref = root.getAttribute('data-toc') || '#contents';
  bar.innerHTML =
    '<div class="book-bar-inner">' +
      '<a class="book-bar-toc" href="' + tocHref + '">' + (zh ? '目錄' : 'Contents') + '</a>' +
      '<span class="book-bar-title"></span>' +
      '<span class="book-bar-no"></span>' +
    '</div>' +
    '<div class="book-bar-progress"><span></span></div>';
  bar.querySelector('.book-bar-title').textContent = root.getAttribute('data-book-title') || document.title;
  document.body.appendChild(bar);
  var noEl = bar.querySelector('.book-bar-no');
  var fill = bar.querySelector('.book-bar-progress span');

  var chapters = [].slice.call(root.querySelectorAll('.chapter'));
  var text = root.querySelector('.book-text') || root.querySelector('.post-body') || root;
  // the bar appears once the book's opening (contents / title page / running head) is gone
  var opening = root.querySelector('.book-toc') || root.querySelector('.book-title') ||
                root.querySelector('.book-running') || root.querySelector('.post-header');

  function currentChapter() {
    var line = window.innerHeight * 0.3, cur = 0;
    for (var i = 0; i < chapters.length; i++) {
      if (chapters[i].getBoundingClientRect().top <= line) cur = i; else break;
    }
    return cur;
  }

  var savedCh = -1;
  function update() {
    var r = text.getBoundingClientRect();
    var span = r.height - window.innerHeight;
    var p = span > 0 ? Math.min(1, Math.max(0, -r.top / span)) : (r.top < 0 ? 1 : 0);
    fill.style.transform = 'scaleX(' + p + ')';
    bar.classList.toggle('is-shown', !opening || opening.getBoundingClientRect().bottom < 0);
    if (chapters.length) {
      var c = currentChapter();
      noEl.textContent = chapters[c].getAttribute('data-no') + ' / ' +
                         chapters[chapters.length - 1].getAttribute('data-no');
      if (r.top < 0 && c !== savedCh) { savedCh = c; store(id, String(c + 1)); }
    } else {
      noEl.textContent = root.getAttribute('data-label') || '';
    }
  }

  var ticking = false;
  window.addEventListener('scroll', function () {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () { ticking = false; update(); });
  }, { passive: true });
  window.addEventListener('resize', update);
  window.addEventListener('load', update);
  update();

  // ---- series chapter: remember it for the cover's 繼續閱讀 ----
  if (root.querySelector('.book-running')) store(id, location.pathname);

  if (!chapters.length) return;

  // ---- chaptered book: resume + keyboard ----
  var n = parseInt(recall(id), 10);
  var resumeEl = root.querySelector('.book-resume');
  if (resumeEl && n > 1 && n <= chapters.length && !location.hash) {
    var ch = chapters[n - 1];
    resumeEl.innerHTML = (zh ? '繼續閱讀：' : 'Continue reading: ') +
      '<a href="#' + ch.id + '">' + ch.getAttribute('data-no') + '</a>';
    resumeEl.hidden = false;
  }

  document.addEventListener('keydown', function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey || /input|textarea|select/i.test(e.target.tagName)) return;
    var dir = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!dir) return;
    var r = text.getBoundingClientRect();
    if (r.top > window.innerHeight || r.bottom < 0) return;   // only while reading
    var target = chapters[Math.max(0, Math.min(chapters.length - 1, currentChapter() + dir))];
    e.preventDefault();
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    history.replaceState(null, '', '#' + target.id);
  });
})();
