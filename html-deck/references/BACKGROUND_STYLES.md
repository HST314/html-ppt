# 背景风格库规范

<!-- TASK-039: 新建——解决"所有项目背景看起来像同一个模板"问题 -->
<!-- TASK-041: 重建——tech-grid/flow-lines/paper-grain 三种风格骨子里都是
"SVG 线条+圆+散点"的参数变体，视觉语言无实质差异，是 project-changzheng8a
（航天军工）与 project-jixueyuan（高校机构）两个内容完全不同的项目背景构图
撞车的直接根因；本次删除这三种，新增图形基元完全不同的 radial-vector/
rule-ledger/brush-sweep，并接入 state/theme_domain.json（TASK-040 地基产物）
的 domain 判断作为背景风格选择的最高优先级 -->
<!-- TASK-042: 彻底重写——TASK-039/041 只把"装饰图案"从 svg() 里拆了出来，
但 svg() 自身仍然固定画三样东西：①基于 light_focus 定位的柔光大椭圆、
②18 条完全随机对角线、③7 个完全随机同心圆环，不管选中哪种风格都会画，
是"不同主题项目背景看起来还是很像"的真正根因（用户截图看到的"一堆圆环+
对角线"）。本次把这三段固定骨架彻底删除，`svg()` 现在只是薄胶水层；风格库
从"画一层图案叠在固定骨架上"改为"每个风格产出一份完整背景"，并按 6 大
设计分类彻底重做了全部风格的构图（参考 beautiful-html-templates-main /
presentation-md-main 的设计研究），新增 slide_templates/backgrounds/ 与
slide_templates/content/ 两个静态预览模板库 -->

## 背景与根因（TASK-039，仍然成立）

`scripts/extract_art_dna.py::svg()` 早期在装饰层（`motif` 变量）里硬编码了一段
固定 SVG 路径——"轨道弧线 + 火箭上升轴 + 箭头"，坐标完全写死，不随 `analyze()`
算出的任何 dna 参数变化。这是早期为长征八号甲这类航天主题项目做装饰时，误把
项目专属图形焊死进了所有项目共用的通用背景生成函数，导致换任何项目跑一遍，
背景装饰层的构图都长得一样，只是配色（`dna["palette"]`）不同——即"千人一面"。

TASK-039 把"装饰层要画什么构图"从 `svg()` 里拆出来，做成一个分类整理好的
背景风格库（`scripts/bg_styles.py`），并新增一套基于像素统计 + 关键词的
匹配机制，按项目内容自动选择最合适的一种。

## 二次撞车与 TASK-041 的修复

TASK-039 上线后，`tech-grid`/`flow-lines`/`paper-grain` 三种风格暴露出视觉
语言没有实质差异的问题（骨子里都是"细线群+圆/椭圆+散点"的参数变体）。
TASK-041 删除这三种、新增图形基元互不相同的三种风格，并接入
`state/theme_domain.json` 的 `domain` 判断作为最高优先级信号，从根上避免
局部关键词/量化特征的噪音盖过项目级的主题域信号。

## TASK-042：彻底重写的真正根因与修复（本次改动）

TASK-039/041 两轮改动都只处理了"装饰图案叠什么内容"这一层，但从未触碰
`extract_art_dna.py::svg()` 自身——该函数在调用风格库产出的 `motif` 之外，
**自己还固定画三样东西**：

1. 基于 `dna["light_focus"]` 定位的一枚柔光大椭圆（`<ellipse fill="url(#g)">`）；
2. 18 条完全随机（`rnd()`）位置/角度/透明度的对角直线；
3. 7 个完全随机大小/位置的同心圆环（`<circle fill="none" stroke=...>`）。

不管风格库选中哪一种风格，这三样东西**永远都会画**——这才是"不同主题项目
背景看起来还是很像"的真正根因：用户在高校科研教育机构项目截图里看到的
"一堆圆环+对角线"，主要就是这套固定骨架，不是风格库产出的图案本身。

修复方式：**彻底删除这三段固定骨架**，`svg()` 现在只是一层很薄的胶水——
拼装 viewBox/defs（仅一层不构成图形的通用噪点纹理）/尾页镜像翻转等最外层
结构，真正的背景内容（基础色底/渐变 + 全部装饰元素）全部移入
`bg_styles.py` 的风格生成器。风格库的产出模型也从"图案层"改为"完整背景"：
每个 `style_xxx(p, dna, kind, rnd)` 函数返回 `(base_svg, deco_svg)`，`base_svg`
是该风格自己的底色/渐变，`deco_svg` 是该风格的全部装饰元素，两者不再依赖
外层提供任何共享形状。

