"""hr_agent.py — Core HR agent: match a candidate CV against the job vector store."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from hr_agent_format import MatchResponse
from hr_agent_tools import search_jobs

LLM_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You are an expert HR recruiting specialist and career coach.
Given a candidate's CV/resume text:
1. Identify the candidate's key skills, experience level, languages and domains.
2. Call the search_jobs tool (multiple calls with different queries are allowed)
   to find relevant openings in the vector database.
3. Select the TOP 3 best overall matches for the candidate.

For each selected job return: job_id, job_title, job_url (copied exactly from
the search results), match_score (0-100), strengths (why the candidate fits),
reasoning, missing_skills, and improvement_tips (actionable advice).
Write all free-text fields in Vietnamese."""

_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent(
            model=ChatOpenAI(model=LLM_MODEL, temperature=0),
            tools=[search_jobs],
            system_prompt=SYSTEM_PROMPT,
            response_format=MatchResponse,
        )
    return _agent


def find_matching_jobs(cv_text: str) -> MatchResponse:
    result = get_agent().invoke(
        {"messages": [{"role": "user", "content": f"Candidate CV:\n{cv_text[:20000]}"}]}
    )
    return result["structured_response"]


if __name__ == "__main__":
    # Synthetic test candidate (no real personal data).
    sample_cv = """
    Nguyen Van A (synthetic test profile)
    Summary: 8 years in technical program management for consumer electronics
    manufacturing; led cross-functional vendor teams in Vietnam.
    Skills: project management, supply chain, quality assurance, stakeholder
    management, data analysis, English and Vietnamese fluency.
    Education: BSc Industrial Engineering.
    """
    resp = find_matching_jobs(sample_cv)
    for i, m in enumerate(resp.results, 1):
        print(f"#{i} {m.job_title} — {m.match_score}/100")
        print(f"   url: {m.job_url}")
        print(f"   strengths: {m.strengths}")
        print(f"   missing: {m.missing_skills}")
        print()
