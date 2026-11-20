// ===== Sapere Aude calendar card — computed live in the visitor's browser =====
(function () {
  var now = new Date();

  // --- Ganzhi (sexagenary) year: prefer the browser's built-in Chinese calendar ---
  var ganzhi = null, zodiac = null;
  try {
    var parts = new Intl.DateTimeFormat('zh-Hans-CN-u-ca-chinese', { year: 'numeric' }).formatToParts(now);
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].type === 'yearName' || parts[i].type === 'year') { ganzhi = parts[i].value; break; }
    }
    if (ganzhi && !/年$/.test(ganzhi)) ganzhi += '年';
  } catch (e) { /* fall through to cycle math */ }

  var STEMS = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸'];
  var BRANCHES = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'];
  var ZODIAC = { '子':'鼠','丑':'牛','寅':'虎','卯':'兔','辰':'龍','巳':'蛇','午':'馬','未':'羊','申':'猴','酉':'雞','戌':'狗','亥':'豬' };
  if (!ganzhi) {
    // approximation: cycle math, treating early Feb as still the previous cycle year
    var y = now.getFullYear();
    if (now.getMonth() === 0 || (now.getMonth() === 1 && now.getDate() < 10)) y -= 1;
    var idx = ((y - 4) % 60 + 60) % 60;
    ganzhi = STEMS[idx % 10] + BRANCHES[idx % 12] + '年';
  }
  var branch = ganzhi.charAt(1);
  zodiac = ZODIAC[branch] || '';

  // --- Gregorian year in Chinese numerals ---
  var DIGITS = ['〇','一','二','三','四','五','六','七','八','九'];
  var yearCn = String(now.getFullYear()).split('').map(function (d) { return DIGITS[+d]; }).join('');

  // --- Month / day / weekday ---
  var MONTHS = ['一月','二月','三月','四月','五月','六月','七月','八月','九月','十月','十一月','十二月'];
  var WEEKS = ['星期日','星期一','星期二','星期三','星期四','星期五','星期六'];

  // --- Poetry couplets (public-domain classics), rotating by day of year ---
  var POEMS = [
    ['但願人長久', '千里共嬋娟'],
    ['秋水共長天一色', '落霞與孤鶩齊飛'],
    ['山明水淨夜來霜', '數樹深紅出淺黃'],
    ['空山新雨後', '天氣晚來秋'],
    ['蕭蕭梧葉送寒聲', '江上秋風動客情'],
    ['月落烏啼霜滿天', '江楓漁火對愁眠'],
    ['停車坐愛楓林晚', '霜葉紅於二月花'],
    ['自古逢秋悲寂寥', '我言秋日勝春朝']
  ];
  var start = new Date(now.getFullYear(), 0, 0);
  var doy = Math.floor((now - start) / 864e5);
  var poem = POEMS[doy % POEMS.length];

  function set(id, text) { var el = document.getElementById(id); if (el) el.textContent = text; }
  set('cal-ganzhi', ganzhi);
  set('cal-year', yearCn);
  set('cal-month', MONTHS[now.getMonth()]);
  set('cal-day', String(now.getDate()));
  set('cal-week', WEEKS[now.getDay()]);
  set('cal-poem1', poem[0]);
  set('cal-poem2', poem[1]);
  set('cal-zodiac', zodiac);
})();
