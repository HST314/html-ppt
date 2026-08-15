<!-- TASK-007: 新增——HTML 页面布局系统（Grid/Flex/图片区域/色块区域/信息模块五子系统 + 合并蓝图定义 + 输出稳定规则 + 反模式） -->
# HTML LAYOUT SYSTEM（页面布局系统）

本文件是 html-deck 的**布局落版层**规范，回答两个问题：**版式选好后用什么空间系统落版**、**落版必须满足哪些稳定规则**。

与其他文档的分工（互不替代）：

- `page-logic-patterns.md`：内容 → 页面逻辑（13 类），决定"这一页是什么关系"。
- `layout-patterns.md`：逻辑 → layout pattern（12 种），决定"关系如何被看见"（选什么版式）。
- **本文件**：pattern → 空间落版，决定"版式如何用 Grid/Flex/图片区/色块/信息模块稳定搭出来"，并承载 Layout Blueprint 的**唯一字段口径**与 HTML 输出稳定规则。
- `PROJECT_IMAGES.md`：项目图片的内容侧纪律（选图、零遗漏、caption）；本文件 §3 只管图片**区域**的落版几何。

触发时机：执行流程总线第⑤步（视觉结构选择，蓝图落盘）与第⑥步（HTML 生成，落版实现）；QA 在第⑦步按 §6/§7 检查项核验。

---

## 0. Layout Blueprint（合并蓝图定义 · 全库唯一口径）

每一页生成前必须先定义 Layout Blueprint，逐页落盘 `state/visual_blueprints.md`。

**口径合并说明（TASK-007）**：用户蓝图七字段（页面类型/主视觉区域/标题区域/内容区域/辅助区域/图片区域/留白区域）与原视觉蓝图八字段（视觉焦点/标题位置/主体区域/辅助信息区域/留白比例/SVG需求/图片需求/选型理由）**合并为一份蓝图定义**，全库只认本节口径，禁止两套并存。映射关系：

| 用户七字段 | 原八字段 | 合并后字段（九字段） | 填写内容 |
| --- | --- | --- | --- |
| 页面类型 | —（新增列） | **页面类型** | <!-- TASK-008 fix --><!-- TASK-010 fix -->取值域 = 10 类业务场景（封面页/章节页/品牌价值页/产品介绍页/项目方案页/流程页/数据页/案例页/成果展示页/总结页）+ 1 个骨架保留项 `目录页(toc)`，全库唯一口径（唯一定义见 `references/design-scenario-system.md` §2 注）；与 art DNA 四类页面（cover/content/section/closing）为**正交口径**——art DNA 类由场景推导（封面页→cover、章节页→section、总结页-结束形式→closing、其余场景→content），不在蓝图中重复登记 |
| 主视觉区域 | 视觉焦点 | **主视觉区域（视觉焦点）** | 全页唯一视觉锚点所在区域及其承载物（主结论数字 / 主图 / 中心节点 / 第一流程节点） |
| 标题区域 | 标题位置 | **标题区域（标题位置）** | 顶部通栏 / 顶部左侧 / 居中 等，action title 落位 |
| 内容区域 | 主体区域 | **内容区域（主体区域）** | 主结构承载区：用哪个子系统（Grid/Flex/图片区/色块）搭、几个信息模块 |
| 辅助区域 | 辅助信息区域 | **辅助区域（辅助信息）** | takeaway 结论条 / 说明栏 / 编号引导等次级信息落位 |
| 图片区域 | 图片需求 | **图片区域（图片需求）** | 是否需图；需图时登记落位区域、`contain`/`cover`、来源图 ID |
| 留白区域 | 留白比例 | **留白区域（留白比例）** | 留白比例（≥30%/≥35% 按 pattern）与主要留白位置 |
| — | SVG需求 | **SVG需求** | 工程字段保留：是否需 SVG 连接件/环形/动线 |
| — | 选型理由 | **选型理由** | 工程字段保留：pattern/变体选型与冲突裁决记录 |

`state/visual_blueprints.md` 每页一行，机器可读表格，列序固定：

| 页码 | 布局pattern | 变体 | 页面类型 | 主视觉区域(视觉焦点) | 标题区域(标题位置) | 内容区域(主体区域) | 辅助区域(辅助信息) | 图片区域(图片需求) | 留白区域(留白比例) | SVG需求 | 选型理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

