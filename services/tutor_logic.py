import json
import re
from typing import Any, Dict, List, Optional, Tuple

import services.openai_client as openai_client

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


# -----------------------------
# Utilities
# -----------------------------
def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出里尽量提取 JSON（兼容前后夹杂文字）"""
    if not isinstance(text, str):
        return None
    s = text.strip()

    # 直接就是 JSON
    try:
        return json.loads(s)
    except Exception:
        pass

    # 抓最外层 { ... }
    m = re.search(r"\{.*\}", s, flags=re.S)
    if not m:
        return None
    raw = m.group(0)

    # 去掉尾逗号等轻微清洗
    raw2 = re.sub(r",\s*([}\]])", r"\1", raw)
    try:
        return json.loads(raw2)
    except Exception:
        return None


def _normalize_user_answer(ans: str) -> Dict[str, Optional[str]]:
    """
    用户答案可能是：'C' / 'c' / '7' / 'x=7' / '选C' / '答案是C' 等
    这里做简单归一化：提取 letter(A-D) 和 number(int)（如有）
    """
    s = (ans or "").strip()
    low = s.lower()

    # 提取字母选项
    letter = None
    m = re.search(r"\b([a-dA-D])\b", s)
    if m:
        letter = m.group(1).upper()
    else:
        # 兼容“选C”“答案C”
        m2 = re.search(r"([a-dA-D])", s)
        if m2:
            letter = m2.group(1).upper()

    # 提取整数
    num = None
    m3 = re.search(r"-?\d+", s)
    if m3:
        num = m3.group(0)

    return {"raw": s, "letter": letter, "num": num, "low": low}


def _parse_mcq_options(question: str) -> Dict[str, Dict[str, Any]]:
    """
    从题目文本里解析 A/B/C/D 选项。
    支持格式：
      A. 3
      B) 5
      C：7
    返回：
      {
        "A": {"text": "3", "int": 3},
        ...
      }
    """
    opts: Dict[str, Dict[str, Any]] = {}

    if not isinstance(question, str):
        return opts

    lines = question.splitlines()
    for line in lines:
        # 允许 A. / A) / A： / A: 等
        m = re.match(r"^\s*([A-Da-d])\s*[\.\)\:\：]\s*(.+?)\s*$", line)
        if not m:
            continue
        key = m.group(1).upper()
        text = m.group(2).strip()

        # 如果选项是纯整数（或开头就是整数），提取
        mi = re.match(r"^\s*(-?\d+)\s*$", text)
        intval = int(mi.group(1)) if mi else None

        opts[key] = {"text": text, "int": intval}

    return opts


def _try_eval_simple_java_int_expression(question: str) -> Optional[int]:
    """
    仅处理非常简单的 Java 形式（用于兜底纠错）：
      int x = <int>;
      x = <expr containing x, ints, + - * / ( ) >;
    返回最终 x 值；无法解析则返回 None。

    例：
      int x = 5;
      x = x + 3 * 2 - 4;
    """
    if not isinstance(question, str):
        return None

    # 提取初始 x
    m1 = re.search(r"\bint\s+x\s*=\s*(-?\d+)\s*;", question)
    if not m1:
        return None
    x0 = int(m1.group(1))

    # 提取赋值表达式：x = ...
    # 允许有空格/换行，但只取到分号前
    m2 = re.search(r"\bx\s*=\s*([^\n;]+)\s*;", question)
    if not m2:
        return None
    expr = m2.group(1).strip()

    # 只允许安全字符（避免 eval 风险）
    if not re.fullmatch(r"[0-9xX+\-*/\s()]+", expr):
        return None

    # 替换 x
    expr_py = re.sub(r"\b[xX]\b", str(x0), expr)

    try:
        # 仅数值表达式，禁用 builtins
        val = eval(expr_py, {"__builtins__": {}}, {})
        # Java int 除法是整除；但这里用 Python 的 / 会变 float
        # 所以我们要求题目里如果有除法，尽量用 / 但我们做整除修正：
        # 简化做法：若出现 '/', 使用 Python 的 '//' 重新算一次
        if "/" in expr_py:
            expr_py2 = expr_py.replace("/", "//")
            val = eval(expr_py2, {"__builtins__": {}}, {})
        return int(val)
    except Exception:
        return None


def _build_math_explanation(question: str, expected: int) -> str:
    """
    给简单表达式题生成一个可靠解释（不依赖模型）
    """
    # 尝试提取表达式，做一份简短解释
    m2 = re.search(r"\bx\s*=\s*([^\n;]+)\s*;", question)
    expr = m2.group(1).strip() if m2 else ""
    return (
        "按运算优先级：先乘除、再加减（同级从左到右）。\n"
        f"题目表达式：x = {expr}\n"
        f"最终结果：x = {expected}"
    )


def _llm_explain_and_drills(question: str, expected: str, user_answer: str, unit_hint: str) -> Dict[str, Any]:
    """
    让模型只做“解释 + 错因 + 同错因练习”，并要求 JSON 输出。
    """
    system = (
        "你是AP CSA(Java)批改老师。你只负责：解释、错因、生成同错因练习。"
        "正确答案由系统提供，你不得修改。只输出严格JSON。"
    )

    user = f"""