## 与既有能力的关系（不是推倒重来）

- `detect_style.py` 的色相/明度/饱和度分析（决定主题 CSS 变量 `--accent` 等）
  **保留不变**，本次改动完全不涉及。
- `extract_art_dna.py::analyze()`/`analyze_png()` 的调色板提取（`semantic_palette()`）
  与线条/明暗统计（`line_language`/`dark_focus`/`light_focus`/`saturation`/
  `contrast`）**保留不变**，本次改动只是替换这些量化结果之上"背景实际画
  什么"这一层实现——每个风格函数的颜色仍然 100% 来自 `dna["palette"]`
  （图片像素真实分析结果），不写死任何 hex 值。
- `state/theme_domain.json` 驱动的三级风格匹配优先级（domain 命中 > 关键词 >
  量化特征兜底）**保留复用**，`select_background_style()` 的匹配算法本身
  未改动，本次只重写"选中风格后画什么"。
- 四类角色背景（cover/content/section/closing）、`non_template_signature`、
  主题线条插画装饰机制（`assets/motifs/library/`，见 `ART_DNA.md`）等既有
  机制全部保留。
- `slide_templates/toc/` 目录页模板库、`render_deck.py` 的
  `select_toc_template()` **不动**（用户明确要求：目录页模板库"还可以"）。

## 文件组织

```
scripts/bg_styles.py              # 风格库实现：7 个生成器函数 + STYLE_LIBRARY 注册表 + 三级匹配逻辑 + content 态弱化包装
references/BACKGROUND_STYLES.md   # 本文档：六大风格分类体系、设计来源、domain 对接、匹配规则
references/THEME_DOMAINS.md       # 项目主题域判定（TASK-040 地基），本文档消费其 domain 字段
scripts/classify_theme_domain.py  # 产出 state/theme_domain.json，供本风格库读取
scripts/extract_art_dna.py        # svg() 现在只是薄胶水层：调用 bg_styles 选风格 + 组装完整背景，不再自己画任何固定图形
scripts/art_dna_from_md.py        # md 路径复用同一个 svg()，domain 优先级同样生效
slide_templates/backgrounds/      # 6 大类共 7 个风格的 cover 态静态预览文件（人工参考，不参与渲染）
slide_templates/content/          # 同 7 个风格的 content 态静态预览文件（人工参考，展示"弱化规则"后的效果）
```

不新增素材文件目录（区别于 `assets/motifs/library/*.svg` 那种"预画好的静态
线条素材"）——背景风格库里的每种风格都是**参数化生成逻辑**（Python 函数），
不是预制图片，因为每种风格必须在任意项目的任意配色/构图统计下都能生成有效
背景，静态素材做不到这一点。`slide_templates/backgrounds/`、
`slide_templates/content/` 两个目录是**人工预览/参考库**，性质上与
`slide_templates/toc/` 一致：一批用 `{{占位符}}` 标记参数化点的独立单文件，
供人工浏览目视核对每种风格的构图，不是渲染时真正读取执行的文件；实际渲染
时背景内容 100% 由 `bg_styles.py` 的 Python 函数生成。

## 结构模板与配色分离原则（每种风格都必须遵守）

风格生成器函数只描述"构图逻辑"——线条走向、形状类型、叠加方式、坐标计算，
**不写死任何具体 hex 色值**。所有颜色都通过调用方传入的 `p`（即
`dna["palette"]`，来自图片像素真实分析）取值，例如 `p[1 % len(p)]`。这保证
同一套风格能在不同项目的不同配色下复用，不需要为每个项目重新实现一遍。

## 六大风格分类 / 七个风格 key

设计研究来源：`skill reference learning/beautiful-html-templates-main`
（28 个完整模板）与 `skill reference learning/presentation-md-main`
（`surfaces.css` 按主题命名的背景系统）。分类 1「极简科技/网格数据」按
强度拆成动感版/克制版两个 key，服务不同 domain；其余 5 类各一个 key，
共 7 个风格 key、6 个设计分类。

