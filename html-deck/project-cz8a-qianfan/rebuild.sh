#!/bin/sh
# 一键重建：build_ir → 封面/尾页字段微调 → render → inline → audit → qa
# 用法：cd project-cz8a-qianfan && sh rebuild.sh
set -e
cd "$(dirname "$0")"
python3 ../scripts/build_ir.py --deck deck.md --manifest images/manifest.json --brief context/brief.md --style state/style_report.json --output outline.json --state state/run_state.json
python3 - <<'EOF'
import json
d = json.load(open('outline.json'))
cov = d['slides'][0]
cov['eyebrow'] = 'CZ-8A · QIANFAN CONSTELLATION'
cov['subtitle'] = '从一枚徽章，到一片星座——五种工艺，同一种航天精神'
cov['meta'] = ['5款纪念徽章', '5种工艺路线', '1次首飞部署任务']
clo = d['slides'][-1]
clo['eyebrow'] = 'EPILOGUE · 星辰大海'
clo['echo'] = '任务视觉纪念系列'
clo['echo_sub'] = 'CZ-8A · QIANFAN CONSTELLATION · MEMORIAL BADGE SERIES'
json.dump(d, open('outline.json','w'), ensure_ascii=False, indent=1)
EOF
python3 ../scripts/render_deck.py --ir outline.json --theme business-dark --art-dna state/art_dna.json --output dist/deck.html --state state/run_state.json
python3 ../scripts/inline_assets.py --html dist/deck.html --manifest images/manifest.json --mode inline --output dist/deck.single.html
python3 inject_toc.py
python3 ../scripts/audit_images.py --manifest images/manifest.json --html dist/deck.single.html --output state/image_coverage.md
python3 ../scripts/qa_render.py --html dist/deck.single.html --ir outline.json --output state/qa_report.md --history state/qa_history.jsonl --manifest images/manifest.json --art-dna state/art_dna.json
echo "REBUILD OK"
