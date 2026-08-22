---
name: html-deck
description: 将 Markdown 大纲和项目图片转换为演示文稿，支持两条明确路线：可交互的单文件 HTML 网页 PPT，或通过“提取设计元素→逐页生成视觉底图→准确文字叠加→纯图片 PDF”制作图片型 PPT。适用于客户汇报、产品发布、技术分享、培训教学、需要离线 HTML 演示或不可编辑的逐页图片 PDF 交付场景。
---

# html-deck

html-deck 接收 Markdown 大纲与项目图片，按用户指定的交付格式选择路线。路线 A 输出固定 16:9 舞台的单文件 HTML deck；路线 B 输出每页均为整页位图的 PDF。两条路线共享内容规划与项目图片优先原则，但分别执行各自的渲染和 QA 门禁。

## 路线选择（必须先判定）

- 用户要求 HTML、网页 PPT、交互、演讲者模式或可编辑网页时，执行**路线 A：HTML deck**，继续使用下方既有七阶段流水线。
- 用户要求图片 PPT、逐页生图、不可编辑 PDF、每页都是图片或 PDF 格式时，执行**路线 B：image-PDF**，完整读取并遵循 `references/IMAGE_PDF_ROUTE.md`。
- 用户未指定格式时，只问一个问题：“需要 HTML 演示文稿，还是每页为图片的 PDF？”格式明确时不得追问。
- 两条路线不得混跑：路线 B 不调用 `build_ir.py`、`render_deck.py` 或 HTML QA；路线 A 不把截图 PDF 冒充 image-PDF。

### 路线 B 的不可省略产物

1. 第一轮设计提取：`state/design_dna.md`。
2. 大纲分页与文字定稿：`state/page_plan.json`。
3. 第二轮逐页视觉生成计划：`state/image_prompts.json`。
4. 每页无字视觉底图与准确文字合成后的 `dist/pages/NN-*.png`。
5. `dist/deck.image.pdf`，其页数与 PNG 数一致，且 PDF 文本层为空。
6. `state/image_pdf_qa.json`。

路线 B 在分页前必须先冻结顶层 `chapters`。目录、章节转场和内容页使用同一个 `chapter_id`；目录由渲染器从 `chapters` 自动生成，禁止在目录页手工维护另一套标题。每章必须按“同名 section → 该章 content”连续排列，并通过结构校验后才可交付。

路线 B 默认采用“生成无字视觉底图 + `scripts/render_image_deck.py` 确定性叠加文字”的方式，避免图片模型生成错误中文。只有用户明确接受模型内嵌文字时，才允许让模型直接绘制正文；即使如此，也必须逐字核对。

## 路线 A 环境依赖（必须前置，TASK-021）

- 在执行阶段 5 的 `qa_render.py` 之前，必须先安装 Playwright 并下载 Chromium：

  ```bash
  pip install playwright
  python -m playwright install chromium
  ```

  这不是可选建议——`qa_render.py` 缺 Playwright 时会静默降级为 `structural-fallback`（正则扫描 HTML 源码 + 字符数估算，不做真实像素测量），此前正是这个降级路径产出过「98.5 分」的假通过（画面实际仍有文字溢出/重叠）。降级路径现在会在 `state/qa_report.md` 顶部打印醒目警告，但警告不能替代真实测量——凡是能安装 Playwright 的环境，必须装。

## 路线 A 运行原则

- 最终 HTML 必须双击可演示；CSS/JS 内联，禁止 CDN。
- Agent 只能选择 `references/COMPONENTS.md` 中登记的 role 组件和 `assets/components/typography.css` 中登记的装饰组件，禁止临场发明版式。
<!-- TASK-003 -->- 所有 PPT 生成必须走「执行流程总线」七阶段流水线：项目理解 → 故事线分析 → 页面任务定义 → 页面逻辑判断 → 视觉结构选择 → HTML 生成 → 质量检查；页面逻辑分析（总线③④步）为必经阶段，任何 deck 不得跳过。
- 所有中间产物落盘：`outline.json`、`state/run_state.json`、`state/qa_history.jsonl`、`qa_report.md`；<!-- TASK-003 -->流程产物另含 `state/storyline.md`、`state/page_semantics.md`、`state/visual_blueprints.md`。
- <!-- TASK-044 --> **用户/素材提供了图片时必须使用，禁止图省事改走纯文字路径**：阶段 1「项目理解」核实素材来源时，若用户提供的原始资料（聊天中粘贴的图片、素材包、截图等）包含图片，必须将其保存为项目 `images/` 目录下的文件并登记进 `images/manifest.json`（`id`/`file`/`alt`/`description`/`content_type`/`suggested_role` 等字段齐全），走真实图片路径（`extract_art_dna.py` 的像素提取，QA 标注 `art_dna=image`）——不得因为"反正也能生成"就静默降级为纯文字 deck（`art_dna=domain-only`/`fallback`）。只有以下两种情况可以不用图片：①用户明确说明本次不使用图片、只要文字版；②图片确实无法获取（如仅有图片描述、没有实际像素文件，这种走 `references/ART_DNA.md`「图片 md 解读路径」而非直接跳过）。Agent 自身若因为工具限制无法把聊天中粘贴的图片保存为本地文件，必须向用户说明这一限制并请其提供图片文件路径，不能默默按纯文字处理。
- 图片根据元数据参与排版决策；不得拉伸，必须 `contain` 或 `cover`。
- 视觉风格由场景图驱动：先用 `detect_style.py` 分析图片色相/明度/饱和度，推荐基础主题并派生 accent 配色与高权重封面背景；清单中带 `url` 的联网素材先经 `fetch_assets.py` 本地化。
- 图片零遗漏：build_ir 自动拆页扩容，`audit_images.py` 最终核验，漏图即 QA 失败。
- 项目图片只承担内容展示：必须置于独立、稳定、不可溢出的容器，默认 `contain` 保持原貌；禁止出血、叠字、背景融合、主体抠出越界和持续运动。背景系统独立承担主题视觉。生成或审查图片页时必须读取 `references/PROJECT_IMAGES.md`。
- 全 Deck 必须先运行 `extract_art_dna.py`：将项目图转成 `art_expression`，生成 cover/content/section/closing 四种同源角色背景和统一设计令牌。封面展开、章节转场强化、内容页弱化、尾页收束；禁止首尾项目化而中间页继续套通用主题。禁止把 `deco.py` 的固定行业图形当成跨项目模板；它只允许在无可读项目图时作为明确标注的降级方案。<!-- TASK-005 --> 无可读项目图但存在图片 md 解读时，禁止直接落入 `art_dna=fallback` 裸模板降级：必须先按 `references/ART_DNA.md`「无像素输入：图片 md 解读路径」提取 md 解读清单 `state/art_dna_md.json`，运行 `scripts/art_dna_from_md.py` 生成与图片路径同风格的四类生成式背景（QA 标注 `art_dna=md`）；仅当图片与 md 解读都没有时才允许 deco 降级（QA 标注 `art_dna=fallback`）。<!-- TASK-043 --> 图片与 md 解读都没有（纯文字 deck）时，也禁止直接落入 `art_dna=fallback` 裸模板降级：`extract_art_dna.py` 在无可读图片时会自动改用 `state/style_report.json` 的主题色 token 合成轻量 dna，照常按 `theme_domain`+正文关键词调用 `bg_styles.select_background_style()` 生成四类角色背景（QA 标注 `art_dna=domain-only`）；`deco.py` 的零参数固定图形（`cover_deco()`/`closing_deco()`/`quiet_deco()`，不感知 domain）现在仅在 `extract_art_dna.py` 本身因更底层原因未能产出 `art_dna.json`（如 `state/style_report.json` 也缺失）时才作为最终兜底触发。<!-- TASK-017 --> 首尾页保留生成式融合背景路线（用户 v9 截图确认为目标版式，撤销 TASK-015 的模板回退）：封面/尾页照常注入 project-art 生成背景（深藏蓝近黑实底、设计元素低饱和融入）；"融为一体"根因修复——首尾页自带 var(--bg) 实底深色基底 + 本地重声明 --ho/--ho-deep/--ho-gold（CSS 自定义属性在 :root 定义处即固化，不随局部 --accent 覆盖）；QA 覆盖门禁按 cover/content/section/closing 四类页面全核对。
- 内容必须经过 `references/NARRATIVE.md` 的叙事框架；第 2 页强制生成目录，收束固定拆成“行动页 + 低负载结束页”。内容页必须有 action title、至少 3 个内容块、takeaway、150-300 字演讲备注。
<!-- TASK-001: 新增页面语义分析层原则 -->
- 每页生成前必须先完成「页面语义分析层」的五步判断（主结论 / 信息层级 / 逻辑关系 / 视觉结构 / 视觉焦点），并按 `references/page-logic-patterns.md` 的 13 类页面逻辑显式选择页面结构；禁止未经语义判断直接落“标题 + 多条横向 bullet”版式，`bullets` 只允许作为语义判断后的显式结论并附理由。单页信息 ≥4 条时必须先归为 2–4 个视觉信息组再选结构。
<!-- TASK-009: 视觉布局决策引擎原则 -->
- 禁止从文字内容直接进入 HTML。每个内容页必须走完四步链路：① 页面逻辑识别（语义五步判断）→ ② 选择 layout pattern（`references/layout-patterns.md` 12 种之一，显式记录选型理由）→ ③ 生成视觉蓝图（逐页落盘 `state/visual_blueprints.md`，<!-- TASK-007 fix -->含蓝图九字段：页面类型/主视觉区域/标题区域/内容区域/辅助区域/图片区域/留白区域/SVG需求/选型理由，口径见 `references/html-layout-system.md` §0）→ ④ 生成 HTML。缺任一步即 QA 判失败。
<!-- TASK-008: 页面场景识别系统原则 -->
- 每页生成前必须先完成「页面场景判定」（`references/design-scenario-system.md` 10 类业务场景：封面/章节/品牌价值/产品介绍/项目方案/流程/数据/案例/成果展示/总结），在总线③页面任务定义时连同页面任务一并判定（页面任务决定场景），并回答两问——"这一页属于什么场景？为什么选择这种设计？"；判定结论落 `state/page_semantics.md`「页面场景」列，<!-- TASK-010 fix -->蓝图「页面类型」取值域 = 10 类业务场景 + 1 个骨架保留项 `目录页(toc)`（全库唯一口径，唯一定义见 `references/design-scenario-system.md` §2 注），蓝图「选型理由」必须引用场景判定结论。禁止所有页面使用同一个模板（场景多样性为事前预防，连页签名检查为事后兜底）。deck 级场景（`references/NARRATIVE.md`）与 page 级场景（10 类业务场景）为两层口径，不得混淆或合并。
- 默认视觉方向：浅色、高亮度、深蓝信息骨架、青蓝辅助、留白充分、轻科技、商业提案感，以下方「默认视觉方向设计 token」为准；未声明视觉方向的项目一律按此执行。
- 连续多个内容页不得使用完全相同的“横条列表”布局；同一 layout pattern 连页出现时必须使用可辨识变体（布局签名 = pattern + 变体，连页相同即 QA 判失败）。<!-- TASK-018 fix -->全 deck 内视觉结构相同或高度相似的页面不得超过 2 页（转场页除外；渲染级签名四元组口径与判定见 `references/html-layout-system.md` §9，终审强制检查见 `references/final-quality-check.md` D1）；仅改配色/描边的伪变体不算结构差异。每页结构类符号有产出下限（内容页 ≥2 个实例且 ≥1 个承担方向/关系职能，骨架页 ≥1 个，口径见 `references/visual-symbol-system.md` §0.4；缺符号为终审阻断项）；正文/背景对比度 ≥4.5:1、大标题 ≥3:1，禁止近似色组合（强调件与其承载面 <3:1 或同 token 前后景，终审阻断，见 `references/final-quality-check.md` V1）。
- 每一步失败都要产出可执行恢复路径，不能卡死。

