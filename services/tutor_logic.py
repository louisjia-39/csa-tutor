import re
import streamlit as st

from services.wrongbook import (
    init_db,
    add_entry,
    list_entries,
    get_entry,
)

from services.tutor_logic import (
    generate_new_question,
    grade_and_extract_mistake,
    UNITS,
)

from services.auth import (
    check_user_password,
    check_admin_password,
    weekly_password,
    next_rotation_time,
)

# -----------------------------
# Page / Init
# -----------------------------
st.set_page_config(page_title="AP CSA Tutor + 错题本", layout="wide")
init_db()

# Session defaults
if "is_user_authed" not in st.session_state:
    st.session_state.is_user_authed = False
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "current_q" not in st.session_state:
    st.session_state.current_q = ""
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "unit" not in st.session_state:
    st.session_state.unit = UNITS[0]


# -----------------------------
# Helpers
# -----------------------------
def is_mcq(text: str) -> bool:
    """粗略判断是否是选择题：是否包含 A./B./C./D. 这样的选项行"""
    if not isinstance(text, str):
        return False
    # 支持 A. A) A: A： 四种
    lines = text.splitlines()
    hit = 0
    for L in lines:
        if re.match(r"^\s*[A-Da-d]\s*[\.\)\:\：]\s*.+", L):
            hit += 1
    return hit >= 2  # 至少两项就认为是 MCQ


def extract_mcq_options(text: str):
    """从题目提取 A/B/C/D 选项文本，用于显示"""
    opts = {}
    if not isinstance(text, str):
        return opts
    for L in text.splitlines():
        m = re.match(r"^\s*([A-Da-d])\s*[\.\)\:\：]\s*(.+?)\s*$", L)
        if m:
            k = m.group(1).upper()
            v = m.group(2).strip()
            opts[k] = v
    return opts


# -----------------------------
# Sidebar: Auth
# -----------------------------
with st.sidebar:
    st.header("🔐 登录")

    # 用户登录
    if not st.session_state.is_user_authed:
        user_pw = st.text_input("本周访问密码", type="password")
        if st.button("登录（用户）"):
            if check_user_password(user_pw):
                st.session_state.is_user_authed = True
                st.success("用户已登录")
            else:
                st.error("密码错误")
    else:
        st.success("用户已登录")
        if st.button("退出用户登录"):
            st.session_state.is_user_authed = False

    st.divider()

    # 管理员登录
    st.header("🔥 管理员")
    if not st.session_state.is_admin:
        admin_pw = st.text_input("管理员密码", type="password")
        if st.button("登录（管理员）"):
            if check_admin_password(admin_pw):
                st.session_state.is_admin = True
                st.success("管理员已登录")
            else:
                st.error("管理员密码错误")
    else:
        st.success("管理员已登录")
        if st.button("退出管理员"):
            st.session_state.is_admin = False

    st.divider()

    # 每周密码（仅管理员可见）
    st.subheader("本周密码（管理员可见）")
    if st.session_state.is_admin:
        st.code(weekly_password(), language="text")
        st.caption(f"下次自动切换时间：{next_rotation_time()}")
    else:
        st.info("管理员登录后可查看")


# 未登录用户：直接阻止访问主功能
if not st.session_state.is_user_authed:
    st.stop()


# -----------------------------
# Main UI
# -----------------------------
tab1, tab2, tab3 = st.tabs(["💬 讲解/提问", "🧪 刷题", "📒 错题本"])


# -----------------------------
# Tab 1: Ask / Explain
# -----------------------------
with tab1:
    st.subheader("💬 讲解/提问（你可以把题目/代码/疑问贴这里）")

    prompt = st.text_area("你的问题", height=150, placeholder="例如：解释一下 Java 的 String 比较，或者贴一题让我讲解。")

    if st.button("让AI讲解"):
        if not prompt.strip():
            st.warning("先输入问题。")
        else:
            # 这里你原来可能有聊天模式；如果你暂时没有，就先简单复用判题逻辑的 LLM 输出
            # 也可以后续单独做一个 chat_service
            res = grade_and_extract_mistake(
                question="（讲解模式）\n" + prompt.strip(),
                user_answer="请讲解并给例子。",
                unit_hint=st.session_state.unit,
            )
            st.markdown("### 讲解")
            st.write(res.get("explanation", ""))