题目：
{question}

系统计算的正确答案（不要改）：
{expected}

学生答案：
{user_answer}

unit_hint：
{unit_hint}

请输出严格 JSON：
{{
  "explanation": "中文解释，点出考点，简洁",
  "mistake_type": "一句话错因标签（如：运算优先级/String比较/循环边界等）",
  "topic": "推断topic（可空）",
  "drills": [
    {{"q":"同错因练习题1（题干不要出现答案/解析字样）","a":"答案要点"}},
    {{"q":"同错因练习题2","a":"答案要点"}},
    {{"q":"同错因练习题3","a":"答案要点"}}
  ]
}}
只输出 JSON，不要多余文字。
"""

    raw = openai_client.generate_text(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
    )
    data = _extract_json(raw) or {}

    # 兜底格式
    drills_out: List[Dict[str, str]] = []
    drills = data.get("drills", [])
    if isinstance(drills, list):
        for d in drills[:3]:
            if isinstance(d, dict):
                drills_out.append(
                    {"q": str(d.get("q", "")).strip(), "a": str(d.get("a", "")).strip()}
                )

    return {
        "explanation": str(data.get("explanation", "")).strip(),
        "mistake_type": str(data.get("mistake_type", "")).strip(),
        "topic": str(data.get("topic", "")).strip(),
        "drills": drills_out,
    }


# -----------------------------
# Public API used by app.py
# -----------------------------
def generate_new_question(unit: str, topic: str = "", difficulty: str = "easy") -> str:
    """
    只生成题目（不包含答案/解析/正确选项字母），防止泄题。
    """
    topic = (topic or "").strip()
    difficulty = (difficulty or "easy").strip().lower()

    system = (
        "你是 AP CSA(Java) 出题官。只输出【题目本身】，绝对不要输出答案、解析、正确选项字母、标准答案。"
        "如果是选择题，给 4 个选项 A/B/C/D，但不要标注正确答案。"
        "输出语言：中文为主，代码/关键术语用英文。"
    )

    user = f"""
请按以下要求生成 1 道题：
- Unit: {unit}
- Topic（可空）: {topic if topic else "（无）"}
- Difficulty: {difficulty}