<!-- TASK-003: 新增整节——执行流程总线（七阶段强制流水线） -->
## 执行流程总线（七阶段强制流水线）

所有 PPT 生成必须依序走完以下七个阶段，禁止跳步、禁止从需求文本直接进入 HTML 生成；任一阶段的落盘产物缺失即判流程失败，不得进入下一阶段。本总线是「页面语义分析层」「视觉布局决策引擎」与「阶段 1–6」的上位编排：原各层机制内容不变，按本总线位次执行。

```
需求文本
  ↓
① 项目理解        → context/brief.md（含场景归类结论）
  ↓
② 故事线分析      → state/storyline.md
  ↓
③ 页面任务定义    → state/page_semantics.md「页面任务」列<!-- TASK-008 --> +「页面场景」列
  ↓
④ 页面逻辑判断    → state/page_semantics.md（五步判断，同表）
  ↓
⑤ 视觉结构选择    → state/visual_blueprints.md
  ↓
⑥ HTML 生成       → outline.json → dist/deck.single.html
  ↓
⑦ 质量检查        → state/qa_report.md（含流程门禁）
```

### ① 项目理解

- 动作：建立/补全 `context/brief.md`（受众、场合、时长、场景类型、密度），并显式判定本项目落入 `references/NARRATIVE.md` 的哪一类场景框架；不在已登记场景内时登记「自定义场景」并给出章节顺序理由。<!-- TASK-040 -->同一步内运行 `scripts/classify_theme_domain.py`（判定项目落入 `references/THEME_DOMAINS.md` 8 类主题域中的哪一类），产出 `state/theme_domain.json`，并在 `context/brief.md` 追加一行人类可读摘要（形如 `theme_domain：academic-institutional（高校科研教育机构）——判定依据见 state/theme_domain.json`），不把完整 JSON 细节写入 brief.md 正文；该判定结果供后续背景风格选择、目录页模板选择复用，避免各自重复维护一套不一致的行业关键词表。
- 落盘：`context/brief.md`，必须含 `scene_type` 与场景归类结论。<!-- TASK-040 -->另落盘 `state/theme_domain.json`（主题域判定结果，字段含 `domain`/`confidence`/`trace` 等，见 `references/THEME_DOMAINS.md`）。
- 门禁：brief 五字段齐全且场景归类有结论，否则不得进入②。<!-- TASK-040 -->`state/theme_domain.json` 缺失或 brief 未追加 `theme_domain` 摘要行同样视为①未完成。
- 对应原机制：阶段 1「上下文管理」。

### ② 故事线分析

- 动作：按场景框架排出全 deck 章节顺序，划定封面/目录/章节过渡/行动页/结束页位置，为每章分配叙事任务与页数配额，标注节奏（数据先行章、证据章、收束章）。
- 落盘：`state/storyline.md`（章节序列 / 各章叙事任务 / 页数配额 / 节奏标注）。
- 门禁：目录节点 3–6 个、收束为两段式（行动页 + 低负载结束页）；缺 `state/storyline.md` 不得进入③。
- 对应原机制：`references/NARRATIVE.md` 场景框架与 Deck 级叙事门禁——由事后检查前置为规划产物。

### ③ 页面任务定义

