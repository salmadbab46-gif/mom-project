import requests
import json
import time
from typing import Generator, List, Dict, Any
import xml.etree.ElementTree as ET
import hashlib

SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"
PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

HEADERS = {
    "User-Agent": "PsychNeuroResearchBot/1.0 (research-tool)",
    "Accept": "application/json"
}

# Psychology & Neurology specific query boosters
DOMAIN_TERMS = "psychology OR neuroscience OR neurology OR cognitive OR brain OR mental OR behavioral"


def search_semantic_scholar(query: str, max_results: int = 8) -> List[Dict]:
    """Search Semantic Scholar for academic papers."""
    articles = []
    try:
        params = {
            "query": f"{query} {DOMAIN_TERMS}",
            "limit": max_results,
            "fields": "title,authors,year,abstract,externalIds,openAccessPdf,citationCount,venue",
            "sort": "citationCount"
        }
        resp = requests.get(
            f"{SEMANTIC_SCHOLAR_BASE}/paper/search",
            params=params,
            headers=HEADERS,
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            for paper in data.get("data", []):
                if not paper.get("abstract"):
                    continue
                authors = [a.get("name", "") for a in paper.get("authors", [])[:3]]
                paper_id = paper.get("paperId", "")
                url = f"https://www.semanticscholar.org/paper/{paper_id}"
                pdf_url = paper.get("openAccessPdf", {})
                if pdf_url and isinstance(pdf_url, dict):
                    url = pdf_url.get("url", url)

                citations = paper.get("citationCount", 0) or 0
                reliability = min(1.0, 0.6 + (citations / 500) * 0.4)

                articles.append({
                    "id": hashlib.md5(paper_id.encode()).hexdigest(),
                    "title": paper.get("title", "Untitled"),
                    "authors": authors,
                    "year": paper.get("year"),
                    "abstract": paper.get("abstract", ""),
                    "source": "Semantic Scholar",
                    "source_url": url,
                    "source_type": "academic",
                    "reliability_score": round(reliability, 2),
                    "citations": citations,
                    "venue": paper.get("venue", "")
                })
    except Exception as e:
        print(f"[Semantic Scholar] Error: {e}")
    return articles


def search_pubmed(query: str, max_results: int = 8) -> List[Dict]:
    """Search PubMed for peer-reviewed medical and psych papers."""
    articles = []
    try:
        # Step 1: search for IDs
        search_params = {
            "db": "pubmed",
            "term": f"{query}[Title/Abstract] AND (psychology[MeSH] OR neuroscience[MeSH] OR brain[MeSH])",
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance",
            "usehistory": "y"
        }
        search_resp = requests.get(
            f"{PUBMED_BASE}/esearch.fcgi",
            params=search_params,
            headers=HEADERS,
            timeout=15
        )
        if search_resp.status_code != 200:
            return articles

        search_data = search_resp.json()
        ids = search_data.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return articles

        time.sleep(0.5)  # Respect NCBI rate limit

        # Step 2: fetch details
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(ids[:max_results]),
            "retmode": "xml",
        }
        fetch_resp = requests.get(
            f"{PUBMED_BASE}/efetch.fcgi",
            params=fetch_params,
            headers=HEADERS,
            timeout=20
        )
        if fetch_resp.status_code != 200:
            return articles

        root = ET.fromstring(fetch_resp.content)
        for article in root.findall(".//PubmedArticle"):
            try:
                title_el = article.find(".//ArticleTitle")
                title = title_el.text if title_el is not None else "Untitled"
                if title and title.endswith(".."):
                    title = title[:-1]

                abstract_parts = article.findall(".//AbstractText")
                abstract = " ".join(
                    (el.text or "") for el in abstract_parts if el.text
                ).strip()

                if not abstract:
                    continue

                authors = []
                for author in article.findall(".//Author")[:3]:
                    last = author.findtext("LastName", "")
                    first = author.findtext("ForeName", "")
                    if last:
                        authors.append(f"{last} {first}".strip())

                year_el = article.find(".//PubDate/Year")
                year = int(year_el.text) if year_el is not None else None

                pmid_el = article.find(".//PMID")
                pmid = pmid_el.text if pmid_el is not None else ""
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

                journal_el = article.find(".//Journal/Title")
                journal = journal_el.text if journal_el is not None else ""

                articles.append({
                    "id": hashlib.md5(f"pubmed_{pmid}".encode()).hexdigest(),
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "abstract": abstract,
                    "source": f"PubMed — {journal}" if journal else "PubMed",
                    "source_url": url,
                    "source_type": "peer-reviewed",
                    "reliability_score": 0.92,  # PubMed = peer-reviewed, high reliability
                    "citations": 0,
                    "venue": journal
                })
            except Exception:
                continue

    except Exception as e:
        print(f"[PubMed] Error: {e}")
    return articles


