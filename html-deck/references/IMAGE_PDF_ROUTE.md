# Image-PDF 路线

当用户要求图片 PPT、逐页生图或每页为整页位图的 PDF 时，执行本路线。不要调用 HTML 渲染链。

## 输入与输出

输入：Markdown 大纲、可选项目图片/参考图、可选品牌约束。输出：16:9 PNG 页面序列与无文本层 PDF。

固定目录：

```text
<project>/
├── outline.md
├── images/
├── state/
│   ├── design_dna.md
│   ├── page_plan.json
│   ├── image_prompts.json
│   └── image_pdf_qa.json
└── dist/
    ├── pages/NN-*.png
    └── deck.image.pdf
```

## 两轮交互

### 第一轮：提取设计元素

读取全部参考图与图片描述，写入 `state/design_dna.md`：

- 主题与情绪；
- 构图骨架与焦点位置；
- 主色、辅助色、强调色；
- 材质、纹理、光影；
- 重复符号与禁用元素；
- cover、toc、section/content、closing 四类页面的继承与变化规则；
- 文本安全区、图片安全区和最小对比度。

如用户正在实时协作，展示这份提取结果并等待确认后进入第二轮。若用户明确要求直接完成、批量生成或给出的设计说明已经充分，记录“按现有资料直接执行”的假设并继续，不制造额外阻塞。

### 第二轮：逐页生图

1. 将大纲压缩为真正的幻灯片内容，而不是把原文整段塞入画面。
2. 先建立 `chapters`，再分页。`page_plan.json` 顶层必须包含按叙事顺序排列的 `chapters`（每项含唯一 `id`、`title`、可选 `lead`），每页必须包含 `id`、`role`、`title`；section/content 页还必须包含 `chapter_id`。角色至少区分 cover、toc、section、content、closing。
3. `image_prompts.json` 为每页登记生成提示词；提示词必须复述设计 DNA、页面角色、构图、文本安全区、参考图角色和“禁止任何文字/数字/水印”。
4. 每一页调用图片生成能力生成无字视觉底图。为了跨页一致，可先生成四类母版，再以母版作为风格参考逐页生成；不得只生成一张图后机械复制为所有页面。
5. 使用 `scripts/render_image_deck.py` 把最终中文、数字和图表标签确定性叠加到视觉底图上。模型内不得承担准确文字。
6. 合成后逐页检查并执行 `scripts/validate_image_pdf.py`。

## 页面角色约束

- cover：首页只保留标题、副标题、短标识；视觉焦点最强，保留大面积标题安全区。
- toc：目录项只允许从顶层 `chapters` 自动生成，3–7 项；显示章节名及实际页码范围，不得在 toc 页另写一套目录文案。
- section：每个 `chapters` 项必须且只能有一个 section 页；section 的 `title` 必须逐字等于对应章节 `title`，情绪化转场文案放在 `subtitle`，不得用另一套标题替代章节名。
- content：一个结论、2–4 个信息组；正文建议不超过 110 个中文字符。复杂内容拆页。
- closing：一句收束文案与可选副句，不出现长列表、表格或大段说明。

## 图片提示词模板

```text
Use case: productivity-visual
Asset type: 16:9 image-based presentation visual plate, <role> role
Primary request: <本页视觉任务，不写正文>
Input images: Image 1: style reference; Image 2: supporting subject reference
Scene/backdrop: <从 design_dna.md 继承>
Composition/framing: <焦点位置 + 明确的文字安全区>
Color/material/light: <从 design_dna.md 继承>
Constraints: preserve the requested empty text-safe region; no letters, words,
numerals, logos, UI controls, watermark, border, or fake text; 16:9 landscape
```

## 合成命令

安装 Pillow 后运行：

```bash
python3 scripts/render_image_deck.py \
  --spec <project>/state/page_plan.json \
  --output-dir <project>/dist/pages \
  --pdf <project>/dist/deck.image.pdf

python3 scripts/validate_image_pdf.py \
  --spec <project>/state/page_plan.json \
  --pages <project>/dist/pages \
  --pdf <project>/dist/deck.image.pdf \
  --report <project>/state/image_pdf_qa.json
```

## QA 门禁

- 页面均为同一尺寸，默认 1920×1080；页序由两位数字前缀决定。
- 目录、转场与正文必须共享同一 `chapter_id`：章节顺序与 `chapters` 完全一致；每章先出现同名 section，再出现至少一页 content；章节之间不得穿插。
- 目录页的章节名和页码范围由渲染脚本根据 `chapters` 与页面顺序计算，禁止复制粘贴维护。
- PDF 页数等于 PNG 数量；PDF 页面仅含整页位图，`pdftotext` 结果必须为空。
- 标题、目录、数字、专名逐字匹配 `page_plan.json`。
- 任何文字不得越界；正文最小字号 30 px，标题最小字号 48 px。
- 正文与承载面静态对比度至少 4.5:1；大标题至少 3:1。
- 项目图片不得拉伸；使用 contain 或经过明确主体检查的 cover。
- 相邻内容页至少在焦点位置、主图、卡片结构或视觉节奏之一有可辨识变化。
- 缺页、重复页、模型伪文字、错误中文、水印、尺寸不一致均为阻断项。