- 动作：把故事线展开到页——每个 `###` 页登记唯一页面任务：`提出判断` / `展示证据` / `解释机制` / `请求决策` / `过渡收束`。一页一个任务；任务写不出的页回炉拆页或并页。<!-- TASK-008 -->同一步内按 `references/design-scenario-system.md` 完成页面场景判定（10 类；页面任务决定场景，骨架页按故事线位置判定，判定流程见该文 §1），逐页登记「页面场景」。
- 落盘：`state/page_semantics.md` 表格新增「页面任务」列<!-- TASK-008 -->与「页面场景」列（<!-- TASK-010 fix -->枚举 = 10 类业务场景 + 1 个骨架保留项 `目录页(toc)`），与④的五步判断同表登记。
- 门禁：每页有且仅有一个页面任务<!-- TASK-008 -->与唯一页面场景；缺任务或场景登记不得进入④。
- 对应原机制：NARRATIVE.md「中段每页只完成一个任务」由 Deck 级门禁升级为逐页显式登记。<!-- TASK-008 -->页面场景体系（10 类 × 五属性）由 design-scenario-system.md 承载，场景判定前置为规划产物。

### ④ 页面逻辑判断

- 动作：执行「页面语义分析层」五步判断（主结论 / 信息层级 / 逻辑关系 / 视觉结构 / 视觉焦点）与 ≥4 条信息分组。<!-- TASK-018 fix -->同一步内执行**正文语义关系分析**（强制微步骤，`references/design-scenario-system.md` §1A）：除标题外所有正文先判定主导关系（并列 / 递进 / 因果 / 对比 / 总分 / 层级六类），登记「正文关系」列，再按关系 → 结构映射表选正文承载结构；禁止正文未做关系分析直接落结构（防裸列表平铺）。
- 落盘：`state/page_semantics.md`（与③同表<!-- TASK-018 fix -->，含「正文关系」列）。
- 门禁：沿用语义层门禁（IR `decision` 为 `default content role` 判失败等<!-- TASK-018 fix -->；内容页缺「正文关系」登记判失败）。
- 对应原机制：「页面语义分析层（强制）」全节。

### ⑤ 视觉结构选择

- 动作：执行「视觉布局决策引擎」第②③步——layout pattern 选型（含冲突裁决）+ 逐页视觉蓝图落盘。
- 落盘：`state/visual_blueprints.md`。
- 门禁：沿用布局引擎门禁（<!-- TASK-007 fix -->蓝图九字段空缺、连页签名相同、计数变体节点数不符均判失败）。
- 对应原机制：「视觉布局决策引擎（四步强制链路）」全节；其第①步即本总线④，第④步即本总线⑥。

### ⑥ HTML 生成

- 动作：按阶段 2 工具链运行 `build_ir.py` → `render_deck.py` → `inline_assets.py`；渲染以蓝图与显式 role 指令为准，禁止绕开蓝图临场拼版式。
- 落盘：`outline.json`、`dist/deck.single.html`。
- 对应原机制：阶段 2「工具系统」、阶段 3「执行编排」、阶段 4「状态与记忆」。

### ⑦ 质量检查

- 动作：按阶段 5 执行 QA（语义门禁、布局门禁、反同质化签名核对、对比度硬指标等），并执行流程门禁（见下）。
- 落盘：`state/qa_report.md`、`state/qa_history.jsonl`。
- 不合格处理：回到最早出问题的阶段修复后重跑后续阶段，最多 3 轮。

### 流程门禁（任一不满足即 QA 判失败，不属于可恢复缺陷）

- 缺 `context/brief.md` 场景归类结论 → 判失败（①缺失）。
- 缺 `state/storyline.md`，或故事线无目录节点/收束两段式登记 → 判失败（②缺失）。
- `state/page_semantics.md` 任一内容页缺「页面任务」<!-- TASK-008 -->、「页面场景」或五步判断任一字段 → 判失败（③④缺失）。<!-- TASK-018 fix -->任一内容页缺「正文关系」列登记（`references/design-scenario-system.md` §1A 六类枚举）→ 同判失败（④缺失）。
- 缺 `state/visual_blueprints.md` 或内容页蓝图九字段空缺（<!-- TASK-007 fix -->口径见 `references/html-layout-system.md` §0）→ 判失败（⑤缺失）。
- IR 中 `layout_pattern` 与蓝图登记不一致 → 判失败（⑥绕开⑤直接生成）。

<!-- TASK-001: 新增整节——页面语义分析层（强制门禁） -->
## 页面语义分析层（强制）

触发时机：执行流程总线第④步（页面逻辑判断）；`build_ir.py` 运行之前必须完成；任何修订、重排、换 role 操作也必须重读本层结论。该层是 Agent 的强制推理步骤，不是可选建议。

### 五步判断（每页必填）

对 deck.md 中每一个 `###` 页面，依次写出：

1. **主结论**：本页要让观众记住的唯一一句话。写不出主结论的页必须回炉拆页或并页。
2. **信息层级**：本页信息分为哪几层（结论层 / 支撑层 / 细节层），各层分别有哪些条目。
3. **逻辑关系**：条目之间属于 `references/page-logic-patterns.md` 13 类中的哪一类（并列、对比、因果、流程、时间轴、递进、中心辐射、闭环、矩阵、层级、数据、产品展示、图文叙事）。一页一个主导逻辑；出现第二个主导逻辑时拆页。
4. **视觉结构**：该逻辑类型在 patterns 文档中对应的结构（编号链、分层条、中心辐射、双栏对照、图锚信息栏等），并映射到组件库 role。
5. **视觉焦点**：页面上唯一的视觉锚点（主结论数字 / 主图 / 中心节点 / 第一流程节点），焦点必须占据最大字号、最大面积或最高对比之一，其余元素只做视线引导。

### 信息分组规则（≥4 条强制）

- 单页信息条目 ≥4 条时，先按「对象（谁）→ 阶段（何时）→ 属性（哪类）→ 价值（为何）」的优先维度归为 **2–4 个视觉信息组**，每组 2–4 条，每组提炼一个名词短语作为组标题。
- 每个信息组对应页面上一个独立视觉区块（卡片 / 栏 / 层 / 节点），组内再排条目；组与组之间的关系决定主导逻辑（平等→并列，先后→流程/递进，主次→层级/中心辐射）。
- 归组后超过 4 组、或单组超过 4 条、或组标题无法提炼时，必须拆页，禁止压缩字号硬塞。

### 落地方式

- 五步判断与分组结论逐页落盘到 `state/page_semantics.md`（表格：页码 / <!-- TASK-003 -->页面任务 / <!-- TASK-008 -->页面场景 / 主结论 / 逻辑类型 / 视觉结构 / 视觉焦点 / 信息组划分 / 选定 role / 选role理由），作为可审计中间产物；「页面任务」<!-- TASK-008 -->与「页面场景」列在执行流程总线第③步（页面任务定义）先行填好，本层只补后续列。
- 每页结构以显式 `<!-- role: xxx -->` 指令写回 deck.md，再运行 `build_ir.py`；禁止依赖 `build_ir.py` 的关键词猜测与默认兜底。
- 13 类逻辑与组件库 role 的完整映射、结构示意与避坑清单见 `references/page-logic-patterns.md`；patterns 文档未覆盖的结构需求必须先在 patterns 文档中补登记，禁止临场发明版式。

### 门禁

- 任何内容页在 IR 中的 `decision` 为 `default content role`（即未经语义判断落入默认 `bullets`）时，阶段 5 QA 直接判门禁失败，必须回到本层补语义判断并显式指定 role 后重跑。
- `bullets` 仅在五步判断结论确为「并列」且分组后无更贴切结构时允许使用，并必须在 `state/page_semantics.md` 写明理由。

<!-- TASK-009: 新增整节——视觉布局决策引擎（四步强制链路） -->
## 视觉布局决策引擎（四步强制链路）

触发时机：「页面语义分析层」完成后、运行 `build_ir.py` 之前——即执行流程总线第⑤步（视觉结构选择，其第①步为总线④、第④步为总线⑥）。四步依序执行，禁止跳步，禁止从文字内容直接进入 HTML。

### 四步定义

