#!/usr/bin/env python3
"""生成 example-many 压力测试图片：13 张场景图 + manifest。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_example_assets import draw_image

SPECS = [
    ("mimg-001", "line-dashboard.png", 1920, 1080, "16:9", "screenshot", "hero", "high", ["产线", "看板"], "产线实时看板总览截图"),
    ("mimg-002", "line-a.png", 1600, 900, "16:9", "photo", "gallery", "medium", ["产线", "现场"], "一号产线现场照片"),
    ("mimg-003", "line-b.png", 1600, 900, "16:9", "photo", "gallery", "medium", ["产线", "现场"], "二号产线现场照片"),
    ("mimg-004", "line-c.png", 1400, 1400, "1:1", "photo", "gallery", "medium", ["产线", "现场"], "三号产线设备特写"),
    ("mimg-005", "alert-detail.png", 1600, 900, "16:9", "screenshot", "inline", "medium", ["看板", "异常"], "异常告警明细界面截图"),
    ("mimg-006", "gateway.png", 1200, 900, "4:3", "photo", "gallery", "low", ["设备", "网关"], "边缘网关安装现场"),
    ("mimg-007", "review-room.png", 1600, 1000, "16:10", "photo", "background", "high", ["复盘", "会议"], "产线复盘会议现场照片"),
    ("mimg-008", "response-trend.png", 1600, 900, "16:9", "chart", "inline", "high", ["数据", "响应"], "异常响应时长趋势图"),
    ("mimg-009", "mobile-inspect.png", 900, 1600, "9:16", "screenshot", "inline", "medium", ["移动端", "巡检"], "移动端巡检任务界面截图"),
    ("mimg-010", "quality-system.png", 1600, 900, "16:9", "screenshot", "inline", "medium", ["质检", "系统"], "质检系统批次管理界面"),
    ("mimg-011", "warehouse.png", 1600, 900, "16:9", "photo", "gallery", "medium", ["仓储", "现场"], "立体仓库现场照片"),
    ("mimg-012", "energy-meter.png", 1600, 900, "16:9", "photo", "gallery", "low", ["园区", "电表"], "园区电表箱照片"),
    ("mimg-013", "gate.png", 1600, 900, "16:9", "photo", "gallery", "low", ["园区", "大门"], "园区大门照片"),
]

PALETTE = [
    ("#101827", "#2f7d6d"), ("#18202f", "#c7653d"), ("#f8fafc", "#2d7a9f"),
    ("#111827", "#4dd4ac"), ("#1c2340", "#7a5fd0"), ("#fbf7f0", "#b1362f"),
    ("#0f1b2d", "#3d8fc7"), ("#231a2f", "#c75f9a"), ("#14201a", "#6aa84f"),
    ("#20242e", "#c7a23d"), ("#16202c", "#4fb3b8"), ("#2a1f1a", "#c7863d"),
    ("#1a2233", "#8f9fb8"),
]


def main():
    out = Path(__file__).resolve().parent / "images"
    out.mkdir(parents=True, exist_ok=True)
    images = []
    for idx, spec in enumerate(SPECS):
        img_id, file, w, h, ratio, ctype, role, weight, tags, desc = spec
        draw_image(out / file, w, h, img_id + " " + ctype, desc, PALETTE[idx])
        images.append({
            "id": img_id, "file": file, "alt": desc, "description": desc,
            "content_type": ctype, "width": w, "height": h, "aspect_ratio": ratio,
            "suggested_role": role, "scene_tags": tags, "weight": weight,
        })
    (out / "manifest.json").write_text(
        json.dumps({"version": "1.0", "images": images}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(out / "manifest.json")


if __name__ == "__main__":
    main()
