<!-- TASK-001: 新增——外部 skill 对标结论库(2026-08-15 落盘) -->
# BENCHMARK(外部 skill 对标结论)

对 4 个外部参考 skill 做对标分析,提炼可复用的版式逻辑/页面逻辑模式,并登记**学到什么、沉淀到哪个文档、应用到目标 deck 哪页**。本文件只登记结论与落点;具体规则写进各专项文档,不重复。

目标 deck:`模拟项目大纲-演示-TASK017首尾页融合恢复.html`(20 页,深藏蓝+金航天主题)。

---

## 1. guizang-ppt-skill(动效克制 · 排版变量承载层级)

**仓库特征**:SKILL.md 工作流 + 双风格单文件模板(杂志风/瑞士风) + 11 份 references + Node 校验器;美学靠约束与校验器守护。

**学到什么**:
1. **克制动效的工程化**:只动 opacity + translateY(16→0),duration .5–.9s,统一 easing;动效按语义选配方(数字弹入/bar 拉起/描线),禁止全 deck 同一 fade-up。
2. **视觉权重全由排版变量承载**:层级 = 字号 × 字重反比阶梯(字越大重越轻)× 字体三分工(mono 标签/标题/正文)× 单一 accent;零阴影零渐变也能分层。
3. **行内关键词高亮不伤排版**:`.hi` 荧光条(底部 .28em 半透明条)、`.mark` 用 `box-decoration-break:clone` 防断行断色;每页只点 1–3 个关键词。
4. **数据大字三段式**:label(mono 小字)→ nb(巨数)→ note(口径);单位缩 .32em + opacity .6。
5. **节奏硬规则反同质化**:禁连续 3 页同结构;生成后 grep 版式签名自检;校验器渲染测量 overflow px 阶梯修正。

**沉淀落点**:`ANIMATIONS.md`(克制原则已有,不重复)、`page-logic-patterns.md` 第 17 节(文本内部升级)、`QA_RUBRIC.md`(对比度/反同质化量化项)。

**应用到哪页**:`.hl`/`.num` 行内高亮 → P02/P04/P05/P07–P12/P14/P15/P17–P19 全内容页关键词与数据;数据三段式 → P05「15 批 × 600 枚」、P17「15 套 / 600 枚」、P19「T+7/20/30」;节奏自检 → 20 页版式签名逐页核对(P10→P11 同 pattern 已修复)。

## 2. html-ppt-skill(排版稳定 · 图片与色块搭页面)

**仓库特征**:四层解耦(base tokens ← 36 套主题 ← 31 种单页模板 ← 15 套作用域整 deck);渲染即出 1920×1080 PNG,版式零回流。

**学到什么**:
1. **视口即画布 + absolute 堆叠 slide**:fixed 安全区 padding、仅 `.is-active` 可见,杜绝回流——与本 skill 的 deck-stage 模型一致,互为印证。
2. **渐变色块 + 模糊光斑 + scrim 三板斧**替代真实图片,全程 token 取色(color-mix 派生),换肤后图片位不破;图底文字必压 transparent→暗色渐变条保证可读。
3. **卡片族四变体全 token 化**(soft/outline/accent/默认),surface/border/radius/shadow 无一硬编码。
4. **符号引导轻量化**:字符 `→` 作流程连接、48px 圆形数字徽章半浮卡顶、时间轴 `::before` 横线+圆点——纯 CSS 即可成立,无需 SVG 重型件。
5. **反同质化靠规则不靠发挥**:明文"相邻页不用同一 layout"+ 骨架 cover→toc→divider→内容循环。

**沉淀落点**:`layout-patterns.md` 第 14 节(符号引导轻量件清单)、`page-logic-patterns.md` 第 17 节;`THEMES.md`(token 纪律条款)。

**应用到哪页**:编号徽章 → P02 目录 01–04 编号chip、P15 阶梯 STEP 编号、P17 链式编号(原有)统一为 mono 徽章;`→` 方向符号 → P10 因果页(原有)、P11 编辑条向下引导;色块+scrim 纪律 → 全 deck 面板配色统一为金/钢蓝 token 派生(清除遗留硬编码蓝)。

## 3. baoyu-design(左侧预览 · 发布会式克制卡片)