- 行键三列（页码/布局pattern/变体）+ 蓝图九字段，共 12 列；九字段任一空缺即 QA 判失败（见 `QA_RUBRIC.md` 流程门禁第 4 条）。
- 蓝图字段必须与本页语义登记一致（主视觉区域与 `state/page_semantics.md` 视觉焦点同一、信息组数与内容区域承载一致）。
- 蓝图各区域字段的落版实现必须落在 §1–§5 五个子系统之一，禁止绕开子系统临场拼版式。

---

## 1. Grid 系统（多列等宽/格阵容器）

**适用场景**：平等并列的多区块排布——矩阵格阵、KPI 大数字行、目录编号卡片、明细格阵、多卡分区。需要严格行列对齐、等高列、通栏跨列时一律用 Grid，不用 float/绝对定位手排。

**token / 变量**：

- 列轨：`repeat(N, minmax(0, 1fr))`（N=2/3/4），`minmax(0,1fr)` 防长内容撑爆列宽（对标来源 §8-A）。
- 间距：gap 走间距阶梯 token（§6 规则 5），格阵默认 24px 档；页边距 `--slide-padding`（96px，≥86px）。
- 通栏：标题/takeaway/单容器分支用 `grid-column: 1 / -1` 跨全宽（实现于 `assets/components/layouts.css`）。
- 复杂格阵允许 `grid-column: span 2` / `grid-row: span 2` 的主格放大（bento 用法），主格即蓝图主视觉区域。

**与 layout-patterns.md 版式的映射**：

| pattern / 变体 | Grid 用法 |
| --- | --- |
| ⑦ 矩阵（matrix，grid-2x2 / grid-2x3 变体） | `repeat(2|3, minmax(0,1fr))` 等宽格阵 |
| ⑥ 数据大数字（big-number / kpi 行） | 一行 `repeat(4, minmax(0,1fr))`，大数字卡逐格落位 |
| 目录页（toc） | 2×N 编号卡片格阵 |
| ⑫ 层级空间结构（规整网格变体） | 分层格阵，L1 层主格放大 |
| ⑨ 非对称图文（bento 变体） | 主格 `span 2` + 副格阵 |

---

## 2. Flex 系统（单轴链式/居中/空间分配）

**适用场景**：单轴排布——流程链与步骤条（横向链）、封面/结束页纵向居中堆叠、标题+kicker+lede 的纵向节奏、标签 pill 行、双栏左右分区的行容器；需要某块吸收剩余空间（`flex:1`）时用 Flex，不用 Grid 硬凑。

**token / 变量**：

- 行容器：`.row`（`display:flex; gap:24px; align-items:center`），可换行 `.row.wrap`。
- 纵向节奏：`.stack > * + * { margin-top: 14px }` 基线节奏，配合 `mt-s/m/l`（8/18/32）间距阶梯。
- 空间分配：`.fill { flex:1 }` 吸收余量；链式节点 `flex:1` 等分、连接符号 `flex-shrink:0` 不压缩。
- 居中：`.center`（align+justify 双居中）用于封面/结束页主视觉。

**与 layout-patterns.md 版式的映射**：

| pattern / 变体 | Flex 用法 |
| --- | --- |
| ③ 路径式流程（chain-3 / chain-4 链式变体） | 横向 flex 链：节点 `flex:1` + 方向符号/箭头 `flex-shrink:0` |
| 封面 / 尾页（cover / closing） | 纵向 flex 居中堆叠（kicker→标题→lede→pill 行） |
| ⑧ 左文右图（text-image） | 双栏 flex 行：文栏 `flex:1`，图栏定比 |
| ⑤ 对比构图（compare / vs-split） | 双侧 flex 栏 + 分界徽标 |
| ⑩ 产品英雄图（product-hero） | 图区与信息栏的 flex 分配 |

---

## 3. 图片区域系统（独立稳定容器 + 保真落版）

**适用场景**：一切图片落位——满幅主图（hero）、左文右图图锚、图集、对比图、产品主体图。图片只进**独立、稳定、不可溢出的图片容器**，禁止裸 `<img>` 直接塞进文字流。

**token / 变量**：

