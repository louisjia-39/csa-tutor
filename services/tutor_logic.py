import json
from services.openai_client import generate_text

UNITS = [
    "Unit1 Java基础", "Unit2 控制结构", "Unit3 面向对象",
    "Unit4 数组", "Unit5 继承与多态", "Unit6 递归"
]

def grade_and_extract_mistake(question: str, user_answer: str, unit_hint: str = ""):
    system = (
        "你是AP CSA(Java)家教。你必须：\n"
        "1) 先判断学生答案是否正确；2) 给出正确答案；3) 用最短步骤解释；\n"
        "4) 识别错误类型(mistake_type)，例如：概念混淆/边界条件/循环次数/引用与值/数组下标/递归出口/OOP构造器等；\n"
        "5) 生成3道“同错因”针对练习题(drills)，每题附标准答案(a)。\n"
        "输出严格JSON："
        '{is_correct:boolean, correct_answer:string, explanation:string, mistake_type:string, unit:string, topic:string, drills:[{q:string,a:string},{q:string,a:string},{q:string,a:string}]}\n'
        f"unit必须从{UNITS}中选或用{unit_hint}最接近的。"
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"题目：{question}\n学生答案：{user_answer}\nunit提示：{unit_hint}".strip()},
    ]
    text = generate_text(messages, temperature=0.2)

    try:
        data = json.loads(text)
        return data
    except Exception:
        return {
            "is_correct": None,
            "correct_answer": "",
            "explanation": text,
            "mistake_type": "unknown",
            "unit": unit_hint or "",
            "topic": "",
            "drills": []
        }

def generate_new_question(unit: str, topic: str = "", difficulty: str = "easy"):
    system = (
        "你是AP CSA(Java)出题官。请只输出一道题：包含题干 +（如适用）选项 + 标准答案 + 简要解析。"
        "题目要符合AP CSA风格，避免过长。"
    )
    user = f"按{unit}出一道{difficulty}题。topic偏向：{topic}".strip()
    return generate_text(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.6
    )
