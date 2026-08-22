/* TASK-022: 内嵌可视化编辑器——让用户打开最终交付的 deck.single.html 后，
 * 不需要回来改代码/重新生成，就能在浏览器里直接微调文字的字号和小范围位置。
 *
 * 交互模式借鉴 [frontend-slides] 参考库的 UX 规范（左上角隐形热区悬停延迟
 * 显示编辑按钮、E 键切换编辑态、编辑态下元素可点选高亮），但字号/位置调整
 * 控件、localStorage 持久化方案、导出逻辑均为本 skill 自行设计实现（参考库
 * 只给了"进入/退出编辑模式"这一层 UX 规范，没有现成的调节控件代码）。
 *
 * 与 runtime.js 的按键体系互不冲突：runtime.js 已占用 S(演讲者)/O(总览)/
 * F(全屏)/B(静态降级)/方向键/空格/Home/End/Escape，本文件新增 E 键，读过
 * runtime.js 全文确认未被占用。
 *
 * 与 autofit.js 的优先级关系（写在这里，autofit.js 里也有对称注释）：
 * autofit.js 负责"页面激活时自动收缩到不溢出"的兜底，本编辑器负责"用户手动
 * 进一步精修"。一旦某个 [data-autofit] 元素被本编辑器调整过（无论是当场
 * 调整还是刷新页面后从 localStorage 还原），就会打上 data-editor-adjusted
 * 标记；autofit.js 的 fitOne() 在处理每个元素前会先检查这个标记，命中则
 * 整个跳过（不 reset、不重新测量），确保用户手动值永远优先于自动收缩，
 * 不会被下次翻页/resize 悄悄覆盖回去。用户在编辑器面板点"重置"时会摘掉
 * 这个标记，并调用 autofit.js 暴露的 window.__deckAutofitRefit() 让自动
 * 收缩重新接管该元素。
 */
