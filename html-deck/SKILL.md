---
name: html-deck
description: 将标准 Markdown 文稿和带元数据的场景图片转换为可演示的单文件 HTML 网页 PPT。适用于客户汇报、产品发布、技术分享、培训教学等需要离线演示、演讲者模式、打印导出的场景。
---

# html-deck

html-deck 是一个零依赖交付优先的 Agent Skill：输入 `deck.md` 与 `images/manifest.json`，输出固定 16:9 舞台的单文件 HTML deck。所有流程必须经过结构化 IR、逐页渲染和 QA 门禁。

## 运行原则

- 最终 HTML 必须双击可演示；CSS/JS 内联，禁止 CDN。
- Agent 只能选择 `references/COMPONENTS.md` 中登记的 role 组件和 `assets/components/typography.css` 中登记的装饰组件，禁止临场发明版式。
- 所有中间产物落盘：`outline.json`、`state/run_state.json`、`state/qa_history.jsonl`、`qa_report.md`。
- 图片根据元数据参与排版决策；不得拉伸，必须 `contain` 或 `cover`。
- 视觉风格由场景图驱动：先用 `detect_style.py` 分析图片色相/明度/饱和度，推荐基础主题并派生 accent 配色与高权重封面背景；清单中带 `url` 的联网素材先经 `fetch_assets.py` 本地化。
- 图片零遗漏：build_ir 自动拆页扩容，`audit_images.py` 最终核验，漏图即 QA 失败。
- 项目图片只承担内容展示：必须置于独立、稳定、不可溢出的容器，默认 `contain` 保持原貌；禁止出血、叠字、背景融合、主体抠出越界和持续运动。背景系统独立承担主题视觉。生成或审查图片页时必须读取 `references/PROJECT_IMAGES.md`。
- 全 Deck 必须先运行 `extract_art_dna.py`：将项目图转成 `art_expression`，生成 cover/content/section/closing 四种同源角色背景和统一设计令牌。封面展开、章节转场强化、内容页弱化、尾页收束；禁止首尾项目化而中间页继续套通用主题。禁止把 `deco.py` 的固定行业图形当成跨项目模板；它只允许在无可读项目图时作为明确标注的降级方案。<!-- TASK-005 --> 无可读项目图但存在图片 md 解读时，禁止直接落入 `art_dna=fallback` 裸模板降级：必须先按 `references/ART_DNA.md`「无像素输入：图片 md 解读路径」提取 md 解读清单 `state/art_dna_md.json`，运行 `scripts/art_dna_from_md.py` 生成与图片路径同风格的四类生成式背景（QA 标注 `art_dna=md`）；仅当图片与 md 解读都没有时才允许 deco 降级（QA 标注 `art_dna=fallback`）。
- 内容必须经过 `references/NARRATIVE.md` 的叙事框架；第 2 页强制生成目录，收束固定拆成“行动页 + 低负载结束页”。内容页必须有 action title、至少 3 个内容块、takeaway、150-300 字演讲备注。
<!-- TASK-001: 新增页面语义分析层原则 -->
- 每页生成前必须先完成「页面语义分析层」的五步判断（主结论 / 信息层级 / 逻辑关系 / 视觉结构 / 视觉焦点），并按 `references/page-logic-patterns.md` 的 13 类页面逻辑显式选择页面结构；禁止未经语义判断直接落“标题 + 多条横向 bullet”版式，`bullets` 只允许作为语义判断后的显式结论并附理由。单页信息 ≥4 条时必须先归为 2–4 个视觉信息组再选结构。
<!-- TASK-009: 视觉布局决策引擎原则 -->
- 禁止从文字内容直接进入 HTML。每个内容页必须走完四步链路：① 页面逻辑识别（语义五步判断）→ ② 选择 layout pattern（`references/layout-patterns.md` 12 种之一，显式记录选型理由）→ ③ 生成视觉蓝图（逐页落盘 `state/visual_blueprints.md`，含焦点/标题位/主体区/辅助区/留白比例/SVG 与图片需求）→ ④ 生成 HTML。缺任一步即 QA 判失败。
- 默认视觉方向：浅色、高亮度、深蓝信息骨架、青蓝辅助、留白充分、轻科技、商业提案感，以下方「默认视觉方向设计 token」为准；未声明视觉方向的项目一律按此执行。
- 连续多个内容页不得使用完全相同的“横条列表”布局；同一 layout pattern 连页出现时必须使用可辨识变体（布局签名 = pattern + 变体，连页相同即 QA 判失败）。
- 每一步失败都要产出可执行恢复路径，不能卡死。

