#!/usr/bin/env python3
"""项目主题分类：判定 deck 项目属于哪一类主题域（domain），供背景风格选择、
目录页模板选择等下游环节复用，避免各自重新发明一套不一致的行业关键词表。

背景（TASK-040）：`project-changzheng8a`（航天徽章）与 `project-jixueyuan`
（高校学院介绍）内容完全不同，但生成的封面背景构图几乎一样。排查确认根因
是 `bg_styles.py::select_background_style()` 的关键词表没有区分"体裁词"
（决定"这是什么类型的文档"，如"学院/大学/揭牌"）与"话题词"（决定"讲的是
什么行业内容"，容易跨领域共享，如"系统/工程/芯片"），导致学院项目正文里的
技术性话题词反而盖过了真正决定文档类型的体裁词信号。

本脚本独立于背景风格库/目录模板库之外，先做一次"项目主题域"判定，把体裁词
和话题词分开计权（体裁词权重远高于话题词），产出机器可读、人类可审计的
判定结果，供后续两个环节直接消费，不需要各自重复踩同一个坑。

用法：
    python classify_theme_domain.py --deck deck.md --brief context/brief.md \
        --style state/style_report.json --output state/theme_domain.json

--brief 与 --style 均可选：--brief 缺省时只扫描 deck.md；--style 缺省或文件
不含可用的色彩量化字段时，量化评分环节全部记 0（不影响关键词判断，只是没有
可用的"打散"依据）。

输出 state/theme_domain.json 结构：
{
  "domain": "academic-institutional",
  "domain_label": "高校科研教育机构",
  "secondary_domain": null,               # 竞争激烈时的次选 domain，否则 null
  "confidence": "keyword-strong",         # keyword-strong / keyword-weak / quant-fallback
  "keyword_scores": {domain_key: 加权分, ...},
  "quant_scores": {domain_key: 加权分, ...},
  "total_scores": {domain_key: 加权分, ...},
  "trace": ["...可读推理链条..."],
  "illustration_recommended": false,
  "illustration_reason": "..."
}

分类体系定义、每个 domain 的体裁词/话题词表、权重设计说明见
references/THEME_DOMAINS.md（本文件是该文档描述的落地实现，改动任一侧都要
同步另一侧，避免文档与代码脱节——与 bg_styles.py/BACKGROUND_STYLES.md 的
既有约定同一个模式）。
"""
import argparse
import colorsys
import sys
from pathlib import Path

from common import read_json, write_json


# ─────────────────────────── 8 类主题域注册表 ───────────────────────────
# genre_keywords：体裁词（高优先级，决定"这是什么类型的文档"）
# topic_keywords：话题词（低优先级，决定"讲的是什么行业内容"，容易跨领域共享，
#                 仅在体裁词打平/全 0 时起区分作用，不单独决定结果）
DOMAIN_LIBRARY = {
    "aerospace-defense-tech": {
        "label": "航天军工/精密科技",
        "genre_keywords": ("火箭", "卫星", "发射", "星座", "徽章", "运载", "航天", "军工", "战机", "导弹", "舰艇", "太空"),
        "topic_keywords": ("轨道", "系统", "工程", "精密", "装备", "技术"),
        "default_illustration": False,
    },
    "academic-institutional": {
        "label": "高校科研教育机构",
        "genre_keywords": ("学院", "大学", "高校", "揭牌", "校训", "学科", "师资", "招生", "人才培养", "科研平台", "系所", "书院"),
        "topic_keywords": ("科研", "平台", "创新", "人才", "教育"),
        "default_illustration": False,
    },
    "corporate-professional": {
        "label": "企业咨询金融通用商务",
        "genre_keywords": ("咨询", "财报", "方案", "客户", "合规", "董事会"),
        "topic_keywords": ("战略", "增长", "市场", "团队", "商务"),
        "default_illustration": False,
    },
    "product-launch-design": {
        "label": "消费电子/品牌产品发布",
        "genre_keywords": ("发布", "品牌", "产品", "设计", "上市"),
        "topic_keywords": ("体验", "潮流", "极简", "旗舰", "卖点"),
        "default_illustration": False,
    },
    "cultural-heritage-formal": {
        "label": "历史文博档案出版",
        "genre_keywords": ("历史", "展览", "文物", "档案", "出版", "纪念"),
        "topic_keywords": ("藏品", "古籍", "博物馆", "考古", "民俗"),
        "default_illustration": False,
    },
    "cultural-heritage-warm": {
        "label": "传统技艺/非遗/温暖人文",
        "genre_keywords": ("匠人", "手作", "传承", "社区", "非遗"),
        "topic_keywords": ("温暖", "手工", "纸", "复古", "篆刻"),
        "default_illustration": True,
    },
    "consumer-lifestyle-future": {
        "label": "潮流/沉浸/科幻消费",
        "genre_keywords": ("科幻", "未来", "沉浸", "元宇宙", "潮流"),
        "topic_keywords": ("虚拟", "赛博", "光影", "电子", "炫彩"),
        "default_illustration": True,
    },
    "generic-fallback": {
        "label": "未命中/无法判定",
        "genre_keywords": (),
        "topic_keywords": (),
        "default_illustration": False,
    },
}