| key | 所属分类 | 构图逻辑 | 参考范例 | 对接 domain | 适用场景关键词 |
|---|---|---|---|---|---|
| `tech-grid-hud` | 1. 极简科技/网格数据·动感版 | 深底通铺网格细线(40px间距,~0.07透明度) + 双层同心圆环角标(固定右下角,像雷达瞄准镜) + 十字准星 + 22 点稀疏星点 | `hud-grid` | `aerospace-defense-tech` | 科技、航天、数据、仪表、精密、系统、智能、芯片、算法、工程、蓝图、坐标、卫星、雷达、导弹、火箭、发射、军工、国防 |
| `tech-grid-blueprint` | 1. 极简科技/网格数据·克制版 | 网格更淡(52px间距,~0.045透明度,约动感版强度的六成) + 空心方框角标(非圆环,右上角) + 四角CAD式括号,无发光星场,像制图纸 | `blueprint-grid` | `academic-institutional`、`corporate-professional` | 规程、文牍、档案、制度、规范、机构、科研、学术、合规、流程、标准、评审、评估、报告 |
| `print-texture` | 2. 复古人文/印刷质感 | 暖色纸底(取 palette 中感知亮度最高的颜色) + 两枚不规则圆润色块 multiply 混合叠印(4-6px位移模拟套印不准) + 一条极细墨线点缀 | `riso-print` / `Biennale Yellow` | `cultural-heritage-formal` | 历史、展览、文物、印刷、版画、档案、博物、考古、民俗、出版、古籍 |
| `geo-brutalist` | 3. 几何色块/粗野主义 | 骨白底(取 palette 中感知亮度最高的颜色) + 6 个圆角22-26px高饱和色块拼贴(3px硬描边+方向性硬投影,无渐变无模糊) + 背景细网格纹理 | `Stencil & Tablet` / `acid-block` | `product-launch-design` | 设计、品牌、极简、现代、发布、产品、几何、建筑、模块化、包豪斯、潮流、新品 |
| `organic-warm` | 4. 有机手绘/温暖人文 | 角落柔和暖色椭圆光晕 + 一枚旋转的空心叶形不对称圆角图形 + 2 道开放式笔触扫痕(多层描边模拟笔锋) + 纸纤维颗粒散点 | `botanical-leaf` / `brush-sweep` | `cultural-heritage-warm` | 传统、文化、纪念、手工、纸、复古、书法、篆刻、匠人、温暖、非遗、草木、自然、乡土 |
| `refined-literary` | 5. 奢华质感/文艺克制 | 单一深色纯色通铺全屏(零渐变零阴影零圆角) + 一条极细(20%透明度)发丝线 + 一段极简批注刻度,画面角落极度安静 | `Vellum` | 不占用 domain 名额，纯 keyword/quant 驱动，服务 `corporate-professional` 高端定位项目的可选补充 | 奢华、尊享、高端、文艺、雅致、静谧、克制、品鉴、典藏、美学 |
| `retro-digital` | 6. 怀旧数字/潮流 | 下方40%透视网格地平线(9条汇聚线+5条渐密横线,旋转延伸消失感) + 深色天空渐变 + 中间一条发光水平线 + 全屏CRT扫描线 | `vapor-horizon` / `8-Bit Orbit` | `consumer-lifestyle-future` | 科幻、未来、沉浸、梦幻、电子、潮流、炫彩、虚拟、元宇宙、赛博、游戏、数字、像素 |

`generic-fallback`（未命中/无法判定）domain 不强制指定风格 key，交由关键词/
量化特征两级算法自行决定，全部为 0 时兜底走 `tech-grid-blueprint`（见下方
「合成与决策」）。

每种风格的具体实现见 `scripts/bg_styles.py` 对应的 `style_*` 函数，函数头部
docstring 与本表描述保持同步，改动任一侧都要同步另一侧。每种风格的 cover 态
静态预览见 `slide_templates/backgrounds/bg-<key>.html`，content 态弱化后
效果见 `slide_templates/content/content-<key>.html`。

> 与 `ART_DNA.md` 生成纪律第 4 条的关系：该条禁止的是"固定使用...科技网格
> 等行业图形"，指的是不加分析、不管项目内容一律套用同一种图形。风格库里的
> 每种风格现在都要经过 domain/关键词/量化特征三级匹配才会被选中，且实际
> 线条走向/焦点位置/底色仍由 dna 参数计算，不是写死坐标或颜色——这与该条
> 禁止的"不分析直接套用"是两回事。

