<!-- TASK-019: 新增——瀑布式全景总览（G 键）机制拆解与实现口径；来源 huashu-slides 技能学习 + 用户指定参考效果图，缩略图机制承接 BENCHMARK.md §7（baoyu-design 同源 DOM 深克隆 + transform:scale()） -->
# PANORAMA OVERVIEW（瀑布式全景总览）

本文件定义 html-deck 运行时的**第三种导航视图**：G 键瀑布式全景总览——全部 slide 以真实缩略图铺成一面 3D 倾斜墙，用于开场展示体量、收尾回顾全貌、宣讲中快速跳页。与既有两视图的分工：

- **O 键总览**：文字按钮格阵（编号 + 标题），轻量、按标题检索；
- **G 键全景（本文件）**：同源 DOM 克隆缩略图墙 + 3D 倾斜，重视觉冲击、按版面视觉检索；
- **S 键演讲者窗口**：讲者私有视图（讲稿 / 计时 / 下一页）。

三者互斥同屏（开任一即收其余显示态），各自独立开关。

---

## 1. 机制拆解（用户参考效果图 → 可实现四要素）

参考效果图特征：纯黑背景上，一排排 slide 缩略图卡片组成微倾斜的"照片墙"，卡片带编号，整体有透视纵深，边缘卡片出血到视口外。拆解为四个可原生实现的要素：

1. **缩略图生成 = 同源 DOM 深克隆 + `transform:scale()`**（承接 `BENCHMARK.md` §7 baoyu-design 结论）：不截图、不引入渲染管线——`slide.cloneNode(true)` 放入 1920×1080 的 `.wf-scale` 容器，整体 `scale(卡片宽/1920)` 缩到卡片尺寸。预览与成品永远一致、零外部依赖；克隆体内的 canvas 动效层（`.fx-canvas` 等）在克隆中关闭显示，避免重复动画开销。
2. **3D 倾斜墙 = 单层透视 + 复合旋转**：容器 `.waterfall` 设 `perspective: 1150px`；内部网格 `.wf-wall` 固定 2120px 宽、4 列 × 460px 卡片，居中后 `translate(-50%,-50%) rotateY(-24deg) rotateX(7deg) scale(1.16)`，另加个体 `rotate: 1.2deg` 制造"随手一斜"的非机械感。放大 1.16 倍让边缘卡片出血，复刻参考图的铺满感。
3. **网格布局 = 固定宽 Grid 居中**：`grid-template-columns: repeat(4, 460px)` + `justify-content: center`，卡片 `aspect-ratio: 16/9` 与 slide 画布同比例；墙宽不随视口缩放（全景本身就是"俯视一整面墙"，小视口自然出血，无需响应式重排）。
4. **入场/出场 = 交错缩放淡入**：每张卡片 `animation: wfIn .7s` 从 `scale: 1.5`（个体 scale 属性，与卡片自身 transform 解耦）淡入到 1，`animation-delay: calc(var(--i) * 28ms)` 按页序交错，形成"瀑布"落位感；`body.no-motion`（B 键静态降级）下动画整体关闭，直接呈现终态。

## 2. 跳转机制（零导航逻辑复制）

全景模块**不实现自有翻页逻辑**，跳转委托既有 O 总览的按钮：

1. 首次需要跳转时若 `.overview` 按钮未构建，向 document 派发一次合成 `keydown('o')`，借内核原生处理构建按钮，随后收回 `.is-open` 显示态（与 Esc 关闭同口径）；
2. 点击 `.wf-card[i]` → `overview.children[i].click()`，内核按钮的原生点击处理器执行 `remove('is-open') + show(i)`——翻页、hash 深链接、演讲者同步全部由既有内核闭环，全景模块只做"点哪个按钮"。

此设计保证：导航内核一字节不改（铁律），全景与 O 总览永远走同一条跳转路径，无双份逻辑漂移风险。

## 3. 交互口径

| 操作 | 行为 |
| --- | --- |
| G 键 | 开关全景；打开时标注当前页卡片（`.current`，accent 描边），并收回 O 总览显示态 |
| Esc 键 | 关闭全景（内核原有 Esc 关 O 总览逻辑不受影响，两者独立） |
| O 键 | 开 O 总览时若全景开着，全景关闭（互斥） |
| 点击卡片 | 跳转到对应页并关闭全景 |
| 点击卡片外空白 | 仅关闭性操作，**不触发** document 级左半/右半翻页（`.waterfall` 上 `stopPropagation`） |
| B 键（no-motion） | 全景可正常开关，入场动画静态化 |
| 打印 | `@media print` 中 `.waterfall` 强制 `display:none`，不进打印流 |

## 4. 样式口径

- 全部颜色从主题 token 派生：`var(--bg)` 铺底（径向渐变加深）、`var(--accent)` 标当前卡、`var(--text)` 透明度档做边框与提示文字——换主题不破，禁止硬编码 hex（`THEMES.md` token 派生纪律）；
- 克隆体内 `.slide` 强制终态显示（`opacity:1; visibility:visible; transform:none; filter:none`），选择器 `.wf-scale .slide`  specificity 高于 `.slide`、与 `.slide.is-active` 同级但声明在后，稳赢；`body.transition-fade/scale-fade` 的 filter/transform 钩子用 `filter:none` 兜底；
- 卡片编号徽章（`.wf-num`）走 `var(--font-mono)` + 半透明黑底 pill，与 deck-ui 同语言；标题条（`.wf-title`）用底部渐变 scrim（与 `html-layout-system.md` 图底文字 scrim 纪律一致）。

## 5. QA 核对点（deck 级，挂接 final-quality-check.md §3）

- G 键可开关全景，卡片数 = slide 总数，当前页卡片有 `.current` 标注；
- 卡片缩略图与对应 slide 成品视觉一致（同源克隆保证；抽查封面 / 最重版面 / 尾页）；
- 点击卡片跳转后 `[data-current]` 页码、hash、演讲者窗口同步正确；
- 空白处点击不翻页；Esc/G/O 三键互斥行为符合 §3 表；
- B 键静态降级与 `@media print` 下全景不破版、不进打印；
- 零 console 报错；无任何外部资源请求（零 CDN 纪律）。