# 权重：体裁词单次命中 = 15 分，话题词单次命中 = 3 分。设计意图（TASK-040
# 核心修复目标）：一次体裁词命中就必须能压过多次话题词命中的噪音——5 次话题
# 词命中也只有 15 分，仅与 1 次体裁词命中打平、不会反超，从根上避免"技术话题
# 词盖过体裁词信号"的误判。
GENRE_WEIGHT = 15
TOPIC_WEIGHT = 3

# 量化特征单项加分上限（见 _quant_scores），确保任意 domain 的量化总分明显
# 小于一次体裁词命中（15 分），量化特征只能在关键词打平/全 0 时起区分作用。
_QUANT_STEP = 1.2

# 置信度判定：最高分 ≥ 次高分 × 该倍数才算"断层领先"
_STRONG_MARGIN_RATIO = 1.5


def parse_args():
    p = argparse.ArgumentParser(description="判定项目主题域（domain），供背景风格库/目录模板库复用。")
    p.add_argument("--deck", required=True, help="deck.md 路径")
    p.add_argument("--brief", required=False, help="context/brief.md 路径（可选）")
    p.add_argument("--style", required=False, help="state/style_report.json 或含等价 dna 字段的 art_dna.json 路径（可选）")
    p.add_argument("--output", required=True, help="输出 JSON 路径，通常为 state/theme_domain.json")
    return p.parse_args()


def _read_text(path):
    p = Path(path)
    if not p.exists():
        return "", False
    try:
        return p.read_text(encoding="utf-8"), True
    except Exception as exc:
        print(f"警告：读取 {path} 失败（{exc}），按空文本处理", file=sys.stderr)
        return "", False


# ─────────────────────────── 第一优先级：关键词判断 ───────────────────────────

def _keyword_hits(text):
    """逐 domain 统计体裁词/话题词命中次数（原始计数，未加权），
    返回 {domain_key: {"genre": {word: count}, "topic": {word: count}}}。"""
    hits = {}
    for key, spec in DOMAIN_LIBRARY.items():
        genre_hits = {w: text.count(w) for w in spec["genre_keywords"] if text.count(w) > 0}
        topic_hits = {w: text.count(w) for w in spec["topic_keywords"] if text.count(w) > 0}
        hits[key] = {"genre": genre_hits, "topic": topic_hits}
    return hits


def _keyword_scores(hits):
    """把原始命中计数按体裁词/话题词权重折算为每 domain 一个加权分。"""
    scores = {}
    for key, h in hits.items():
        genre_score = sum(h["genre"].values()) * GENRE_WEIGHT
        topic_score = sum(h["topic"].values()) * TOPIC_WEIGHT
        scores[key] = genre_score + topic_score
    return scores


