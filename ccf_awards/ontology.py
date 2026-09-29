"""Lossless award-name classification for award events."""

import re


CATEGORIES = {
    "paper": "最佳／杰出论文奖",
    "student": "学生论文奖",
    "impact": "经典／影响力奖",
    "recognition": "提名／亚军",
    "other": "其他／未标明奖项",
}


def classify_award(name):
    """Assign one of five broad labels; retain the official name separately."""
    value = re.sub(r"\s+", " ", name or "").strip().casefold()
    student = bool(re.search(r"student|doctoral|dissertation|学生|博士", value))
    if re.search(r"honou?rable mention|honou?rable|honorary mention|runner[- ]?up|second place|finalist|荣誉提名|亚军|入围", value):
        category = "recognition"
    elif re.search(r"test[- ]of[- ]time|classic paper|most influential|longuet.higgins|lasting impact|经典论文|影响力", value):
        category = "impact"
    elif student and re.search(r"paper|论文", value):
        category = "student"
    elif (re.search(r"best|outstanding|distinguished|最佳|优秀|杰出", value)
          and re.search(r"paper|论文", value)) or re.search(r"publisher['’]s prize", value):
        category = "paper"
    else:
        category = "other"
    return {"category": category, "category_label": CATEGORIES[category],
            "student_only": student}