(function () {
  'use strict';

  var TEXT_SELECTOR = 'h1,h2,h3,h4,p,li,small,figcaption,blockquote,td,th,dt,dd';
  var FONT_STEP = 2;   // 字号每次调整步进（px）
  var POS_STEP = 4;    // 位置每次调整步进（px）
  var MIN_FONT = 8;    // 字号下限，避免调没
  var PANEL_WIDTH = 340; // 需要与下面注入的 CSS .editor-panel 宽度保持一致

  var editModeActive = false;
  var selectedEl = null;
  var hoverEl = null;
  var panelEl = null;
  var hotzoneEl = null;
  var fontInputEl = null;
  var posLabelEl = null;
  var selInfoEl = null;
  var controlsWrapEl = null;

  // ── localStorage 持久化 ──────────────────────────────────────────────
  // 存储 key 里带上 document.title，避免同一浏览器里打开的多份不同 deck
  // 互相串键；同一份文件（同一 file:// 路径）刷新/重开浏览器后 localStorage
  // 按惯例仍会保留，满足"关闭浏览器再打开，之前调整还在"的要求。
  var STORAGE_KEY = 'html-deck-editor:' + (document.title || location.pathname || 'deck');

  function loadStore() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') || {}; }
    catch (e) { return {}; }
  }
  function saveStore(store) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(store)); }
    catch (e) { /* 隐私模式/存储禁用等场景下静默失败，不影响当场编辑效果 */ }
  }

  // 简易字符串哈希（djb2），仅作诊断用途——文本内容一致性的“软信号”，
  // 不作为定位是否成功的硬性门槛（例如计数器动画元素在还原时刻 textContent
  // 可能还没跑完，若严格比对哈希会导致误判为“找不到元素”，因此这里只存
  // 不做强校验）。真正的定位依据是下面的 DOM 路径索引。
  function hashText(s) {
    s = (s || '').trim().slice(0, 80);
    var h = 5381;
    for (var i = 0; i < s.length; i++) { h = ((h * 33) ^ s.charCodeAt(i)) >>> 0; }
    return h.toString(36);
  }

  // 元素在所在 .slide 内的稳定路径：从 slide 到 el 逐层记录“在父元素的
  // 第几个子元素”，例如 "1.0.2"。同一份渲染结果（deck.md 内容不变、只是
  // 重新跑一次 render_deck.py）DOM 结构确定性不变，路径可稳定复现。
  function getPathWithinSlide(slide, el) {
    var parts = [];
    var node = el;
    while (node && node !== slide) {
      var parent = node.parentElement;
      if (!parent) return null;
      var idx = Array.prototype.indexOf.call(parent.children, node);
      if (idx < 0) return null;
      parts.unshift(idx);
      node = parent;
    }
    if (node !== slide) return null;
    return parts.join('.');
  }
  function getElementByPath(slide, path) {
    var parts = path.split('.');
    var node = slide;
    for (var i = 0; i < parts.length; i++) {
      var idx = Number(parts[i]);
      if (!node || !node.children || !node.children[idx]) return null;
      node = node.children[idx];
    }
    return node;
  }

  function slidePage(slide) {
    return slide.getAttribute('data-page') || String(Array.prototype.indexOf.call(document.querySelectorAll('.slide'), slide) + 1);
  }

  function persistElement(el) {
    var slide = el.closest('.slide');
    if (!slide) return;
    var page = slidePage(slide);
    var path = getPathWithinSlide(slide, el);
    if (path == null) return;
    var store = loadStore();
    store[page] = store[page] || {};
    var rec = { hash: hashText(el.textContent), updatedAt: Date.now() };
    if (el.hasAttribute('data-editor-font')) rec.font = Number(el.getAttribute('data-editor-font'));
    if (el.hasAttribute('data-editor-tx')) rec.tx = Number(el.getAttribute('data-editor-tx'));
    if (el.hasAttribute('data-editor-ty')) rec.ty = Number(el.getAttribute('data-editor-ty'));
    store[page][path] = rec;
    saveStore(store);
  }

  function removeFromStore(el) {
    var slide = el.closest('.slide');
    if (!slide) return;
    var page = slidePage(slide);
    var path = getPathWithinSlide(slide, el);
    if (path == null) return;
    var store = loadStore();
    if (store[page]) {
      delete store[page][path];
      if (!Object.keys(store[page]).length) delete store[page];
    }
    saveStore(store);
  }

  // ── 动画/变换叠加 ────────────────────────────────────────────────────
  // CSS 动画（[data-animate]）在层叠优先级上高于普通作者样式（含内联
  // style），animation-fill-mode:both 结束后仍会持续覆盖内联 transform，
  // 导致我们手动设置的 translate 不生效。本 skill 里全部入场动画的 to
  // 关键帧都收敛到“等价于无变换”的终态（translate(0)/scale(1)），所以
  // 直接切断该元素（或其 data-animate 祖先容器）的 animation 不会产生
  // 可见跳变，之后即可安全地叠加编辑器的位移调整。
  function neutralizeAnimation(el) {
    var host = el.closest('[data-animate]');
    if (host && host.style.animation !== 'none') host.style.animation = 'none';
    if (el !== host && el.style.animation && el.style.animation !== 'none') el.style.animation = 'none';
  }

  // 捕获“编辑前”的基础 transform（可能是组件 CSS 自带的定位型 transform，
  // 例如 translateX(-50%) 这类居中技巧），只捕获一次并存进 data 属性，
  // 之后所有位移调整都在这个基础上追加 translate()，不会把原有定位/动画
  // 终态覆盖掉。
  function ensureBaseTransform(el) {
    if (el.hasAttribute('data-editor-base-transform')) return el.getAttribute('data-editor-base-transform');
    neutralizeAnimation(el);
    var base = getComputedStyle(el).transform;
    if (!base || base === 'none') base = '';
    el.setAttribute('data-editor-base-transform', base);
    return base;
  }

  function setOffset(el, tx, ty) {
    var base = ensureBaseTransform(el);
    el.setAttribute('data-editor-tx', String(tx));
    el.setAttribute('data-editor-ty', String(ty));
    el.style.transform = (base ? base + ' ' : '') + 'translate(' + tx.toFixed(1) + 'px,' + ty.toFixed(1) + 'px)';
    el.setAttribute('data-editor-adjusted', 'true');
  }
  function nudge(el, dx, dy) {
    var tx = (parseFloat(el.getAttribute('data-editor-tx')) || 0) + dx;
    var ty = (parseFloat(el.getAttribute('data-editor-ty')) || 0) + dy;
    setOffset(el, tx, ty);
    persistElement(el);
    refreshPanelForSelection();
  }

  function setFontSize(el, px) {
    px = Math.max(MIN_FONT, Math.round(px));
    el.style.fontSize = px + 'px';
    el.setAttribute('data-editor-font', String(px));
    el.setAttribute('data-editor-adjusted', 'true');
    return px;
  }
  function nudgeFont(el, delta) {
    var current = parseFloat(el.getAttribute('data-editor-font'));
    if (!current) current = parseFloat(getComputedStyle(el).fontSize) || 16;
    setFontSize(el, current + delta);
    persistElement(el);
    refreshPanelForSelection();
  }
  function applyFontInput(el, pxValue) {
    var n = parseFloat(pxValue);
    if (isNaN(n)) { refreshPanelForSelection(); return; }
    setFontSize(el, n);
    persistElement(el);
    refreshPanelForSelection();
  }

  function resetElement(el) {
    el.style.fontSize = '';
    el.style.transform = '';
    el.removeAttribute('data-editor-font');
    el.removeAttribute('data-editor-tx');
    el.removeAttribute('data-editor-ty');
    el.removeAttribute('data-editor-base-transform');
    el.removeAttribute('data-editor-adjusted');
    removeFromStore(el);
    // 摘掉标记后，若该元素本就受 autofit.js 管理，主动请它重新接管一次，
    // 而不是等到下次翻页/resize 才恢复自适应效果。
    if (el.hasAttribute('data-autofit') && typeof window.__deckAutofitRefit === 'function') {
      window.__deckAutofitRefit();
    }
    refreshPanelForSelection();
  }

  function restoreFromStorage() {
    var store = loadStore();
    var slides = document.querySelectorAll('.slide');
    slides.forEach(function (slide) {
      var page = slidePage(slide);
      var entries = store[page];
      if (!entries) return;
      Object.keys(entries).forEach(function (path) {
        var el = getElementByPath(slide, path);
        if (!el) return; // 结构已变化，找不到就放弃，不强行乱套到别的元素上
        var rec = entries[path];
        if (typeof rec.font === 'number') setFontSize(el, rec.font);
        if (typeof rec.tx === 'number' || typeof rec.ty === 'number') {
          setOffset(el, rec.tx || 0, rec.ty || 0);
        }
      });
    });
  }

  // ── 舞台缩放（为右侧面板让出空间）────────────────────────────────────
  // runtime.js 的 scale() 用 innerWidth/innerHeight 计算 --deck-scale，
  // 不知道编辑面板的存在。编辑模式开启时这里按“预留右侧面板宽度”重新计算
  // 同一个 CSS 变量；关闭编辑模式时按 reserveRight=0 还原，与 runtime.js
  // 原生计算结果一致，不需要改 runtime.js 本身。
  function rescaleStage(reserveRight) {
    var s = Math.min((innerWidth - reserveRight) / 1920, innerHeight / 1080);
    document.documentElement.style.setProperty('--deck-scale', Math.max(0.05, s).toFixed(4));
  }
  function onEditorResize() { rescaleStage(PANEL_WIDTH); }

  // ── 选中/高亮 ────────────────────────────────────────────────────────
  function selectElement(el) {
    if (selectedEl && selectedEl !== el) selectedEl.classList.remove('editor-selected-el');
    if (hoverEl) hoverEl.classList.remove('editor-hover-el');
    selectedEl = el;
    selectedEl.classList.add('editor-selected-el');
    refreshPanelForSelection();
  }
  function deselectElement() {
    if (selectedEl) selectedEl.classList.remove('editor-selected-el');
    selectedEl = null;
    refreshPanelForSelection();
  }

  function refreshPanelForSelection() {
    if (!panelEl) return;
    if (!selectedEl) {
      controlsWrapEl.style.display = 'none';
      selInfoEl.textContent = '点击画面里的文字元素进行调整（字号 / 上下左右微移）';
      return;
    }
    controlsWrapEl.style.display = '';
    var tag = selectedEl.tagName.toLowerCase();
    var snippet = (selectedEl.textContent || '').trim().slice(0, 24);
    selInfoEl.textContent = '<' + tag + '> ' + snippet + (snippet.length === 24 ? '…' : '');
    var curFont = Math.round(parseFloat(getComputedStyle(selectedEl).fontSize) || 0);
    fontInputEl.value = curFont;
    var tx = parseFloat(selectedEl.getAttribute('data-editor-tx')) || 0;
    var ty = parseFloat(selectedEl.getAttribute('data-editor-ty')) || 0;
    posLabelEl.textContent = '水平 ' + (tx >= 0 ? '+' : '') + tx.toFixed(0) + 'px ／ 垂直 ' + (ty >= 0 ? '+' : '') + ty.toFixed(0) + 'px';
  }

  // ── 编辑模式切换 ─────────────────────────────────────────────────────
  function enterEditMode() {
    if (editModeActive) return;
    // 编辑模式与全屏演示互斥：进编辑前若已在全屏，先退出全屏。
    if (document.fullscreenElement) { try { document.exitFullscreen(); } catch (e) {} }
    editModeActive = true;
    document.body.classList.add('editor-mode-active');
    panelEl.classList.add('is-open');
    rescaleStage(PANEL_WIDTH);
    window.addEventListener('resize', onEditorResize);
    refreshPanelForSelection();
  }
  function exitEditMode() {
    if (!editModeActive) return;
    editModeActive = false;
    document.body.classList.remove('editor-mode-active');
    panelEl.classList.remove('is-open');
    window.removeEventListener('resize', onEditorResize);
    if (hoverEl) { hoverEl.classList.remove('editor-hover-el'); hoverEl = null; }
    deselectElement();
    rescaleStage(0);
  }
  function toggleEditMode() { if (editModeActive) exitEditMode(); else enterEditMode(); }

  function onFullscreenChange() {
    var fs = !!(document.fullscreenElement || document.webkitFullscreenElement);
    document.body.classList.toggle('editor-fullscreen-active', fs);
    // 正式演示时全屏放大、隐藏编辑器：只要进入全屏，无条件退出编辑模式。
    if (fs) exitEditMode();
  }

  // ── 导出 ────────────────────────────────────────────────────────────
  function exportHtml() {
    // 只在克隆节点上做清理，不动当前页面的真实状态：把编辑器自身的
    // UI（热区按钮/右侧面板/注入的 <style>）以及临时的悬停/选中高亮
    // class 从导出内容里摘掉，这样导出的文件重新打开时是“干净”的
    // 展示状态（editor.js 会在那份文件里自己重新创建一套热区/面板），
    // 而不会把当前这份里已经实例化的 DOM 节点重复带出去。
    // 已经调整过的字号/位置本来就是内联 style + data-editor-* 属性，
    // 克隆时天然保留，导出文件本身就是可直接演示、也可继续编辑的
    // 完整单文件。
    var clone = document.documentElement.cloneNode(true);
    ['.editor-hotzone', '.editor-panel', '#editor-runtime-style'].forEach(function (sel) {
      var n = clone.querySelector(sel);
      if (n) n.parentNode.removeChild(n);
    });
    var cloneBody = clone.querySelector('body');
    if (cloneBody) cloneBody.classList.remove('editor-mode-active', 'editor-fullscreen-active');
    Array.prototype.forEach.call(clone.querySelectorAll('.editor-hover-el,.editor-selected-el'), function (n) {
      n.classList.remove('editor-hover-el', 'editor-selected-el');
    });
    var html = '<!doctype html>\n' + clone.outerHTML;

    // 注意（环境限制说明，非 bug）：下面这套“创建临时 <a download> + Blob
    // + 触发 click”下载方式，在用户本地双击打开的 HTML 文件里可以正常
    // 工作；但如果这份 HTML 是被放在某些“沙箱化”的在线预览环境里查看
    // （例如受限的 sandbox iframe，未声明 allow-downloads），浏览器可能会
    // 出于安全策略直接拦截这类脚本触发的下载，这是宿主环境的限制，
    // 不是本编辑器的功能缺陷；此时用户仍可用浏览器的“查看源代码/另存为”
        // 兜底导出当前 DOM。
    try {
      var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'deck-edited.html';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    } catch (e) {
      alert('导出下载被当前环境拦截（可能处于沙箱化预览环境），请改用浏览器菜单“另存为”保存本页面。');
    }
  }

  function clearAllAdjustments() {
    if (!confirm('确定要清除本机保存的全部字号/位置调整吗？此操作不可撤销。')) return;
    try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
    location.reload();
  }

  // ── DOM 构建 ─────────────────────────────────────────────────────────
  function injectStyle() {
    var style = document.createElement('style');
    style.id = 'editor-runtime-style';
    style.textContent =
      '.editor-hotzone{position:fixed;left:0;top:0;width:80px;height:80px;z-index:500;}' +
      '.editor-toggle-btn{position:absolute;left:10px;top:10px;width:44px;height:44px;border-radius:50%;' +
      'border:1px solid rgba(255,255,255,.25);background:rgba(9,13,20,.85);color:#f8fafc;font-size:20px;' +
      'line-height:1;cursor:pointer;opacity:0;pointer-events:none;transition:opacity .18s ease,transform .18s ease;' +
      'display:flex;align-items:center;justify-content:center;box-shadow:0 6px 18px rgba(0,0,0,.35);}' +
      '.editor-hotzone.is-hover .editor-toggle-btn,body.editor-mode-active .editor-toggle-btn{opacity:1;pointer-events:auto;}' +
      '.editor-toggle-btn:hover{transform:scale(1.08);}' +
      'body.editor-mode-active .editor-toggle-btn{background:rgba(126,232,250,.92);color:#06101d;border-color:transparent;}' +
      '.editor-hover-el{outline:1px dashed rgba(126,232,250,.75);outline-offset:2px;cursor:pointer;}' +
      '.editor-selected-el{outline:2px dashed #7ee8fa;outline-offset:3px;}' +
      '.editor-panel{display:none;position:fixed;right:0;top:0;height:100%;width:' + PANEL_WIDTH + 'px;z-index:499;' +
      'background:rgba(9,13,20,.96);color:#f8fafc;border-left:1px solid rgba(255,255,255,.14);' +
      'font:14px/1.5 system-ui,"Microsoft YaHei",sans-serif;flex-direction:column;box-shadow:-14px 0 34px rgba(0,0,0,.4);}' +
      '.editor-panel.is-open{display:flex;}' +
      '.editor-panel h3{margin:0;padding:16px 16px 10px;font-size:16px;border-bottom:1px solid rgba(255,255,255,.12);}' +
      '.editor-panel .editor-body{flex:1;overflow:auto;padding:14px 16px;}' +
      '.editor-panel .editor-sel-info{min-height:40px;color:#9aa8bd;font-size:13px;margin-bottom:12px;word-break:break-all;}' +
      '.editor-panel .editor-row{margin-bottom:16px;}' +
      '.editor-panel .editor-row label{display:block;margin-bottom:6px;color:#9aa8bd;font-size:12px;text-transform:uppercase;letter-spacing:.04em;}' +
      '.editor-panel .editor-hstack{display:flex;align-items:center;gap:8px;}' +
      '.editor-panel button{cursor:pointer;border:1px solid rgba(255,255,255,.22);background:#151b27;color:#f8fafc;' +
      'border-radius:6px;padding:8px 10px;font:700 13px/1 system-ui,sans-serif;}' +
      '.editor-panel button:hover{background:#1d2634;}' +
      '.editor-panel input[type=number]{width:64px;text-align:center;background:#0d121b;color:#f8fafc;' +
      'border:1px solid rgba(255,255,255,.22);border-radius:6px;padding:8px 4px;font:700 13px/1 ui-monospace,monospace;}' +
      '.editor-panel .editor-dpad{display:grid;grid-template-columns:repeat(3,36px);grid-template-rows:repeat(2,36px);gap:6px;justify-content:start;}' +
      '.editor-panel .editor-dpad button{padding:0;}' +
      '.editor-panel .editor-pos-label{margin-top:8px;color:#7ee8fa;font:700 12px/1 ui-monospace,monospace;}' +
      '.editor-panel .editor-reset-btn{width:100%;background:#3a1620;border-color:rgba(255,120,120,.4);}' +
      '.editor-panel .editor-reset-btn:hover{background:#4a1a26;}' +
      '.editor-panel .editor-footer{border-top:1px solid rgba(255,255,255,.12);padding:14px 16px;display:flex;flex-direction:column;gap:8px;}' +
      '.editor-panel .editor-export-btn{background:#123a2e;border-color:rgba(120,255,190,.35);}' +
      '.editor-panel .editor-export-btn:hover{background:#164a3a;}' +
      '.editor-panel .editor-note{color:#66738a;font-size:11px;line-height:1.5;}' +
      'body.editor-fullscreen-active .editor-hotzone,body.editor-fullscreen-active .editor-panel{display:none!important;}' +
      '@media print{.editor-hotzone,.editor-panel{display:none!important;}}';
    document.head.appendChild(style);
  }

  function buildHotzone() {
    hotzoneEl = document.createElement('div');
    hotzoneEl.className = 'editor-hotzone';
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'editor-toggle-btn';
    btn.title = '切换可视化编辑模式（E）';
    btn.setAttribute('aria-label', '切换可视化编辑模式');
    btn.textContent = '✏️'; // ✏️
    btn.addEventListener('click', function (e) { e.stopPropagation(); toggleEditMode(); });
    hotzoneEl.appendChild(btn);

    var hoverTimer = null;
    hotzoneEl.addEventListener('mouseenter', function () {
      hoverTimer = setTimeout(function () { hotzoneEl.classList.add('is-hover'); }, 400);
    });
    hotzoneEl.addEventListener('mouseleave', function () {
      clearTimeout(hoverTimer);
      hotzoneEl.classList.remove('is-hover');
    });
    document.body.appendChild(hotzoneEl);
  }

  function buildPanel() {
    panelEl = document.createElement('div');
    panelEl.className = 'editor-panel';

    var h3 = document.createElement('h3');
    h3.textContent = '可视化编辑器';
    panelEl.appendChild(h3);

    var bodyWrap = document.createElement('div');
    bodyWrap.className = 'editor-body';

    selInfoEl = document.createElement('div');
    selInfoEl.className = 'editor-sel-info';
    bodyWrap.appendChild(selInfoEl);

    controlsWrapEl = document.createElement('div');

    // 字号控制
    var fontRow = document.createElement('div');
    fontRow.className = 'editor-row';
    var fontLabel = document.createElement('label');
    fontLabel.textContent = '字号 (px)';
    fontRow.appendChild(fontLabel);
    var fontStack = document.createElement('div');
    fontStack.className = 'editor-hstack';
    var minusBtn = document.createElement('button');
    minusBtn.type = 'button'; minusBtn.textContent = '−'; // −
    minusBtn.addEventListener('click', function () { if (selectedEl) nudgeFont(selectedEl, -FONT_STEP); });
    fontInputEl = document.createElement('input');
    fontInputEl.type = 'number';
    fontInputEl.min = String(MIN_FONT);
    fontInputEl.addEventListener('change', function () { if (selectedEl) applyFontInput(selectedEl, fontInputEl.value); });
    var plusBtn = document.createElement('button');
    plusBtn.type = 'button'; plusBtn.textContent = '+';
    plusBtn.addEventListener('click', function () { if (selectedEl) nudgeFont(selectedEl, FONT_STEP); });
    fontStack.appendChild(minusBtn); fontStack.appendChild(fontInputEl); fontStack.appendChild(plusBtn);
    fontRow.appendChild(fontStack);
    controlsWrapEl.appendChild(fontRow);

    // 位置控制（四向方向键）
    var posRow = document.createElement('div');
    posRow.className = 'editor-row';
    var posLabel = document.createElement('label');
    posLabel.textContent = '位置微移';
    posRow.appendChild(posLabel);
    var dpad = document.createElement('div');
    dpad.className = 'editor-dpad';
    var mk = function (label, dx, dy, col, row) {
      var b = document.createElement('button');
      b.type = 'button'; b.textContent = label;
      b.style.gridColumn = String(col); b.style.gridRow = String(row);
      b.addEventListener('click', function () { if (selectedEl) nudge(selectedEl, dx, dy); });
      return b;
    };
    dpad.appendChild(mk('↑', 0, -POS_STEP, 2, 1));
    dpad.appendChild(mk('←', -POS_STEP, 0, 1, 2));
    dpad.appendChild(mk('↓', 0, POS_STEP, 2, 2));
    dpad.appendChild(mk('→', POS_STEP, 0, 3, 2));
    posRow.appendChild(dpad);
    posLabelEl = document.createElement('div');
    posLabelEl.className = 'editor-pos-label';
    posRow.appendChild(posLabelEl);
    controlsWrapEl.appendChild(posRow);

    // 重置
    var resetRow = document.createElement('div');
    resetRow.className = 'editor-row';
    var resetBtn = document.createElement('button');
    resetBtn.type = 'button';
    resetBtn.className = 'editor-reset-btn';
    resetBtn.textContent = '重置当前元素';
    resetBtn.addEventListener('click', function () { if (selectedEl) resetElement(selectedEl); });
    resetRow.appendChild(resetBtn);
    controlsWrapEl.appendChild(resetRow);

    bodyWrap.appendChild(controlsWrapEl);
    panelEl.appendChild(bodyWrap);

    var footer = document.createElement('div');
    footer.className = 'editor-footer';
    var exportBtn = document.createElement('button');
    exportBtn.type = 'button';
    exportBtn.className = 'editor-export-btn';
    exportBtn.textContent = '⬇ 导出调整后的 HTML';
    exportBtn.addEventListener('click', exportHtml);
    footer.appendChild(exportBtn);
    var clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.textContent = '清空本机全部调整';
    clearBtn.addEventListener('click', clearAllAdjustments);
    footer.appendChild(clearBtn);
    var note = document.createElement('div');
    note.className = 'editor-note';
    note.textContent = '按 E 或点击左上角按钮退出编辑；按 F 全屏演示时会自动隐藏编辑器。调整会自动保存在本机浏览器中。';
    footer.appendChild(note);
    panelEl.appendChild(footer);

    document.body.appendChild(panelEl);
    refreshPanelForSelection();
  }

  // ── 事件绑定 ─────────────────────────────────────────────────────────
  function bindEvents() {
    document.addEventListener('mouseover', function (e) {
      if (!editModeActive) return;
      var el = e.target.closest ? e.target.closest(TEXT_SELECTOR) : null;
      if (!el || !el.closest('.slide.is-active')) return;
      if (hoverEl && hoverEl !== el) hoverEl.classList.remove('editor-hover-el');
      hoverEl = el;
      if (el !== selectedEl) el.classList.add('editor-hover-el');
    });
    document.addEventListener('mouseout', function (e) {
      if (!editModeActive) return;
      var el = e.target.closest ? e.target.closest(TEXT_SELECTOR) : null;
      if (el && el !== selectedEl) el.classList.remove('editor-hover-el');
    });

    // 点击拦截分两层，注意先后顺序（这是一处容易踩坑的地方）：
    // ① 面板/热区容器本身挂“冒泡阶段”的 stopPropagation 监听（见下方
    //    panelEl/hotzoneEl.addEventListener），事件传播顺序是
    //    捕获(document→…→target) → 目标阶段(按钮自己的 click 回调先跑)
    //    → 冒泡(target→…→document)；在冒泡阶段挡在 panelEl/hotzoneEl
    //    这一层，能保证按钮自己的回调已经先正常执行完，只是不让事件
    //    再往上冒泡到 document 触发 runtime.js 的翻页逻辑。
    //    早期实现曾经在 document 的“捕获阶段”对面板/热区点击也调用
    //    stopPropagation()，结果事件在还没到达按钮（目标阶段）之前就被
    //    掐断，导致面板里所有按钮的 click 回调全部失效——这里改用②的
    //    捕获阶段监听只负责画面内容区域，不再插手面板/热区自己的点击。
    // ② 编辑模式开启时，画面（.slide）内容区域的点击不该触发翻页
    //    （否则调整途中误点就翻页、丢失当前选中状态），改为选中/取消
    //    选中文字元素；这部分沿用 document 捕获阶段 + stopPropagation，
    //    因为 .slide 内容元素本身没有需要保留的原生 click 回调。
    document.addEventListener('click', function (e) {
      var inChrome = e.target.closest && (e.target.closest('.editor-panel') || e.target.closest('.editor-hotzone'));
      if (inChrome) return; // 交给面板/热区自己冒泡阶段的监听处理，这里不拦截
      if (!editModeActive) return;
      e.stopPropagation();
      var el = e.target.closest ? e.target.closest(TEXT_SELECTOR) : null;
      if (el && el.closest('.slide.is-active')) selectElement(el);
      else deselectElement();
    }, true);
    panelEl.addEventListener('click', function (e) { e.stopPropagation(); });
    hotzoneEl.addEventListener('click', function (e) { e.stopPropagation(); });

    document.addEventListener('keydown', function (e) {
      var tag = (document.activeElement && document.activeElement.tagName) || '';
      var typing = tag === 'INPUT' || tag === 'TEXTAREA' || (document.activeElement && document.activeElement.isContentEditable);
      if (e.key.toLowerCase() === 'e' && !typing) { e.preventDefault(); toggleEditMode(); }
      if (e.key.toLowerCase() === 'f') { exitEditMode(); } // 全屏与编辑模式互斥，实际 requestFullscreen 由 runtime.js 负责
    });

    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('webkitfullscreenchange', onFullscreenChange);
  }

  function init() {
    injectStyle();
    buildHotzone();
    buildPanel();
    bindEvents();
    restoreFromStorage();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