# -----------------------------
# Tab 2: Practice
# -----------------------------
with tab2:
    st.subheader("🧪 刷题")

    colA, colB = st.columns([1, 1])

    with colA:
        st.session_state.unit = st.selectbox("选择单元（Unit）", UNITS, index=UNITS.index(st.session_state.unit))
        topic = st.text_input("topic（可选，比如：for循环/构造器/ArrayList）", "")

        if st.button("生成新题"):
            st.session_state.current_q = generate_new_question(
                st.session_state.unit,
                topic,
                difficulty="easy",
            )
            st.session_state.last_result = None

    with colB:
        st.markdown("### 题目")
        q = st.session_state.current_q or "点击“生成新题”开始。"
        st.write(q)

    st.divider()

    # ---------- Answer Input ----------
    st.subheader("提交你的答案（写思路或写最终答案都行）")

    mcq = is_mcq(st.session_state.current_q)
    opts = extract_mcq_options(st.session_state.current_q) if mcq else {}

    user_answer = ""

    if mcq and opts:
        # 用 radio 根治大小写/格式问题
        labels = []
        keys = ["A", "B", "C", "D"]
        for k in keys:
            if k in opts:
                labels.append(f"{k}. {opts[k]}")
        # 兜底：如果解析不到四项，就给纯字母
        if len(labels) < 2:
            chosen = st.radio("选择你的选项", ["A", "B", "C", "D"], horizontal=True)
            user_answer = chosen
        else:
            chosen_label = st.radio("选择你的选项", labels)
            user_answer = chosen_label.split(".", 1)[0].strip().upper()
    else:
        user_answer = st.text_area("你的答案", height=120, placeholder="例如：C，或写出推导过程/最终值。")

    if st.button("判题 + 生成同错因练习 + 加入错题本"):
        if not st.session_state.current_q or st.session_state.current_q.startswith("点击"):
            st.warning("先生成题目。")
        else:
            result = grade_and_extract_mistake(
                question=st.session_state.current_q,
                user_answer=user_answer,
                unit_hint=st.session_state.unit,
            )
            st.session_state.last_result = result

            st.markdown("## 判题结果")
            st.write("是否正确：", result.get("is_correct", False))

            st.markdown("### 正确答案")
            st.write(result.get("correct_answer", ""))

            st.markdown("### 解析/你错在哪")
            st.write(result.get("explanation", ""))

            st.markdown("### 错因类型")
            st.write(result.get("mistake_type", ""))

            st.markdown("### 同错因针对练习（3题）")
            drills = result.get("drills", []) or []
            for i, d in enumerate(drills, 1):
                st.markdown(f"**{i}. {d.get('q','')}**")
                st.caption(f"答案要点：{d.get('a','')}")

            # 写入错题本（只在判错时记录；你想记录全部也可以改）
            if not result.get("is_correct", False):
                add_entry(
                    question=st.session_state.current_q,
                    user_answer=user_answer,
                    correct_answer=result.get("correct_answer", ""),
                    explanation=result.get("explanation", ""),
                    mistake_type=result.get("mistake_type", ""),
                    unit=result.get("unit", st.session_state.unit),
                    topic=result.get("topic", ""),
                )
                st.success("已加入错题本 ✅")
            else:
                st.info("本题答对了，不加入错题本。")


# -----------------------------
# Tab 3: Wrongbook
# -----------------------------
with tab3:
    st.subheader("📒 错题本")

    entries = list_entries(limit=50)
    if not entries:
        st.info("错题本还没有内容。去刷题吧。")
    else:
        # 左侧列表
        left, right = st.columns([1, 2])
        with left:
            labels = []
            ids = []
            for e in entries:
                ids.append(e["id"])
                labels.append(f'#{e["id"]} | {e.get("mistake_type","")} | {e.get("unit","")}')
            selected = st.selectbox("选择一条错题", list(range(len(labels))), format_func=lambda i: labels[i])

        with right:
            item = get_entry(ids[selected])
            st.markdown("### 题目")
            st.write(item.get("question", ""))

            st.markdown("### 你的答案")
            st.write(item.get("user_answer", ""))

            st.markdown("### 正确答案")
            st.write(item.get("correct_answer", ""))

            st.markdown("### 解析")
            st.write(item.get("explanation", ""))

            st.markdown("### 错因类型")
            st.write(item.get("mistake_type", ""))

            st.markdown("### Unit / Topic")
            st.write(item.get("unit", ""), " / ", item.get("topic", ""))
