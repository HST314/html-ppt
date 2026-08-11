#!/usr/bin/env python3
"""叙事结构回归测试：目录强制存在，内容型尾页必须拆分。"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    deck = """# 无章节测试：验证目录与收束

### 已完成首轮验证并锁定核心判断
- 证据一
- 证据二
- 证据三

### 下一步行动已经明确
<!-- role: closing -->
- 确认负责人
- 确认日期
- 确认产物
"""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "deck.md").write_text(deck, encoding="utf-8")
        (base / "manifest.json").write_text('{"images": []}', encoding="utf-8")
        subprocess.run([
            sys.executable, str(ROOT / "scripts/build_ir.py"),
            "--deck", str(base / "deck.md"), "--manifest", str(base / "manifest.json"),
            "--output", str(base / "outline.json"), "--state", str(base / "state.json"),
        ], cwd=ROOT, check=True, capture_output=True, text=True)
        slides = json.loads((base / "outline.json").read_text(encoding="utf-8"))["slides"]
        assert slides[1]["role"] == "toc", "无章节输入也必须生成目录"
        assert slides[-1]["role"] == "closing", "最后一页必须是 closing"
        assert slides[-2]["role"] not in {"cover", "toc", "section", "closing"}, "尾页前必须有行动页"
        assert len(slides[-1]["blocks"]) <= 1 and not slides[-1]["takeaway"], "尾页必须低负载"
        assert any("moved to pre-closing" in s.get("decision", "") for s in slides), "内容型 closing 必须前移"
    print("narrative regression: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
