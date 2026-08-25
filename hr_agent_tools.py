"""hr_agent_tools.py — LangChain tool for similarity search over the job Chroma DB."""

from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings

load_dotenv(Path(__file__).resolve().parent / ".env")

PERSIST_DIR = str(Path(__file__).resolve().parent / "chroma_db")
COLLECTION = "job_postings"
EMBED_MODEL = "text-embedding-3-small"

# Created eagerly at import time: chromadb's PersistentClient cannot be
# instantiated from the worker threads LangGraph runs tools in.
_store = Chroma(
    collection_name=COLLECTION,
    embedding_function=OpenAIEmbeddings(model=EMBED_MODEL),
    persist_directory=PERSIST_DIR,
)


def get_store() -> Chroma:
    return _store


@tool
def search_jobs(query: str, top_k: int = 5) -> str:
    """Search the job-postings vector database for positions matching the query.

    Args:
        query: skills, experience, languages or role description to match against job postings.
        top_k: number of results to return (default 5).
    """
    docs = get_store().similarity_search(query, k=top_k)
    if not docs:
        return "No matching jobs found."
    parts = []
    for d in docs:
        parts.append(
            f"job_id: {d.metadata.get('job_id', '')}\n"
            f"title: {d.metadata.get('title', '')}\n"
            f"url: {d.metadata.get('url', '')}\n"
            f"description: {d.page_content[:2000]}"
        )
    return "\n\n---\n\n".join(parts)