- 容器：固定区域 + `overflow:hidden`；图底文字必须压 scrim 渐变条（`linear-gradient(transparent → rgba(暗色,.55–.65))`）保证可读（对标来源 §8-D）。
- 保真：`object-fit` 默认 `contain`；仅确认裁切不损主体时才允许显式 `cover` 并在 QA 记录理由（沿用 SKILL.md 阶段 6 硬约束）。
- 比例：缩略/预览位用 `aspect-ratio: 16/9` 等比占位，禁止双向硬拉伸（§6 规则 4）。
- 内容侧纪律（选图/零遗漏/caption）以 `PROJECT_IMAGES.md` 为准，本节只管区域几何。

**与 layout-patterns.md 版式的映射**：

| pattern | 图片区域用法 |
| --- | --- |
| ⑩ 产品英雄图（product-hero） | 主图区 ≥40% 面积，独立容器 + 信息栏 |
| ⑪ 主图+细节（hero-details） | 1 主图区 + 1–3 细节图区，同容器族 |
| ⑧ 左文右图（text-image） | 图栏定比容器，文栏 flex:1 |
| ⑨ 非对称图文（asym-mix） | 主图格 + 文字格的非对称格阵 |
| gallery / compare（组件库 role） | 等比图格阵 / 双图对照容器 |

---

## 4. 色块区域系统（无图骨架 + 强调面）

**适用场景**：无真实图片时的版面骨架与氛围——渐变色块、低饱和光斑、scrim 暗条、accent 强调面、分区底色；以及封面/章节/尾页的生成式背景（art DNA 双路径）。色块全走 token 取色，换肤后色块位不破。

**token / 变量**：

- 取色：`--accent` / `--accent-2` / `--surface` / `--line` / `--on-accent`；派生色用 `color-mix()`（如 accent 12%/28% 透明度档），禁止散落硬编码 hex（对标来源 §8-E）。
- 深色面文字：白透明度阶梯（100/72/55/45%）分级（见 `THEMES.md` 深色纪律）。
- 背景色上限：每 deck 至多 1–2 种背景色（`THEMES.md`），色块服从该上限。
- 生成式背景：封面/章节/尾页按 art DNA 注入 project-art 背景，内容页弱化、落在默认 token 上（SKILL.md 运行原则）。

**与 layout-patterns.md 版式的映射**：

| pattern / 页面 | 色块用法 |
| --- | --- |
| 封面 / 章节 / 尾页 | art DNA 生成背景 + scrim 压字 |
| ① 中心节点+分支（center-hub） | 中心核 accent 面色块（反色文字走 `--on-accent`） |
| ⑥ 数据大数字（big-number） | 大数字 accent 面或 surface 卡片色块 |
| ⑤ 对比构图（compare） | 双侧分区底色 + 分界色条 |
| 内容页面板 | surface 卡片 + `--line` 发丝边，全 token 派生 |

---

## 5. 信息模块系统（卡片/栏/层/节点/结论条）

**适用场景**：页面信息组（语义层 2–4 个视觉信息组）的可视化承载——每个信息组落为一个**信息模块**（卡片 / 栏 / 层 / 节点），页面上模块按 §1/§2 的空间系统排布； takeaway 结论条为每页固定收尾模块。

**token / 变量**：

- 卡片四变体全 token 化：默认 / soft / outline / accent（surface/border/radius/shadow 无一硬编码）；`--radius`、发丝边 `--line`、卡距 24px 档。
- 模块件：kicker / eyebrow（mono 小标签）、标题 `.h1/.h2`、lede、pill、编号徽章（CSS counter）、takeaway 结论条。
- 卡片容器 `overflow:hidden`，防内容刺穿卡面。
- 文本内部升级件：`.hl` 关键词高亮、`.num` 数据三段式（`page-logic-patterns.md` §17）。

**与 layout-patterns.md 版式的映射**：12 种 pattern 的「内容区域」全部由信息模块承载——信息组（2–4 组规则）→ 模块，模块 → Grid 格 / Flex 链节点 / 栏 / 层；组标题可见，模块边界清晰。蓝图的「辅助区域」默认落 takeaway 结论条模块。

---

## 6. HTML 输出稳定规则（五条 · 强制 · 可量化 QA）

以下五条为每个内容页的硬约束，QA 逐页核验（检查项登记见 `QA_RUBRIC.md`「布局稳定与结构纪律检查」）：

