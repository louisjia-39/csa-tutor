import streamlit as st
st.write("BUILD: 2026-01-31-2050")
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

from services.openai_client import generate_text

from services.auth import (
    check_user_password,
    check_admin_password,
    weekly_password,
    next_rotation_time,
)

st.set_page_config(page_title="AP CSA Tutor + 错题本", layout="wide")
init_db()
# ---------------- Auth Gate (Sidebar) ----------------
if "is_user_authed" not in st.session_state:
    st.session_state.is_user_authed = False
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

with st.sidebar:
    st.header("🔐 登录")

    if not st.session_state.is_user_authed:
        user_pw = st.text_input("本周访问密码", type="password")
        if st.button("登录（用户）"):
            if check_user_password(user_pw):
                st.session_state.is_user_authed = True
                st.success("登录成功")
            else:
                st.error("密码不对（每周一 00:00 会更新）")
    else:
        st.success("用户已登录")
        if st.button("退出用户登录"):
            st.session_state.is_user_authed = False

    st.divider()

    st.subheader("👑 管理员")
    if not st.session_state.is_admin:
        admin_pw = st.text_input("管理员密码", type="password")
        if st.button("登录（管理员）"):
            if check_admin_password(admin_pw):
                st.session_state.is_admin = True
                st.success("管理员登录成功")
            else:
                st.error("管理员密码不对")
    else:
        st.success("管理员已登录")
        if st.button("退出管理员"):
            st.session_state.is_admin = False

    if st.session_state.is_admin:
        st.divider()
        st.subheader("本周密码（管理员可见）")
        st.code(weekly_password(), language="text")
        st.caption("下次自动切换时间：" + next_rotation_time().strftime("%Y-%m-%d %H:%M %Z"))

if not st.session_state.is_user_authed:
    st.info("请在左侧输入“本周访问密码”后使用。")
    st.stop()

# ---------------- Main UI ----------------
st.title("AP CSA(Java) 练习 + 讲解 + 自动错题本")

tab1, tab2, tab3 = st.tabs(["💬 讲解聊天", "📝 做题模式", "📚 错题本"])

with tab1:
    st.caption("你问概念/代码题，我用AP CSA风格解释。")

    if "chat" not in st.session_state:
        st.session_state.chat = [{"role": "assistant", "content": "把题目或你卡住的点发我（可贴代码）。"}]

    for m in st.session_state.chat:
        with st.chat_message("assistant" if m["role"] == "assistant" else "user"):
            st.write(m["content"])

    prompt = st.chat_input("输入你的疑问/题目（可贴代码）")
    if prompt:
        st.session_state.chat.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        system = (
            "你是AP CSA(Java)家教。回答要：短句、分点、先结论后原因、给1个小例子。"
            "如果是代码题，指出常见坑。"
        )
        reply = generate_text(
            [{"role": "system", "content": system}] + st.session_state.chat[-6:],
            temperature=0.4
        )
        st.session_state.chat.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.write(reply)

with tab2:
    colA, colB = st.columns([1, 1])

    with colA:
        unit = st.selectbox("选择单元(Unit)", UNITS, index=0)
        topic = st.text_input("topic（可选，比如：for循环/构造器/ArrayList）", "")
        if st.button("生成新题"):
            st.session_state.current_q = generate_new_question(unit, topic, difficulty="easy")

    with colB:
        st.subheader("题目")
        q = st.session_state.get("current_q", "点击“生成新题”开始。")

        leak_words = ["标准答案", "答案：", "答案:", "解析", "正确答案"]
        if isinstance(q, str) and any(w in q for w in leak_words):
            st.warning("检测到题目里包含答案/解析，已隐藏。请点击“生成新题”重新出题。")
            st.session_state.current_q = "点击“生成新题”开始。"
            q = st.session_state.current_q

        st.write(q)

    st.divider()
    st.subheader("提交你的答案（写思路或写最终答案都行）")
    user_answer = st.text_area("你的答案", height=120)

    if st.button("判题 + 生成同错因练习 + 加入错题本"):
        if not q or (isinstance(q, str) and q.startswith("点击")):
            st.warning("先生成题目。")
        else:
            result = grade_and_extract_mistake(q, user_answer, unit_hint=unit)

            st.markdown("### 判题结果")
            st.write("是否正确：", result.get("is_correct"))

            st.markdown("**正确答案**")
            st.write(result.get("correct_answer", ""))

            st.markdown("**解析/你错在哪**")
            st.write(result.get("explanation", ""))

            st.markdown("**错因类型**")
            st.write(result.get("mistake_type", ""))

            drills = result.get("drills", [])
            if drills:
                st.markdown("### 同错因针对练习（3题）")
                for i, d in enumerate(drills, 1):
                    st.markdown(f"**{i}. {d.get('q','')}**")
                    st.write("答案：", d.get("a", ""))

            add_entry(
                unit=result.get("unit", unit),
                topic=result.get("topic", topic),
                question=q,
                user_answer=user_answer,
                correct_answer=result.get("correct_answer", ""),
                explanation=result.get("explanation", ""),
                mistake_type=result.get("mistake_type", ""),
                next_drill=str(drills[:1])
            )
            st.success("已加入错题本。去「错题本」查看。")

with tab3:
    st.subheader("最近错题")
    rows = list_entries(limit=200)
    if not rows:
        st.info("还没有记录。去「做题模式」做一道题试试。")
    else:
        options = [f"#{r[0]} | {r[2]} | {r[3]} | {r[7]}" for r in rows]
        pick = st.selectbox("选择一条错题记录", options, index=0)
        entry_id = int(pick.split("|")[0].strip().replace("#", ""))
        full = get_entry(entry_id)
        if full:
            st.markdown("### 详情")
            st.write("创建时间：", full[1])
            st.write("Unit：", full[2])
            st.write("Topic：", full[3])
            st.markdown("**题目**"); st.write(full[4])
            st.markdown("**你的答案**"); st.write(full[5])
            st.markdown("**正确答案**"); st.write(full[6])
            st.markdown("**解析**"); st.write(full[7])
            st.write("错因类型：", full[8])