## content 态弱化规则（`slide_templates/content/` 的设计依据）

内容页背景遵守两条共同规律，由 `bg_styles.py::_content_wrap()` **统一实现**
（不需要每个风格函数各自重写一遍）：

1. **与封面/章节页同一款式**：保持主题连续性，content 态调用的仍是同一个
   `style_xxx()` 函数产出的 `base_svg`/`deco_svg`，不会切换成另一种风格，
   不会让 deck 显得割裂。
2. **所有装饰性图形元素统一"缩小58% + 挪到边角(不居中) + 透明度砍半以上"**：
   `_content_wrap()` 把整个 `deco_svg` 用 `translate+scale(0.42)` 包一层，
   缩放锚点固定在画布右下角 `(1920,1080)`——scale 以该点为原点收缩，天然
   产生"挪到角落"的效果，不需要每个风格单独计算平移量；再叠加一层独立的
   `opacity × 0.45` 弱化系数。基础色底/渐变（`base_svg`）不受这层包装影响，
   保证内容页背景底色仍与封面/章节页一致。

绝不新增装饰、绝不使用高饱和纯色块、绝不遮挡正文内容区域——这两条规则
配合"7 个风格 key 各自的构图"，保证 content 页背景永远是"封面page 的
安静弱化版"，而不是另一套视觉语言。

## 匹配机制：如何从分析结果选出一种风格

匹配逻辑实现在
`scripts/bg_styles.py::select_background_style(dna, keyword_text, domain, domain_confidence)`，
由 `extract_art_dna.py`/`art_dna_from_md.py` 在生成四类背景前调用一次。
**本次改动未改动匹配算法本身**（三级优先级、权重、trace 记录格式与
TASK-041 一致），只重写了"选中某个 key 之后画什么"。

### 三级优先级信号来源

1. **domain 命中（最高优先级）**：`extract_art_dna.py` 通过 `--theme-domain`
   参数读取 `classify_theme_domain.py`（TASK-040）产出的
   `state/theme_domain.json`，解析出 `domain`/`confidence` 传入。命中该
   domain 的风格（见上表「对接 domain」列，对应 `STYLE_LIBRARY[key]["domains"]`
   注册表）获得固定大权重加成（`_DOMAIN_CONFIDENCE_BONUS`）：
   - `keyword-strong`：+5000（domain 判断断层领先，是项目级强信号，
     必须能确定性压过局部关键词/量化特征）
   - `keyword-weak`：+800（domain 判断存在竞争，仍给明显话语权，但留出
     空间让其余信号在服务同一 domain 的多个候选风格间做区分）
   - `quant-fallback`：+150（domain 本身只是量化兜底得出，最低置信度，
     不应死死锁定风格选择）
   `domain=None`（例如函数被独立单元测试调用、未传该参数）时该项加成
   全部为 0，完全退化为下面两级算法，不报错、不改变旧行为。
2. **关键词信号**（`_keyword_scores`）：扫描 `keyword_text`（`extract_art_dna.py`
   自动读取项目根目录下的 `deck.md` 正文 + `context/brief.md` 简报，只读，不
   修改这两个文件）里每种风格登记关键词表（上表最后一列）的命中次数，命中
   权重 ×10。
3. **量化特征信号**（`_quant_scores`）：基于 `analyze()` 已经算出的
   `saturation`（饱和度）、`contrast`（明暗层次）、`line_language`（线条方向）、
   以及从 `palette[1]` 推导的暖色倾向，按每种风格各自的判据打分，判据与理由
   见 `bg_styles.py::_quant_scores` 的函数注释，摘要：
   - `tech-grid-hud`：有方向性的线条语言(纵向/横向) + 中高对比(>0.32) + 中等饱和度(0.35~0.68)
   - `tech-grid-blueprint`：均衡网格线条 + 中等饱和度(0.25~0.55)
   - `print-texture`：均衡网格 + 中等饱和度(0.25~0.55) + 偏暖色相
   - `geo-brutalist`：高对比(>0.38) + 中低饱和度(<0.5)
   - `organic-warm`：低饱和度(<0.35) + 低对比(<0.30) + 偏暖色相
   - `refined-literary`：低饱和度(<0.3) + 中高对比(>0.3)
   - `retro-digital`：高饱和度(>0.55) + 低对比(<0.28)

