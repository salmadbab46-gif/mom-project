"""
Free summarizer — no API, no downloads, no external models.
Uses TextRank + TF-IDF sentence scoring, tuned for psychology/neuroscience abstracts.
"""
import re
import math
from collections import Counter


# ── Stop words (built-in, no NLTK needed) ────────────────────────────────────
STOP_WORDS = {
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","are","was","were","be","been","being","have","has",
    "had","do","does","did","will","would","could","should","may","might",
    "this","that","these","those","it","its","we","our","their","they",
    "he","she","his","her","as","if","so","than","then","when","where",
    "which","who","whom","how","what","whether","both","all","each","more",
    "also","not","no","nor","yet","either","neither","such","there","here",
    "about","into","through","during","before","after","above","below","up",
    "down","out","off","over","under","again","further","once","while","i",
    "me","my","myself","you","your","he","him","his","she","her","we","us",
    "they","them","can","cannot","just","only","very","too","much","many",
    "most","some","any","few","other","between","among","within","across"
}

# Psychology & neuroscience signal phrases that indicate important content
FINDING_SIGNALS = [
    "found","showed","demonstrated","revealed","observed","identified",
    "suggest","indicate","conclude","results","evidence","significant",
    "associated","linked","related","effect","impact","role","function",
    "increase","decrease","improve","reduce","enhance","impair","alter",
    "compared","difference","higher","lower","greater","less","more",
]

DOMAIN_KEYWORDS = [
    "brain","neural","neuron","cortex","hippocampus","amygdala","prefrontal",
    "dopamine","serotonin","cognitive","memory","learning","attention","emotion",
    "behavior","mental","psychological","therapy","treatment","clinical",
    "disorder","anxiety","depression","stress","trauma","plasticity","synapse",
    "consciousness","perception","motivation","reward","inhibition","activation",
]

CONCLUSION_SIGNALS = [
    "suggest","conclude","implication","therefore","thus","may help","could",
    "future","clinical","treatment","therapy","findings indicate","results suggest",
    "important","practical","application","intervention","potential"
]


# ── Text utilities ─────────────────────────────────────────────────────────────
def split_sentences(text: str) -> list:
    text = re.sub(r'\s+', ' ', text.strip())
    # Split on period/exclamation/question followed by space+capital
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [p.strip() for p in parts if len(p.strip()) > 25]


def tokenize(text: str) -> list:
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return [w for w in words if w not in STOP_WORDS]


def tfidf_scores(sentences: list) -> dict:
    """Compute TF-IDF score for each word across sentences."""
    n = len(sentences)
    if n == 0:
        return {}
    # TF per sentence
    tf = [Counter(tokenize(s)) for s in sentences]
    # IDF
    doc_freq = Counter()
    for t in tf:
        for w in set(t):
            doc_freq[w] += 1
    idf = {w: math.log((n + 1) / (df + 1)) for w, df in doc_freq.items()}
    return tf, idf


def sentence_tfidf_vector(tokens: Counter, idf: dict) -> dict:
    total = sum(tokens.values()) or 1
    return {w: (c / total) * idf.get(w, 0) for w, c in tokens.items()}


