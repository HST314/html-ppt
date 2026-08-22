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

## 2026-08-21：图片 PDF 独立 QA 与蓝图消费

- 图片渲染消费 `layout_pattern`、`layout_variant`、`blueprint`、主题与 art DNA，再按语义 role 回退；登记 pattern 对应不同视觉骨架。
- QA 直接读取 IR、manifest 和逐页 PNG 内嵌审计信息，独立核对页面身份、源文本、素材覆盖、蓝图/role、溢出、16:9 比例与 PDF 页数。
- `scripts/test_image_pdf.py` 覆盖支持矩阵正例，以及重复 PNG、超长标题、manifest 漏用三个必须失败的反例。
- 徽章资料的完整可复跑项目与 PDF 产物登记在 `examples/badge-poster-image-pdf/`。

## 2026-08-22：图片 PDF 可见容器与三方像素绑定

- 文本紧致度由真实可见容器承担：渲染器登记容器边界与关联文字，QA 在容器裁片中独立计算像素占用，不再以字形框自证卡片紧致。
- 主题母题登记可核验元素边界与裁片指纹，并与 IR 语义、PNG 内嵌审计和渲染报告交叉验证。
- QA 提取 PDF 每页的内嵌栅格，与逐页 JPEG、PNG 做页面级绑定；任何单侧像素篡改都会使文本紧致度与视觉语义结论失效。
- 自动化反例直接绘制“大空卡”和“无关叶片”到真实像素，保留审计字段不变，确保两种视觉篡改均被拒绝。

## 2026-08-22：QA 独立视觉发现与语义模板

- QA v2.3 从缩小后的页面像素建立扁平填色连通域，独立发现卡片候选；候选必须能匹配 `visible_containers`，已登记容器则继续接受真实裁片占用检查，形成发现与登记的双向约束。
- QA v2.4 将项目原图与衍生设计拆成两条可审计链路：项目原图只能以 `image_placements.fit=contain` 进入内容容器，QA 从 manifest 独立复算比例并拒绝 `bg_image`、背景式超大容器、裁切与变形；背景、卡片、时间轴和转场则登记 `derived_components`，证明其来自项目母题的重新绘制，而非把项目位图直接铺底。
- QA v2.5 不再把“实际边界比例与原图一致”视为图片完整性的充分条件。QA 对 manifest 原图独立执行 EXIF 方向归一化、RGB 转换和 Pillow LANCZOS `contain`，在每个 `rendered_bbox` 生成完整像素基准并与页面裁片精确比较；保持原宽高比的中心裁切即使同步更新 PNG 审计、render report、JPEG、PDF 与全部哈希也必须拒绝。
- QA v2.6 将四项视觉终审升级为独立门禁：装饰图标不得与文字边界相交；叙事元素密集页须以遮蔽主体后的背景边缘密度证明背景已删减；艺术字登记字面与装饰线几何且禁止相交；含明确枚举数量的标题必须由同页可见正文或项目证据逐项兑现。对应真实像素/真实渲染反例必须分别拒绝。
- QA 在自身代码中维护 badge、ribbon、star、orbit、satellite、rocket、leaf 的别名、允许形状模板与排他颜色特征，不引用渲染器的绘制函数或自报裁片哈希作为语义真值。
- 对抗测试模拟不可信渲染侧：漏报大空卡与“绿色叶片伪装 badge”均同步更新 PNG 审计、渲染报告、JPEG、PDF 和相关指纹；只有 QA 的独立像素发现/模板门禁负责拒绝。

## 2026-08-22：图集观众名称完整性

- QA v2.7 规定图集标签只能来自 manifest 的 `audience_label`（缺省回退到完整 `alt`），内部图片 ID 永远不能充当观众文案；渲染器以真实字宽自适应标签宽度和 12–18 px 字号，禁止字符串切片、省略或截断。
- PNG 审计与渲染报告逐项登记图集标签、图片 ID、边界、文字原点和字号；QA 同 manifest 双向核对完整文案，并用 QA 自己加载的字体掩膜检查完整名称的真实可见像素。
- 第九组同步对抗把标签真实重绘为前 12 字符并同步更新 PNG 审计、渲染报告、JPEG、PDF 与全部指纹；即使渲染侧自报一致，文本完整性与标题正文对应门禁仍必须拒绝。
