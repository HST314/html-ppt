# html-deck v2 迭代总结

## 修复反面清单

- 内容薄：新增 `references/NARRATIVE.md`，`build_ir.py` 输出 v2 IR；内容页强制 action title、至少 3 个内容块、`takeaway`、150-300 字演讲备注。示例客户汇报生成 18 页，产品发布生成 13 页。
- 视觉浅：新增 `assets/components/typography.css`，落地 7 档字号、12 列网格、发丝线、outline number、水印词、caption bar、takeaway bar。六套主题新增 signature 样式，不再只是换色。
- 动画少：`assets/animations/animations.css` 登记 12 个命名动画，覆盖 KPI count-up、hero kenburns、列表 stagger、timeline 点亮、compare 左右入场、表格逐行进入。
- 运行时弱：`assets/runtime/runtime.js` 支持 S 键独立演讲者窗口（BroadcastChannel 同步当前页/下一页/讲稿/计时器）、O 键缩略图总览、B 静态降级、F 全屏和深链接。

## 交付产物

- 客户汇报型 HTML：`example/dist/saas-2026-business-dark.single.html`
- 产品发布型 HTML：`example/dist/nebulaops-tech-dark.single.html`
- 客户汇报 QA：`example/state/saas_qa_report.md`，18 页，平均 100.0，失败 0 页。
- 产品发布 QA：`example/state/product_qa_report.md`，13 页，平均 100.0，失败 0 页。
- ADR：`ADR.md` 已新增“内容充实度与视觉表现 v2”章节，说明参考 skill 手法如何落地。

## QA 说明

当前运行环境未发现 Playwright 或本地 Chromium/Chrome，因此 `qa_render.py` 自动使用 `structural-fallback`。降级 QA 已覆盖离线外链、绝对路径、页数一致性、action title、takeaway、notes、信息密度、截图美化、caption 和关键动画。若目标环境安装 Playwright，同一命令会自动输出逐页截图到 `example/state/screenshots-*`。