def search_crossref(query: str, max_results: int = 5) -> List[Dict]:
    """Search CrossRef for DOI-indexed academic papers."""
    articles = []
    try:
        params = {
            "query": query,
            "filter": "type:journal-article",
            "rows": max_results,
            "select": "DOI,title,author,published,abstract,container-title,is-referenced-by-count",
            "sort": "is-referenced-by-count",
            "order": "desc"
        }
        resp = requests.get(
            "https://api.crossref.org/works",
            params=params,
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15
        )
        if resp.status_code == 200:
            items = resp.json().get("message", {}).get("items", [])
            for item in items:
                abstract = item.get("abstract", "")
                if not abstract or len(abstract) < 50:
                    continue
                # Clean up JATS XML tags
                abstract = abstract.replace("<jats:p>", "").replace("</jats:p>", "")
                abstract = abstract.replace("<jats:bold>", "").replace("</jats:bold>", "")

                title_list = item.get("title", ["Untitled"])
                title = title_list[0] if title_list else "Untitled"

                authors = []
                for a in item.get("author", [])[:3]:
                    name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                    if name:
                        authors.append(name)

                doi = item.get("DOI", "")
                year_parts = item.get("published", {}).get("date-parts", [[None]])
                year = year_parts[0][0] if year_parts and year_parts[0] else None

                citations = item.get("is-referenced-by-count", 0) or 0
                reliability = min(1.0, 0.65 + (citations / 300) * 0.35)

                journal = ""
                ct = item.get("container-title", [])
                if ct:
                    journal = ct[0]

                articles.append({
                    "id": hashlib.md5(doi.encode()).hexdigest(),
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "abstract": abstract,
                    "source": f"CrossRef — {journal}" if journal else "CrossRef",
                    "source_url": f"https://doi.org/{doi}" if doi else "",
                    "source_type": "academic",
                    "reliability_score": round(reliability, 2),
                    "citations": citations,
                    "venue": journal
                })
    except Exception as e:
        print(f"[CrossRef] Error: {e}")
    return articles


def deduplicate(articles: List[Dict]) -> List[Dict]:
    """Remove duplicates based on title similarity."""
    seen_titles = set()
    unique = []
    for article in articles:
        title_key = article.get("title", "").lower()[:60]
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique.append(article)
    return unique


def research_subjects(
    subjects: List[str],
    max_per_source: int = 6
) -> Generator[Dict, None, None]:
    """
    Research multiple subjects across sources.
    Yields status updates and article data as a generator.
    """
    all_articles = []

    for subject in subjects:
        yield {"type": "status", "message": f"Searching Semantic Scholar for: {subject}..."}

        ss_articles = search_semantic_scholar(subject, max_per_source)
        for a in ss_articles:
            a["subjects"] = [subject]
        all_articles.extend(ss_articles)

        yield {
            "type": "progress",
            "message": f"Found {len(ss_articles)} academic papers for '{subject}'",
            "count": len(ss_articles),
            "source": "Semantic Scholar"
        }

        time.sleep(0.3)

        yield {"type": "status", "message": f"Searching PubMed for: {subject}..."}

        pm_articles = search_pubmed(subject, max_per_source)
        for a in pm_articles:
            a["subjects"] = [subject]
        all_articles.extend(pm_articles)

        yield {
            "type": "progress",
            "message": f"Found {len(pm_articles)} PubMed papers for '{subject}'",
            "count": len(pm_articles),
            "source": "PubMed"
        }

        time.sleep(0.3)

        yield {"type": "status", "message": f"Searching CrossRef for: {subject}..."}

        cr_articles = search_crossref(subject, max_per_source - 2)
        for a in cr_articles:
            a["subjects"] = [subject]
        all_articles.extend(cr_articles)

        yield {
            "type": "progress",
            "message": f"Found {len(cr_articles)} CrossRef papers for '{subject}'",
            "count": len(cr_articles),
            "source": "CrossRef"
        }

    # Deduplicate and sort
    unique_articles = deduplicate(all_articles)
    unique_articles.sort(key=lambda x: x.get("reliability_score", 0), reverse=True)

    yield {
        "type": "articles_ready",
        "articles": unique_articles,
        "total": len(unique_articles)
    }
