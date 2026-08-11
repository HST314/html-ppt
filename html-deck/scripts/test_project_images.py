#!/usr/bin/env python3
"""项目图片布局规则回归：无关系拆页，有 group_id 才组合。"""
from build_ir import images_are_related, split_overflow_slides


def slide(images, role="gallery"):
    return {
        "role": role, "title": "项目图片完整展示支撑当前判断", "section": "证据",
        "blocks": [{"type": "paragraph", "text": "项目图片用于展示内容。"}],
        "images": images, "decision": "test", "takeaway": "结论", "notes": "说明" * 80,
    }


def main():
    unrelated = [{"id": "a", "alt": "A"}, {"id": "b", "alt": "B"}]
    assert not images_are_related(unrelated)
    split = split_overflow_slides([slide(unrelated)])
    assert len(split) == 2 and all(len(s["images"]) == 1 for s in split)
    related = [{"id": "a", "alt": "A", "group_id": "case-1"}, {"id": "b", "alt": "B", "group_id": "case-1"}]
    assert images_are_related(related)
    grouped = split_overflow_slides([slide(related)])
    assert len(grouped) == 1 and grouped[0]["role"] == "gallery"
    print("project image regression: ok")


if __name__ == "__main__":
    main()
