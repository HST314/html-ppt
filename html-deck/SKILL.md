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
- 全 Deck 必须先运行 `extract_art_dna.py`：将项目图转成 `art_expression`，生成 cover/content/section/closing 四种同源角色背景和统一设计令牌。封面展开、章节转场强化、内容页弱化、尾页收束；禁止首尾项目化而中间页继续套通用主题。禁止把 `deco.py` 的固定行业图形当成跨项目模板；它只允许在无可读项目图时作为明确标注的降级方案。
- 内容必须经过 `references/NARRATIVE.md` 的叙事框架；第 2 页强制生成目录，收束固定拆成“行动页 + 低负载结束页”。内容页必须有 action title、至少 3 个内容块、takeaway、150-300 字演讲备注。
- 每一步失败都要产出可执行恢复路径，不能卡死。

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

动作：按顺序调用：

```bash
python3 scripts/validate_input.py --deck deck.md --manifest images/manifest.json --output state/input_report.json
python3 scripts/fetch_assets.py --manifest images/manifest.json
python3 scripts/detect_style.py --manifest images/manifest.json --output state/style_report.json --theme-css dist/auto-theme.css
python3 scripts/extract_art_dna.py --manifest images/manifest.json --output state/art_dna.json --assets-dir dist/art
python3 scripts/build_ir.py --deck deck.md --manifest images/manifest.json --brief context/brief.md --style state/style_report.json --output outline.json --state state/run_state.json
python3 scripts/render_deck.py --ir outline.json --theme $(python3 -c "import json;print(json.load(open('state/style_report.json'))['recommended_theme'])") --theme-css dist/auto-theme.css --art-dna state/art_dna.json --output dist/deck.html --state state/run_state.json
python3 scripts/inline_assets.py --html dist/deck.html --manifest images/manifest.json --mode inline --output dist/deck.single.html
python3 scripts/audit_images.py --manifest images/manifest.json --html dist/deck.single.html --output state/image_coverage.md
python3 scripts/qa_render.py --html dist/deck.single.html --ir outline.json --output state/qa_report.md --history state/qa_history.jsonl --manifest images/manifest.json --art-dna state/art_dna.json
```

工具退出码：`0` 成功，`1` 可恢复输入/质量问题，`2` 阻断性工具错误。所有工具必须支持 `--help`。

出口产物：输入报告、IR、HTML、内联 HTML、QA 报告。

校验点：每个 JSON 输出可解析；`art_dna.json` 含非空 `art_expression`、来源图片 ID、四类页面背景及 `non_template_signature`；HTML 中每页必须有项目背景层，四类背景不得全部同构；`dist/deck.single.html` 不含外链或输入绝对路径。

失败回退：退出码 1 按报告修复后重跑；退出码 2 记录 `state/run_state.json.errors` 并使用上个 checkpoint 继续。

## 阶段 3：执行编排

入口条件：`outline.json` 通过 schema 与风险预测。

动作：
1. 先渲染封面主题预览：
   ```bash
   python3 scripts/render_deck.py --ir outline.json --theme business-dark --preview-only --output dist/preview-business-dark.html
   python3 scripts/render_deck.py --ir outline.json --theme minimal-white --preview-only --output dist/preview-minimal-white.html
   ```
2. 主题优先采用 `state/style_report.json` 的 `recommended_theme` 并叠加 `dist/auto-theme.css`；无风格报告时客户汇报默认 `business-dark`，用户明确要求极简或打印优先时选 `minimal-white`。
3. 按 `outline.json.slides[]` 逐页渲染。每页 role 必须来自组件库：cover、toc、section、bullets、two-column、image-hero、image-side、gallery、table、kpi、quote、compare、timeline、closing。
4. 图片自动分配遵循 `COMPONENTS.md` 决策矩阵；显式 `<!-- image: id -->` 优先。
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
1. 渲染前预测：检查标题长度、正文条数、每条字数、表格列数、图片数量与组件容量；高风险页先拆页或换 role。
2. 渲染后 QA：优先使用 Playwright 逐页截图；不可用时降级为 HTML/IR 结构检查。
3. 每页按 `QA_RUBRIC.md` 100 分制评分，写入 `state/qa_history.jsonl`。
4. 分数 < 90 必须进入修复循环，最多 3 轮；仍不达标时输出缺陷清单，不阻塞最终半成品交付。
5. 美学首因检查必须覆盖：第一屏视觉焦点、主题 signature、图片 caption/screenshot framing、密文页不空洞、动画不干扰阅读。

出口产物：`state/qa_history.jsonl`、`state/qa_report.md`。

校验点：每页最近一次分数 >= 90，或报告列出未达标原因与修复建议。

失败回退：Playwright 缺失时报告 `mode=structural-fallback`，并执行溢出、图片、离线、路径泄漏检查。

## 阶段 6：约束与恢复

入口条件：准备交付。

硬约束：
- 单文件零 CDN；字体使用中文系统字体栈兜底。
- 图片不拉伸；每个 `img` 必须有 `object-fit` 与 `alt`。
- 每页标题建议 <= 42 字；正文列表建议 <= 8 条；每条 <= 58 字。超限先拆页。
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