<!-- TASK-001: 新增整节——页面语义分析层（强制门禁） -->
## 页面语义分析层（强制）

触发时机：`build_ir.py` 运行之前必须完成；任何修订、重排、换 role 操作也必须重读本层结论。该层是 Agent 的强制推理步骤，不是可选建议。

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

- 五步判断与分组结论逐页落盘到 `state/page_semantics.md`（表格：页码 / 主结论 / 逻辑类型 / 视觉结构 / 视觉焦点 / 信息组划分 / 选定 role / 选role理由），作为可审计中间产物。
- 每页结构以显式 `<!-- role: xxx -->` 指令写回 deck.md，再运行 `build_ir.py`；禁止依赖 `build_ir.py` 的关键词猜测与默认兜底。
- 13 类逻辑与组件库 role 的完整映射、结构示意与避坑清单见 `references/page-logic-patterns.md`；patterns 文档未覆盖的结构需求必须先在 patterns 文档中补登记，禁止临场发明版式。

### 门禁

- 任何内容页在 IR 中的 `decision` 为 `default content role`（即未经语义判断落入默认 `bullets`）时，阶段 5 QA 直接判门禁失败，必须回到本层补语义判断并显式指定 role 后重跑。
- `bullets` 仅在五步判断结论确为「并列」且分组后无更贴切结构时允许使用，并必须在 `state/page_semantics.md` 写明理由。

<!-- TASK-009: 新增整节——视觉布局决策引擎（四步强制链路） -->
## 视觉布局决策引擎（四步强制链路）

触发时机：「页面语义分析层」完成后、运行 `build_ir.py` 之前。四步依序执行，禁止跳步，禁止从文字内容直接进入 HTML。

### 四步定义

1. **页面逻辑识别**：沿用「页面语义分析层」五步判断，逐页落盘 `state/page_semantics.md`（本步产物即四步链路第①步）。
2. **选择 layout pattern**：按 `references/layout-patterns.md` 的「13 类逻辑 → 12 种 layout pattern」映射表为每页选定唯一 pattern，并显式记录选型理由；多 pattern 适用时按冲突裁决规则（资源约束 → 逻辑忠实 → 连页去重 → 焦点唯一 → 容量兜底）裁决。
3. **生成视觉蓝图（中间产物落盘）**：逐页写入 `state/visual_blueprints.md`，机器可读表格，列序固定：`页码 / 布局pattern / 变体 / 视觉焦点 / 标题位置 / 主体区域 / 辅助信息区域 / 留白比例 / SVG需求 / 图片需求 / 选型理由`。蓝图字段必须与本页语义登记一致（焦点同一、组数与主体区域承载一致）。
4. **生成 HTML**：`build_ir.py` 消费蓝图把 `layout_pattern` / `layout_variant` / 蓝图片段写入 IR；渲染层按蓝图落版（`data-pattern` / `data-variant` 与 `layout-*` 变体类）；QA 门禁核验。

### 门禁（缺任一步即 QA 判失败）

- 缺 `state/visual_blueprints.md`，或内容页在蓝图中无登记 → QA 判失败（四步链路第③步缺失）。
- 蓝图 pattern 不在 12 种登记之内、八字段（焦点/标题位/主体区/辅助区/留白比例/SVG需求/图片需求/选型理由）任一空缺 → QA 判失败。
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

入口条件：用户给出或指定工作目录，至少存在 `deck.md`；图片可选但若存在必须有 `images/manifest.json`。