1. **页面逻辑识别**：沿用「页面语义分析层」五步判断，逐页落盘 `state/page_semantics.md`（本步产物即四步链路第①步）。
2. **选择 layout pattern**：按 `references/layout-patterns.md` 的「13 类逻辑 → 12 种 layout pattern」映射表为每页选定唯一 pattern，并显式记录选型理由；多 pattern 适用时按冲突裁决规则（资源约束 → 逻辑忠实 → 连页去重 → 焦点唯一 → 容量兜底）裁决。<!-- TASK-008 -->选型理由必须引用总线③的页面场景判定结论（"本页为 X 场景，故选 Y pattern"，回答"为什么选择这种设计"；模板句见 `references/design-scenario-system.md` §3），未引用场景判定即 QA 判失败；同 deck 内同场景页面的布局签名不得雷同。
3. **生成视觉蓝图（中间产物落盘）**：逐页写入 `state/visual_blueprints.md`，机器可读表格，列序固定：`页码 / 布局pattern / 变体 / 页面类型 / 主视觉区域(视觉焦点) / 标题区域(标题位置) / 内容区域(主体区域) / 辅助区域(辅助信息) / 图片区域(图片需求) / 留白区域(留白比例) / SVG需求 / 选型理由`。<!-- TASK-007 fix: 蓝图七字段与原八字段合并为一份定义，全库唯一口径见 references/html-layout-system.md §0 -->蓝图字段必须与本页语义登记一致（主视觉区域与语义焦点同一、组数与内容区域承载一致）；蓝图九字段口径（页面类型/主视觉区域/标题区域/内容区域/辅助区域/图片区域/留白区域/SVG需求/选型理由）以 `references/html-layout-system.md` §0 为唯一定义，禁止另立口径。
4. **生成 HTML**：`build_ir.py` 消费蓝图把 `layout_pattern` / `layout_variant` / 蓝图片段写入 IR；渲染层按蓝图落版（`data-pattern` / `data-variant` 与 `layout-*` 变体类）；QA 门禁核验。

### 门禁（缺任一步即 QA 判失败）

- 缺 `state/visual_blueprints.md`，或内容页在蓝图中无登记 → QA 判失败（四步链路第③步缺失）。
- 蓝图 pattern 不在 12 种登记之内、蓝图九字段（<!-- TASK-007 fix -->页面类型/主视觉区域/标题区域/内容区域/辅助区域/图片区域/留白区域/SVG需求/选型理由，口径见 `references/html-layout-system.md` §0）任一空缺 → QA 判失败。
- IR 中的 `layout_pattern` 与蓝图登记不一致（渲染绕开蓝图）→ QA 判失败。
- 连续内容页布局签名（pattern + 变体）完全相同 → QA 判失败（连页变体禁令）。
- <!-- TASK-011 -->计数变体（ascend-N / chain-N / loop-N）实际渲染节点数与蓝图登记数 N 不一致 → QA 判失败（存在无来源幻影节点或内容缺失）；渲染层不得把 IR 补位块（`generated` 标记）落成节点卡片。

### 默认视觉方向设计 token

未声明视觉方向的项目按以下 token 执行（实现于 `assets/themes/proposal-light.css`）：

| token | 基准值 | 含义 |
| --- | --- | --- |
| `--bg` / `--page-bg` | `#f7fafd` / `#e9eef5` | 浅色、高亮度背景（明度基准 ≥92%） |
| `--accent` | `#123a6b` | 深蓝信息骨架（标题、组标题、结构线、大数字） |
| `--accent-2` | `#1fa8d8` | 青蓝辅助（连接线、编号、焦点描边、次级强调） |
| `--text` / `--muted` | `#14263f` / `#55677f` | 深蓝正文 / 灰蓝辅助文字 |
| `--surface` / `--line` | `#ffffff` / `#d4e0ec` | 留白充分的卡片面与分隔线 |
| `--slide-padding` | `96px` | 留白基准（页边距 ≥86px，卡片区留白 ≥30%） |

视觉气质：轻科技（细线、编号、低饱和渐变纹理）、商业提案感（观点式标题 + 结论条 + 充分留白）。封面/章节/尾页按 art DNA 双路径规则生成项目专属背景，不受本 token 约束；内容页一律落在本 token 上。

## 阶段 1：上下文管理

入口条件：用户给出或指定工作目录，至少存在 `deck.md`；图片可选但若存在必须有 `images/manifest.json`。本阶段即执行流程总线第①步（项目理解）。

动作：
1. 读取 `context/brief.md`；不存在则创建，缺省值为：受众=客户决策层，场合=客户汇报，时长=15 分钟，场景类型=客户汇报，密度=低密度演讲型。
2. 若受众、场合、时长、场景类型同时缺失，最多问 3 个问题；有合理默认值时继续执行。
3. <!-- TASK-003 -->显式判定场景归类：本项目落入 `references/NARRATIVE.md` 哪一类场景框架（客户汇报型 / 产品发布型 / 技术分享型），写入 `context/brief.md` 的场景归类结论；不在登记场景内时写「自定义场景」并给出章节顺序理由。
4. 只在需要时读取 `references/`：叙事读 `NARRATIVE.md`，主题读 `THEMES.md`，组件读 `COMPONENTS.md`，动画读 `ANIMATIONS.md`，QA 读 `QA_RUBRIC.md`。<!-- TASK-007 fix -->布局落版（Grid/Flex/图片区/色块/信息模块、合并蓝图定义、输出稳定规则）读 `html-layout-system.md`。<!-- TASK-008 -->页面场景判定（10 类场景、五属性量规、选型理由模板）读 `design-scenario-system.md`。<!-- TASK-040 -->项目主题域判定（8 类主题域、体裁词/话题词权重设计、与背景风格库/目录模板库的对接口径）读 `THEME_DOMAINS.md`。
5. 长文稿按 `##` 章节分批处理，批间只保留 `outline.json` 与 `state/run_state.json`。

出口产物：`context/brief.md`、初始化或恢复后的 `state/run_state.json`、<!-- TASK-040 -->`state/theme_domain.json`（项目主题域判定结果）。

校验点：brief 包含 audience、occasion、duration_minutes、scene_type、density；<!-- TASK-003 -->并含场景归类结论。

失败回退：brief 不可写时使用内存默认值继续，并在 QA 报告中列为可恢复缺陷。

## 阶段 2：工具系统

入口条件：完成阶段 1。

<!-- TASK-001: 工具链前置语义分析步骤 -->
动作：

0. **页面语义分析 + 布局决策（强制前置）**：<!-- TASK-003 -->先按执行流程总线完成前置各步——②故事线分析（落盘 `state/storyline.md`）、③页面任务定义（`state/page_semantics.md`「页面任务」列<!-- TASK-008 -->与「页面场景」列）；再执行「页面语义分析层」（总线④）——对每个 `###` 页完成五步判断与 ≥4 条信息分组，结论写入 `state/page_semantics.md`，并将每页显式 `<!-- role: xxx -->` 写回 deck.md；<!-- TASK-009 -->再执行「视觉布局决策引擎」第②③步（总线⑤）——为每页选定 layout pattern 并把视觉蓝图逐页落盘 `state/visual_blueprints.md`；未完成②③④⑤不得调用 `build_ir.py`。
1. 按顺序调用：

