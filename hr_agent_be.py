"""hr_agent_be.py — FastAPI backend: health check + CV upload with SSE progress."""

import io
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import StreamingResponse
from pypdf import PdfReader

from hr_agent import find_matching_jobs

app = FastAPI(title="HR Agent API")


@app.get("/health")
def health():
    return {"status": "ok", "message": "Hệ thống đang hoạt động bình thường"}


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.post("/find_jobs")
async def find_jobs(resume: UploadFile = File(...)):
    pdf_bytes = await resume.read()

    def event_stream():
        yield sse({"type": "status", "message": "Đã nhận CV, đang bắt đầu phân tích..."})
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            cv_text = "\n".join((page.extract_text() or "") for page in reader.pages)
            if not cv_text.strip():
                yield sse({"type": "error", "message": "Không đọc được nội dung PDF."})
                return
            yield sse({"type": "status", "message": "Đang tìm kiếm việc làm..."})
            response = find_matching_jobs(cv_text)
            yield sse({"type": "status", "message": "Phân tích hoàn tất!"})
            yield sse({"type": "result", "data": response.model_dump()})
        except Exception as e:
            yield sse({"type": "error", "message": f"Lỗi xử lý: {e}"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