**仓库特征**:文档驱动(SKILL.md → system-prompt.md 单一事实源 → 13 类场景路由 → ~50 个场景子技能 + 脚手架);左侧缩略图 rail 为标志性交互。

**学到什么**:
1. **发布会式克制卡片硬约束**:1px 发丝边框(极低透明度)+ 小圆角 + 无/轻阴影;卡距 24–26px;明令禁止"圆角+左侧色条"卡片、蓝紫渐变、emoji(AI slop 清单)。
2. **一切尺寸 token 化**:字号/间距/留白全走 `:root` 变量,单点修改全局重排;重复元素跨页同位(章节页外观平行一致)。
3. **配色纪律**:每 deck 至多 1–2 种背景色;主色 + 锐利 accent 胜过平均铺色;深色 UI 文字用 100/72/55/45% 白透明度阶梯分级,保证可读层级。
4. **wrapper-fill 规则**:每页单一 in-flow wrapper 强制 height:100%,防背景塌陷;底部留白是刻意构图。
5. **左侧预览 rail**(本 deck 已由 O 键 overview 承担同职能):缩略图为 slide 深克隆 + scale,激活态 2px accent outline + 光晕。

**沉淀落点**:`THEMES.md`(透明度阶梯/背景色上限)、`QA_RUBRIC.md`(克制卡片检查项)、`page-logic-patterns.md` 第 17 节。

**应用到哪页**:白透明度阶梯 → 封面副标题、meta-line、caption 的可读性校核;克制卡片纪律 → 组卡边框收敛为 token 发丝线(清除 rgba(48,149,242) 硬编码蓝边);尺寸 token 化 → 本轮新增样式全部走 var(),无自由 hex(唯一例外:accent 面上的反色墨文字,登记为 `--on-accent` token)。

## 4. autoppt(版式轮换目录 · 三段页面骨架)

**仓库特征**:Codex skill 库,整页生图/绝对定位重建驱动;设计知识集中在提示词规程与示例页。

**学到什么**:
1. **三段页面骨架**:大标题+短下划线 / 一句话副题 / 主视觉区 / **底部深色结论条(白字)**——每页锁定结论条,与 NARRATIVE.md 的 takeaway 一致,互为印证。
2. **版式轮换目录**:11 种构图(封面/目录/链路/矩阵/飞轮/架构/路线图/证据墙/对比/大数字/结束卡),每页选一种、相邻页强制不同。
3. **大编号徽章**:01–09 圆角色块编号串联流程与层级;目录页"大编号+错落章节条"。
4. **语义化强调色**:常规=主色、风险/终点=暖色小面积;蓝→红递进表达链路方向。
5. **文本框余量纪律**:预留 10–15% 余量;标题/pill/徽章禁换行、先缩字不溢出。

**沉淀落点**:`layout-patterns.md`(连页轮换条款强化)、`page-logic-patterns.md` 第 17 节;`QA_RUBRIC.md`(结论条/余量检查)。

**应用到哪页**:底部结论条 → 全内容页 takeaway 重写为真结论(原为机械复制首条 bullet);大编号徽章 → P02/P15/P17 编号体系;语义色 → 金=主强调/钢蓝=结构与引导,双色分工全 deck 统一;余量纪律 → P11 新 structure 留白 ≥30%。

---

## 5. 汇总:本轮新增/修订的文档清单

| 文档 | 动作 | 内容 |
| --- | --- | --- |
| `references/BENCHMARK.md` | 新增 | 本文(4 家对标结论 + 应用页码) |
| `references/page-logic-patterns.md` | 修订 | 新增第 17 节「文本内部升级与符号视觉引导」(关键词高亮、数据突出、编号徽章、结论条、克制卡片) |
| `references/layout-patterns.md` | 修订 | 新增「编辑式动线条」变体登记 + 轻量符号引导件清单 + 连页轮换条款强化 |
| `references/THEMES.md` | 修订 | 新增深色主题配色纪律(背景色上限、白透明度阶梯、token 派生禁硬编码、accent 面反色文字) |
| `references/QA_RUBRIC.md` | 修订 | 新增对比度硬指标、反同质化签名核对、克制卡片/结论条检查项 |
| `assets/components/typography.css` | 修订 | 新增 `.hl` / `.num` 文本升级工具类与引导符号样式 |

---