1. **固定 16:9**：舞台固定 1920×1080（`--deck-width` / `--deck-height` token），视口缩放走等比 `scale = min(视口宽/1920, 视口高/1080)`，任何窗口尺寸下不变形、不出现第二比例。QA 判定：deck-stage 计算宽高比与 16/9 偏差 >0.01 判失败。
2. **元素不可溢出**：slide 容器 `overflow:hidden` + 内容不越界；溢出靠拆页/归组解决，禁止硬塞。QA 判定：逐页任一元素 `scrollWidth > clientWidth` 或 `scrollHeight > clientHeight` 成立即判溢出失败；打印静态流同样适用。
3. **字体不可异常缩小**：1920 画布基准下，正文计算字号不得 <14px，标题与正文字号比 ≥2.2（沿用 QA_RUBRIC 字号层级项）；内容超限先拆页，禁止压缩字号硬塞。QA 判定：正文 `getComputedStyle` 字号 <14px 判失败。
4. **图片不可变形**：每个 `<img>` 必须有 `object-fit`（默认 `contain`）与 `alt`；禁止 width/height 双向硬拉伸。QA 判定：渲染宽高比与 `naturalWidth/naturalHeight` 宽高比偏差 >2%（`contain` 的留白边不算变形）判失败。
5. **页面间距统一**：页边距 = `--slide-padding`（96px，全 deck 一致，≥86px）；卡距/组距/行距走间距阶梯 token（8/14/18/24/32/40 档），同 deck 同类间距禁止自由值。QA 判定：页边距实测与 token 偏差 >4px，或同页出现 ≥3 种非标间距值，判不合格。

## 7. 反模式（禁止项）

1. **禁止 div 堆叠文字**：禁止用一串无空间结构、无模块边界的裸 `<div>` 直接堆叠文字段落充当页面。每个页面必须由三层组成——**空间结构**（§1 Grid / §2 Flex 容器）+ **视觉模块**（§5 信息模块 / §3 图片区 / §4 色块）+ **信息层级**（标题层 / 正文层 / 辅助层）。QA 判定：内容页内容区域的直接子级中，无 class 的裸 div / 纯文本节点占比 >60%，或页面无法分解出"空间结构 + 视觉模块 + 信息层级"三层，判失败。
2. **禁止绕开蓝图临场拼版式**：未落盘蓝图九字段即生成 HTML（流程门禁第 4 条阻断）。
3. **禁止默认"标题 + 多条横向 bullet"版式**：未经语义五步判断落入 `bullets`（语义门禁阻断）。
4. **禁止满页高亮 / 满页色块**：>3 处/卡的高亮视同无高亮；色块服从背景色上限（§4）。
5. **禁止"圆角+左侧色条"卡片、蓝紫渐变、emoji**（克制卡片纪律，QA_RUBRIC 已有检查项）。

---

## 8. 对标来源与沉淀位置（脚注）

本文件五子系统与稳定规则的对标来源：**lewislulu/html-ppt-skill**（https://github.com/lewislulu/html-ppt-skill ， commit `f3a8435`，2026-08-15 复标），只抽取布局稳定性 / Grid / Flex / 图片区域 / 色块组合五类经验；完整结论登记于 `references/BENCHMARK.md` §6。逐类沉淀位置：

- A. 布局稳定性（固定 1920×1080 画布 + `min(cw/1920,ch/1080)` 等比缩放 + `.slide` `overflow:hidden` 防回流）→ 沉淀于本文件 §6 规则 1/2。
- B. Grid（`.grid.g2/.g3/.g4` = `repeat(N,1fr)` + 24px gap；bento `grid-auto-rows` + `span 2` 主格）→ 沉淀于 §1；本库落地为 `minmax(0,1fr)` 防撑爆写法。
- C. Flex（`.row/.stack/.fill/.center` 原语；flow 节点 `flex:1` + 箭头 `flex-shrink:0`）→ 沉淀于 §2。
- D. 图片区域（hero scrim `linear-gradient(180deg,transparent 40%,rgba(10,12,20,.65))`；bento cell caption 渐变条；缩略 `aspect-ratio:16/9`）→ 沉淀于 §3。
- E. 色块组合（渐变色块+光斑+scrim 三板斧替代真实图片；`color-mix` 派生；主题全量同构 token、换肤不破）→ 沉淀于 §4。
