"""Similarity computation, deduplication, and clustering functions."""

import math
from collections import Counter
from typing import Dict, List, Optional, Tuple

from weft.utils.text import hamming_distance, jaccard, tokenize
from weft.utils.url import canonicalize_url


def cosine_similarity(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def similarity_score(ta: Dict, tb: Dict, domain_bonus: float) -> float:
    """Compute similarity score between two tabs."""
    similarity = cosine_similarity(ta.get("embedding"), tb.get("embedding"))
    if similarity == 0.0:
        similarity = jaccard(ta.get("keywords", []), tb.get("keywords", []))
    if ta.get("domain") and ta.get("domain") == tb.get("domain"):
        similarity += domain_bonus
    return similarity


def build_similarity_matrix(tabs: List[Dict], domain_bonus: float) -> List[List[float]]:
    """Build pairwise similarity matrix for all tabs."""
    count = len(tabs)
    matrix = [[0.0 for _ in range(count)] for _ in range(count)]
    for i in range(count):
        for j in range(i + 1, count):
            score = similarity_score(tabs[i], tabs[j], domain_bonus)
            matrix[i][j] = score
            matrix[j][i] = score
    return matrix


def build_edges(
    tabs: List[Dict],
    similarity_matrix: List[List[float]],
    threshold: float,
) -> List[Dict]:
    """Build graph edges from similarity matrix."""
    edges: List[Dict] = []
    for i in range(len(tabs)):
        for j in range(i + 1, len(tabs)):
            weight = similarity_matrix[i][j]
            if weight >= threshold:
                reason = "similarity"
                if tabs[i].get("domain") == tabs[j].get("domain"):
                    reason = "similarity+domain"
                edges.append(
                    {
                        "source": tabs[i]["id"],
                        "target": tabs[j]["id"],
                        "weight": round(weight, 3),
                        "reason": reason,
                    }
                )
    return edges


def build_groups(
    tabs: List[Dict],
    similarity_matrix: List[List[float]],
    threshold: float,
    domain_group: bool,
    domain_group_min: int,
    mutual_knn: bool,
    knn_k: int,
) -> Tuple[List[Dict], Dict[int, int]]:
    """Cluster tabs into groups using Union-Find with domain grouping and mutual KNN."""
    parent = list(range(len(tabs)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Domain-based pre-grouping
    if domain_group:
        domain_map: Dict[str, List[int]] = {}
        for idx, tab in enumerate(tabs):
            domain = tab.get("domain")
            if domain:
                domain_map.setdefault(domain, []).append(idx)
        for indices in domain_map.values():
            if len(indices) >= max(2, domain_group_min):
                root = indices[0]
                for idx in indices[1:]:
                    union(root, idx)

    # Mutual KNN clustering
    if mutual_knn:
        neighbors = []
        for i in range(len(tabs)):
            scored = [(j, similarity_matrix[i][j]) for j in range(len(tabs)) if j != i]
            scored.sort(key=lambda t: t[1], reverse=True)
            filtered = [j for j, score in scored if score >= threshold]
            if knn_k > 0:
                filtered = filtered[:knn_k]
            neighbors.append(set(filtered))
        for i in range(len(tabs)):
            for j in neighbors[i]:
                if i in neighbors[j]:
                    union(i, j)
    else:
        for i in range(len(tabs)):
            for j in range(i + 1, len(tabs)):
                if similarity_matrix[i][j] >= threshold:
                    union(i, j)

    # Collect groups
    groups_map: Dict[int, List[int]] = {}
    for idx in range(len(tabs)):
        root = find(idx)
        groups_map.setdefault(root, []).append(idx)

    groups: List[Dict] = []
    tab_to_group: Dict[int, int] = {}
    for gid, (root, indices) in enumerate(groups_map.items()):
        group_tabs = [tabs[i] for i in indices]
        tab_ids = [t["id"] for t in group_tabs]
        groups.append(
            {
                "id": gid,
                "tab_ids": tab_ids,
                "size": len(tab_ids),
            }
        )
        for tid in tab_ids:
            tab_to_group[tid] = gid
    return groups, tab_to_group


def dedupe_tabs(tabs: List[Dict], hamming_threshold: int) -> Tuple[Dict[int, int], int]:
    """Deduplicate tabs using canonical URLs and SimHash."""
    parent = list(range(len(tabs)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Canonical URL matching
    canonical_map: Dict[str, int] = {}
    for idx, tab in enumerate(tabs):
        canonical = tab.get("canonical_url") or canonicalize_url(tab.get("url", ""))
        if not canonical:
            continue
        tab["canonical_url"] = canonical
        if canonical in canonical_map:
            union(idx, canonical_map[canonical])
        else:
            canonical_map[canonical] = idx

    # SimHash near-duplicate detection (same domain only)
    for i in range(len(tabs)):
        sim_a = tabs[i].get("simhash")
        if sim_a is None:
            continue
        for j in range(i + 1, len(tabs)):
            sim_b = tabs[j].get("simhash")
            if sim_b is None:
                continue
            if tabs[i].get("domain") and tabs[i].get("domain") == tabs[j].get("domain"):
                if hamming_distance(sim_a, sim_b) <= hamming_threshold:
                    union(i, j)

    # Build primary map and count duplicates
    groups: Dict[int, List[int]] = {}
    for idx in range(len(tabs)):
        root = find(idx)
        groups.setdefault(root, []).append(idx)

    duplicates = 0
    primary_map: Dict[int, int] = {}
    for indices in groups.values():
        primary = min(indices)
        aliases = []
        for idx in indices:
            if idx != primary:
                duplicates += 1
                primary_map[idx] = primary
                aliases.append(tabs[idx].get("url"))
            else:
                primary_map[idx] = primary
        if aliases:
            primary_tab = tabs[primary]
            existing = set(primary_tab.get("aliases", []))
            for url in aliases:
                if url:
                    existing.add(url)
            primary_tab["aliases"] = sorted(existing)
            for idx in indices:
                if idx != primary:
                    tabs[idx]["duplicate_of"] = primary
                    if not tabs[idx].get("canonical_url"):
                        tabs[idx]["canonical_url"] = primary_tab.get("canonical_url")
    return primary_map, duplicates


def compute_idf(docs_tokens: List[List[str]]) -> Dict[str, float]:
    """Compute inverse document frequency for tokens."""
    doc_count = len(docs_tokens)
    df = Counter()
    for tokens in docs_tokens:
        for token in set(tokens):
            df[token] += 1
    idf = {}
    for token, count in df.items():
        idf[token] = math.log((1 + doc_count) / (1 + count)) + 1.0
    return idf


def top_tfidf_terms(tokens: List[str], idf: Dict[str, float], max_terms: int) -> List[str]:
    """Get top terms by TF-IDF score."""
    tf = Counter(tokens)
    scored = []
    for token, count in tf.items():
        scored.append((token, count * idf.get(token, 0.0)))
    scored.sort(key=lambda t: t[1], reverse=True)
    return [token for token, _ in scored[:max_terms]]


def label_group(group_tabs: List[Dict], idf: Dict[str, float]) -> str:
    """Generate a label for a group of tabs."""
    domains = [t.get("domain") for t in group_tabs if t.get("domain")]
    if domains:
        counts = Counter(domains)
        domain, count = counts.most_common(1)[0]
        if count / max(1, len(group_tabs)) >= 0.55:
            return domain
    tokens: List[str] = []
    for tab in group_tabs:
        tokens.extend(tab.get("tokens", []))
    top_terms = top_tfidf_terms(tokens, idf, 3)
    if top_terms:
        return " / ".join(top_terms)
    return "group"
