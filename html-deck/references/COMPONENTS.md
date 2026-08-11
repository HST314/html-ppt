# COMPONENTS

## raw 原子组件

- title：页标题，最高 30 字。
- subtitle：封面副标题或章节说明。
- body：正文段落。
- list：最多 6 条，支持有序/无序。
- quote：引用正文与来源。
- kpi：数字、单位、说明。
- tag：短标签。
- rule：分割线。
- image-slot：`data-image-slot` 图片槽，必须含 alt 与 object-fit。
- color-block：主题 token 色块，用于分组和强调。

## role 组件

- `cover`：标题、副标题、hero 背景或大留白。
- `toc`：目录，最多 6 节。
- `section`：章节过渡页。
- `bullets`：标题 + 3-6 条要点。
- `two-column`：左右等宽文本/图表/列表。
- `image-hero`：大尺寸独立图片容器 + 相邻文字，禁止全屏出血或叠字。
- `image-side`：文字 + 侧图，适合竖图、截图、图表。
- `gallery`：3-6 张图网格。
- `table`：结构化表格。
- `kpi`：3-5 个核心数字。
- `quote`：一句观点或客户证言。
- `compare`：前后/左右方案对比。
- `timeline`：3-6 个阶段。
- `closing`：结尾、行动项、联系方式。

## 图片布局决策矩阵

显式 `<!-- image: id -->` 优先。无显式绑定时：

| 条件 | role | fit | 决策理由 |
| --- | --- | --- | --- |
| suggested_role=hero 且 weight=high | image-hero | contain | 高权重图用大容器完整展示，不作为背景 |
| aspect_ratio 接近 16:9 且 content_type=screenshot/photo | image-hero 或 two-column | contain | 横图适合大幅或半屏独立容器 |
| aspect_ratio 接近 9:16 | image-side | contain | 竖图需要侧栏保真 |
| aspect_ratio 接近 1:1 | gallery 或 image-side | contain | 方图适合克制卡片化 |
| content_type=chart/diagram | image-side 或 two-column | contain | 图表必须保真 |
| 3 张以上且共享 group_id | gallery | contain | 只组合有明确内容关系的图片 |

## 容量规则

- `bullets`：最多 6 条。
- `two-column`：每列最多 4 条。
- `gallery`：最多 6 图。
- `table`：最多 5 列 8 行。
- `timeline`：最多 6 节点。
- `kpi`：最多 5 项。
