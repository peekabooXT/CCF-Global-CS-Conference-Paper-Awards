"""Lossless award-name classification for award events."""

import re


CATEGORIES = {
    "best": "最佳论文",
    "distinguished": "杰出论文",
    "outstanding": "优秀论文",
    "honorable_mention": "荣誉提名",
    "runner_up": "亚军 / 入围",
    "test_of_time": "时间检验 / 经典论文",
    "other": "其他原名奖项",
}


def classify_award(name):
    """Return an ontology label while retaining the unmodified official name."""
    value = re.sub(r"\s+", " ", name or "").strip().casefold()
    if re.search(r"honou?rable mention|honou?rable|honorary mention", value):
        category = "honorable_mention"
    elif re.search(r"runner[- ]?up|second place|finalist", value):
        category = "runner_up"
    elif re.search(r"test of time|classic paper|most influential|longuet.higgins|lasting impact", value):
        category = "test_of_time"
    elif "distinguished" in value:
        category = "distinguished"
    elif "outstanding" in value:
        category = "outstanding"
    elif "best" in value:
        category = "best"
    else:
        category = "other"
    return {"category": category, "category_label": CATEGORIES[category],
            "student_only": bool(re.search(r"student|doctoral|dissertation", value))}
