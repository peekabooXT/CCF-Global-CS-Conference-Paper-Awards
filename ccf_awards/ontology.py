"""Lossless award-name classification for award events."""

import re


CATEGORIES = {
    "paper": "最佳／杰出论文奖",
    "student": "学生论文奖",
    "impact": "经典／影响力奖",
}


def classify_award(name):
    """Assign one of three broad labels; retain the official name separately."""
    value = re.sub(r"\s+", " ", name or "").strip().casefold()
    student = bool(re.search(r"student|doctoral|dissertation|学生|博士", value))
    if re.search(r"test[- ]of[- ]time|classic paper|most influential|longuet.higgins|lasting impact|经典论文|影响力", value):
        category = "impact"
    elif student:
        category = "student"
    else:
        category = "paper"
    return {"category": category, "category_label": CATEGORIES[category],
            "student_only": student}
