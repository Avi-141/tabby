/**
 * Clustering algorithms: Union-Find, similarity computation, and grouping.
 * Ported from weft/export/similarity.py
 */

import { jaccard, hammingDistance } from "./text.js";

// Default thresholds (matching Python defaults)
export const DEFAULT_OPTIONS = {
  edgeThreshold: 0.2,
  groupThreshold: 0.25,
  domainBonus: 0.25,
  domainGroupMin: 2,
  knnK: 6,
  dedupeHamming: 3
};

/**
 * Union-Find data structure with path compression.
 */
export class UnionFind {
  constructor(size) {
    this.parent = Array.from({ length: size }, (_, i) => i);
  }

  find(x) {
    if (this.parent[x] !== x) {
      this.parent[x] = this.find(this.parent[x]); // Path compression
    }
    return this.parent[x];
  }

  union(a, b) {
    const ra = this.find(a);
    const rb = this.find(b);
    if (ra !== rb) {
      this.parent[rb] = ra;
    }
  }

  connected(a, b) {
    return this.find(a) === this.find(b);
  }
}

/**
 * Compute cosine similarity between two embedding vectors.
 * @param {number[]|null} a - First embedding
 * @param {number[]|null} b - Second embedding
 * @returns {number} - Cosine similarity (0-1)
 */
export function cosineSimilarity(a, b) {
  if (!a || !b || a.length !== b.length) return 0;

  let dot = 0;
  let normA = 0;
  let normB = 0;

  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }

  normA = Math.sqrt(normA);
  normB = Math.sqrt(normB);

  if (normA === 0 || normB === 0) return 0;
  return dot / (normA * normB);
}

/**
 * Compute similarity score between two tabs.
 * Uses embeddings if available, falls back to keyword Jaccard.
 * @param {Object} tabA - First tab
 * @param {Object} tabB - Second tab
 * @param {number} domainBonus - Bonus for same domain
 * @returns {number} - Similarity score
 */
export function similarityScore(tabA, tabB, domainBonus = DEFAULT_OPTIONS.domainBonus) {
  // Try embeddings first
  let similarity = cosineSimilarity(tabA.embedding, tabB.embedding);

  // Fallback to keyword Jaccard
  if (similarity === 0) {
    similarity = jaccard(tabA.keywords || [], tabB.keywords || []);
  }

  // Domain bonus
  if (tabA.domain && tabA.domain === tabB.domain) {
    similarity += domainBonus;
  }

  return similarity;
}

/**
 * Build pairwise similarity matrix for all tabs.
 * @param {Object[]} tabs - Array of tab objects
 * @param {number} domainBonus - Bonus for same domain
 * @returns {number[][]} - Similarity matrix
 */
export function buildSimilarityMatrix(tabs, domainBonus = DEFAULT_OPTIONS.domainBonus) {
  const n = tabs.length;
  const matrix = Array.from({ length: n }, () => Array(n).fill(0));

  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const score = similarityScore(tabs[i], tabs[j], domainBonus);
      matrix[i][j] = score;
      matrix[j][i] = score;
    }
  }

  return matrix;
}

/**
 * Build graph edges from similarity matrix.
 * @param {Object[]} tabs - Array of tab objects
 * @param {number[][]} matrix - Similarity matrix
 * @param {number} threshold - Minimum similarity for edge
 * @returns {Object[]} - Array of edge objects
 */
export function buildEdges(tabs, matrix, threshold = DEFAULT_OPTIONS.edgeThreshold) {
  const edges = [];

  for (let i = 0; i < tabs.length; i++) {
    for (let j = i + 1; j < tabs.length; j++) {
      const weight = matrix[i][j];
      if (weight >= threshold) {
        let reason = "similarity";
        if (tabs[i].domain === tabs[j].domain) {
          reason = "similarity+domain";
        }
        edges.push({
          source: tabs[i].id,
          target: tabs[j].id,
          weight: Math.round(weight * 1000) / 1000,
          reason
        });
      }
    }
  }

  return edges;
}

/**
 * Build navigation edges from tracked navigations.
 * @param {Object[]} navigations - Array of {sourceTabId, targetUrl, timestamp}
 * @param {Object[]} tabs - Array of tab objects
 * @returns {Object[]} - Array of navigation edge objects
 */
