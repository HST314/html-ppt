# 项目艺术 DNA 规范

仅在生成或审查封面、尾页背景时读取。

## 输入与输出

- 输入：`images/manifest.json` 中所有可读项目场景图或成品图；高权重图决定主视觉，其余图参与来源追踪。
- 输出：`state/art_dna.json` 与 cover/content/section/closing 四类同源 SVG 背景。
- 文字描述必须明确记录：特色主题颜色、线条方向、形状语言、构图重心、质感与留白、版式节奏、光影纹样、空间层次。

## 生成纪律

1. 从像素统计和边缘分布提取视觉事实，禁止仅依据项目行业名称猜测。
2. 全部页面共享同一艺术 DNA：封面展开、章节强化、内容页低权重铺陈、尾页镜像或变奏收束。
3. 保留标题侧安全留白；背景只承载视觉氛围，不嵌入正文。
4. 不得固定使用奖牌、圆环、光柱、科技网格等行业图形。只有输入图片确实支持时，才可由 DNA 参数自然产生相近语言。
5. 无可读图片时退出码非零；只有用户接受降级后，才使用基础主题装饰，并在 QA 报告标注 `art_dna=fallback`。

## 阻断检查

- `source_image_ids` 为空：失败。
- `art_expression` 缓漏任一维度：失败。
- 四类角色背景缺任一个，或 HTML 任一页没有项目视觉层：失败。（<!-- TASK-017 -->「HTML 任一页」含封面/尾页——TASK-017 撤销 TASK-015 的模板回退、恢复四类页面全核对，见文末说明）
- HTML 未内联两个背景或仍包含本地绝对路径：失败。
- 不同项目得到相同 `non_template_signature`：失败。

<!-- TASK-005: 新增 md 解读输入路径；以上像素提取规则逐字保留，未改动 -->
## 无像素输入：图片 md 解读路径

适用场景：项目没有可读图片（无法像素提取），但存在图片的 md 解读文档（如设计方向 candidate 的图文解读）。此时不得直接落入 `art_dna=fallback` 的裸模板降级，必须以 md 解读作为 art DNA 的视觉事实来源。

- 输入：项目图片 md 解读文档（一份或多份）。Agent 通读后按本规范同一组维度提取视觉事实：特色主题颜色、线条方向、形状语言、构图重心、质感与留白、版式节奏、光影纹样、空间层次。禁止仅依据项目行业名称猜测；每个维度必须能指回 md 解读中的原文描述。
- 清单落盘：Agent 将提取结果写成机器可读清单 `state/art_dna_md.json`，字段：`source_md_ids`（解读文档标识列表）、`dna`（`palette` 至少 3 个 hex 色、`line_language`（纵向生长/横向延展/均衡网格）、`light_focus`/`dark_focus`（九宫格 [x,y]，0–2）、`saturation`、`contrast`）、`art_expression`（覆盖全部 8 维度的文字描述）。
- 代码消费：运行 `scripts/art_dna_from_md.py --md-report state/art_dna_md.json --output state/art_dna.json --assets-dir dist/art`。清单缺任一维度时退出码非零并输出字段级修复清单；通过时生成与图片路径同风格的 cover/content/section/closing 四类同源 SVG 背景（同一套生成器），`art_dna.json` 附加 `source_mode="md"`。
- 生成纪律与图片路径一致：全部页面共享同一艺术 DNA（封面展开、章节强化、内容页低权重铺陈、尾页镜像或变奏收束）；保留标题侧安全留白；不得固定使用行业图形；QA 报告标注 `art_dna=md`。
- 只有既无可读图片、又无图片 md 解读时，才允许使用基础主题装饰降级，并在 QA 报告标注 `art_dna=fallback`。
- md 路径阻断检查：`source_md_ids` 为空失败；`art_expression` 缺任一维度失败；其余阻断检查与图片路径相同（`source_image_ids` 一项由 `source_md_ids` 替代）。

<!-- TASK-017: 首尾页方向更正说明 -->
## 首尾页生成式融合背景（TASK-017，取代 TASK-015 回退）

用户 19:42 v9 截图明确：首尾页目标版式 = 生成式融合背景路线（深藏蓝近黑基底、轨道圆环/横向轨迹线/星点融入背景、左下标题安全区、白标题+金副标题高对比、含动画），TASK-015 的模板经典版式回退（奖牌圆环+光柱）已撤销。自 TASK-017 起：

- 封面（cover）/尾页（closing）照常注入 project-art 生成背景（md 路径与图片路径一致）；经典 cover_deco/closing_deco 仅在无 art DNA 时作为降级方案。
- "融为一体"根因修复在渲染端配套 CSS 完成，不改背景生成行为：① 首尾页自带 `var(--bg)`（#06101d 深藏蓝近黑）实底，生成背景图叠在实底上，基底不被浅色舞台稀释；② 首尾页本地重声明 `--ho/--ho-deep/--ho-gold`，渐变标题按局部 accent（art DNA 金）重推导。
- QA「项目视觉 DNA 覆盖」门禁恢复 cover/content/section/closing 四类页面全核对（原范围，容差不变）。