# ─────────────────────────── 第二优先级：量化特征（仅打散/兜底） ───────────────────────────

def _hex_hue(hexcolor):
    h = (hexcolor or "").lstrip("#")
    if len(h) != 6:
        return None
    try:
        r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    except ValueError:
        return None
    hue, _s, _v = colorsys.rgb_to_hsv(r, g, b)
    return hue


def _is_warm_hue(hue):
    if hue is None:
        return None
    return hue < 0.14 or hue > 0.92


def _load_visual_stats(style_path):
    """从 --style 指向的 JSON 里尽量提取 saturation/contrast/warm 三个粗粒度
    信号；兼容 state/style_report.json（无量化字段，仅 accent 等）与
    state/art_dna.json（嵌套 dna.{saturation,contrast,palette,line_language}）
    两种真实存在的文件形态，都提取不到时返回全 None（quant 评分全部为 0，
    不影响关键词判断，只是没有可用的"打散"依据）。"""
    if not style_path:
        return {"saturation": None, "contrast": None, "warm": None}, "未提供 --style 参数"
    p = Path(style_path)
    if not p.exists():
        return {"saturation": None, "contrast": None, "warm": None}, f"--style 文件不存在：{style_path}"
    try:
        data = read_json(p)
    except Exception as exc:
        return {"saturation": None, "contrast": None, "warm": None}, f"--style 文件解析失败：{exc}"

    dna = data.get("dna") if isinstance(data.get("dna"), dict) else None
    if dna:
        palette = dna.get("palette") or []
        warm = _is_warm_hue(_hex_hue(palette[min(1, len(palette) - 1)])) if palette else None
        return {
            "saturation": dna.get("saturation"),
            "contrast": dna.get("contrast"),
            "warm": warm,
        }, f"从 {style_path} 的 dna 字段提取（palette/saturation/contrast/line_language 口径）"

    per_image = data.get("per_image") if isinstance(data.get("per_image"), dict) else None
    if per_image:
        sats = [v.get("saturation") for v in per_image.values() if isinstance(v.get("saturation"), (int, float))]
        lumas = [v.get("luma") for v in per_image.values() if isinstance(v.get("luma"), (int, float))]
        hues = [v.get("hue") for v in per_image.values() if isinstance(v.get("hue"), (int, float))]
        saturation = sum(sats) / len(sats) if sats else None
        # 无直接 contrast 字段时，用明度极差近似（同一 deck 内图片明度分布越
        # 分散，说明画面明暗对比语言越强），仅作粗略打散依据。
        contrast = (max(lumas) - min(lumas)) if len(lumas) >= 2 else None
        warm = _is_warm_hue(sum(hues) / len(hues)) if hues else None
        return {
            "saturation": saturation,
            "contrast": contrast,
            "warm": warm,
        }, f"从 {style_path} 的 per_image 字段聚合估算（style_report.json 无独立 saturation/contrast 统计，用图片级数据近似）"

    return {"saturation": None, "contrast": None, "warm": None}, f"{style_path} 未含可用的色彩量化字段（既无 dna 也无 per_image）"


