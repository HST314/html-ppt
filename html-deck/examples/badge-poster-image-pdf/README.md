# 徽章海报图片型演示复验项目

这是 `image-pdf` 路线的可复跑真实项目。`images/` 保存用户提供的 10 张原始素材及 manifest；`deck.md`、`outline.json`、`state/visual_blueprints.md` 是源文件；`dist/`、`state/image_pdf_render.json`、`state/qa_image_pdf.json` 是同一次运行产物。

从 `html-deck/` 执行：

```bash
python3 scripts/render_image_pdf.py \
  --ir examples/badge-poster-image-pdf/outline.json \
  --manifest examples/badge-poster-image-pdf/images/manifest.json \
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

新增路线自动化正反例：`python3 scripts/test_image_pdf.py`。