### 合成与决策

`总分 = domain 命中加成 + 关键词命中次数 × 10 + 量化特征得分`，取总分最高的
风格。domain 加成权重（150~5000）明显大于关键词×10 与量化特征能达到的现实
上限，确保项目级主题域判断能确定性主导选择；关键词权重放大 10 倍，理由同
TASK-039：正文/简报里出现的行业词是比像素统计更直接的项目内容信号；量化特征
在 domain 与关键词信号都缺失或多个风格打平手时兜底/修正。全部风格总分为 0
（domain 未命中、关键词无命中、量化特征所有判据都不成立，理论上极少见）时
兜底选 `tech-grid-blueprint`——它的构图逻辑对任意 `dna` 输入都能产出合理、
克制的结果，兜底选择本身仍由 dna 参数驱动，不是写死模板。

判断依据（`trace`）会写入 `art_dna.json` 的 `background_style_reason` 字段，
第一行即为 domain 命中说明，可读、可追溯，不是黑箱决策。

### 校验通用性的方法

新增/调整风格或匹配规则后，应构造几组差异明显的模拟 `dna` + `keyword_text` +
`domain`（例如 domain=`aerospace-defense-tech` vs domain=`academic-institutional`
vs 不传 domain 只给不同的 saturation/contrast 组合），直接调用
`select_background_style()` 打印选中结果，确认不同输入确实匹配到不同风格，
不会全部落到同一个 key；对同一 domain 下渲染出的实际 SVG，还应目视核对图形
基元本身是否有实质差异（不是只看 style_key 字符串是否不同），并核对渲染
结果里**不应出现**已删除的固定骨架特征（不成方向的随机对角线群 + 不成角标
逻辑的随机同心圆环散布全图）——这是 TASK-042 要修复的问题，回归时优先核查。

## 新增风格的步骤

1. 在 `bg_styles.py` 写一个新的 `style_xxx(p, dna, kind, rnd) -> (base_svg, deco_svg)`
   函数：`base_svg` 是该风格自己的底色/渐变（可用 `_flat_fill()` 起步，
   或自己在 `base_svg` 字符串里内联 `<defs>` + 渐变），`deco_svg` 是该风格
   的全部装饰元素；只用 `p` 里的颜色、不写死 hex；随机性通过 `rnd(n)` 取得，
   使用一个与现有风格家族不重叠的偏移量区间（现有七种风格共用
   300-699，见各函数内 `rnd(数字)` 调用；再新增建议另起 700+ 区间）。
   **不需要**处理 content 态弱化——`generate_full_background()` 会统一调用
   `_content_wrap()` 处理，风格函数只管产出 cover 态强度的完整构图。
2. 在 `STYLE_LIBRARY` 注册 `label`/`category`/`generator`/`keywords`/
   `description`/`domains`（元组，登记该风格服务哪些
   `references/THEME_DOMAINS.md` 的 domain key；不强制服务任何 domain 时
   可留空元组 `()`）/`reference`（该风格对应的设计研究参考范例名）。
3. 在 `_quant_scores()` 补一条该风格的量化判据（用现有量化特征即可，不需要
   新增分析维度），并写清楚判据背后的理由（保持可解释、不做黑箱阈值）。
4. 更新本文档的风格总表与关键词列表，保持代码与文档同步；若该风格要接管
   某个 domain 的默认风格，同步更新 `references/THEME_DOMAINS.md` 的「对接
   背景风格 key」列。
5. 在 `slide_templates/backgrounds/` 与 `slide_templates/content/` 各补一份
   `bg-<key>.html` / `content-<key>.html` 静态预览文件（可直接调用
   `bg_styles.generate_full_background()` 用一套占位色生成 SVG 后包一层
   1920×1080 预览页外壳，参考现有 7 份文件的结构）。
6. 用上面「校验通用性的方法」验证新风格确实能在合适的输入下被选中，且不会
   抢占其余风格原本该覆盖的输入范围；并目视核对渲染出的 SVG 图形基元与库内
   其余风格确有区分度，不是"换了参数的同一种视觉语言"。