export function buildNavigationEdges(navigations, tabs) {
  const edges = [];
  const urlToTab = new Map();

  for (const tab of tabs) {
    urlToTab.set(tab.canonicalUrl || tab.url, tab);
    // Also map the raw URL
    if (tab.url && tab.url !== tab.canonicalUrl) {
      urlToTab.set(tab.url, tab);
    }
  }

  console.log("[Weft] buildNavigationEdges - navigations:", navigations.length, "tabs:", tabs.length, "urlMap size:", urlToTab.size);

  for (const nav of navigations) {
    // Find source tab by URL (more reliable than chromeTabId for closed tabs)
    const sourceTab = nav.sourceUrl ? urlToTab.get(nav.sourceUrl) : null;
    const targetTab = urlToTab.get(nav.targetUrl);

    console.log("[Weft] Nav:", nav.sourceUrl, "->", nav.targetUrl, "| sourceTab:", !!sourceTab, "targetTab:", !!targetTab);

    if (sourceTab && targetTab && sourceTab.id !== targetTab.id) {
      edges.push({
        source: sourceTab.id,
        target: targetTab.id,
        weight: 1.0,
        reason: "navigation",
        timestamp: nav.timestamp
      });
    }
  }

  console.log("[Weft] Navigation edges created:", edges.length);
  return edges;
}

/**
 * Cluster tabs into groups using Union-Find with domain grouping and mutual KNN.
 * @param {Object[]} tabs - Array of tab objects
 * @param {number[][]} matrix - Similarity matrix
 * @param {Object} options - Clustering options
 * @returns {{groups: Object[], tabToGroup: Map}} - Groups and tab-to-group mapping
 */
export function buildGroups(tabs, matrix, options = {}) {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const n = tabs.length;
  const uf = new UnionFind(n);

  // Domain-based pre-grouping
  if (opts.domainGroup !== false) {
    const domainMap = new Map();
    for (let i = 0; i < n; i++) {
      const domain = tabs[i].domain;
      if (domain) {
        if (!domainMap.has(domain)) {
          domainMap.set(domain, []);
        }
        domainMap.get(domain).push(i);
      }
    }

    for (const indices of domainMap.values()) {
      if (indices.length >= opts.domainGroupMin) {
        const root = indices[0];
        for (let i = 1; i < indices.length; i++) {
          uf.union(root, indices[i]);
        }
      }
    }
  }

  // Mutual KNN clustering
  if (opts.mutualKnn !== false) {
    const neighbors = [];

    for (let i = 0; i < n; i++) {
      const scored = [];
      for (let j = 0; j < n; j++) {
        if (j !== i) {
          scored.push({ idx: j, score: matrix[i][j] });
        }
      }
      scored.sort((a, b) => b.score - a.score);

      const filtered = scored
        .filter(s => s.score >= opts.groupThreshold)
        .slice(0, opts.knnK)
        .map(s => s.idx);

      neighbors.push(new Set(filtered));
    }

    for (let i = 0; i < n; i++) {
      for (const j of neighbors[i]) {
        if (neighbors[j].has(i)) {
          uf.union(i, j);
        }
      }
    }
  } else {
    // Simple threshold clustering
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        if (matrix[i][j] >= opts.groupThreshold) {
          uf.union(i, j);
        }
      }
    }
  }

  // Collect groups
  const groupsMap = new Map();
  for (let i = 0; i < n; i++) {
    const root = uf.find(i);
    if (!groupsMap.has(root)) {
      groupsMap.set(root, []);
    }
    groupsMap.get(root).push(i);
  }

  const groups = [];
  const tabToGroup = new Map();
  let groupId = 0;

  for (const indices of groupsMap.values()) {
    const tabIds = indices.map(i => tabs[i].id);
    groups.push({
      id: `group_${groupId}`,
      tabIds,
      size: tabIds.length
    });

    for (const tabId of tabIds) {
      tabToGroup.set(tabId, `group_${groupId}`);
    }
    groupId++;
  }

  return { groups, tabToGroup };
}

