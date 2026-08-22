/* TASK-021 B.2: 运行时自适应字号收缩——文字溢出画布/互相重叠的最后一道防线。
 * B.1 的 CSS overflow:hidden/min-height:0 边界补丁只保证"不再撑破布局互相重叠"，
 * 但仍可能把文字裁掉一部分（观众看不到内容）；本脚本在此基础上先尝试迭代降字号
 * 让内容自己缩小到放得下，缩到下限仍装不下时才退化到 line-clamp 省略号裁切。
 * 兜底约定：运行时兜底只保证观众看不到溢出/重叠（体验层不失败），但会在溢出
 * 容器与 <body> 上打 data-autofit-overflow="true" 标记——qa_render.py 的 Playwright
 * 分支据此读取并判定为硬失败（流程层要失败），倒逼回源头精简内容或拆页，
 * 不能让 line-clamp 变成"眼不见为净"。
 */
(function () {
  var STEP = 0.04; // 每轮降 4%
  var FLOOR = 0.70; // 降到基准字号的 70% 为止
  var MAX_ROUNDS = 8;

  function baseFontPx(el) {
    var stored = el.getAttribute('data-autofit-base');
    if (stored) return parseFloat(stored);
    var px = parseFloat(getComputedStyle(el).fontSize) || 16;
    el.setAttribute('data-autofit-base', String(px));
    return px;
  }

  function overflows(el) {
    // +2 容差，避免因子像素四舍五入触发误判
    return el.scrollHeight > el.clientHeight + 2 || el.scrollWidth > el.clientWidth + 2;
  }

  function resetFit(el) {
    el.style.fontSize = '';
    el.classList.remove('autofit-clamped');
    el.removeAttribute('data-autofit-overflow');
  }

  function fitOne(el) {
    // TASK-022: 可视化编辑器（editor.js）用户手动调整过字号/位置的元素带有
    // data-editor-adjusted 标记——手动调整的优先级高于自动收缩，一旦生效
    // 就应该被后续每次翻页/resize 一直尊重，不能被下面的 resetFit()/自动
    // 降字号逻辑悄悄覆盖回去。用户在编辑器面板点“重置”时会摘掉这个标记，
    // 并调用本文件暴露的 window.__deckAutofitRefit() 主动让自动收缩重新
    // 接管该元素，不需要等到下次翻页才恢复。
    if (el.hasAttribute('data-editor-adjusted')) return;
    resetFit(el);
    if (!overflows(el)) return;
    var base = baseFontPx(el);
    var ratio = 1;
    for (var round = 0; round < MAX_ROUNDS; round++) {
      ratio = Math.max(FLOOR, 1 - STEP * (round + 1));
      el.style.fontSize = (base * ratio).toFixed(2) + 'px';
      if (!overflows(el)) return;
      if (ratio <= FLOOR) break;
    }
    // 降到下限仍溢出：line-clamp 兜底裁切，同时打硬失败标记供 QA 读取
    el.classList.add('autofit-clamped');
    el.setAttribute('data-autofit-overflow', 'true');
    document.body.setAttribute('data-autofit-overflow', 'true');
  }

  function fitSlide(slide) {
    if (!slide) return;
    var targets = slide.querySelectorAll('[data-autofit]');
    for (var i = 0; i < targets.length; i++) fitOne(targets[i]);
  }

  function fitActive() {
    fitSlide(document.querySelector('.slide.is-active'));
  }

  function init() {
    // 标记脚本已跑过一轮，供 QA 区分"没溢出"与"脚本没跑"两种情况
    document.body.setAttribute('data-autofit-ready', 'true');
    fitActive();
    var stage = document.querySelector('.deck-stage');
    if (!stage || typeof MutationObserver === 'undefined') return;
    // 只响应 .slide 元素自身的 class 变化（runtime.js 的 is-active 切换）——
    // fitOne() 会在 data-autofit 后代元素上 add/remove 'autofit-clamped' 类，
    // 若 subtree:true 不加过滤，这些自身产生的 class 变化会被同一个观察者
    // 再次捕获，反过来触发 fitActive() 重新丈量，形成无限反馈循环（曾导致
    // Playwright QA 在真实环境下卡死）。用 mutation.target 过滤只认 .slide。
    var mo = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        var m = mutations[i];
        if (m.attributeName === 'class' && m.target && m.target.classList && m.target.classList.contains('slide')) {
          fitActive();
          break;
        }
      }
    });
    mo.observe(stage, {attributes: true, attributeFilter: ['class'], subtree: true});
    // 视口缩放（--deck-scale）变化或窗口 resize 后，clientHeight/clientWidth 的
    // CSS 像素值不变（--deck-scale 只是 transform 视觉缩放，不改变布局盒尺寸），
    // 理论上不需要重新计算；仍在 resize 后兜底重估一次，覆盖字体子像素误差场景。
    var resizeTimer = null;
    window.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(fitActive, 200);
    });
  }

  // TASK-022: 供 editor.js 在用户点“重置”后主动请求重新计算当前页自适应
  // 字号（摘掉 data-editor-adjusted 标记之后，不等下次翻页/resize 就立刻
  // 恢复自动收缩效果）。两个文件通过 window 上的这一个函数名互相协作，
  // 不需要互相引用彼此的内部实现。
  window.__deckAutofitRefit = fitActive;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