<!-- TASK-007: 新增——布局系统专题复标(用户指定五类,2026-08-15 二轮落盘) -->
## 6. TASK-007 专题复标:html-ppt-skill 布局五类经验

**来源**:lewislulu/html-ppt-skill(https://github.com/lewislulu/html-ppt-skill ,commit `f3a8435`)。本轮只抽取**布局稳定性 / Grid / Flex / 图片区域 / 色块组合**五类,不重复 TASK-001 已沉淀的符号引导/卡片变体等结论。

**学到什么(按五类)**:

1. **布局稳定性**:固定 1920×1080 画布 + 视口等比缩放(`scale = min(cw/1920, ch/1080)`,runtime.js L650),任何窗口尺寸零回流不变形;`.slide` `overflow:hidden` + 仅 `.is-active` 可见;缩略/演讲者预览用同一份 CSS 的 iframe/深克隆 + `transform:scale()` 等比缩小,保证预览与观众视图像素级一致。
2. **Grid**:布局原语 `.grid.g2/.g3/.g4` = `repeat(N,1fr)` + 固定 `gap:24px`,全库统一三档;bento 格阵用 `grid-auto-rows:180px` + 主格 `grid-column/row: span 2` 制造视觉重心;每页只用一个格阵容器,卡片逐格落位。
3. **Flex**:四个原语覆盖全部单轴场景——`.row`(横排 gap:24 居中)、`.stack > * + *`(纵向 14px 节奏)、`.fill`(`flex:1` 吸收余量)、`.center`(双居中);流程图 `.flow` 节点 `flex:1` 等分 + 箭头 `flex-shrink:0` 不压缩,方向符号不被节点挤压。
4. **图片区域**:图片只进独立容器;图底文字必压 scrim 渐变条(hero: `linear-gradient(180deg,transparent 40%,rgba(10,12,20,.65))`;bento caption: `linear-gradient(transparent,rgba(0,0,0,.55))`);缩略位 `aspect-ratio:16/9` + `overflow:hidden`;无图位用渐变色块占位,换肤不破。
5. **色块组合**:渐变色块 + 模糊光斑 + scrim 三板斧替代真实图片;全部 `color-mix()` 从 token 派生(accent 12%/28% 透明度档);36 套主题定义同一组变量(`--bg/--surface/--border/--text-1/2/3/--accent...`),主题文件 <200 行、只覆盖 token 不改结构——换肤后色块位、图片位全部不破。

**沉淀落点**:`references/html-layout-system.md`(新建)——A 布局稳定性 → §6 规则 1/2;B Grid → §1;C Flex → §2;D 图片区域 → §3;E 色块组合 → §4;反模式与量化 QA → §6/§7 与 `QA_RUBRIC.md`「布局稳定与结构纪律检查」。与本库既有机制的关系:`minmax(0,1fr)` 防撑爆、`--slide-padding` 页边距、`object-fit` 纪律、`deck-stage` 等比缩放均为本库已有实现,本轮登记为显式系统规则并补齐量化阈值。

---

<!-- TASK-008: 新增——baoyu-design 三维专题复标(用户指定三维,2026-08-15 三轮落盘) -->
## 7. TASK-008 专题复标:baoyu-design 页面预览思维 / 场景匹配 / 内容与视觉关系

**来源**:JimLiu/baoyu-design(https://github.com/JimLiu/baoyu-design ,commit `026d4ea`)。本轮只抽取用户指定三维;§3(TASK-001)已沉淀的克制卡片/token 化/配色纪律/左侧 rail 交互不重复。

**学到什么(按三维)**:

1. **页面预览思维**:
   - 缩略图 rail 用同源 DOM 深克隆 + `transform:scale()`(`starter-components/deck-stage.js`),不是截图——预览与成品永远一致、零额外渲染管线,且 MutationObserver 实时同步;
   - "基态即终态"约定:动画只藏不露,缩略图/打印/PPTX 导出三处预览共用同一份最终布局(`make-a-deck.md`);
   - 预览是交付的一部分:强制本地 HTTP serve 后预览与截图,禁止 `file://` 直开(`system-prompt.md`);
   - 多方案对比用单画布并排 artboard(design-canvas / options-stack 的 file-options board),不用 N 个散文件;
   - 早期露出 + 先小后大:第一次落盘即向用户展示,先骨架预览确认方向、再细化单页(hi-fi-design / wireframe 先出 3–5 粗稿圈定设计空间)。
2. **场景匹配**:
   - 13 类项目路由表做成机器可读 JSON(`project-types.json`:id → skills → starters 三元组),`system-prompt.md` 中的表格只是镜像——场景判定既可人读也可程序消费;
   - "开工前必读"门禁:命中场景必须先 load 对应子技能再动手(BEFORE starting);
   - 默认分支防死锁:匹配不到 13 类时兜底 hi-fi-design + interactive-prototype;
   - 场景不明不盲猜:强制向用户提问(deck 必问时长/受众);
   - 场景子技能内部自带页面构成规程(make-a-deck:先写标题序列,只读标题能复述全篇;website-landing-page:hero→信任证明→答疑区→footer 的 anatomy)。
3. **内容和视觉关系**:
   - 禁模板先行:禁止占位文字凑版面,每个元素必须 earn its place;版面空是设计问题,不靠编造内容填(`system-prompt.md`);
   - 文字超载 → 换视觉形式(表格/图示/引用/图片),不是压缩字号(`make-a-deck.md`);
   - 信息层级变量化:一切字号走 `--type-*` CSS 变量,先定尺度再写页;
   - 留白是结构不是空缺(`--pad-bottom` 显式保留,底部三分之一留白是正确构图而非缺陷);
   - 溢出是校验错误(组件级 `no_overflowing_text` 校验),不允许缩放硬塞;
   - 图文按内容类型分流:截图/图示 aspect-fit 且极少叠字;每页自成语义单元、重复元素跨页同位。

**沉淀落点**:`references/design-scenario-system.md`(新建——10 类 page 级场景 × 五属性量规 + 判定流程 + 反模式);`SKILL.md` 总线③(场景判定落点)与场景门禁;`state/page_semantics.md` 新增「页面场景」列(格式定义于 SKILL.md);`references/QA_RUBRIC.md`「场景判定与场景多样性检查」;`references/html-layout-system.md` §0(<!-- TASK-010 fix -->蓝图「页面类型」取值域对齐 10 类业务场景 + 1 个骨架保留项 `目录页(toc)`);`references/NARRATIVE.md`(deck 级 / page 级两层场景关系);`references/page-logic-patterns.md`(决策流程 ⓪ 步同步场景判定)。

**与本库既有机制的关系**:O 键缩略图总览与 S 键演讲者预览已承担"同源预览"职能,B 键静态降级与打印媒体查询即"基态即终态"的本库实现,本轮不再重复建设;场景路由 JSON 化思路落地为 <!-- TASK-010 fix -->10 类业务场景体系 + 总线③强制判定门禁;"内容决定视觉"落成场景卡五属性量化区间与「禁止全 deck 同模板」反模式,与 TASK-007 输出稳定规则五条(不溢出/不缩字/图不变形)方向一致、互为强化。

---

<!-- TASK-019: 新增——huashu-slides 逐文件对标 + 用户点名「瀑布式全景图演示」机制破解(2026-08-16 落盘) -->
## 8. huashu-slides(内容→设计→构建工作流 · 风格预设 · 英雄数字 · 瀑布式全景)

**来源**:平台技能库 `huashu-slides`(SKILL.md + references 4 份 + scripts/create_slides.py)。工作流为 Content→Design→Build→Assembly→Polish 五段,Path A(HTML→PPTX)/ Path B(全 AI 图)双路径,内置 18 种风格预设(Snoopy/Manga/Ligne Claire/Neo-Pop/xkcd/Neo-Brutalism + 5 种 Professional Editorial:Pentagram/Fathom/Müller-Brockmann/Build/Takram)。**注意:该技能分发文件中不含瀑布全景实现代码**——用户点名的瀑布式全景效果图来自其 HTML deck 实践(培训长 deck),机制由本库按效果图逆向拆解并原生实现(见「沉淀落点」)。

**学到什么(逐文件)**:
1. **SKILL.md**:① Assertion-Evidence 标题法——每页标题是"断言句"而非"主题词"(本库 page-logic-patterns 主结论纪律同向);② 5/5/5 密度律(每页 ≤5 块、每块 ≤5 行、每行 ≤5 词组)——与本库场景卡密度档互补,偏口头宣讲场景;③ "mood over layout" 提示词黄金律——先定情绪/氛围词再定版式,与本库 art DNA 四类生成先行的方向一致。
2. **design-principles.md**:① 60-30-10 配色(主 60 / 辅 30 / 强调 10)——对应本库双色分工的比例化表达;② "distraction test"(逐元素问"删掉观众会漏掉信息吗")——与本库 §8 删除测试同口径;③ "design for disaster"(投影偏色/远距/亮光环境兜底)——呼应本库 V1 对比度阻断项的动机层。
3. **design-movements.md**:设计运动 → 视觉特征 → 提示词映射表(Bauhaus/Swiss/Brutalism 等),把"风格"从历史名词转成可执行的 token 特征清单——本库主题 signature 元素可借用此表的"特征 → token"写法。
4. **prompt-templates.md**:风格预设的结构化描述模板(色彩/字体/材质/禁忌四段式),其中 **Fathom 风格的 hero-metric 版式**(超大等宽数字 + 小标签 + 发丝线,数字即图形焦点)直接可迁移到数据页。
5. **proven-styles-gallery.md / proven-styles-snoopy.md**:成品风格实证库——同一内容在 18 种风格下的成稿对照,证明"风格 = token 组 + 少量 signature 件"而非结构重写,印证本库主题只覆盖 token 不改结构的纪律;Ligne Claire 的"面板克制"(每格一焦点、粗描边平面色)与 Müller-Brockmann 的网格纪律对信息页有直接借鉴。
6. **scripts/create_slides.py**:PPTX 组装器(HTML 渲染图 → 16:9 幻灯片),Path A 的出口工程化;本库出口是单文件 HTML,不引入,但其"每页先渲染成图再组装"的质检思路(渲染即校验)与 render_deck 预览流同向。

**瀑布式全景机制拆解(用户点名效果)**:效果图特征 = 黑底 + slide 缩略图卡片组成的 3D 微倾"照片墙" + 编号徽章 + 边缘出血。四要素全部可原生化:① 缩略图 = 同源 DOM 深克隆 + `transform:scale()`(承接 §7 baoyu-design 结论,零截图零管线);② 3D 墙 = 容器 `perspective` + 网格 `rotateY(-24deg) rotateX(7deg) scale(1.16)` + 个体 `rotate 1.2deg`;③ 网格 = 固定 2120px 4 列 Grid 居中,`aspect-ratio:16/9` 卡片;④ 入场 = 个体 `scale` 属性 1.5→1 交错淡入(`--i * 28ms`)。跳转不复制导航逻辑:委托既有 O 总览按钮(合成 `keydown('o')` 构建 + 点击对应按钮),导航内核零改动。

**沉淀落点**:`references/panorama-overview.md`(新建——机制拆解 + 交互口径 + 样式 token 纪律 + QA 核对点);`assets/components/base.css`(瀑布全景增量样式块,全 token 派生);`assets/runtime/runtime.js`(G 键全景增量模块,委托跳转);`scripts/render_deck.py`(骨架挂 `.waterfall` 挂载点 + deck-ui 提示加 G);`SKILL.md` 阶段 3 动作 8(运行时特性行挂 G 键);`references/final-quality-check.md` §3(deck 级核对点挂接);本节(§8)登记。

**应用到哪页**(目标 deck 新增 2 处页面级迁移,均模块内部改造、不动布局签名):① **Fathom hero-metric → P17 量产行**(`15 批 × 600 枚` 升级为卡内英雄数字块:52px 等宽大数字 + 标签 + 单位降档,文本零改动);② **焦点即图形面 → P18 中心核**(`.spoke-core` 标题 27px→42px、副题 24px→27px,中心核成为版面最大视觉件,呼应 hub-spoke 的中心→周围空间语义)。

**与本库既有机制的关系**:Assertion-Evidence / 主结论纪律、60-30-10 / 双色分工、distraction test / §8 删除测试、design for disaster / V1 对比度阻断——四组口径互为印证,不重复建设;5/5/5 密度律作为口头宣讲场景的补充档位参考,不改本库场景卡量规;G 键全景与 O 键文字总览互补(视觉检索 vs 标题检索),共用同一跳转路径;风格预设四段式描述法留作后续主题扩展的参考格式。
