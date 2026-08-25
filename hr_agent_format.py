"""hr_agent_format.py — Pydantic schemas for structured HR-agent output.

Validators tolerate common LLM key/format variations (e.g. "position" for
"job_title", a newline string where a list is expected).
"""

from typing import List

from pydantic import BaseModel, Field, field_validator, model_validator

_ALIASES = {
    "position": "job_title",
    "title": "job_title",
    "url": "job_url",
    "score": "match_score",
    "weaknesses": "missing_skills",
    "explanation": "reasoning",
    "advice": "improvement_tips",
    "tip": "improvement_tips",
    "improvement": "improvement_tips",
}


class MatchResult(BaseModel):
    job_id: str = ""
    job_title: str = ""
    job_url: str = ""
    match_score: int = Field(0, ge=0, le=100)
    strengths: List[str] = []
    reasoning: str = ""
    missing_skills: List[str] = []
    improvement_tips: str = ""

    @model_validator(mode="before")
    @classmethod
    def _apply_aliases(cls, data):
        if isinstance(data, dict):
            for src, dst in _ALIASES.items():
                if src in data and dst not in data:
                    data[dst] = data.pop(src)
        return data

    @field_validator("strengths", "missing_skills", mode="before")
    @classmethod
    def _to_list(cls, v):
        if isinstance(v, str):
            items = [s.strip("-• \t") for s in v.splitlines() if s.strip()]
            return items or [v]
        return v

    @field_validator("reasoning", "improvement_tips", mode="before")
    @classmethod
    def _to_str(cls, v):
        if isinstance(v, list):
            return " ".join(str(x) for x in v)
        return v

    @field_validator("match_score", mode="before")
    @classmethod
    def _to_int(cls, v):
        try:
            return max(0, min(100, int(round(float(v)))))
        except (TypeError, ValueError):
            return 0


class MatchResponse(BaseModel):
    results: List[MatchResult] = []
