(function () {
  const slides = Array.from(document.querySelectorAll('.slide'));
  const stage = document.querySelector('.deck-stage');
  const currentEl = document.querySelector('[data-current]');
  const totalEl = document.querySelector('[data-total]');
  const overview = document.querySelector('.overview');
  const channel = 'BroadcastChannel' in window ? new BroadcastChannel('html-deck-sync') : null;
  let index = Math.max(0, Math.min(slides.length - 1, Number(location.hash.replace('#/', '')) - 1 || 0));
  let started = Date.now();
  let speakerWin = null;

  function scale() {
    if (!stage) return;
    const s = Math.min(innerWidth / 1920, innerHeight / 1080);
    document.documentElement.style.setProperty('--deck-scale', s.toFixed(4));
  }

  function slideData(i) {
    const slide = slides[i];
    return {
      index: i,
      total: slides.length,
      title: slide?.querySelector('h1,h2')?.textContent || '',
      notes: slide?.querySelector('.notes')?.innerHTML || '本页没有备注。',
      nextTitle: slides[i + 1]?.querySelector('h1,h2')?.textContent || '结束',
      elapsed: Math.floor((Date.now() - started) / 1000)
    };
  }

  function publish() {
    const data = slideData(index);
    if (channel) channel.postMessage({type: 'state', data});
    if (speakerWin && !speakerWin.closed) speakerWin.postMessage({type: 'state', data}, '*');
  }

  function show(i, silent) {
    index = Math.max(0, Math.min(slides.length - 1, i));
    slides.forEach((slide, n) => slide.classList.toggle('is-active', n === index));
    if (currentEl) currentEl.textContent = String(index + 1);
    if (totalEl) totalEl.textContent = String(slides.length);
    history.replaceState(null, '', '#/' + (index + 1));
    runCounters();
    if (!silent) publish();
  }

  function runCounters() {
    const nums = slides[index]?.querySelectorAll('[data-count-to]') || [];
    nums.forEach((el) => {
      const target = Number(el.getAttribute('data-count-to')) || 0;
      const suffix = el.getAttribute('data-suffix') || '';
      if (document.body.classList.contains('no-motion')) {
        el.textContent = String(target) + suffix;
        return;
      }
      const start = performance.now();
      function tick(t) {
        const p = Math.min(1, (t - start) / 700);
        el.textContent = String(Math.round(target * p)) + suffix;
        if (p < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    });
  }

  function next() { show(index + 1); }
  function prev() { show(index - 1); }

  function buildOverview() {
    if (!overview || overview.children.length) return;
    slides.forEach((slide, i) => {
      const button = document.createElement('button');
      button.innerHTML = '<span>' + String(i + 1).padStart(2, '0') + '</span>' + (slide.querySelector('h1,h2')?.textContent || 'Untitled');
      button.addEventListener('click', () => {
        overview.classList.remove('is-open');
        show(i);
      });
      overview.appendChild(button);
    });
  }

  function openSpeaker() {
    if (speakerWin && !speakerWin.closed) {
      speakerWin.focus();
      publish();
      return;
    }
    speakerWin = window.open('', 'html-deck-speaker', 'width=1180,height=760');
    if (!speakerWin) return;
    speakerWin.document.write(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>Speaker</title><style>
      *{box-sizing:border-box}body{margin:0;background:#090d14;color:#f8fafc;font-family:system-ui,"Microsoft YaHei",sans-serif}
      main{height:100vh;display:grid;grid-template-columns:1.1fr .9fr;grid-template-rows:150px 1fr;gap:16px;padding:16px}
      .card{border:1px solid rgba(255,255,255,.14);border-radius:8px;background:#151b27;padding:18px;overflow:auto}
      h1,h2,p{margin:0}.title{font-size:30px;line-height:1.18}.next{color:#7ee8fa;font-size:24px}
      .timer{font:800 70px/1 ui-monospace,Consolas,monospace;color:#4dd4ac}.notes{font-size:25px;line-height:1.45}
      .meta{color:#9aa8bd;font:700 16px/1 ui-monospace,Consolas,monospace}
    </style></head><body><main>
      <section class="card"><p class="meta" id="page"></p><h1 class="title" id="title"></h1></section>
      <section class="card"><p class="meta">NEXT</p><h2 class="next" id="next"></h2></section>
      <section class="card"><p class="meta">SCRIPT</p><div class="notes" id="notes"></div></section>
      <section class="card"><p class="meta">TIMER</p><div class="timer" id="timer">00:00</div></section>
    </main><script>
      function pad(n){return String(n).padStart(2,'0')}
      function render(d){if(!d)return;page.textContent=(d.index+1)+' / '+d.total;title.textContent=d.title;next.textContent=d.nextTitle;notes.innerHTML=d.notes;timer.textContent=pad(Math.floor(d.elapsed/60))+':'+pad(d.elapsed%60)}
      addEventListener('message',e=>{if(e.data&&e.data.type==='state')render(e.data.data)})
      if('BroadcastChannel' in window){const c=new BroadcastChannel('html-deck-sync');c.onmessage=e=>{if(e.data&&e.data.type==='state')render(e.data.data)}}
    </script></body></html>`);
    speakerWin.document.close();
    setTimeout(publish, 80);
  }

  function drawFx() {
    const canvas = document.querySelector('.fx-canvas');
    if (!canvas || document.body.classList.contains('no-motion')) return;
    const ctx = canvas.getContext('2d');
    const ratio = devicePixelRatio || 1;
    canvas.width = 1920 * ratio;
    canvas.height = 1080 * ratio;
    ctx.scale(ratio, ratio);
    const points = Array.from({length: 42}, (_, i) => ({x: (i * 137) % 1920, y: (i * 89) % 1080, r: 1 + (i % 4)}));
    let frame = 0;
    function tick() {
      ctx.clearRect(0, 0, 1920, 1080);
      ctx.strokeStyle = 'rgba(126,232,250,.18)';
      ctx.fillStyle = 'rgba(77,212,172,.35)';
      points.forEach((p, i) => {
        const x = p.x + Math.sin((frame + i * 12) / 80) * 24;
        const y = p.y + Math.cos((frame + i * 8) / 90) * 18;
        ctx.beginPath(); ctx.arc(x, y, p.r, 0, Math.PI * 2); ctx.fill();
        if (i % 3 === 0) {
          const q = points[(i + 7) % points.length];
          ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(q.x, q.y); ctx.stroke();
        }
      });
      frame += 1;
      requestAnimationFrame(tick);
    }
    tick();
  }

  document.addEventListener('keydown', (e) => {
    if (['ArrowRight', ' ', 'PageDown'].includes(e.key)) { e.preventDefault(); next(); }
    if (['ArrowLeft', 'PageUp'].includes(e.key)) { e.preventDefault(); prev(); }
    if (e.key === 'Home') show(0);
    if (e.key === 'End') show(slides.length - 1);
    if (e.key.toLowerCase() === 'f' && document.documentElement.requestFullscreen) document.documentElement.requestFullscreen();
    if (e.key.toLowerCase() === 'b') { document.body.classList.toggle('no-motion'); publish(); }
    if (e.key.toLowerCase() === 's') openSpeaker();
    if (e.key.toLowerCase() === 'o') { buildOverview(); overview?.classList.toggle('is-open'); }
    if (e.key === 'Escape') overview?.classList.remove('is-open');
  });
  document.addEventListener('click', (e) => {
    if (e.target.closest('.overview')) return;
    if (e.clientX > innerWidth / 2) next(); else prev();
  });
  setInterval(publish, 1000);
  addEventListener('resize', scale);
  scale();
  drawFx();
  show(index, true);
  publish();
})();
