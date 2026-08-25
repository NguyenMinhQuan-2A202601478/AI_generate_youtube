"""job_crawls.py — Crawl Google Careers (Vietnam) postings into a local Chroma DB.

Fetches up to 5 listing pages, pulls each job's detail page, then embeds the
descriptions with OpenAI text-embedding-3-small in batches of 15 and persists
them to ./chroma_db (collection: job_postings).
"""

import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

load_dotenv(Path(__file__).resolve().parent / ".env")

BASE = "https://www.google.com/about/careers/applications/jobs/results/"
LIST_URL = BASE + "?location=Vietnam&page={page}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
MAX_PAGES = 5
BATCH_SIZE = 15
PERSIST_DIR = str(Path(__file__).resolve().parent / "chroma_db")
COLLECTION = "job_postings"
EMBED_MODEL = "text-embedding-3-small"


def list_job_urls() -> dict:
    """Return {job_id: detail_url} across listing pages."""
    seen = {}
    for page in range(1, MAX_PAGES + 1):
        print(f"Fetching listing page {page}...")
        r = requests.get(LIST_URL.format(page=page), headers=HEADERS, timeout=30)
        r.raise_for_status()
        found = re.findall(r"jobs/results/(\d+)-([a-z0-9-]+)", r.text)
        new = 0
        for job_id, slug in found:
            if job_id not in seen:
                seen[job_id] = f"{BASE}{job_id}-{slug}"
                new += 1
        print(f"  page {page}: {new} new jobs")
        if new == 0:
            break
        time.sleep(1)
    return seen


def fetch_job(job_id: str, url: str) -> Document:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    h = soup.find("h1") or soup.find("h2")
    title = h.get_text(strip=True) if h else job_id
    main = soup.find("main") or soup.body
    text = main.get_text(" ", strip=True)
    return Document(
        page_content=f"{title}\n\n{text[:8000]}",
        metadata={"job_id": job_id, "title": title, "url": url},
    )


def main() -> None:
    jobs = list_job_urls()
    print(f"Total unique jobs: {len(jobs)}")

    docs = []
    for i, (job_id, url) in enumerate(jobs.items(), 1):
        print(f"[{i}/{len(jobs)}] fetching {url}")
        try:
            docs.append(fetch_job(job_id, url))
        except Exception as e:
            print(f"  skip ({e})")
        time.sleep(0.5)

    store = Chroma(
        collection_name=COLLECTION,
        embedding_function=OpenAIEmbeddings(model=EMBED_MODEL),
        persist_directory=PERSIST_DIR,
    )
    existing = store.get().get("ids", [])
    if existing:
        print(f"Clearing {len(existing)} existing documents...")
        store.delete(ids=existing)

    total_batches = (len(docs) + BATCH_SIZE - 1) // BATCH_SIZE
    for b in range(0, len(docs), BATCH_SIZE):
        batch = docs[b : b + BATCH_SIZE]
        store.add_documents(batch, ids=[d.metadata["job_id"] for d in batch])
        print(f"Embedded batch {b // BATCH_SIZE + 1}/{total_batches} ({len(batch)} documents)")

    print(f"Done. Chroma DB persisted at {PERSIST_DIR}")


if __name__ == "__main__":
    main()