```bash
python3 scripts/validate_input.py --deck deck.md --manifest images/manifest.json --output state/input_report.json
python3 scripts/fetch_assets.py --manifest images/manifest.json
python3 scripts/detect_style.py --manifest images/manifest.json --output state/style_report.json --theme-css dist/auto-theme.css --deck deck.md
# TASK-040: 项目主题域判定（8 类，见 references/THEME_DOMAINS.md）——只读扫描 deck.md + context/brief.md，
# 体裁词权重远高于话题词，避免正文技术性话题词（如"系统/工程/芯片"）盖过真正决定项目类型的体裁词信号；
# 产出 state/theme_domain.json 供后续背景风格选择、目录页模板选择复用，--brief/--style 均可选：
python3 scripts/classify_theme_domain.py --deck deck.md --brief context/brief.md --style state/style_report.json --output state/theme_domain.json
python3 scripts/extract_art_dna.py --manifest images/manifest.json --output state/art_dna.json --assets-dir dist/art --deck deck.md --theme-domain state/theme_domain.json
# 上一行 --deck 可选：供 references/BACKGROUND_STYLES.md 描述的背景风格库做关键词匹配（只读扫描，不修改 deck.md）；省略时自动探测同一目录
# TASK-041: --theme-domain 可选（缺省则背景风格选择退化为关键词+量化两级算法）——指向上一步 classify_theme_domain.py
# 产出的 state/theme_domain.json，其 domain/confidence 作为背景风格选择的最高优先级信号，详见 references/BACKGROUND_STYLES.md
# TASK-005: 无可读项目图、仅有图片 md 解读时，用下行替代上一行（md 解读清单由 Agent 按 ART_DNA.md 维度提取落盘）：
# python3 scripts/art_dna_from_md.py --md-report state/art_dna_md.json --output state/art_dna.json --assets-dir dist/art --theme-domain state/theme_domain.json
# TASK-028: 可选——若 Agent 从项目图/图片 md 解读中提炼出可识别主题图形主体（火箭/祥云/轨道连线等），
# 手写落盘 state/art_motifs.json（schema 见 references/ART_DNA.md「主题线条插画装饰机制」），上两行脚本
# 会自动读取同目录下的该文件并把选中素材接入 art_dna.json；无该文件时静默跳过，不影响其余产出。
python3 scripts/build_ir.py --deck deck.md --manifest images/manifest.json --brief context/brief.md --style state/style_report.json --output outline.json --state state/run_state.json
python3 scripts/render_deck.py --ir outline.json --theme $(python3 -c "import json;print(json.load(open('state/style_report.json'))['recommended_theme'])") --theme-css dist/auto-theme.css --art-dna state/art_dna.json --output dist/deck.html --state state/run_state.json
python3 scripts/inline_assets.py --html dist/deck.html --manifest images/manifest.json --mode inline --output dist/deck.single.html
python3 scripts/audit_images.py --manifest images/manifest.json --html dist/deck.single.html --output state/image_coverage.md
python3 scripts/qa_render.py --html dist/deck.single.html --ir outline.json --output state/qa_report.md --history state/qa_history.jsonl --manifest images/manifest.json --art-dna state/art_dna.json
```

工具退出码：`0` 成功，`1` 可恢复输入/质量问题，`2` 阻断性工具错误。所有工具必须支持 `--help`。

出口产物：输入报告、IR、HTML、内联 HTML、QA 报告。

校验点：每个 JSON 输出可解析；<!-- TASK-040 -->`state/theme_domain.json` 存在且含 `domain`/`confidence`/`trace` 字段，`context/brief.md` 含 `theme_domain` 摘要行；`art_dna.json` 含非空 `art_expression`、来源图片 ID、四类页面背景及 `non_template_signature`；HTML 中每页必须有项目背景层，四类背景不得全部同构；`dist/deck.single.html` 不含外链或输入绝对路径。<!-- TASK-005 --> md 解读路径下 `art_dna.json` 的 `source_mode` 必须为 `"md"`、来源标识为 `source_md_ids`（替代来源图片 ID），QA 报告须标注 `art_dna=md`。<!-- TASK-003 --> 附加校验：`state/storyline.md` 存在且含章节序列、各章叙事任务、页数配额与节奏标注；`state/page_semantics.md` 每个内容页均含「页面任务」列登记。<!-- TASK-008 --> 附加校验：`state/page_semantics.md` 每页均含「页面场景」列登记（<!-- TASK-010 fix -->枚举 = `references/design-scenario-system.md` 10 类业务场景 + 1 个骨架保留项 `目录页(toc)`）。<!-- TASK-005 fix: 阶段2校验点补登记必经阶段要求，与运行原则表述一致 --> 附加校验：页面逻辑分析为必经阶段，不得跳过——任一内容页未完成总线④五步判断（主结论/信息层级/逻辑关系/视觉结构/视觉焦点）即调用 `build_ir.py` 的，本校验点判不通过。<!-- TASK-001 --> 附加校验：`state/page_semantics.md` 存在且每个内容页都有主结论、逻辑类型、视觉结构、视觉焦点与选定 role；deck.md 中每个内容页均带显式 `<!-- role: -->` 指令。<!-- TASK-009 --> 附加校验：`state/visual_blueprints.md` 存在且每个内容页都有布局 pattern、可辨识变体，<!-- TASK-007 fix -->以及蓝图九字段——页面类型、主视觉区域（视觉焦点）、标题区域（标题位置）、内容区域（主体区域）、辅助区域（辅助信息）、图片区域（图片需求）、留白区域（留白比例）、SVG 需求与选型理由（口径见 `references/html-layout-system.md` §0）；IR 中每个内容页带 `layout_pattern` / `layout_variant`。

失败回退：退出码 1 按报告修复后重跑；退出码 2 记录 `state/run_state.json.errors` 并使用上个 checkpoint 继续。

## 阶段 3：执行编排

入口条件：`outline.json` 通过 schema 与风险预测。

动作：
1. 先渲染封面主题预览：
   ```bash
   python3 scripts/render_deck.py --ir outline.json --theme business-dark --preview-only --output dist/preview-business-dark.html
   python3 scripts/render_deck.py --ir outline.json --theme minimal-white --preview-only --output dist/preview-minimal-white.html
   ```
2. 主题优先采用 `state/style_report.json` 的 `recommended_theme` 并叠加 `dist/auto-theme.css`；无风格报告时客户汇报默认 `proposal-light`（<!-- TASK-009 -->默认视觉方向：浅色高亮 / 深蓝骨架 / 青蓝辅助），用户明确要求深色或极简打印优先时选 `business-dark` / `minimal-white`。
3. 按 `outline.json.slides[]` 逐页渲染。每页 role 必须来自组件库：cover、toc、section、bullets、two-column、image-hero、image-side、gallery、table、kpi、quote、compare、timeline、closing。<!-- TASK-001 --> 内容页 role 必须与 `state/page_semantics.md` 中该页的逻辑类型映射一致（映射表见 `references/page-logic-patterns.md`），禁止在渲染阶段临时更换为默认 `bullets`；信息组必须渲染为独立视觉区块，组标题可见。<!-- TASK-009 --> 内容页布局必须与 `state/visual_blueprints.md` 登记一致：渲染以 IR 的 `layout_pattern` / `layout_variant` 为准（`layout-*` 变体类由 `assets/components/layouts.css` 承载），禁止绕开蓝图临场拼版式；连页布局签名必须不同。
4. 图片自动分配遵循 `COMPONENTS.md` 与 `PROJECT_IMAGES.md` 决策矩阵；显式 `<!-- image: id -->` 优先。无明确 `group_id` 关系的多图默认拆为单图页。
5. 图片零遗漏由两级机制保证：build_ir 自动拆页（gallery 超 6 张拆多页；hero/side/compare 超 1 张的溢出图移入自动图集页；无法匹配到内容页的清单图自动汇入兜底图集页），并保证所有证据图页位于行动页和结束页之前；`audit_images.py` 与 QA `--manifest` 做最终覆盖核验，漏图直接判失败。
6. 第 2 页必须为 `toc`；倒数第 2 页必须承载行动/决策内容；最后页必须为 `closing`，且至多一个短句、无 takeaway、无列表/表格/KPI/多图。内容型 closing 自动降级为普通内容页并另起结束页。<!-- TASK-021: toc 版式改用模板库，禁止 ul/li -->`role=toc` 页禁止使用 `ul`/`li` 项目符号列表渲染，必须按「目录页版式模板库（slide_templates/toc）」一节的调度规则选模板并替换占位符。
7. 动画只使用 `ANIMATIONS.md` 的 `data-animate` 名称，并支持 B 键静态降级。
8. 运行时必须支持：S 键独立演讲者窗口（BroadcastChannel 同步当前页/下一页/讲稿/计时器）、O 键缩略图总览、F 全屏、B 静态降级、#/N 深链接。<!-- TASK-022 --> E 键内嵌可视化编辑器（`assets/runtime/editor.js`）：左上角隐形热区悬停 400ms 显示编辑按钮，点击或按 E 进入编辑态后右侧滑出面板，可点选文字元素微调字号（±2px）与上下左右位置（±4px），调整实时内联到元素 style 并自动存 localStorage（关闭浏览器重开后仍保留），支持一键重置单个元素、导出调整后的完整 HTML；编辑态与 F 全屏互斥（进全屏自动退出编辑态），且与 `autofit.js` 的自动收缩不打架——元素一旦被手动调整过即标记 `data-editor-adjusted`，之后 autofit 永久跳过该元素，重置后才交还控制权。

