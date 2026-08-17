#!/usr/bin/env python3
"""按 SKILL.md「目录页(toc)模板调度逻辑」把 slide_templates/toc/toc-fluid-loop.html
替换占位符后注入 deck.single.html 的第 2 页（role-toc），替代默认目录渲染。

调度口径：
- 条目数 6 ∈ 5–6 区间，按 deck 深空航天视觉风格选 toc-fluid-loop（流体闭环发散式）。
- 6 节点取六边形对称槽位 pos-1/2/4/5/6/8，删除 pos-3/pos-7 节点及其 data-link 连线与圆点。
- 仅按主题改 :root 变量（作用域收敛为 .toc-stage，避免污染 deck 全局 token）；
  保留模板全部布局、异形容器、渐变描边与曲线连线。
- 保留该页 project-art-frame 背景层（QA 门禁：每页项目视觉层计数）与 aside.notes。
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT.parent.parent / "slide_templates" / "toc" / "toc-fluid-loop.html"
DECK = ROOT / "dist" / "deck.single.html"

MAIN_TITLE = "任务视觉纪念系列"
ITEMS = {
    1: ("01", "序章与系列总览", "系列数据与五款阵列总览"),
    2: ("02", "作品深读", "五款徽章工艺与象征逐一深读"),
    3: ("03", "任务纪实", "火箭星座技术与发射时序"),
    4: ("04", "工艺解码", "五种工艺路线同台对比"),
    5: ("05", "收藏生态", "限量编号与数字收藏延伸"),
    6: ("06", "未来回望", "里程碑链路与三项行动"),
}
# 章节 → 槽位（六边形对称：上、右上、右下、下、左下、左上）
SLOT_OF = {1: 1, 2: 2, 3: 4, 4: 5, 5: 6, 6: 8}
DROP_SLOTS = [3, 7]

# 深空主题改色（仅 :root 变量，作用域 .toc-stage；配色映射 deck 主题 token：金 #f4c95d / 蓝 #3d7bfa）
THEME_VARS = """.toc-stage {
    --bg: rgba(8, 12, 26, 0.84);
    --ink: #eef4ff;
    --ink-soft: #a8bde0;
    --accent-1: #3d7bfa;
    --accent-2: #f4c95d;
    --accent-3: #12406e;
    --card-bg: rgba(15, 24, 46, 0.90);
    --line: rgba(244, 201, 93, 0.38);
  }"""


def main():
    tpl = TEMPLATE.read_text(encoding="utf-8")

    # 1) 取模板 <style> 与 .stage 主体
    style = re.search(r"<style>(.*?)</style>", tpl, re.S).group(1)
    stage = re.search(r'(<div class="stage">.*?</div>)\s*</body>', tpl, re.S).group(1)

    # 2) 占位符替换
    stage = stage.replace("{{toc_main_title}}", MAIN_TITLE)
    for n, (num, title, desc) in ITEMS.items():
        slot = SLOT_OF[n]
        # 逐槽位处理：该槽位的节点块内替换 item_XX 占位符为第 n 章内容
        node_re = re.compile(
            r'<section class="toc-node pos-%d">.*?</section>' % slot, re.S)
        m = node_re.search(stage)
        node = m.group(0)
        node = (node.replace("{{item_%02d_num}}" % slot, num)
                    .replace("{{item_%02d_title}}" % slot, title)
                    .replace("{{item_%02d_desc}}" % slot, desc))
        stage = stage[:m.start()] + node + stage[m.end():]

    # 3) 删除未用槽位节点 + 对应 SVG 连线/圆点
    for slot in DROP_SLOTS:
        stage = re.sub(r'\s*<section class="toc-node pos-%d">.*?</section>' % slot,
                       "", stage, flags=re.S)
        stage = re.sub(r'\s*<path data-link="%d"[^/]*/>' % slot, "", stage)
    # 圆点：pos-3 → (1090,360)，pos-7 → (190,360)
    stage = stage.replace('<circle cx="1090" cy="360" r="5"/>', "")
    stage = stage.replace('<circle cx="190" cy="360" r="5"/>', "")

    assert "{{" not in stage, "占位符未清零"

    # 4) 样式作用域收敛 + 深空改色 + 舞台适配 slide
    style = re.sub(r":root \{.*?\}", THEME_VARS, style, count=1, flags=re.S)
    assert ".toc-stage {" in style and "--accent-2: #f4c95d" in style, "主题变量替换失败"
    style = style.replace("* { margin: 0; padding: 0; box-sizing: border-box; }",
                          ".toc-stage, .toc-stage * { margin: 0; padding: 0; box-sizing: border-box; }")
    style = re.sub(r"body \{.*?}\n", "", style, flags=re.S)  # 模板 body 规则在 deck 内无意义
    style += """
  /* TASK-022: toc 模板接入 deck——toc 页整页铺放，保留 art 背景层透出 */
  .slide.role-toc { padding: 0; }
  .toc-stage { position: absolute; inset: 0; z-index: 2; }
  .toc-stage .stage { width: 100%; height: 100%; }
  .toc-stage .hub { box-shadow: 0 1.2cqw 3cqw rgba(18, 64, 110, 0.55); }
  .toc-stage .toc-node { box-shadow: 0 0.8cqw 2cqw rgba(0, 0, 0, 0.45); }

  /* TASK-004 fix: 打印（PDF）路径不支持 mask-composite 渐变描边，::before 会整卡铺满渐变
     导致近白文字不可读；打印时退回实色细边框，恢复深色卡片底与文字对比度（屏幕端不变） */
  @media print {
    .toc-stage .toc-node::before {
      background: none;
      -webkit-mask: none;
              mask: none;
      border: 2px solid var(--accent-2);
      border-radius: inherit;
      padding: 0;
    }
  }
"""

    # 5) 注入 deck.single.html 的 role-toc 页
    deck = DECK.read_text(encoding="utf-8")
    sec_re = re.compile(r'(<section class="slide role-toc".*?</section>)', re.S)
    m = sec_re.search(deck)
    assert m, "未找到 role-toc 页"
    sec = m.group(1)
    art = re.search(r'<div class="project-art-frame">.*?</div>', sec, re.S)
    notes = re.search(r'<aside class="notes">.*?</aside>', sec, re.S)
    assert art and notes, "toc 页缺 art 层或 notes"
    open_end = sec.index(">") + 1
    new_sec = (sec[:open_end] + art.group(0)
               + '<div class="toc-stage">' + stage + "</div>"
               + notes.group(0) + "</section>")
    deck = deck[:m.start()] + new_sec + deck[m.end():]

    # 6) toc 样式注入 <head>（幂等：先清旧块）
    deck = re.sub(r"<style id=\"toc-template-css\">.*?</style>\n?", "", deck, flags=re.S)
    deck = deck.replace("</head>",
                        '<style id="toc-template-css">' + style + "</style>\n</head>", 1)

    assert deck.count('class="project-art-bg') >= 22, "项目视觉层计数不足"
    DECK.write_text(deck, encoding="utf-8")
    print("toc injected:", DECK)


if __name__ == "__main__":
    sys.exit(main())