/**
 * Deduplicate tabs using canonical URLs and SimHash.
 * @param {Object[]} tabs - Array of tab objects
 * @param {number} hammingThreshold - Max hamming distance for near-duplicates
 * @returns {{primaryMap: Map, duplicates: number}} - Primary tab mapping and duplicate count
 */
export function dedupeTabs(tabs, hammingThreshold = DEFAULT_OPTIONS.dedupeHamming) {
  const n = tabs.length;
  const uf = new UnionFind(n);

  // Canonical URL matching
  const canonicalMap = new Map();
  for (let i = 0; i < n; i++) {
    const canonical = tabs[i].canonicalUrl || tabs[i].url;
    if (canonical) {
      if (canonicalMap.has(canonical)) {
        uf.union(i, canonicalMap.get(canonical));
      } else {
        canonicalMap.set(canonical, i);
      }
    }
  }

  // SimHash near-duplicate detection (same domain only)
  for (let i = 0; i < n; i++) {
    const simA = tabs[i].simhash;
    if (simA === null || simA === undefined) continue;

    for (let j = i + 1; j < n; j++) {
      const simB = tabs[j].simhash;
      if (simB === null || simB === undefined) continue;

      if (tabs[i].domain && tabs[i].domain === tabs[j].domain) {
        if (hammingDistance(simA, simB) <= hammingThreshold) {
          uf.union(i, j);
        }
      }
    }
  }

  // Build primary map
  const groupsMap = new Map();
  for (let i = 0; i < n; i++) {
    const root = uf.find(i);
    if (!groupsMap.has(root)) {
      groupsMap.set(root, []);
    }
    groupsMap.get(root).push(i);
  }

  let duplicates = 0;
  const primaryMap = new Map();

  for (const indices of groupsMap.values()) {
    const primary = Math.min(...indices);
    for (const idx of indices) {
      primaryMap.set(tabs[idx].id, tabs[primary].id);
      if (idx !== primary) {
        duplicates++;
        tabs[idx].duplicateOf = tabs[primary].id;
      }
    }
  }

  return { primaryMap, duplicates };
}

/**
 * Compute IDF (Inverse Document Frequency) for tokens.
 * @param {string[][]} docs - Array of token arrays
 * @returns {Map<string, number>} - Token to IDF mapping
 */
export function computeIdf(docs) {
  const docCount = docs.length;
  const df = new Map();

  for (const tokens of docs) {
    const unique = new Set(tokens);
    for (const token of unique) {
      df.set(token, (df.get(token) || 0) + 1);
    }
  }

  const idf = new Map();
  for (const [token, count] of df) {
    idf.set(token, Math.log((1 + docCount) / (1 + count)) + 1.0);
  }

  return idf;
}

/**
 * Get top terms by TF-IDF score.
 * @param {string[]} tokens - Array of tokens
 * @param {Map<string, number>} idf - IDF mapping
 * @param {number} maxTerms - Maximum terms to return
 * @returns {string[]} - Top terms
 */
export function topTfidfTerms(tokens, idf, maxTerms = 3) {
  const tf = new Map();
  for (const token of tokens) {
    tf.set(token, (tf.get(token) || 0) + 1);
  }

  const scored = [];
  for (const [token, count] of tf) {
    scored.push({ token, score: count * (idf.get(token) || 0) });
  }

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, maxTerms).map(s => s.token);
}

/**
 * Generate a label for a group of tabs.
 * @param {Object[]} groupTabs - Tabs in the group
 * @param {Map<string, number>} idf - IDF mapping
 * @returns {string} - Group label
 */
export function labelGroup(groupTabs, idf) {
  // Check for domain majority
  const domains = groupTabs.map(t => t.domain).filter(Boolean);
  if (domains.length > 0) {
    const counts = new Map();
    for (const d of domains) {
      counts.set(d, (counts.get(d) || 0) + 1);
    }
    const [topDomain, count] = Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])[0];

    if (count / groupTabs.length >= 0.55) {
      return topDomain;
    }
  }

  // Fall back to TF-IDF keywords
  const allTokens = [];
  for (const tab of groupTabs) {
    if (tab.keywords) {
      allTokens.push(...tab.keywords);
    }
  }

  const topTerms = topTfidfTerms(allTokens, idf, 3);
  return topTerms.length > 0 ? topTerms.join(" / ") : "group";
}