出口产物：主题预览和完整 HTML。

校验点：页数与 IR 一致；所有图片槽有 alt；演示运行时可翻页、S、F、B、E。

失败回退：单页渲染失败时将该页 role 改为 `bullets` 或 `image-side`，保留内容并继续。

<!-- TASK-021: 新增整节——目录页版式模板库调度规则；TASK-032：改用真实机制重写，替换已过时的"运行时占位符替换"描述；TASK-041：调度面精简+按项目主题域自动调度，替换"手动开关"旧描述 -->
## 目录页版式模板库（slide_templates/toc + render_deck.py toc_*_html）

触发时机：执行流程总线第⑥步（HTML 生成），渲染 `role=toc` 的页面（deck 第 2 页）时；本节是阶段 3 第 6 条约束的具体落地方式，优先级高于组件库内置的 toc 默认实现。

### 实际渲染机制（TASK-041：从"手动开关"改为"按项目主题域自动调度"）

`role=toc` 页**不是**在渲染时读取 `slide_templates/toc/*.html` 模板文件做字符串占位符替换——那些 `.html` 文件是**纯布局/CSS 骨架的人工预览/参考文件**（用 `{{占位符}}` 标记业务插入点，供人工在浏览器里打开预览版式效果，不参与实际渲染流程）。真正的渲染逻辑是 `scripts/render_deck.py` 里一组 `toc_*_html(cards, main_title, fallback_html)` Python 函数：接收 `build_ir.py` 产出的结构化 `toc_cards`（`num`/`title`/`desc`）与主标题，在渲染阶段现场拼出该版式的完整 HTML。

TASK-032/036 阶段，`slide_html()` 里 `role == "toc"` 分支曾是**代码维护层面的手动开关**——全部项目固定调用同一个函数，导致不同主题的项目目录页趋同（诊断详见下方"调度面精简"）。TASK-041 起改为 `select_toc_template(domain, node_count)` 自动调度：`main()` 从 `--theme-domain` 参数指向的 `state/theme_domain.json`（`scripts/classify_theme_domain.py` 产出，见 `references/THEME_DOMAINS.md`）读取该项目的 `domain` 字段（参数缺省或文件不存在/解析失败时兜底 `generic-fallback`，不中断渲染），按 `references/THEME_DOMAINS.md`「对接目录模板 key」列的映射选出目录版式 key，再从 `TOC_TEMPLATE_FUNCS` 映射表取出对应渲染函数调用——不再是渲染阶段现场发明分支，也不需要人工改代码切换。

### 调度面精简（TASK-041 诊断结论）

`toc-modern-card`/`toc-segment-strip`/`toc-grid-matrix` 三款诊断确认本质都是「编号 + 标题 + 一句描述」套不同卡片容器形状（同一批卡片彼此等大，只是外壳形状不同：圆角卡片 / 满版色块铭牌 / 网格线卡片），结构同质化严重；`toc-orbit-hub`（中心枢纽环形辐射拓扑）与 `toc-magazine-index`（纯文字编号索引列表，无卡片容器）才是真正结构不同的两款。据此把调度面从 5 款收窄为 4 款真正参与自动调度的版式，`toc-grid-matrix` 定为「卡片网格类默认代表款」（三款同质卡片里实现最扎实，有条目数自适应的 `compute_grid_columns(N)` 逻辑），新增 `toc-collage-asym` 补齐库里从未出现过的「尺寸不对称」结构语言。

### 当前参与自动调度的 4 款版式

| 版式 | 渲染函数 | 样式文件 | 适用节点数 | 视觉特征 |
| --- | --- | --- | --- | --- |
| `toc-orbit-hub` | `toc_orbit_hub_html()` | `assets/components/toc-orbit-hub.css` | 3–8（`compute_orbit_layout()` 用 `360°/N` 现场算坐标，任意 N 均匀分布，无稀疏/拥挤区间限制） | 深色科技风：中心径向渐变发光球体（承载总标题）+ N 个卫星节点圆形环绕（编号/标题/一句话释义），暖色辐条虚线连接 + 外圈虚线轨道环，中心辐射式信息层级 |
| `toc-magazine-index` | `toc_magazine_index_html()` | `assets/components/toc-magazine-index.css` | 3–8（每行 `flex:1 1 0` 均分 `.tmi-list` 纵向可用空间，条目越少单行越宽裕、越多越紧凑，不依赖固定行高表） | 极简书目录风：编号 + 标题 + 虚线引导线 + 页码横向单行排列，行间实线分隔，纯文本导向、克制 |
| `toc-grid-matrix` | `toc_grid_matrix_html()` | `assets/components/toc-grid-matrix.css` | 3–8（`compute_grid_columns(N)` 按条目数决策列数：≤4 单行铺满，5–6 取 3 列两行，7–8 取 4 列两行；每格具体像素位置交给 CSS Grid `repeat(cols,1fr)+grid-auto-rows:1fr` 自动排布，不写死坐标） | 浅色高对比编辑风：顶部主标题占满整行 + 右侧条目计数，下方卡片按行列精确铺满网格线，每格大号幽灵数字打底 + 编号 + 章节名 + 一句话描述；**卡片网格类默认代表款/通用兜底** |
| `toc-collage-asym`（TASK-041 新增） | `toc_collage_asym_html()` | `assets/components/toc-collage-asym.css` | 3–8（头条卡 `flex:0 0 58%` 自动占满 `.tca-body` 全高，其余短条 `flex:1 1 0` 自动等分，不依赖坐标表/像素查表） | 非对称拼贴：第 1 个章节放大为左侧「头条卡」（编号+标题+一句话说明，占满全部可用高度），其余章节收进右侧纵向排列的紧凑编号短条（仅编号+标题，不放描述）——库里唯一的"尺寸不对称"结构语言，区别于其余三款"同批卡片彼此等大"的共性 |

### 调度规则：domain 优先，条目数退居第二

`select_toc_template(domain, node_count)` 的选择优先级：

1. **第一优先级 —— 项目主题域（domain）**：按 `references/THEME_DOMAINS.md`「对接目录模板 key」列：
   - `aerospace-defense-tech` → `toc-orbit-hub`
   - `academic-institutional` / `corporate-professional` / `cultural-heritage-formal` → `toc-magazine-index`
   - `product-launch-design` → `toc-grid-matrix`
   - `cultural-heritage-warm` → `toc-collage-asym`
   - `consumer-lifestyle-future` → `toc-orbit-hub`（条目数 ≥6）/ `toc-collage-asym`（条目数 <6）
   - `generic-fallback`（含 domain 缺省/无法判定） → `toc-grid-matrix`
