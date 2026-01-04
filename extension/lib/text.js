/**
 * Text processing utilities for tokenization, hashing, and keyword extraction.
 * Ported from weft/utils/text.py
 */

// Standard English stopwords
const ENGLISH_STOPWORDS = [
  "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
  "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
  "by", "can", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
  "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
  "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
  "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on",
  "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same",
  "she", "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
  "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too",
  "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which",
  "while", "who", "whom", "why", "with", "would", "you", "your", "yours", "yourself",
  "yourselves", "get", "got", "also", "like", "new", "one", "two", "use", "way", "well",
  "will", "even", "back", "make", "want", "see", "know", "take", "come", "could", "good",
  "look", "think", "say", "much", "really", "still", "thing", "things", "need", "first",
  "going", "right", "something", "using", "best", "every", "find", "give", "many", "made"
];

// Web/URL garbage tokens - fragments from URLs and common web terms
const WEB_GARBAGE = [
  // URL fragments
  "http", "https", "www", "com", "org", "net", "edu", "gov", "co", "io", "dev",
  "html", "htm", "php", "asp", "aspx", "jsp", "css", "xml", "json", "api",
  // Broken domain parts
  "goo", "gle", "google", "youtube", "youtu", "facebook", "twitter", "instagram",
  "linkedin", "reddit", "github", "stackoverflow", "wikipedia", "amazon", "ebay",
  // Common UI/navigation terms
  "click", "tap", "menu", "nav", "navigation", "sidebar", "header", "footer",
  "button", "link", "links", "page", "pages", "home", "next", "prev", "previous",
  "show", "hide", "open", "close", "toggle", "expand", "collapse", "more", "less",
  "share", "save", "download", "upload", "submit", "send", "cancel", "delete",
  "edit", "update", "add", "remove", "search", "filter", "sort", "view", "views",
  "login", "logout", "signin", "signout", "signup", "register", "subscribe",
  "follow", "unfollow", "like", "unlike", "dislike", "comment", "comments",
  "reply", "replies", "post", "posts", "read", "watch", "listen", "play", "pause",
  // Social/engagement
  "subscribers", "subscriber", "followers", "following", "likes", "shares",
  "liked", "shared", "commented", "replied", "posted", "watched",
  // Time-related
  "ago", "hours", "hour", "minutes", "minute", "seconds", "second", "days", "day",
  "weeks", "week", "months", "month", "years", "year", "today", "yesterday",
  "time", "date", "when", "before", "after", "since", "until", "during",
  // Numbers and counts
  "million", "thousand", "hundred", "billion", "number", "count", "total",
  // Generic terms
  "video", "videos", "image", "images", "photo", "photos", "file", "files",
  "content", "contents", "loading", "load", "error", "success", "failed",
  "please", "thanks", "thank", "welcome", "hello", "help", "info", "information",
  "copyright", "rights", "reserved", "privacy", "policy", "terms", "conditions",
  "cookie", "cookies", "accept", "decline", "allow", "deny", "settings", "preferences",
  // YouTube/video specific
  "channel", "playlist", "playlists", "autoplay", "queue", "thumbnail", "thumbnails",
  "premiere", "premieres", "live", "stream", "streaming", "streams", "episode",
  "episodes", "season", "seasons", "series", "clip", "clips", "trailer", "trailers",
  "intro", "outro", "sponsored", "sponsor", "sponsors", "advertisement", "promo",
  // Interview/generic content words
  "interview", "interviews", "episode", "part", "chapter", "section", "segment",
  "featured", "featuring", "presents", "presented", "hosted", "host", "guest", "guests"
];

const STOPWORDS = new Set([...ENGLISH_STOPWORDS, ...WEB_GARBAGE]);

/**
 * Check if a token looks like garbage (numeric, hex, random chars).
 * @param {string} token - Token to check
 * @returns {boolean} - True if token is garbage
 */
function isGarbageToken(token) {
  // Pure numbers
  if (/^\d+$/.test(token)) return true;
  // Hex-like strings (e.g., "a1b2c3")
  if (/^[0-9a-f]+$/.test(token) && token.length >= 6) return true;
  // Too many digits mixed in (e.g., "abc123def456")
  const digitCount = (token.match(/\d/g) || []).length;
  if (digitCount > token.length * 0.4) return true;
  // Single repeated character
  if (/^(.)\1+$/.test(token)) return true;
  return false;
}

/**
 * Tokenize text into lowercase words, removing stopwords.
 * @param {string} text - Input text
 * @returns {string[]} - Array of tokens
 */