def cosine_similarity(v1: dict, v2: dict) -> float:
    common = set(v1) & set(v2)
    if not common:
        return 0.0
    dot = sum(v1[w] * v2[w] for w in common)
    mag1 = math.sqrt(sum(x**2 for x in v1.values()))
    mag2 = math.sqrt(sum(x**2 for x in v2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def textrank(sentences: list, top_n: int = 3) -> list:
    """TextRank: score sentences by similarity graph, return top_n indices."""
    n = len(sentences)
    if n == 0:
        return []
    if n <= top_n:
        return list(range(n))

    tf, idf = tfidf_scores(sentences)
    vectors = [sentence_tfidf_vector(tf[i], idf) for i in range(n)]

    # Build similarity matrix
    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                sim[i][j] = cosine_similarity(vectors[i], vectors[j])

    # Normalize rows
    for i in range(n):
        row_sum = sum(sim[i])
        if row_sum > 0:
            sim[i] = [x / row_sum for x in sim[i]]

    # Power iteration (PageRank)
    scores = [1.0 / n] * n
    damping = 0.85
    for _ in range(30):
        new_scores = [(1 - damping) / n] * n
        for i in range(n):
            for j in range(n):
                new_scores[i] += damping * sim[j][i] * scores[j]
        scores = new_scores

    # Domain + signal boosting
    for i, s in enumerate(sentences):
        s_lower = s.lower()
        boost = sum(0.1 for kw in DOMAIN_KEYWORDS if kw in s_lower)
        boost += sum(0.15 for sig in FINDING_SIGNALS if sig in s_lower)
        scores[i] += boost

    ranked = sorted(range(n), key=lambda i: scores[i], reverse=True)
    return ranked[:top_n]


# ── Difficulty estimator ───────────────────────────────────────────────────────
JARGON = [
    "cortex","hippocampus","amygdala","neurotransmitter","synaptic","prefrontal",
    "dopaminergic","serotonergic","neurogenesis","fMRI","PET","EEG","MRI",
    "longitudinal","meta-analysis","randomized","glutamate","gaba","receptor",
    "axon","dendrite","myelination","neuroinflammation","hypothalamus","thalamus",
    "basal ganglia","cerebellum","limbic","allostasis","epigenetic","phenotype",
]

def estimate_difficulty(text: str) -> str:
    count = sum(1 for j in JARGON if j.lower() in text.lower())
    if count >= 5:
        return "advanced"
    if count >= 2:
        return "intermediate"
    return "beginner"


# ── Main summarizer ────────────────────────────────────────────────────────────
def summarize_article(article: dict) -> dict:
    abstract = (article.get("abstract") or "").strip()

    if not abstract or len(abstract) < 40:
        article["summary"] = "Abstract not available for this article."
        article["key_points"] = []
        article["implications"] = ""
        article["difficulty"] = "intermediate"
        return article

    sentences = split_sentences(abstract)

    if len(sentences) <= 2:
        # Short abstract — use as-is
        article["summary"] = abstract[:400]
        article["key_points"] = []
        article["implications"] = ""
        article["difficulty"] = estimate_difficulty(abstract)
        return article

    # Get top sentences via TextRank
    top_indices = textrank(sentences, top_n=min(5, len(sentences)))

    # Summary: top 2 sentences, in original order for readability
    summary_indices = sorted(top_indices[:2])
    summary = " ".join(sentences[i] for i in summary_indices)
    if len(summary) > 520:
        summary = summary[:520] + "..."

    # Key points: next 3 best sentences not already in summary
    used = set(summary_indices)
    kp_indices = [i for i in top_indices if i not in used][:3]
    kp_indices = sorted(kp_indices)
    key_points = [sentences[i] for i in kp_indices]

    # Implication: last sentence if it has conclusion signal words
    last = sentences[-1]
    has_signal = any(sig in last.lower() for sig in CONCLUSION_SIGNALS)
    implication = last if (has_signal and last not in summary) else ""

    article["summary"] = summary
    article["key_points"] = key_points
    article["implications"] = implication
    article["difficulty"] = estimate_difficulty(abstract)
    return article


def generate_overview(subjects: list, articles: list) -> str:
    """Build a structured research overview from all articles."""
    if not articles:
        return "No articles found."

    total = len(articles)
    top_reliable = sorted(articles, key=lambda x: x.get("reliability_score", 0), reverse=True)

    lines = []
    lines.append(f"Research overview for: {', '.join(subjects)}")
    lines.append(f"Analysed {total} peer-reviewed and academic articles from Semantic Scholar, PubMed, and CrossRef.\n")

    # Collect all summaries and extract main themes
    all_summaries = " ".join(
        a.get("summary") or a.get("abstract", "")[:200]
        for a in articles if a.get("summary") or a.get("abstract")
    )

    # Per-subject breakdown
    for subject in subjects:
        subj_arts = [a for a in articles if subject in (a.get("subjects") or [])]
        if not subj_arts:
            continue
        lines.append(f"— {subject.upper()} ({len(subj_arts)} articles)")
        for a in subj_arts[:3]:
            summ = a.get("summary") or (a.get("abstract") or "")[:180]
            title = a.get("title","")[:65]
            year = a.get("year","N/A")
            lines.append(f"  • ({year}) {title}")
            if summ:
                lines.append(f"    {summ[:200]}")
        lines.append("")

    # Top sources
    lines.append("— MOST RELIABLE SOURCES")
    for a in top_reliable[:5]:
        rel = int((a.get("reliability_score") or 0) * 100)
        src = (a.get("source") or "").split("—")[0].strip()
        lines.append(f"  ★ {rel}% — {a.get('title','')[:65]} ({a.get('year','N/A')}) via {src}")

    # Key points pool
    all_kps = []
    for a in articles:
        all_kps.extend(a.get("key_points") or [])
    if all_kps:
        lines.append("\n— KEY FINDINGS ACROSS ALL ARTICLES")
        seen = set()
        count = 0
        for kp in all_kps:
            kp_short = kp[:120]
            if kp_short not in seen:
                seen.add(kp_short)
                lines.append(f"  • {kp_short}")
                count += 1
                if count >= 8:
                    break

    return "\n".join(lines)