2. **第二优先级 —— 目录条目数（node_count）**：仅在同一 domain 存在多款候选时起二级细分作用（当前仅 `consumer-lifestyle-future` 一个 domain 有此情形：条目数较多时选环形 `toc-orbit-hub` 展示丰富度，较少时选 `toc-collage-asym` 突出"聚焦头条章节"的叙事感），不是第一优先级，不覆盖 domain 判断。

### `toc-modern-card` / `toc-segment-strip`：已降级，仅供历史兼容

诊断确认与 `toc-grid-matrix` 结构同质（同款卡片换容器皮），TASK-041 起**不再进入 `select_toc_template()` 的调度候选**，不会被任何 domain 自动选中。函数代码本身**未删除**（`toc_modern_card_html()` / `toc_segment_strip_html()` 仍在 `render_deck.py` 里，对应 CSS 仍在 `main()` 的 css 拼接列表里），仅供以后确有需要时人工手动调用（如临时项目定制），日常自动调度路径不会触达。

### 未接入代码的设计参考文件（仅供风格灵感，禁止直接当作可用实现）

`slide_templates/toc/` 目录下还留有 `toc-arc-card.html`（圆弧环形排布卡片）、`toc-curve-timeline.html`（曲线时间轴异形）、`toc-fluid-loop.html`（流体闭环发散式）、`toc-orbit-dot-list.html`（轨道圆点引线）、`toc-capsule-dock.html`（拱形胶囊坞）5 份文件——这些**从未被 `render_deck.py` 任何函数消费**，是早期人工探索版式时留下的独立预览骨架，且均采用「每个节点坐标手写死在 CSS 选择器里（`[data-idx="1"]`…`[data-idx="8"]`）」的写法，是本 skill 已确认过的**反面案例**：节点数 N<8 时会造成节点分布不均、留白缺口（`toc-orbit-hub` 正是为修正这个问题而新增——用 Python `math.sin`/`math.cos` 现场按 `360°/N` 计算坐标取代硬编码坐标表，见 `render_deck.py::compute_orbit_layout()`）。今后若要把这 5 份文件真正接入渲染，必须先按 `toc-orbit-hub` 的坐标计算方式改写为通用 N 版式，禁止直接照抄其硬编码坐标表。

### 新增版式 / 调整调度规则的操作方式

1. **调整某个 domain 的目录版式映射**：编辑 `render_deck.py` 的 `TOC_TEMPLATE_DOMAIN_MAP` 字典（或 `consumer-lifestyle-future` 走的二级细分分支），同步更新 `references/THEME_DOMAINS.md`「对接目录模板 key」列与本节表格，避免两处口径分裂。这是**全局生效**的改动，影响之后所有用本 skill 渲染的项目。
2. **新增一种版式**：① 在 `slide_templates/toc/` 新增一份人工预览骨架 `.html`（`{{占位符}}` 约定同既有文件，仅供预览，不接入渲染流程）；② 在 `assets/components/` 新增对应 `.css`，颜色 token 一律走 `var(--accent)`/`--accent-2`/`--text`/`--muted`/`--surface`/`--inverse` 派生（`color-mix(in srgb, var(--accent) N%, transparent)` 写法），禁止写死具体 hex；③ 节点排布优先用 CSS flex/grid 自动排布（如 `toc-modern-card`/`toc-collage-asym`，天然适配任意 N）；确需精确环形/曲线/弧线布局时，坐标必须用 Python 现场计算（如 `toc-orbit-hub::compute_orbit_layout()` 用 `360°/N` 均匀分布角度），**禁止把坐标写死在 CSS 选择器里**；④ 在 `render_deck.py` 新增 `toc_xxx_html(cards, main_title, fallback_html)` 函数，`cards` 为空时退回旧版列表渲染兜底；⑤ 在 `main()` 的 css 拼接列表里加入新 `.css` 文件；⑥ 在 `TOC_TEMPLATE_FUNCS` 登记新版式 key；⑦ 决定是否让某个 domain 调度到新版式，更新 `TOC_TEMPLATE_DOMAIN_MAP` 与 `references/THEME_DOMAINS.md`；⑧ 更新本节表格登记。
3. **防溢出机制（三层防护，缺一不可，4 款在调度版式与降级版式均一体适用）**：单靠 CSS `line-clamp` 无法保证不压边/不溢出（学习来源 `frontend-slides` 参考 skill 的目录页实测就出现过标题/说明文字压在容器下边缘甚至轻微溢出容器外的问题）：
   - 标题超阈值优先取冒号前核心词，仍超阈值再硬截断补省略号（`shrink_toc_plaque_title()` / `shrink_toc_node_title()` / `shrink_toc_hub_title()` / `shrink_toc_grid_title()` / `shrink_toc_magazine_title()` / `shrink_toc_collage_headline_title()` / `shrink_toc_collage_row_title()`，同一套算法、按各自容器可用宽度定不同字数阈值）；
   - 说明文字（`desc`）在 `build_ir.py::toc_card_desc()` 数据生成阶段已限制在 20 字以内，渲染层 CSS 仍叠加 `-webkit-line-clamp` 双重兜底（大多数版式取 2 行，`toc-collage-asym` 头条卡标题/说明各放宽到 3 行，短条列表标题收紧到 1 行）；
   - 同一批**彼此并列、设计意图上本该等大**的节点/卡片/铭牌/短条容器必须固定统一的宽高（`height`/`width` 定值或 flex 等分，不用 `min-height`/`max-width` 这类允许内容撑大的写法），不因文字长短产生大小不一致（`scripts/qa_render.py::check_sibling_uniformity` 对 `.ss-row>.ss-plaque` / `.mc-grid>.mc-card` / `.toc-orbit-hub>.oh-node` / `.tgm-grid>.tgm-card` / `.tmi-list>.tmi-row` / `.tca-list>.tca-row` 做 Playwright 实测像素级核验）。**`toc-collage-asym` 的头条卡与短条本就设计为不同尺寸**（非对称是该版式的核心视觉语言），一致性约束只覆盖"同一批短条彼此之间"，不要求头条卡也跟短条同高。

### 门禁

- `role=toc` 页在渲染产物中出现 `<ul` 或 `<li` 标签 → QA 判失败。
- `role=toc` 页 HTML 中残留未替换的 `{{...}}` 占位符 → QA 判失败（正式渲染路径由 Python 函数现场拼接，不会产生占位符残留；此项主要防的是误把独立预览文件内容直接搬进渲染产物）。
- 选用的渲染函数必须是 `TOC_TEMPLATE_FUNCS` 登记的其中之一，禁止在渲染阶段现场发明新版式 DOM 结构。

## 阶段 4：状态与记忆

入口条件：任一阶段开始。

动作：
1. 每个工具开始和结束时更新 `state/run_state.json`：`current_phase`、`completed_pages`、`qa_round`、`errors`、`checkpoints`。
2. 读取 `memory/brand.md`；若出现品牌色、字体、logo 偏好，优先映射到已有主题 token，不写自由 hex。
3. 中断后重跑必须读取 state，跳过 `completed_pages` 已完成的逐页渲染。

出口产物：最新 state 与可追踪错误历史。

校验点：state JSON 可解析，`current_phase` 不倒退，`completed_pages` 单调递增。

失败回退：state 损坏时备份为 `state/run_state.corrupt.json`，从 `outline.json` 重建最小 state。

## 阶段 5：评估与预测

入口条件：IR 已生成。