动作：
1. 读取 `context/brief.md`；不存在则创建，缺省值为：受众=客户决策层，场合=客户汇报，时长=15 分钟，场景类型=客户汇报，密度=低密度演讲型。
2. 若受众、场合、时长、场景类型同时缺失，最多问 3 个问题；有合理默认值时继续执行。
3. 只在需要时读取 `references/`：叙事读 `NARRATIVE.md`，主题读 `THEMES.md`，组件读 `COMPONENTS.md`，动画读 `ANIMATIONS.md`，QA 读 `QA_RUBRIC.md`。
4. 长文稿按 `##` 章节分批处理，批间只保留 `outline.json` 与 `state/run_state.json`。

出口产物：`context/brief.md`、初始化或恢复后的 `state/run_state.json`。

校验点：brief 包含 audience、occasion、duration_minutes、scene_type、density。

失败回退：brief 不可写时使用内存默认值继续，并在 QA 报告中列为可恢复缺陷。

## 阶段 2：工具系统

入口条件：完成阶段 1。

<!-- TASK-001: 工具链前置语义分析步骤 -->
动作：

0. **页面语义分析 + 布局决策（强制前置）**：先执行「页面语义分析层」——对每个 `###` 页完成五步判断与 ≥4 条信息分组，结论写入 `state/page_semantics.md`，并将每页显式 `<!-- role: xxx -->` 写回 deck.md；<!-- TASK-009 -->再执行「视觉布局决策引擎」第②③步——为每页选定 layout pattern 并把视觉蓝图逐页落盘 `state/visual_blueprints.md`；未完成这两步不得调用 `build_ir.py`。
1. 按顺序调用：

```bash
python3 scripts/validate_input.py --deck deck.md --manifest images/manifest.json --output state/input_report.json
python3 scripts/fetch_assets.py --manifest images/manifest.json
python3 scripts/detect_style.py --manifest images/manifest.json --output state/style_report.json --theme-css dist/auto-theme.css
python3 scripts/extract_art_dna.py --manifest images/manifest.json --output state/art_dna.json --assets-dir dist/art
# TASK-005: 无可读项目图、仅有图片 md 解读时，用下行替代上一行（md 解读清单由 Agent 按 ART_DNA.md 维度提取落盘）：
# python3 scripts/art_dna_from_md.py --md-report state/art_dna_md.json --output state/art_dna.json --assets-dir dist/art
python3 scripts/build_ir.py --deck deck.md --manifest images/manifest.json --brief context/brief.md --style state/style_report.json --output outline.json --state state/run_state.json
python3 scripts/render_deck.py --ir outline.json --theme $(python3 -c "import json;print(json.load(open('state/style_report.json'))['recommended_theme'])") --theme-css dist/auto-theme.css --art-dna state/art_dna.json --output dist/deck.html --state state/run_state.json
python3 scripts/inline_assets.py --html dist/deck.html --manifest images/manifest.json --mode inline --output dist/deck.single.html
python3 scripts/audit_images.py --manifest images/manifest.json --html dist/deck.single.html --output state/image_coverage.md
python3 scripts/qa_render.py --html dist/deck.single.html --ir outline.json --output state/qa_report.md --history state/qa_history.jsonl --manifest images/manifest.json --art-dna state/art_dna.json
```

工具退出码：`0` 成功，`1` 可恢复输入/质量问题，`2` 阻断性工具错误。所有工具必须支持 `--help`。

出口产物：输入报告、IR、HTML、内联 HTML、QA 报告。

