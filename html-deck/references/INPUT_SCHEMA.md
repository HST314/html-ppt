# INPUT_SCHEMA

## deck.md

- `#`：演示标题，只允许 1 个。
- `##`：章节标题，可生成 section 页，也可仅作为页分组。
- `###`：幻灯片标题。每个 `###` 及其后正文属于一页。
- HTML 注释元数据：
  - `<!-- role: image-hero -->` 指定当前页 role。
  - `<!-- image: img-001 -->` 绑定图片。
  - `<!-- theme: tech-dark -->` 指定推荐主题。
  - `<!-- notes: ... -->` 写入演讲者备注。

支持内容块：段落、无序列表、有序列表、Markdown 表格、 fenced code、引用。

约束：页标题 <= 30 字；列表 <= 6 条；单条 <= 40 字；表格建议 <= 5 列、<= 8 行。

## images/manifest.json

```json
{
  "version": "1.0",
  "images": [
    {
      "id": "img-001",
      "file": "dashboard.png",
      "alt": "产品仪表盘截图",
      "description": "SaaS 产品仪表盘完整界面，深色主题",
      "content_type": "screenshot",
      "width": 1920,
      "height": 1080,
      "aspect_ratio": "16:9",
      "suggested_role": "hero",
      "scene_tags": ["产品", "界面"],
      "weight": "high"
    }
  ]
}
```

必填字段：`id`、`file`、`alt`、`description`、`content_type`、`width`、`height`、`aspect_ratio`、`suggested_role`、`scene_tags`、`weight`。

枚举：
- `content_type`: `screenshot`、`photo`、`chart`、`diagram`、`illustration`
- `suggested_role`: `hero`、`inline`、`gallery`、`background`
- `weight`: `high`、`medium`、`low`

校验：id 唯一；文件存在；像素尺寸与元数据一致；aspect_ratio 与宽高相符。

## outline.json 可选设计字段（场景基因装饰层）

以下字段均为可选，作用于封面/结尾页的设计表现；缺省时渲染层自动给出得体的默认值，agent 可在 build_ir 之后按 brief 微调：

- `cover.eyebrow`：封面眉线，默认 `CONCEPT PROPOSAL · 概念方案`。建议格式 `英文主题词 · 中文场景`。
- `cover.subtitle`：封面副标题，默认 `从核心主张到落地计划的一次完整汇报`。
- `cover.meta`：封面底部铭牌胶囊数组（1–3 条），默认取各 section 标题前三条。
- `cover.title`：含 `：` 时自动拆为白色主标题行 + 主题渐变强调行（h1-em）。
- `closing.eyebrow`：结尾眉线，默认 `NEXT STEP · 落地行动`。
- `closing.echo`：结尾收尾语（衬线大字渐变）。build_ir 自动取封面标题冒号后的强调语，形成首尾呼应；无则留空。
- `closing.echo_sub`：收尾语下方英文小字，默认 `HONOR GALLERY · CONCEPT PROPOSAL`。

装饰层元素（奖牌圆环、数据光柱、流动动线、铭牌矩阵）由 `scripts/deco.py` 生成、由 `assets/components/deco.css` 从主题 `--accent` 派生配色，任何主题下均保持协调；中间页自动获得简洁统一背景（角落动线 + 铭牌点阵），章节页额外叠加圆环。