动作：
1. 渲染前预测：检查标题长度、正文条数、每条字数、表格列数、图片数量与组件容量；高风险页先拆页或换 role。<!-- TASK-001 --> 同时核对每页已完成语义五步判断，缺判断的页禁止进入渲染。
2. 渲染后 QA：**必须**先完成上方「环境依赖」的 Playwright 安装，使用 Playwright 逐页截图并做真实 `scrollHeight`/`scrollWidth` 溢出测量；只有在环境确实无法安装 Playwright 时才允许降级为 HTML/IR 结构检查（`structural-fallback`），且必须在交付说明里注明降级原因，不得默认接受降级结果。<!-- TASK-021 --> `structural-fallback` 新增两项硬性检查：视觉符号产出下限（内容页命中结构类符号 <2 个或无方向/关系职能符号，-40）与基于字符数/容器高度预算的近似溢出估算（命中 -25，标注「基于估算，非真实像素测量」）。
3. 每页按 `QA_RUBRIC.md` 100 分制评分，写入 `state/qa_history.jsonl`。
4. 分数 < 90 必须进入修复循环，最多 3 轮；仍不达标时输出缺陷清单，不阻塞最终半成品交付。
5. 美学首因检查必须覆盖：第一屏视觉焦点、主题 signature、图片 caption/screenshot framing、密文页不空洞、动画不干扰阅读。<!-- TASK-001 --> 并新增语义一致性检查：每页视觉焦点与 `state/page_semantics.md` 登记的焦点一致；页面结构与所声明逻辑类型的结构示意一致；≥4 条信息的页可见 2–4 个分组区块。
<!-- TASK-001: 语义层门禁 -->
6. 语义门禁：任一内容页 IR `decision` 为 `default content role`，或内容页使用 `bullets` 但 `state/page_semantics.md` 未写明并列逻辑理由，判 QA 失败并回到「页面语义分析层」，不属于可恢复缺陷。
<!-- TASK-009: 布局层门禁 -->
7. 布局门禁：任一内容页缺视觉蓝图登记、蓝图九字段空缺（<!-- TASK-007 fix -->页面类型/主视觉区域/标题区域/内容区域/辅助区域/图片区域/留白区域/SVG需求/选型理由，口径见 `references/html-layout-system.md` §0）、pattern 未登记于 `references/layout-patterns.md`、IR `layout_pattern` 与蓝图不一致，或连续内容页布局签名（pattern + 变体）完全相同，判 QA 失败并回到「视觉布局决策引擎」第②③步，不属于可恢复缺陷。<!-- TASK-007 --> 落版稳定核验：HTML 输出稳定规则五条与「禁止 div 堆叠文字」反模式按 `references/html-layout-system.md` §6/§7 与 `references/QA_RUBRIC.md`「布局稳定与结构纪律检查」执行。
<!-- TASK-003: 流程门禁 -->
8. 流程门禁：任一内容页缺 `state/storyline.md` 故事线登记、缺「页面任务」登记，或 brief 缺场景归类结论，判 QA 失败并回到执行流程总线对应阶段（①/②/③），不属于可恢复缺陷。
<!-- TASK-008: 场景门禁 -->
9. 场景门禁：任一页面缺场景判定记录（`state/page_semantics.md`「页面场景」列空缺）、蓝图「页面类型」不在<!-- TASK-010 fix -->「10 类业务场景 + 1 个骨架保留项 `目录页(toc)`」取值域内、蓝图「选型理由」未引用场景判定结论（未回答"为什么选择这种设计"），或同 deck 内同场景页面版式签名雷同，判 QA 失败并回到执行流程总线③/⑤修复，不属于可恢复缺陷；检查项口径见 `references/QA_RUBRIC.md`「场景判定与场景多样性检查」。
<!-- TASK-016: 终审门禁 -->
10. 终审门禁：每页生成后必须执行 `references/final-quality-check.md` 四维检查（<!-- TASK-036 fix -->17 条，含标题级文字对比度/字号、背景色漂移、字体排版系统三条永久自动化门禁）+ 二次升级判断，并将结果逐页登记 `state/qa_report.md` 终审节（页码 / 四维结论 / 二次升级命中方式与修改记录 / 重检结论或「无需升级」结论）；二次升级为自动修改回路（命中即改、改后重过四维检查形成闭环），不是建议清单——命中升级方式却只有建议无修改动作、或任一页缺终审登记，判 QA 失败并回到 `references/final-quality-check.md` 对应回路执行，不属于可恢复缺陷。

出口产物：`state/qa_history.jsonl`、`state/qa_report.md`。

校验点：每页最近一次分数 >= 90，或报告列出未达标原因与修复建议。

失败回退：Playwright 缺失时报告 `mode=structural-fallback` 并在报告顶部打印醒目警告，同时执行溢出、图片、离线、路径泄漏检查；此结果不可信任为最终交付依据，必须补装 Playwright 后重跑确认 `mode=playwright` 才能收尾。

## 阶段 6：约束与恢复

入口条件：准备交付。

硬约束：
- 单文件零 CDN；字体使用中文系统字体栈兜底。
- 图片不拉伸；每个 `img` 必须有 `object-fit` 与 `alt`。
- 项目图片容器必须 `overflow:hidden` 且与文字无重叠；默认 `object-fit:contain`。只有确认裁切不损害主体时才允许显式 `cover`，QA 必须记录理由。
- 每页标题建议 <= 42 字；正文列表建议 <= 8 条；每条 <= 58 字。超限先拆页。
<!-- TASK-001 -->- 禁止默认“标题 + 多条横向 bullet”版式：内容页结构必须由「页面语义分析层」的 13 类逻辑显式导出；单页 ≥4 条信息必须先归为 2–4 个视觉信息组。
<!-- TASK-009 -->- 禁止从文字内容直接进 HTML：内容页必须经「逻辑识别 → pattern 选型 → 视觉蓝图落盘 → 生成 HTML」四步；连续多页不得使用完全相同的“横条列表”布局，同 pattern 连页必须有可辨识变体；内容页视觉默认落在浅色高亮 / 深蓝骨架 / 青蓝辅助的设计 token 上。
- 主题只能使用 `assets/themes/*.css` token。
- HTML 不得泄露输入绝对路径。
- 修订已有 deck 时，只改指定页；运行 diff 校验，未指定页应字节级不变。

恢复分类：
- 输入错：输出字段级修复清单，退出码 1。
- 工具错：重试一次，失败则降级或使用上个 checkpoint，退出码 2。
- 质量不达标：最多 3 轮自动修复；仍失败则交付半成品与缺陷清单。

完成标准：生成 `dist/deck.single.html`、两套主题验证产物、QA 报告、ADR，且 example 能端到端跑通。

## 标准流水线命令（按真实项目目录替换路径）

仓库不再内置 `example`/`example-many`/`example-tech`/`example-project` 这类模拟测试项目目录（按用户要求移除，避免与真实交付项目混淆）；下列命令中的 `<project>` 请替换为实际项目工作目录（内含 `deck.md`、`images/manifest.json`、`context/brief.md`）：

```bash
cd html-deck
python3 scripts/validate_input.py --deck <project>/deck.md --manifest <project>/images/manifest.json --output <project>/state/input_report.json
python3 scripts/build_ir.py --deck <project>/deck.md --manifest <project>/images/manifest.json --brief <project>/context/brief.md --output <project>/outline.json --state <project>/state/run_state.json
python3 scripts/render_deck.py --ir <project>/outline.json --theme business-dark --output <project>/dist/business-dark.html --state <project>/state/run_state.json
python3 scripts/inline_assets.py --html <project>/dist/business-dark.html --manifest <project>/images/manifest.json --mode inline --output <project>/dist/business-dark.single.html
python3 scripts/audit_images.py --manifest <project>/images/manifest.json --html <project>/dist/business-dark.single.html --output <project>/state/image_coverage.md
python3 scripts/qa_render.py --html <project>/dist/business-dark.single.html --ir <project>/outline.json --output <project>/state/qa_report.md --history <project>/state/qa_history.jsonl --manifest <project>/images/manifest.json
```
