# ANIMATIONS

动画通过 `data-animate` 挂载，运行时只在当前页激活。按 B 键为静态降级，添加 `body.no-motion`。

## 目录

- `fade-up`：标题、正文从下方轻入。
- `stagger-list`：列表逐项进入。
- `count-up`：KPI 数字从 0 计数到目标值。
- `blur-in`：章节页或 quote 柔和显现。
- `kenburns`：hero 图片缓慢缩放。
- `slide`：翻页过渡。

## 降级策略

- `prefers-reduced-motion: reduce` 自动关闭动画。
- B 键切换静态模式。
- 打印模式关闭所有动画和阴影。
- QA 中如果动画遮挡内容，该页扣 10 分并建议去除动画。
