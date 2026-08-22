# 徽章海报图片型演示复验项目

这是 `image-pdf` 路线的可复跑真实项目。`images/new-pack/` 保存 5 张项目原图，`descriptions/` 保存对应图片 MD 描述；`visual_language.json` 是从 MD 编译出的唯一视觉语言。`outline.json` 经绑定脚本整体替换旧元素语义后，生成 15 页 PDF、逐页图片和 QA v2.6 报告。

从 `html-deck/` 执行：

```bash
python3 scripts/extract_visual_language.py \
  --descriptions-dir examples/badge-poster-image-pdf/descriptions \
  --output examples/badge-poster-image-pdf/visual_language.json

python3 scripts/apply_visual_language.py \
  --ir examples/badge-poster-image-pdf/outline.json \
  --visual-language examples/badge-poster-image-pdf/visual_language.json \
  --output examples/badge-poster-image-pdf/outline.json

python3 scripts/render_image_pdf.py \
  --ir examples/badge-poster-image-pdf/outline.json \
  --manifest examples/badge-poster-image-pdf/images/manifest.json \
  --visual-language examples/badge-poster-image-pdf/visual_language.json \
  --output examples/badge-poster-image-pdf/dist/badge-poster.image.pdf \
  --slides-dir examples/badge-poster-image-pdf/dist/image-slides \
  --report examples/badge-poster-image-pdf/state/image_pdf_render.json \
  --strict-images

python3 scripts/qa_image_pdf.py \
  --pdf examples/badge-poster-image-pdf/dist/badge-poster.image.pdf \
  --ir examples/badge-poster-image-pdf/outline.json \
  --manifest examples/badge-poster-image-pdf/images/manifest.json \
  --render-report examples/badge-poster-image-pdf/state/image_pdf_render.json \
  --output examples/badge-poster-image-pdf/state/qa_image_pdf.json
```

完整回归（含 MD 语言契约、QA v2.6、既有四组同步攻击与新增四项终审门禁）：`python3 scripts/test_image_pdf.py`。
