# 架构决策记录（ADR）

## 参考吸收

- `zarazhangrui/frontend-slides`：吸收三模式思路中的“生成前先识别任务类型”、风格预览先行、固定 16:9 视口纪律、滚动/可见触发动画理念。本 skill 将其固化为阶段 1/3，并用固定 1920×1080 舞台缩放；v2 进一步把 `slide` 的进入态、overview 和 preview-first 写入 SKILL 工作流。
- `op7418/guizang-ppt-skill`：吸收图片资产与提示语成为版式输入、杂志风/瑞士风双体系、Swiss 中的发丝线、极端字重对比、截图背景画布和 caption 处理。本 skill 改为 6 套 token 主题与图片元数据矩阵，并在 `img_html()` 中对 screenshot 自动加背景、留边、圆角、阴影。
- `lewislulu/html-ppt-skill`：吸收 theme × layout × animation 三维组合、演讲者模式、纯静态工程纪律。本 skill 将组件限定为 14 个 role，并内置 S/F/B/O/打印运行时；v2 将 S 键升级为独立 presenter window，通过 BroadcastChannel 同步当前页、下一页、讲稿和计时器。
- `archlizheng/frontend-slides-editable`：吸收浏览器内增强层的状态意识，但本版只保留演讲者模式与静态降级，编辑运行时作为后续增强，避免扩大交付面。
- `mucsbr/ppt-agent-workflow-san`：吸收 HTML 预览先于 PPTX 的两阶段观念。本 skill 将 HTML 作为一等交付，同时保留结构化 IR 以便未来导出 PPTX。
- ClawHub 两个参考仓库当前无法匿名克隆；已按 issue 中给出的架构点落地：`outline.json` IR、相对路径/内联资产、逐页渲染、summary/QA 收尾、截图 QA 优先与结构化降级。

<!-- TASK-005: 本节标题与 1–6 列表更新为七阶段口径，与 SKILL.md「执行流程总线（七阶段强制流水线）」一致；原实现要点并入对应阶段 -->
## 七阶段落地

按 SKILL.md「执行流程总线」七阶段（项目理解 → 故事线分析 → 页面任务定义 → 页面逻辑判断 → 视觉结构选择 → HTML 生成 → 质量检查）落地：

1. 项目理解（原「上下文管理」）：`context/brief.md` 默认值不阻塞，长文只保留 IR；显式判定场景归类结论并写入 brief。
2. 故事线分析：`state/storyline.md` 落盘章节序列、各章叙事任务、页数配额与节奏标注；叙事框架由事后检查前置为规划产物。
3. 页面任务定义：`state/page_semantics.md` 新增「页面任务」列，每页登记唯一任务（提出判断/展示证据/解释机制/请求决策/过渡收束）。
4. 页面逻辑判断：「页面语义分析层」五步判断逐页落盘，为必经阶段；`bullets` 只允许作为语义判断后的显式结论。
5. 视觉结构选择：「视觉布局决策引擎」四步链路选型，逐页视觉蓝图落盘 `state/visual_blueprints.md`；连页布局签名必须不同。
6. HTML 生成（原「工具系统 / 执行编排 / 状态记忆」）：确定性脚本全部支持 `--help`，I/O JSON 化，退出码区分成功/可恢复/阻断；先输出 business-dark 与 minimal-white 预览/验证，逐页只使用登记 role；`state/run_state.json` 保存阶段、页完成情况与 checkpoint，`memory/brand.md` 保存稳定品牌偏好。
7. 质量检查（原「评估预测 / 约束恢复」）：IR 内写入风险预测，`qa_render.py` 优先 Playwright，缺失时结构化 QA 降级；流程门禁任一不满足即判失败；单文件、零 CDN、图片不拉伸、不泄露绝对路径；3 轮 QA 仍失败时输出缺陷清单。

## 不同取舍

- 不引入 CDN 字体或图标，全部使用系统字体栈和 CSS/JS 内联，以离线客户演示优先。
- 不开放任意主题色，限制在 token 主题内，减少 Agent 随机配色导致的质量漂移。
- 不把 Markdown 直接渲染为页面，而是强制 MD → IR → HTML，保证断点续跑和人工可编辑中间产物。
- QA 不把 Playwright 作为硬依赖；无浏览器环境时仍能执行离线、容量、图片、路径泄漏等门禁。

## 内容充实度与视觉表现 v2

- 内容深度：新增 `references/NARRATIVE.md`，把客户汇报型、产品发布型、技术分享型定义为可执行顺序。`build_ir.py` 输出 `version=2.0`，内容页自动生成 `takeaway`、150-300 字 `notes`，并对 action title 做 `risk.issues` 预测。
- 信息密度：从参考 deck 的“观点标题 + 证据块 + so-what”结构中提炼规则，要求内容页至少 3 个内容块；不足时自动补“目标对比、过程证据、业务影响”。
- 视觉系统：新增 `assets/components/typography.css`，定义 7 档字号、12 列网格、发丝线、outline number、水印词、accent bar、quote deco、caption bar。它们作为 raw 装饰组件受治理，不允许 Agent 临时发明。
- 主题 signature：六套主题不再只换色。business-dark 用玻璃拟态和金/翡翠渐变线，business-light 用 6px 左侧 accent 条，tech-dark 用等宽字体和数据网格，editorial 用衬线、首字下沉和多栏，warm-human 用暖纸底和圆角照片描边，minimal-white 用瑞士网格和高饱和锚点。
- 图片表现：hero 图默认多层遮罩和 kenburns；screenshot 自动套 CleanShot 式背景画布；gallery 使用统一裁切、序号角标和 manifest description caption。
- 动画表现：`animations.css` 登记 12 个命名动画，runtime 支持 B 键静态降级和 prefers-reduced-motion；KPI count-up、表格逐行、timeline 依次点亮、compare 左右入场均为声明式。
- 运行时：S 键打开独立演讲者窗口，O 键打开缩略图总览，#/N 深链接仍可恢复页码。所有运行时代码内联、离线、无构建。
- QA：`qa_render.py` 的结构化降级检查已加入 action title、takeaway、notes、截图美化、caption 和关键动画；Playwright 可用时仍输出逐页截图供人工并排比对。
