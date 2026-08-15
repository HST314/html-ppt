# THEMES

所有主题只定义 token，不改变 DOM 结构。Agent 不得自由书写 hex；需要品牌适配时，把品牌倾向映射到最接近的 token。

## business-dark

客户汇报、销售成果、产品路线图默认主题。深背景、清晰高亮、适合大屏。

## business-light

正式报告、打印和白底会议屏。高对比黑白灰，配一个稳重强调色。

## tech-dark

技术分享、系统架构、数据平台。深色控制台感，但保留商务可读性。

## editorial

趋势洞察、行业观点、品牌故事。强调标题排版和图片叙事。

## warm-human

培训、组织沟通、客户成功案例。更温和的底色与人文照片友好。

## minimal-white

打印优先、法务/财务/高层审阅、信息密度高的文稿。结构克制，颜色少。

## token 约定

每个主题 CSS 必须提供：

- `--bg`、`--surface`、`--surface-2`
- `--text`、`--muted`、`--inverse`
- `--accent`、`--accent-2`、`--line`
- `--shadow`、`--radius`
- `--font-sans`、`--font-serif`、`--font-mono`
- `--slide-padding`、`--title-size`、`--body-size`

<!-- TASK-001: 新增——深色主题配色纪律(对标 baoyu-design / html-ppt-skill,结论见 BENCHMARK.md) -->
## 深色主题配色纪律

1. **背景色上限**:一套 deck 至多 1–2 种背景色;内容页共享同一 `--bg`,封面/尾页允许同色系加深变体,禁止每页换底。
2. **文字透明度阶梯**:深色底上的白色系文字只用 100%(正文)/ 72%(副题)/ 55%(说明)/ 45%(最弱可读档)四档,有效文字低于 45% 判 QA 失败(纯装饰水印除外)。
3. **accent 面反色文字**:accent(浅金/亮色)作为填充面时,其上文字必须使用 `--on-accent`(深墨,如 `#171106`),禁止白字压浅金(对比度仅约 2.4:1)。每个深色主题必须定义 `--on-accent`。
4. **token 派生,禁硬编码**:边框/阴影/光晕一律 `color-mix(in srgb, var(--accent) …)` 派生;主题文件内禁止出现与本主题无关的硬编码 hex/rgba(历史上 auto-derived 层残留异色边框/辉光即反面案例,必须清除)。
5. **双色分工**:accent = 强调与焦点(关键词、数据、焦点面);accent-2 = 结构与引导(编号、连接线、符号)。两色职责不交叉,禁止第三强调色。
