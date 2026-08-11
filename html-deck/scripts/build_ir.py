#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path
from common import ROLES, load_state, save_state, write_json, read_json


def parse_args():
    p = argparse.ArgumentParser(description="Build SlidesPlan outline.json from deck.md and image manifest.")
    p.add_argument("--deck", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--brief", required=False)
    p.add_argument("--style", required=False, help="detect_style.py 产出的 style_report.json，用于主题推荐与封面背景")
    p.add_argument("--output", required=True)
    p.add_argument("--state", required=True)
    return p.parse_args()


def parse_md(text):
    title = None
    sections = []
    slides = []
    current_section = None
    current = None
    code = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            code = not code
        if not code and line.startswith("# "):
            title = line[2:].strip()
            continue
        if not code and line.startswith("## "):
            current_section = line[3:].strip()
            sections.append(current_section)
            continue
        if not code and line.startswith("### "):
            if current:
                slides.append(current)
            current = {"title": line[4:].strip(), "section": current_section, "raw": []}
            continue
        if current is not None:
            current["raw"].append(raw)
    if current:
        slides.append(current)
    return title or "Untitled Deck", sections, slides


def toc_entries(sections, md_slides):
    """目录必须存在；无二级章节时，从内容页标题提炼 3—6 个叙事节点。"""
    entries = [s for s in sections if s]
    if not entries:
        entries = [s["title"] for s in md_slides if directives(s["raw"])["role"] != "closing"]
    entries = entries[:6]
    if len(entries) < 3:
        defaults = ["建立共同判断", "展开关键证据", "确认下一步行动"]
        entries.extend(x for x in defaults if x not in entries)
    return entries[:6]


def blocks(raw_lines):
    out, para, table, code = [], [], [], []
    in_code = False
    for line in raw_lines:
        s = line.rstrip()
        if s.startswith("```"):
            if in_code:
                out.append({"type": "code", "text": "\n".join(code)})
                code = []
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        if not s:
            if para:
                out.append({"type": "paragraph", "text": " ".join(para)})
                para = []
            if table:
                out.append({"type": "table", "rows": table})
                table = []
            continue
        if s.startswith("<!--"):
            continue
        if s.startswith(">"):
            out.append({"type": "quote", "text": s.lstrip("> ").strip()})
        elif s.startswith("- ") or re.match(r"^\d+\.\s+", s):
            if para:
                out.append({"type": "paragraph", "text": " ".join(para)})
                para = []
            out.append({"type": "list_item", "text": re.sub(r"^(-|\d+\.)\s+", "", s)})
        elif "|" in s and s.strip().startswith("|"):
            table.append([c.strip() for c in s.strip("|").split("|")])
        else:
            para.append(s)
    if para:
        out.append({"type": "paragraph", "text": " ".join(para)})
    if table:
        out.append({"type": "table", "rows": table})
    return merge_lists(out)


def merge_lists(items):
    merged, acc = [], []
    for item in items:
        if item["type"] == "list_item":
            acc.append(item["text"])
        else:
            if acc:
                merged.append({"type": "list", "items": acc})
                acc = []
            merged.append(item)
    if acc:
        merged.append({"type": "list", "items": acc})
    return merged


def directives(raw):
    text = "\n".join(raw)
    role = re.search(r"<!--\s*role:\s*([a-z0-9-]+)\s*-->", text)
    image = re.findall(r"<!--\s*image:\s*([A-Za-z0-9_.-]+)\s*-->", text)
    theme = re.search(r"<!--\s*theme:\s*([a-z0-9-]+)\s*-->", text)
    notes = re.findall(r"<!--\s*notes:\s*(.*?)\s*-->", text)
    return {
        "role": role.group(1) if role else None,
        "images": image,
        "theme": theme.group(1) if theme else None,
        "notes": " ".join(notes),
    }


def pick_role(slide, assigned_images):
    d = directives(slide["raw"])
    if d["role"] in ROLES:
        return d["role"], "explicit role directive"
    bl = blocks(slide["raw"])
    if any(b["type"] == "table" for b in bl):
        return "table", "table block detected"
    if any(b["type"] == "quote" for b in bl):
        return "quote", "quote block detected"
    joined = "\n".join(slide["raw"])
    if re.search(r"时间线|里程碑|roadmap|timeline|Q[1-4]|202\d[-年]", joined, re.I):
        return "timeline", "timeline content detected"
    if re.search(r"对比|before|after|vs\.?|优势", joined, re.I):
        return "compare", "compare content detected"
    if assigned_images:
        if len(assigned_images) >= 3:
            return "gallery", "three or more images assigned"
        img = assigned_images[0]
        if img.get("suggested_role") == "hero" or img.get("weight") == "high":
            return "image-hero", "high weight or hero image metadata"
        return "image-side", "image metadata selected for side layout"
    if re.search(r"\d+[%x倍万亿千百]|\bKPI\b", "\n".join(slide["raw"]), re.I):
        return "kpi", "numeric KPI content detected"
    return "bullets", "default content role"


def action_title_issues(title):
    issues = []
    text = re.sub(r"\s+", "", title)
    if len(text) < 12:
        issues.append("action_title_too_short")
    if not re.search(r"\d|提升|下降|完成|验证|锁定|进入|减少|扩大|转化|发布|交付|超过|低于|打开|形成|支撑", title):
        issues.append("action_title_lacks_number_or_verb")
    if re.fullmatch(r"[\u4e00-\u9fffA-Za-z\s]{2,12}(概览|总结|介绍|背景|目录|方案|成果)?", title):
        issues.append("topic_title_detected")
    return issues


def infer_takeaway(title, bl, role):
    for b in bl:
        if b.get("type") == "paragraph" and len(b.get("text", "")) >= 18:
            return "So-what：" + b["text"][:52].rstrip("，。；") + "。"
        if b.get("type") == "list" and b.get("items"):
            return "So-what：" + b["items"][0][:52].rstrip("，。；") + "。"
    return f"So-what：本页用 {role} 证据支撑“{title[:28]}”，下一页继续展开方法或行动。"


def speaker_notes(title, bl, fallback):
    raw_points = []
    for b in bl:
        if b.get("type") == "paragraph":
            raw_points.append(b.get("text", ""))
        if b.get("type") == "list":
            raw_points.extend(b.get("items", [])[:3])
        if b.get("type") == "table":
            raw_points.append("表格里的目标、同比、合计或高亮行是本页的证据锚点。")
    points = "；".join(x for x in raw_points if x) or fallback
    note = (
        f"这一页先直接给出结论：{title}。讲的时候不要从组件开始解释，而是先把听众带到业务语境里，"
        f"说明为什么这个变化值得关注。关键证据包括：{points}。这些信息要按“目标、变化、原因、影响”的顺序讲，"
        "让客户能听出当前进展不是孤立数字，而是可以复用到下一阶段的经营判断。\n\n"
        "转场句：基于这个结论，下一页进入更具体的过程、证据或行动安排。"
    )
    return note[:300]


VISUAL_ROLES = {"kpi", "gallery", "image-hero", "image-side", "compare", "table", "two-column"}


def enrich_blocks(bl, role):
    enriched = list(bl)
    if role in VISUAL_ROLES:
        return enriched
    content_count = sum(1 for b in enriched if b.get("type") in {"paragraph", "list", "table", "quote", "code"})
    if content_count < 2:
        enriched.append({"type": "list", "items": ["目标对比：补充目标值、当前值与差距", "过程证据：说明关键动作与责任边界", "业务影响：落到客户可感知的结果"]})
        content_count += 1
    return enriched


def assign_images(slides, images):
    by_id = {i["id"]: i for i in images}
    used = set()
    result = []
    for slide in slides:
        d = directives(slide["raw"])
        chosen = []
        for img_id in d["images"]:
            if img_id in by_id:
                chosen.append(by_id[img_id])
                used.add(img_id)
        result.append(chosen)
    remaining = [i for i in images if i["id"] not in used]
    for idx, slide in enumerate(slides):
        if result[idx]:
            continue
        explicit_role = directives(slide["raw"])["role"]
        if explicit_role not in {None, "image-hero", "image-side", "gallery"}:
            continue
        title_text = (slide["title"] + " " + "\n".join(slide["raw"])).lower()
        scored = []
        for img in remaining:
            score = 0
            if img.get("weight") == "high":
                score += 3
            if img.get("suggested_role") == "hero":
                score += 2
            for tag in img.get("scene_tags", []):
                if str(tag).lower() in title_text:
                    score += 4
            if img.get("content_type") in title_text:
                score += 2
            scored.append((score, img))
        if scored and max(s for s, _ in scored) > 0:
            chosen = sorted(scored, key=lambda x: x[0], reverse=True)[0][1]
            result[idx] = [chosen]
            remaining.remove(chosen)
    unplaced = []
    for idx, img in enumerate(list(remaining)):
        if slides:
            target = min(len(slides) - 1, max(0, idx + 2))
            for probe in range(len(slides)):
                candidate = (target + probe) % len(slides)
                explicit_role = directives(slides[candidate]["raw"])["role"]
                if explicit_role in {None, "image-hero", "image-side", "gallery"}:
                    if result[candidate] and explicit_role != "gallery":
                        continue
                    target = candidate
                    break
            else:
                unplaced.append(img)
                continue
            result[target].append(img)
        else:
            unplaced.append(img)
    return result, unplaced


GALLERY_PAGE_SIZE = 6


def gallery_continuation(base_title, chunk, idx, total, section, note_seed):
    """为拆页产生的图集续页生成完整 slide 记录。"""
    title = f"{base_title}（证据图 {idx}/{total}）"
    bl = [{"type": "paragraph", "text": f"本页为同组场景证据的第 {idx}/{total} 页，与前后页共同构成完整证据链。"}]
    return {
        "page": None, "role": "gallery", "title": title, "section": section,
        "blocks": bl, "images": chunk,
        "takeaway": f"So-what：同组证据共 {total} 页，本页为第 {idx} 页，需结合前后页一起阅读。",
        "notes": speaker_notes(title, bl, note_seed),
        "decision": f"auto-split gallery part {idx}/{total}",
        "risk": risk_for(title, bl, chunk),
    }


def split_overflow_slides(slides):
    """超出组件容量的图片自动拆页，保证任何图片都不被渲染层截断。

    - gallery 超过 GALLERY_PAGE_SIZE 张：拆成多页，标题带“证据图 i/N”后缀。
    - image-hero / image-side / compare / two-column 只会渲染第一张图：
      多出的图片移入紧随其后的自动图集页。
    """
    out = []
    for s in slides:
        role = s.get("role")
        imgs = list(s.get("images", []))
        if role == "gallery" and len(imgs) > GALLERY_PAGE_SIZE:
            chunks = [imgs[i:i + GALLERY_PAGE_SIZE] for i in range(0, len(imgs), GALLERY_PAGE_SIZE)]
            total = len(chunks)
            for ci, chunk in enumerate(chunks):
                if ci == 0:
                    ns = dict(s)
                    ns["images"] = chunk
                    ns["title"] = f"{s['title']}（证据图 1/{total}）"
                    ns["decision"] = s.get("decision", "") + f" | auto-split gallery 1/{total}"
                    ns["risk"] = risk_for(ns["title"], ns.get("blocks", []), chunk)
                    out.append(ns)
                else:
                    out.append(gallery_continuation(s["title"], chunk, ci + 1, total, s.get("section"), "延续上一页图集，继续展示同组证据。"))
        elif role in {"image-hero", "image-side", "compare", "two-column"} and len(imgs) > 1:
            keep, rest = imgs[:1], imgs[1:]
            ns = dict(s)
            ns["images"] = keep
            ns["decision"] = s.get("decision", "") + f" | {len(rest)} overflow image(s) moved to gallery"
            ns["risk"] = risk_for(ns["title"], ns.get("blocks", []), keep)
            out.append(ns)
            chunks = [rest[i:i + GALLERY_PAGE_SIZE] for i in range(0, len(rest), GALLERY_PAGE_SIZE)]
            for ci, chunk in enumerate(chunks):
                out.append(gallery_continuation(s["title"], chunk, ci + 1, len(chunks), s.get("section"), "承接上一页未展示完的场景图片。"))
        else:
            out.append(s)
    return out


def closing_slide(deck_title):
    """生成只承担情绪回收与单一 CTA 的低负载尾页。"""
    echo = ""
    for sep in ("：", ":"):
        if sep in deck_title:
            echo = deck_title.split(sep, 1)[1].strip()
            break
    title = "让下一步从今天开始"
    bl = [{"type": "paragraph", "text": "感谢聆听｜现在确认第一项行动。"}]
    return {
        "page": None, "role": "closing", "title": title, "section": None,
        "blocks": bl, "images": [], "takeaway": "", "echo": echo or None,
        "notes": speaker_notes(title, bl, "用一句感谢和一个明确请求结束，不在尾页继续解释方案。"),
        "decision": "automatic low-load closing after decision page",
        "risk": {"level": "low", "issues": []},
    }


def enforce_ending(slides, deck_title):
    """把内容型 closing 降级为行动页，并保证最后一页是低负载 closing。"""
    normalized = []
    moved_explicit_closing = False
    for slide in slides:
        if slide.get("role") != "closing":
            normalized.append(slide)
            continue
        content_weight = len(slide.get("blocks", [])) + len(slide.get("images", []))
        if content_weight:
            action = dict(slide)
            action.update({
                "role": "bullets", "echo": None,
                "decision": (slide.get("decision") or "explicit closing") + " | moved to pre-closing decision page",
            })
            action["risk"] = risk_for(action.get("title", ""), action.get("blocks", []), action.get("images", []))
            normalized.append(action)
            moved_explicit_closing = True
    if not moved_explicit_closing:
        bl = [
            {"type": "list", "items": ["T+3 天确认试点范围与验收口径", "T+14 天锁定首批场景与数据看板", "T+30 天复盘并决定扩大范围"]},
            {"type": "paragraph", "text": "每项行动绑定负责人、日期与可检查产物。"},
            {"type": "paragraph", "text": "会后决策只保留范围、看板与复盘节奏三件事。"},
        ]
        title = "未来 30 天行动已压缩为 3 个检查点"
        normalized.append({
            "page": None, "role": "bullets", "title": title, "section": None,
            "blocks": bl, "images": [], "takeaway": "So-what：现在只需确认第一项行动的负责人和时间。",
            "notes": speaker_notes(title, bl, "把方案收束为可确认、可跟进、可复盘的行动。"),
            "decision": "automatic closing decision page", "risk": risk_for(title, bl, []),
        })
    normalized.append(closing_slide(deck_title))
    return normalized


def risk_for(title, bl, imgs):
    issues = []
    issues.extend(action_title_issues(title))
    if len(title) > 42:
        issues.append("title_too_long")
    for b in bl:
        if b["type"] == "list":
            if len(b["items"]) > 6:
                issues.append("too_many_bullets")
            if any(len(x) > 40 for x in b["items"]):
                issues.append("bullet_too_long")
        if b["type"] == "table":
            rows = [r for r in b["rows"] if not all(set(c) <= {"-", ":"} for c in r)]
            if rows and (len(rows[0]) > 5 or len(rows) > 9):
                issues.append("table_too_dense")
    if len(imgs) > 6:
        issues.append("too_many_images")
    content_blocks = sum(1 for b in bl if b.get("type") in {"paragraph", "list", "table", "quote", "code"})
    if content_blocks < 3:
        issues.append("content_blocks_below_3")
    return {"level": "high" if issues else "low", "issues": issues}


def main():
    args = parse_args()
    state = load_state(args.state)
    save_state(args.state, state, "build_ir:start")
    deck_text = Path(args.deck).read_text(encoding="utf-8")
    manifest = read_json(args.manifest)
    title, sections, md_slides = parse_md(deck_text)
    style_report = read_json(args.style) if args.style and Path(args.style).exists() else None
    image_groups, unplaced_images = assign_images(md_slides, manifest.get("images", []))
    cover_bg = None
    if style_report and style_report.get("cover_image_id"):
        cover_bg = next((i for i in manifest.get("images", []) if i.get("id") == style_report["cover_image_id"]), None)
    slides = [{"page": 1, "role": "cover", "title": title, "section": None, "blocks": [], "images": [], "bg_image": cover_bg, "takeaway": "", "notes": speaker_notes(title, [], "开场说明演示目标、对象与预期收获。"), "decision": "level-1 title becomes cover", "risk": {"level": "low", "issues": []}}]
    toc_items = toc_entries(sections, md_slides)
    toc_blocks = [{"type": "list", "items": toc_items}, {"type": "paragraph", "text": "目录先建立判断路径，再按证据与行动推进。"}]
    slides.append({"page": 2, "role": "toc", "title": f"{len(toc_items)} 个叙事节点从判断走向行动", "section": None, "blocks": toc_blocks, "images": [], "takeaway": "So-what：先让听众知道结论、证据和行动会怎样展开。", "notes": speaker_notes("目录建立完整叙事路径", toc_blocks, "用目录建立预期，控制节奏。"), "decision": "mandatory toc derived from sections or slide titles", "risk": {"level": "low", "issues": []}})
    last_section = None
    for md, imgs in zip(md_slides, image_groups):
        if md["section"] and md["section"] != last_section:
            slides.append({"page": len(slides) + 1, "role": "section", "title": md["section"], "section": md["section"], "section_index": len([s for s in slides if s["role"] == "section"]) + 1, "blocks": [], "images": [], "takeaway": "", "notes": speaker_notes(md["section"], [], "章节过渡。"), "decision": "new level-2 section", "risk": {"level": "low", "issues": []}})
            last_section = md["section"]
        bl = blocks(md["raw"])
        role, why = pick_role(md, imgs)
        bl = enrich_blocks(bl, role)
        d = directives(md["raw"])
        notes = d["notes"] or speaker_notes(md["title"], bl, "围绕本页标题展开，先讲结论再补充证据。")
        slides.append({"page": len(slides) + 1, "role": role, "title": md["title"], "section": md["section"], "blocks": bl, "images": imgs, "takeaway": infer_takeaway(md["title"], bl, role), "notes": notes, "decision": why, "risk": risk_for(md["title"], bl, imgs)})
    # 自动拆页：任何超出组件容量的图片拆成多页，渲染层不再截断图片
    slides = split_overflow_slides(slides)
    # 零遗漏兜底：无法匹配到任何内容页的图片自动汇入独立图集页
    if unplaced_images:
        chunks = [unplaced_images[i:i + GALLERY_PAGE_SIZE] for i in range(0, len(unplaced_images), GALLERY_PAGE_SIZE)]
        for ci, chunk in enumerate(chunks):
            utitle = f"清单内剩余场景图已自动汇入证据页（{ci + 1}/{len(chunks)}）"
            ubl = [{"type": "paragraph", "text": "以下场景图来自图片清单但未在正文中被显式引用，系统自动拆入本页以保证输入图片零遗漏。"}]
            slides.append({"page": None, "role": "gallery", "title": utitle, "section": last_section, "blocks": ubl, "images": chunk, "takeaway": f"So-what：本页收纳清单内未被引用的 {len(chunk)} 张场景图，可酌情保留或在定稿前删除。", "notes": speaker_notes(utitle, ubl, "说明这些图片自动汇入的原因，由演讲者决定去留。"), "decision": "unplaced images auto-collected into gallery", "risk": risk_for(utitle, ubl, chunk)})
    slides = enforce_ending(slides, title)
    # 拆页与汇入后统一重编页码
    for page_no, s in enumerate(slides, start=1):
        s["page"] = page_no
    plan = {"schema": "SlidesPlan", "version": "2.1", "narrative_framework": "customer_report", "title": title, "source": {"deck": args.deck, "manifest": args.manifest}, "theme_recommendation": (style_report or {}).get("recommended_theme", "business-dark"), "deck_style": (style_report or {}).get("deck_style"), "slides": slides}
    write_json(args.output, plan)
    save_state(args.state, state, "build_ir:done", "outline")
    print(f"Built {args.output} with {len(slides)} slides")
    return 0


if __name__ == "__main__":
    sys.exit(main())