def _quant_scores(stats):
    """基于粗粒度饱和度/对比度/暖色倾向给每个 domain 打小权重分，仅在关键词
    判断打平或全 0 时才可能影响最终选择（单项加分上限 _QUANT_STEP，多个
    domain 合计也远低于一次体裁词命中 15 分）。任一输入维度缺失（None）时，
    该维度对应的判据一律不加分（不臆造数据）。"""
    sat, contrast, warm = stats.get("saturation"), stats.get("contrast"), stats.get("warm")
    scores = {k: 0.0 for k in DOMAIN_LIBRARY}
    if sat is not None:
        if 0.4 <= sat <= 0.75:
            scores["aerospace-defense-tech"] += _QUANT_STEP
        if sat < 0.55:
            scores["academic-institutional"] += _QUANT_STEP
        if sat < 0.4:
            scores["corporate-professional"] += _QUANT_STEP
        if sat > 0.5:
            scores["product-launch-design"] += _QUANT_STEP
        if 0.3 <= sat <= 0.6:
            scores["cultural-heritage-formal"] += _QUANT_STEP
        if sat < 0.4:
            scores["cultural-heritage-warm"] += _QUANT_STEP
        if sat > 0.55:
            scores["consumer-lifestyle-future"] += _QUANT_STEP
    if contrast is not None:
        if contrast > 0.5:
            scores["aerospace-defense-tech"] += _QUANT_STEP
        if 0.3 <= contrast <= 0.6:
            scores["academic-institutional"] += _QUANT_STEP
        if contrast < 0.4:
            scores["corporate-professional"] += _QUANT_STEP
        if contrast > 0.45:
            scores["product-launch-design"] += _QUANT_STEP
        if 0.3 <= contrast <= 0.55:
            scores["cultural-heritage-formal"] += _QUANT_STEP
        if contrast < 0.35:
            scores["cultural-heritage-warm"] += _QUANT_STEP
        if contrast < 0.35:
            scores["consumer-lifestyle-future"] += _QUANT_STEP
    if warm is not None:
        if not warm:
            scores["aerospace-defense-tech"] += _QUANT_STEP
            scores["corporate-professional"] += _QUANT_STEP
        if warm:
            scores["cultural-heritage-formal"] += _QUANT_STEP
            scores["cultural-heritage-warm"] += _QUANT_STEP
    return scores


# ─────────────────────────── 综合判定 ───────────────────────────

def classify(deck_text, brief_text, visual_stats):
    combined_text = (deck_text or "") + "\n" + (brief_text or "")
    hits = _keyword_hits(combined_text)
    kw_scores = _keyword_scores(hits)
    quant_scores_all = _quant_scores(visual_stats)
    # generic-fallback 恒不参与量化打分（兜底项不应被量化特征"选中"，只应在
    # 关键词和量化都为 0 时，由下方显式兜底规则启用）。
    quant_scores_all["generic-fallback"] = 0.0

    total_scores = {k: kw_scores[k] + quant_scores_all[k] for k in DOMAIN_LIBRARY}

    kw_any_hit = any(v > 0 for k, v in kw_scores.items() if k != "generic-fallback")
    quant_any = any(v > 0 for k, v in quant_scores_all.items() if k != "generic-fallback")

    ranked = sorted(
        ((k, v) for k, v in total_scores.items() if k != "generic-fallback"),
        key=lambda kv: kv[1], reverse=True,
    )
    top_key, top_score = ranked[0]
    second_key, second_score = ranked[1] if len(ranked) > 1 else (None, 0.0)

    if not kw_any_hit and not quant_any:
        domain = "generic-fallback"
        confidence = "quant-fallback"
        secondary_domain = None
    elif not kw_any_hit:
        # 关键词全 0，完全靠量化特征决定
        domain = top_key if top_score > 0 else "generic-fallback"
        confidence = "quant-fallback"
        secondary_domain = second_key if second_score > 0 and second_score >= top_score * 0.5 else None
    else:
        domain = top_key
        if second_score > 0 and top_score >= second_score * _STRONG_MARGIN_RATIO:
            confidence = "keyword-strong"
        elif top_score >= GENRE_WEIGHT and second_score == 0:
            # 唯一有分数的 domain，天然断层领先
            confidence = "keyword-strong"
        else:
            confidence = "keyword-weak"
        secondary_domain = second_key if second_score > 0 and second_score >= top_score * 0.5 else None

    spec = DOMAIN_LIBRARY[domain]
    illustration_recommended = spec["default_illustration"]
    illustration_reason = f"domain（{domain}）默认建议" + ("插画" if illustration_recommended else "克制，不默认加插画")

    trace = _build_trace(hits, kw_scores, quant_scores_all, total_scores, visual_stats,
                          domain, confidence, top_score, second_key, second_score)

    return {
        "domain": domain,
        "domain_label": spec["label"],
        "secondary_domain": secondary_domain,
        "confidence": confidence,
        "keyword_scores": {k: round(v, 2) for k, v in kw_scores.items()},
        "quant_scores": {k: round(v, 2) for k, v in quant_scores_all.items()},
        "total_scores": {k: round(v, 2) for k, v in total_scores.items()},
        "trace": trace,
        "illustration_recommended": illustration_recommended,
        "illustration_reason": illustration_reason,
    }


