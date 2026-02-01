import json
import re
from typing import Any, Dict, List, Optional

import services.openai_client as openai_client

# 你可以按需要扩展/改名，但保持是 list[str]
UNITS = [
    "Unit 1: Primitive Types",
    "Unit 2: Using Objects",
    "Unit 3: Boolean Expressions and if Statements",
    "Unit 4: Iteration",
    "Unit 5: Writing Classes",
    "Unit 6: Array",
    "Unit 7: ArrayList",
    "Unit 8: 2D Array",
    "Unit 9: Inheritance",
    "Unit 10: Recursion",
]


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """
    尝试从模型输出中提取 JSON（兼容它前后夹杂说明文字的情况）
    """
    if not isinstance(text, str):
        return None
    text = text.strip()

    # 直接就是 JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # 从文本中抓最外层 { ... }
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None

    raw = m.group(0)
    try:
        return json.loads(raw)
    except Exception:
        # 再做一次简单清洗（去掉尾逗号）
        raw2 = re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            return json.loads(raw2)
        except Exception:
            return None


def generate_new_question(unit: str, topic: str = "", difficulty: str = "easy") -> str:
    """
    只生成题目（不包含答案/解析/正确选项），防止泄题。
    """
    topic = (topic or "").strip()
    difficulty = (difficulty or "easy").strip().lower()

    system = (
        "你是 AP CSA(Java) 出题官。只输出【题目本身】，绝对不要输出答案、解析、正确选项字母、标准答案。"
        "题目要像真实 AP CSA 练习：清晰、可作答、必要时给 Java 代码片段。"
        "如果是选择题，给 4 个选项 A/B/C/D，但不要标注正确答案。"
        "输出语言：中文为主，代码/关键术语用英文。"
    )

    user = f"""
请按以下要求生成 1 道题：
- Unit: {unit}
- Topic（可空）: {topic if topic else "（无）"}
- Difficulty: {difficulty}

硬性规则（必须遵守）：
1) 不要出现这些字眼：标准答案 / 正确答案 / 答案 / 解析
2) 不要在任何形式里泄漏正确选项（比如“正确的是B”）
3) 输出要简洁：题干 +（可选）代码 +（可选）选项
4) 题目必须可被判对错
"""

    q = openai_client.generate_text(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.7,
    )

    # 最后兜底过滤一次
    leak_words = ["标准答案", "正确答案", "答案：", "答案:", "解析", "正确的是", "正确选项"]
    if any(w in q for w in leak_words):
        # 如果模型违规，直接返回一个固定模板题，保证不会挂
        return (
            "【选择题】在 Java 中比较两个字符串内容是否相等，应该使用哪个方法？\n"
            "A. str1 == str2\n"
            "B. str1.equals(str2)\n"
            "C. str1.compareTo(str2) == 1\n"
            "D. str1.equalsIgnoreCase(str2)（忽略大小写）\n"
        )

    return q.strip()


def grade_and_extract_mistake(question: str, user_answer: str, unit_hint: str = "") -> Dict[str, Any]:
    """
    判题 + 给出正确答案 + 解析 + 错因类型 + 生成同错因练习（3题）
    返回 dict，供 app.py 使用。
    """
    system = (
        "你是 AP CSA(Java) 批改老师。你会根据题目和学生答案判断对错，并给出正确答案与解释。"
        "请严格输出 JSON（不要输出任何多余文字）。"
    )

    # 让模型输出结构化 JSON，避免你页面上直接泄题
    user = f"""
题目：
{question}

学生答案（可能是思路或最终答案）：
{user_answer}

unit_hint（可空）：
{unit_hint}

请输出严格 JSON，字段如下：
{{
  "is_correct": true/false,
  "correct_answer": "正确答案（若选择题写选项字母+简短理由；若开放题写关键结论/代码）",
  "explanation": "用中文解释：为什么对/错；点出关键考点",
  "mistake_type": "一句话总结错因（比如：String 比较方法/循环边界/引用与值/数组下标/构造器等）",
  "unit": "{unit_hint}",
  "topic": "从题目推断出的topic（可空）",
  "drills": [
    {{"q":"同错因练习题1（不要带答案/解析在题干）","a":"答案要点"}},
    {{"q":"同错因练习题2","a":"答案要点"}},
    {{"q":"同错因练习题3","a":"答案要点"}}
  ]
}}

注意：
- drills 里的 q 不要出现“标准答案/解析”字样
- 整体只输出 JSON（不要 markdown，不要解释文字）
"""

    raw = openai_client.generate_text(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
    )

    data = _extract_json(raw) or {}

    # 兜底补齐字段，避免 app.py KeyError
    result: Dict[str, Any] = {
        "is_correct": bool(data.get("is_correct", False)),
        "correct_answer": str(data.get("correct_answer", "")).strip(),
        "explanation": str(data.get("explanation", "")).strip(),
        "mistake_type": str(data.get("mistake_type", "")).strip(),
        "unit": str(data.get("unit", unit_hint)).strip(),
        "topic": str(data.get("topic", "")).strip(),
        "drills": data.get("drills", []) if isinstance(data.get("drills", []), list) else [],
    }

    # drills 兜底格式化
    drills_out: List[Dict[str, str]] = []
    for d in result["drills"][:3]:
        if isinstance(d, dict):
            drills_out.append(
                {"q": str(d.get("q", "")).strip(), "a": str(d.get("a", "")).strip()}
            )
    result["drills"] = drills_out

    return result
