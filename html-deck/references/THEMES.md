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