def _build_trace(hits, kw_scores, quant_scores, total_scores, visual_stats,
                  domain, confidence, top_score, second_key, second_score):
    trace = []
    for key, h in hits.items():
        if not h["genre"] and not h["topic"]:
            continue
        parts = [f"{w}×{c}(体裁词)" for w, c in h["genre"].items()]
        parts += [f"{w}×{c}(话题词，已降权)" for w, c in h["topic"].items()]
        trace.append(f"[{key}/{DOMAIN_LIBRARY[key]['label']}] 关键词命中：" + "、".join(parts) +
                     f"  → 关键词加权分 {round(kw_scores[key], 2)}"
                     f"（体裁词×{GENRE_WEIGHT} + 话题词×{TOPIC_WEIGHT}）")
    if not any(v for k, v in kw_scores.items() if k != "generic-fallback"):
        trace.append("关键词命中：全部 domain 均为 0（deck.md + brief.md 未出现任何登记体裁词/话题词）")

    sat, contrast, warm = visual_stats.get("saturation"), visual_stats.get("contrast"), visual_stats.get("warm")
    trace.append(f"量化特征输入：saturation={sat}, contrast={contrast}, warm_hue={warm}")
    trace.append(f"量化特征评分（每项上限 {_QUANT_STEP}，仅供打散/兜底）：{ {k: round(v,2) for k,v in quant_scores.items() if v} or '全部为 0'}")
    trace.append(f"合成总分（关键词加权 + 量化打散）：{ {k: round(v,2) for k,v in total_scores.items()} }")

    if confidence == "keyword-strong":
        reason = f"最高分 {round(top_score,2)}（{domain}）"
        if second_key:
            reason += f" ≥ 次高分 {round(second_score,2)}（{second_key}）× {_STRONG_MARGIN_RATIO}，断层领先"
        else:
            reason += "，其余 domain 均为 0"
    elif confidence == "keyword-weak":
        reason = f"最高分 {round(top_score,2)}（{domain}）与次高分 {round(second_score,2)}（{second_key}）差距不足 {_STRONG_MARGIN_RATIO} 倍，存在竞争，建议人工复核"
    else:
        reason = "关键词命中全为 0，判定完全依赖量化特征（或量化也全为 0，退回 generic-fallback）"
    trace.append(f"选定：{domain}（{DOMAIN_LIBRARY[domain]['label']}），置信度 {confidence} —— {reason}")
    return trace


def main():
    args = parse_args()
    deck_text, deck_ok = _read_text(args.deck)
    if not deck_ok:
        print(f"错误：无法读取 --deck 指定的文件：{args.deck}", file=sys.stderr)
        sys.exit(2)
    brief_text = ""
    if args.brief:
        brief_text, brief_ok = _read_text(args.brief)
        if not brief_ok:
            print(f"警告：--brief 指定的文件读取失败，按无 brief 继续：{args.brief}", file=sys.stderr)

    visual_stats, stats_note = _load_visual_stats(args.style)

    result = classify(deck_text, brief_text, visual_stats)
    result["trace"].insert(0, f"扫描来源：deck={args.deck}" + (f"，brief={args.brief}" if args.brief else "，brief=未提供"))
    result["trace"].insert(1, f"量化特征来源：{stats_note}")

    write_json(args.output, result)
    print(f"主题域判定完成：{result['domain']}（{result['domain_label']}），置信度 {result['confidence']}；结果写入 {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
