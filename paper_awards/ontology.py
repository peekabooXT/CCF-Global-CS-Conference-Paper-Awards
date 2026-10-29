"""Lossless award-name classification for award events."""
import re
CATEGORIES = {'paper': '最佳论文奖', 'student': '最佳学生论文奖', 'other': '其他获奖'}

def classify_award(name):
    """Apply JeffHuang-style scope to award names; keep source names unchanged."""
    value = re.sub('\\s+', ' ', name or '').strip().casefold()
    student = bool(re.search('student|doctoral|dissertation|学生|博士', value))
    excluded = re.search('honou?rable|honorary mention|runners?[- ]?ups?|second place|finalist|poster|demonstration|\\bdemo\\b|abstract|newcomer|short paper|brief paper|test[- ]of[- ]time|classic paper|most influential|longuet.higgins|lasting impact|10[- ]year|ten[- ]year|提名|亚军|入围|海报|演示|摘要|短论文|经典|影响力|十年', value)
    paper_award = re.search('\\b(best|outstanding|distinguished)\\b|最佳|优秀|杰出', value)
    is_paper = re.search('\\bpapers?\\b|论文', value)
    if excluded or not paper_award or (not is_paper):
        category = 'other'
    elif student:
        category = 'student'
    else:
        category = 'paper'
    return {'category': category, 'category_label': CATEGORIES[category], 'student_only': student}