校验点：每个 JSON 输出可解析；`art_dna.json` 含非空 `art_expression`、来源图片 ID、四类页面背景及 `non_template_signature`；HTML 中每页必须有项目背景层，四类背景不得全部同构；`dist/deck.single.html` 不含外链或输入绝对路径。<!-- TASK-005 --> md 解读路径下 `art_dna.json` 的 `source_mode` 必须为 `"md"`、来源标识为 `source_md_ids`（替代来源图片 ID），QA 报告须标注 `art_dna=md`。<!-- TASK-001 --> 附加校验：`state/page_semantics.md` 存在且每个内容页都有主结论、逻辑类型、视觉结构、视觉焦点与选定 role；deck.md 中每个内容页均带显式 `<!-- role: -->` 指令。<!-- TASK-009 --> 附加校验：`state/visual_blueprints.md` 存在且每个内容页都有布局 pattern、可辨识变体、视觉焦点、标题位置、主体区域、辅助信息区域、留白比例、SVG 需求、图片需求与选型理由；IR 中每个内容页带 `layout_pattern` / `layout_variant`。

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
6. 第 2 页必须为 `toc`；倒数第 2 页必须承载行动/决策内容；最后页必须为 `closing`，且至多一个短句、无 takeaway、无列表/表格/KPI/多图。内容型 closing 自动降级为普通内容页并另起结束页。
7. 动画只使用 `ANIMATIONS.md` 的 `data-animate` 名称，并支持 B 键静态降级。
8. 运行时必须支持：S 键独立演讲者窗口（BroadcastChannel 同步当前页/下一页/讲稿/计时器）、O 键缩略图总览、F 全屏、B 静态降级、#/N 深链接。

出口产物：主题预览和完整 HTML。

校验点：页数与 IR 一致；所有图片槽有 alt；演示运行时可翻页、S、F、B。

失败回退：单页渲染失败时将该页 role 改为 `bullets` 或 `image-side`，保留内容并继续。

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
2. 渲染后 QA：优先使用 Playwright 逐页截图；不可用时降级为 HTML/IR 结构检查。
3. 每页按 `QA_RUBRIC.md` 100 分制评分，写入 `state/qa_history.jsonl`。
4. 分数 < 90 必须进入修复循环，最多 3 轮；仍不达标时输出缺陷清单，不阻塞最终半成品交付。
5. 美学首因检查必须覆盖：第一屏视觉焦点、主题 signature、图片 caption/screenshot framing、密文页不空洞、动画不干扰阅读。<!-- TASK-001 --> 并新增语义一致性检查：每页视觉焦点与 `state/page_semantics.md` 登记的焦点一致；页面结构与所声明逻辑类型的结构示意一致；≥4 条信息的页可见 2–4 个分组区块。
<!-- TASK-001: 语义层门禁 -->
6. 语义门禁：任一内容页 IR `decision` 为 `default content role`，或内容页使用 `bullets` 但 `state/page_semantics.md` 未写明并列逻辑理由，判 QA 失败并回到「页面语义分析层」，不属于可恢复缺陷。
<!-- TASK-009: 布局层门禁 -->
7. 布局门禁：任一内容页缺视觉蓝图登记、蓝图八字段空缺、pattern 未登记于 `references/layout-patterns.md`、IR `layout_pattern` 与蓝图不一致，或连续内容页布局签名（pattern + 变体）完全相同，判 QA 失败并回到「视觉布局决策引擎」第②③步，不属于可恢复缺陷。

出口产物：`state/qa_history.jsonl`、`state/qa_report.md`。

校验点：每页最近一次分数 >= 90，或报告列出未达标原因与修复建议。

失败回退：Playwright 缺失时报告 `mode=structural-fallback`，并执行溢出、图片、离线、路径泄漏检查。

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

## 推荐一键示例

```bash
cd html-deck
python3 scripts/generate_example_assets.py --output example/images
python3 scripts/validate_input.py --deck example/deck.md --manifest example/images/manifest.json --output example/state/input_report.json
python3 scripts/build_ir.py --deck example/deck.md --manifest example/images/manifest.json --brief example/context/brief.md --output example/outline.json --state example/state/run_state.json
python3 scripts/render_deck.py --ir example/outline.json --theme business-dark --output example/dist/business-dark.html --state example/state/run_state.json
python3 scripts/render_deck.py --ir example/outline.json --theme minimal-white --output example/dist/minimal-white.html --state example/state/run_state.json
python3 scripts/inline_assets.py --html example/dist/business-dark.html --manifest example/images/manifest.json --mode inline --output example/dist/business-dark.single.html
python3 scripts/audit_images.py --manifest example/images/manifest.json --html example/dist/business-dark.single.html --output example/state/image_coverage.md
python3 scripts/qa_render.py --html example/dist/business-dark.single.html --ir example/outline.json --output example/state/qa_report.md --history example/state/qa_history.jsonl --manifest example/images/manifest.json
```