硬性规则（必须遵守）：
1) 不要出现：标准答案 / 正确答案 / 答案 / 解析
2) 不要以任何形式泄漏正确选项
3) 输出简洁：题干 +（可选）代码 +（可选）选项
"""

    q = openai_client.generate_text(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.7,
    )

    # 最后兜底过滤一次
    leak_words = ["标准答案", "正确答案", "答案：", "答案:", "解析", "正确的是", "正确选项"]
    if any(w in q for w in leak_words):
        return (
            "【选择题】在 Java 中，下列哪一项最准确描述了运算优先级？\n"
            "A. 加减先于乘除\n"
            "B. 乘除先于加减\n"
            "C. 从右到左依次计算\n"
            "D. 所有运算同优先级\n"
        )

    return q.strip()


def grade_and_extract_mistake(question: str, user_answer: str, unit_hint: str = "") -> Dict[str, Any]:
    """
    判题 + 给正确答案 + 解释 + 错因类型 + 同错因练习（3题）
    核心：能用规则算的题，优先规则算（防止模型胡判）。
    """
    # 0) 尝试解析“简单算术表达式题”
    expected_val = _try_eval_simple_java_int_expression(question)
    opts = _parse_mcq_options(question)  # 解析 A/B/C/D

    # 默认返回结构
    result: Dict[str, Any] = {
        "is_correct": False,
        "correct_answer": "",
        "explanation": "",
        "mistake_type": "",
        "unit": (unit_hint or "").strip(),
        "topic": "",
        "drills": [],
    }

    ua = _normalize_user_answer(user_answer)

    # 1) 如果能算出 expected_val：走“强校验路径”
    if expected_val is not None:
        correct_option = None
        # 若选项存在且是纯整数，找到匹配的选项字母
        for k, v in opts.items():
            if v.get("int", None) == expected_val:
                correct_option = k
                break

        # 生成正确答案展示
        if correct_option:
            result["correct_answer"] = f"{correct_option} ({expected_val})"
        else:
            result["correct_answer"] = str(expected_val)

        # 判断用户是否正确：优先比字母，其次比数字
        ok = False
        if correct_option and ua["letter"]:
            ok = (ua["letter"] == correct_option)
        elif ua["num"] is not None:
            ok = (int(ua["num"]) == expected_val)

        result["is_correct"] = ok

        # 解释：先用稳定解释，再让模型补充（模型补充失败也不影响）
        stable_explain = _build_math_explanation(question, expected_val)
        result["explanation"] = stable_explain
        result["mistake_type"] = "运算优先级/表达式计算"
        result["topic"] = "operator precedence"

        try:
            enrich = _llm_explain_and_drills(
                question=question,
                expected=result["correct_answer"],
                user_answer=user_answer,
                unit_hint=unit_hint,
            )
            # 模型解释如果是空就别覆盖稳定解释
            if enrich.get("explanation"):
                result["explanation"] = enrich["explanation"]
            if enrich.get("mistake_type"):
                result["mistake_type"] = enrich["mistake_type"]
            if enrich.get("topic"):
                result["topic"] = enrich["topic"]
            if enrich.get("drills"):
                result["drills"] = enrich["drills"]
        except Exception:
            # 模型挂了也不影响判题正确性
            result["drills"] = [
                {"q": "计算：int x=2; x = x + 4*3 - 5; 最终 x 是多少？", "a": "先算 4*3=12；2+12-5=9"},
                {"q": "计算：int x=10; x = x - 6/2 + 1; 最终 x 是多少？（注意整除）", "a": "6/2=3；10-3+1=8"},
                {"q": "下列哪条规则正确？", "a": "乘除优先于加减；同级从左到右"},
            ]

        return result

    # 2) 否则：走“模型判题路径”，但强制 JSON + 兜底纠偏
    system = (
        "你是AP CSA(Java)批改老师。请根据题目与学生答案判断对错，并给出正确答案与解释。"
        "必须只输出严格JSON，不要输出任何其他文字。"
    )

    user = f"""
题目：
{question}

学生答案：
{user_answer}

unit_hint：
{unit_hint}

请输出严格 JSON：
{{
  "is_correct": true/false,
  "correct_answer": "正确答案（若选择题写'选项字母 (值/要点)'；若开放题写关键结论/代码）",
  "explanation": "中文解释：为什么对/错；点出考点；简洁",
  "mistake_type": "一句话总结错因",
  "topic": "推断topic（可空）",
  "drills": [
    {{"q":"同错因练习题1（题干不要出现答案/解析字样）","a":"答案要点"}},
    {{"q":"同错因练习题2","a":"答案要点"}},
    {{"q":"同错因练习题3","a":"答案要点"}}
  ]
}}
只输出 JSON。
"""

    raw = openai_client.generate_text(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
    )
    data = _extract_json(raw) or {}

    # 兜底组装
    result["is_correct"] = bool(data.get("is_correct", False))
    result["correct_answer"] = str(data.get("correct_answer", "")).strip()
    result["explanation"] = str(data.get("explanation", "")).strip()
    result["mistake_type"] = str(data.get("mistake_type", "")).strip()
    result["topic"] = str(data.get("topic", "")).strip()

    drills_out: List[Dict[str, str]] = []
    drills = data.get("drills", [])
    if isinstance(drills, list):
        for d in drills[:3]:
            if isinstance(d, dict):
                drills_out.append(
                    {"q": str(d.get("q", "")).strip(), "a": str(d.get("a", "")).strip()}
                )
    result["drills"] = drills_out

    # 3) 最后兜底：如果题目里有明显的 A/B/C/D + 数值，并且用户填的是字母/数值，
    #    但模型 correct_answer 看起来不靠谱，我们至少不让它自相矛盾太离谱。
    #    （这里不强行覆盖，因为我们没算出 expected_val；只做轻度修正）
    if opts and ua["letter"] and ua["letter"] in opts and not result["correct_answer"]:
        # 至少补上“用户选了啥”
        result["correct_answer"] = "（系统未能解析正确选项，请查看解析）"

    return result
