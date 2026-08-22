# ANIMATIONS

动画通过 `data-animate` 挂载，运行时只在当前页激活。按 B 键为静态降级，添加 `body.no-motion`。

## 目录

<!-- TASK-034: 补全登记——以下 7 个动画此前已在 assets/animations/animations.css 实现（有真实
     @keyframes + [data-animate] 选择器）并被 render_deck.py 实际使用，但一直没有登记进本文件，
     与 SKILL.md「动画只使用 ANIMATIONS.md 的 data-animate 名称」的口径不一致（文档滞后于实现）。
     本次补齐文档，不新增任何 CSS 动画实现。 -->
- `fade-up`：标题、正文从下方轻入。
- `stagger-list`：列表逐项进入（子元素按 `--i` 自定义属性错开 70ms/项）。
- `count-up`：KPI 数字从 0 计数到目标值（JS 驱动，见 runtime.js，配合 `data-count-to`/`data-suffix`）。
- `blur-in`：章节页或 quote 柔和显现。
- `kenburns`：hero 图片缓慢缩放。
- `slide`：翻页过渡。
- `rise-in`：比 fade-up 位移更大、略带弹性的上浮进入，用于卡片/时间轴条目（`.timeline-item` 默认套用，`--i` 控制错开节奏）。
- `zoom-pop`：轻微放大回弹的缩放入场，用于 KPI 卡片、目录页中心枢纽球体一类"焦点主体"。
- `gradient-flow`：渐变背景持续流动（无限循环），用于强调条/进度感装饰。
- `shimmer-sweep`：一道高光斜向扫过，用于强调卡片/按钮的一次性提示。
- `typewriter`：文字逐字符打出，配合光标闪烁。
- `path-draw`：SVG `path`/`line`/`polyline` 描边从无到有绘制（`stroke-dasharray/dashoffset` 动画）；容器元素挂 `data-animate="path-draw"`，作用于其内部真实的 `path`/`line`/`polyline` 子元素（`circle`/`rect` 不受影响）。**注意**：`stroke-dasharray:900` 会覆盖元素自身在组件 CSS 里声明的装饰性虚线值（如 `stroke-dasharray:6 5`），绘制完成后线条呈现为连续实线，不是原本的虚线节奏——只在"线条本身连续与否不影响设计意图"时使用；B 键静态降级/`prefers-reduced-motion` 下已修复为强制 `stroke-dashoffset:0`（呈现画完的最终态，不会因动画被关闭而线条整体不可见，见 animations.css TASK-034 fix）。
- `ripple-reveal`：从中心向外扩散的圆形揭示，用于强调型卡片或焦点区块的整体入场。

## 降级策略

- `prefers-reduced-motion: reduce` 自动关闭动画。
- B 键切换静态模式。
- 打印模式关闭所有动画和阴影。
- QA 中如果动画遮挡内容，该页扣 10 分并建议去除动画。

<!-- TASK-022 -->
## 与内嵌可视化编辑器（E 键）的关系

`assets/runtime/editor.js` 允许用户在浏览器里对文字元素做小范围字号/位置微调（详见
SKILL.md 阶段 3 第 8 条）。本文件登记的入场动画均通过 `animation-fill-mode: both`
在动画结束后持续持有 `to` 关键帧的最终态；由于 CSS 动画在层叠优先级上高于内联
`style`，若不做处理，编辑器写入的 `style.transform` 会被已完成的入场动画"按住"
不生效。因为上面登记的动画 `to` 关键帧全部收敛到等价于无变换的终态（`translate(0)`
/`scale(1)`），editor.js 在用户开始调整某个带 `data-animate` 的元素（或其内部文字
子元素）时，会先把该元素的 `animation` 置为 `none`（不产生可见跳变，因为 to 关键帧
本就等价于无变换），再叠加自己的 `translate()` 位移，两者不会互相打架。这个
`animation:none` 是内联 style，写入后永久生效——即使之后翻页离开、再翻回来，
`.slide.is-active [data-animate=...]` 这条 CSS 规则依旧匹配，但内联样式的优先级
更高，动画不会重新播放。这是有意的取舍：一旦某元素被手动调整过，就默认放弃它的
入场动画，换取手动位置/字号在此后每次翻回该页时都保持稳定生效，不会被动画重新
播放的瞬间过程覆盖掉。编辑器面板的"重置"只清空字号/位置这两项调整（含对应
`data-editor-*` 属性），不会恢复 `animation`，如需该元素重新播放入场动画，需要
重新执行 `render_deck.py` 生成一份未编辑过的新文件。