export function tokenize(text) {
  if (!text) return [];
  const normalized = text.toLowerCase().replace(/[^a-z0-9]+/g, " ");
  return normalized
    .split(/\s+/)
    .filter(t =>
      t.length >= 4 &&  // Minimum 4 chars to avoid fragments
      !STOPWORDS.has(t) &&
      !isGarbageToken(t)
    );
}

/**
 * Compute 64-bit SimHash from token list.
 * Uses a simple but effective hash function since Web Crypto doesn't support MD5.
 * Returns as string for JSON serialization compatibility.
 * @param {string[]} tokens - Array of tokens
 * @returns {string|null} - 64-bit SimHash value as string
 */
export function simhashFromTokens(tokens) {
  if (!tokens || tokens.length === 0) return null;

  const vector = new Array(64).fill(0);

  for (const token of tokens) {
    // Use two different hashes combined for better distribution
    const h1 = BigInt(hash64a(token));
    const h2 = BigInt(hash64b(token));
    const h = (h1 << 32n) | (h2 & 0xFFFFFFFFn);

    for (let i = 0; i < 64; i++) {
      if ((h >> BigInt(i)) & 1n) {
        vector[i] += 1;
      } else {
        vector[i] -= 1;
      }
    }
  }

  let value = BigInt(0);
  for (let i = 0; i < 64; i++) {
    if (vector[i] > 0) {
      value |= (1n << BigInt(i));
    }
  }
  return value.toString();
}

/**
 * FNV-1a hash for first 32 bits
 */
function hash64a(str) {
  let hash = 2166136261;
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = (hash * 16777619) >>> 0;
  }
  return hash >>> 0;
}

/**
 * DJB2 hash for second 32 bits
 */
function hash64b(str) {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash) ^ str.charCodeAt(i);
  }
  return hash >>> 0;
}

/**
 * Simple hash function as fallback (djb2 algorithm).
 * @param {string} str - Input string
 * @returns {number} - Hash value
 */
function simpleHash(str) {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash) ^ str.charCodeAt(i);
  }
  return hash >>> 0;
}

/**
 * Compute Hamming distance between two simhash values (as strings or BigInt).
 * @param {string|BigInt} a - First value
 * @param {string|BigInt} b - Second value
 * @returns {number} - Hamming distance
 */
export function hammingDistance(a, b) {
  if (a === null || a === undefined || b === null || b === undefined) return 64; // Max distance

  // Convert strings to BigInt if needed
  const bigA = typeof a === 'string' ? BigInt(a) : a;
  const bigB = typeof b === 'string' ? BigInt(b) : b;

  let xor = bigA ^ bigB;
  let count = 0;
  while (xor > 0n) {
    count += Number(xor & 1n);
    xor >>= 1n;
  }
  return count;
}

/**
 * Extract top keywords from text using term frequency.
 * @param {string} text - Input text
 * @param {number} maxKeywords - Maximum keywords to return
 * @returns {string[]} - Array of keywords
 */
export function extractKeywords(text, maxKeywords = 8) {
  const tokens = tokenize(text);
  const counts = new Map();

  for (const token of tokens) {
    counts.set(token, (counts.get(token) || 0) + 1);
  }

  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, maxKeywords)
    .map(([word]) => word);
}

/**
 * Compute Jaccard similarity between two arrays.
 * @param {string[]} a - First array
 * @param {string[]} b - Second array
 * @returns {number} - Jaccard similarity (0-1)
 */
export function jaccard(a, b) {
  if (!a || !b || a.length === 0 || b.length === 0) return 0;

  const setA = new Set(a);
  const setB = new Set(b);

  const intersection = new Set([...setA].filter(x => setB.has(x)));
  const union = new Set([...setA, ...setB]);

  return intersection.size / union.size;
}

/**
 * Fuzzy string match score (simple substring + word matching).
 * @param {string} query - Search query
 * @param {string} text - Text to search in
 * @returns {number} - Match score (0-1)
 */
export function fuzzyMatch(query, text) {
  if (!query || !text) return 0;

  const q = query.toLowerCase();
  const t = text.toLowerCase();

  // Exact substring match
  if (t.includes(q)) return 1;

  // Word-based matching
  const queryWords = q.split(/\s+/).filter(w => w.length > 0);
  const textWords = new Set(t.split(/\s+/).filter(w => w.length > 0));

  let matches = 0;
  for (const qw of queryWords) {
    for (const tw of textWords) {
      if (tw.includes(qw) || qw.includes(tw)) {
        matches++;
        break;
      }
    }
  }

  return queryWords.length > 0 ? matches / queryWords.length : 0;
}
