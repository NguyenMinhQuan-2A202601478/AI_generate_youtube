"""hr_agent_fe.py — Streamlit frontend: upload a CV PDF, stream SSE progress, render matches."""

import json

import requests
import streamlit as st

BACKEND = "http://localhost:8000/find_jobs"
MAX_MB = 10

st.set_page_config(page_title="AI HR Agent", page_icon="💼", layout="centered")
st.title("Tìm việc nhanh hơn, chính xác hơn với AI.")
st.caption("Tải CV (PDF) lên — AI sẽ tìm các vị trí phù hợp nhất từ Google Careers Việt Nam.")

uploaded = st.file_uploader(f"Tải lên CV (PDF, tối đa {MAX_MB}MB)", type=["pdf"])

if uploaded and uploaded.size > MAX_MB * 1024 * 1024:
    st.error(f"File vượt quá {MAX_MB}MB.")
    uploaded = None

if uploaded and st.button("Phân tích & Tìm việc phù hợp", type="primary"):
    status = st.status("Đang gửi CV tới hệ thống...", expanded=True)
    result = None
    try:
        with requests.post(
            BACKEND,
            files={"resume": (uploaded.name, uploaded.getvalue(), "application/pdf")},
            stream=True,
            timeout=600,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                event = json.loads(line[len("data: "):])
                if event["type"] == "status":
                    status.write(event["message"])
                elif event["type"] == "error":
                    status.update(label="Có lỗi xảy ra", state="error")
                    st.error(event["message"])
                elif event["type"] == "result":
                    result = event["data"]
    except requests.RequestException as e:
        status.update(label="Không kết nối được backend", state="error")
        st.error(f"Lỗi kết nối backend: {e}")

    if result:
        status.update(label="Phân tích hoàn tất!", state="complete")
        matches = result.get("results", [])
        if not matches:
            st.warning("Không tìm thấy vị trí phù hợp.")
        for i, m in enumerate(matches, 1):
            with st.expander(
                f"#{i} — {m.get('job_title', 'N/A')} · {m.get('match_score', 0)}/100",
                expanded=(i == 1),
            ):
                st.markdown(f"**Lý do phù hợp:** {m.get('reasoning', '')}")
                st.markdown("**Điểm mạnh:**")
                for s in m.get("strengths", []):
                    st.markdown(f"- {s}")
                st.markdown("**Cần bổ sung:**")
                for s in m.get("missing_skills", []):
                    st.markdown(f"- {s}")
                st.markdown(f"**Gợi ý cải thiện:** {m.get('improvement_tips', '')}")
                if m.get("job_url"):
                    st.link_button("Ứng tuyển", m["job_url"])
