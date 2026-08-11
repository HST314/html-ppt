# QA_RUBRIC

每页 100 分，低于 90 分进入修复循环。

| 项目 | 分值 | 阻断条件 |
| --- | ---: | --- |
| 无溢出/截断 | 20 | 标题、列表、表格、备注可见区外溢 |
| 图片保真与处理质感 | 15 | 缺图、拉伸、截图裸贴、无 caption bar |
| 字号层级与排版节奏 | 20 | 标题小于正文 2.2 倍；网格对齐混乱 |
| 信息密度达标 | 15 | 内容页少于 3 个内容块或缺少 takeaway |
| 主题辨识度 | 15 | signature 元素缺失，看起来只是换色 |
| 动画编排 | 10 | count-up、kenburns、stagger 等关键动效缺失或刺眼 |
| 对比度 | 5 | 前景/背景对比不足 |

## QA 模式

优先模式：Playwright 打开 HTML，逐页截图，检查 viewport、可见文本、图片自然尺寸与截图导出。

降级模式：无 Playwright 时做结构检查：
- HTML 无外链。
- slide 数等于 IR。
- 每页有标题或封面标题。
- 图片 alt、fit、src 均存在。
- 文本容量未超限。
- 内容页有 action title、takeaway、150 字以上 notes。
- 截图类图片出现 `screenshot-frame`，图片说明来自 manifest description。
- 不含绝对路径。

## 美学首因比对

Playwright 可用时，QA 必须输出逐页截图，并将当前 deck 与 `references/` 中记录的参考 skill 示例页做人工并排检查。以下情况直接判不合格：
- 第一屏缺少明确视觉焦点。
- 内容页截图单独看明显空洞。
- 主题 signature 元素不可见。
- 图片没有遮罩、说明条或截图美化处理。
- 动画先后顺序造成阅读干扰。

## 报告格式

`state/qa_history.jsonl` 每行：

```json
{"round":1,"page":3,"score":96,"mode":"structural-fallback","issues":[]}
```

`state/qa_report.md` 包含总分、逐页分、缺陷清单、下一步建议。
# Deck 级阻断门禁

- 第 2 页必须为目录；缺目录不得交付。
- 最后一页必须为 `closing`，且只允许一个标题、至多一个短句和一个 CTA；列表、表格、KPI、takeaway、多图均视为尾页过载。
- 倒数第 2 页必须为独立行动/决策页，不能是封面、目录、章节页或结束页。
- 所有清单图片必须在行动页之前完成展示，图片覆盖率必须为 100%。
