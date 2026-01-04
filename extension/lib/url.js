/**
 * URL utility functions for canonicalization and normalization.
 * Ported from weft/utils/url.py
 */

const TRACKING_PARAMS = new Set([
  "fbclid",
  "gclid",
  "igshid",
  "mc_cid",
  "mc_eid",
  "msclkid",
  "ref",
  "ref_src",
  "utm_campaign",
  "utm_content",
  "utm_medium",
  "utm_source",
  "utm_term"
]);

/**
 * Normalize URL by removing tracking params, www prefix, trailing slashes.
 * @param {string} url - Input URL
 * @returns {string} - Canonicalized URL
 */
export function canonicalizeUrl(url) {
  if (!url) return url;

  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return url;
  }

  // Normalize scheme
  const scheme = parsed.protocol.replace(":", "").toLowerCase();

  // Normalize host
  let host = parsed.hostname.toLowerCase();
  if (host.startsWith("www.")) {
    host = host.slice(4);
  }

  // Handle port
  let port = parsed.port;
  if ((scheme === "http" && port === "80") || (scheme === "https" && port === "443")) {
    port = "";
  }

  // Normalize path
  let path = parsed.pathname || "/";
  if (path !== "/" && path.endsWith("/")) {
    path = path.slice(0, -1);
  }

  // Filter and sort query params
  const params = [];
  for (const [key, value] of parsed.searchParams.entries()) {
    const keyLower = key.toLowerCase();
    if (TRACKING_PARAMS.has(keyLower) || keyLower.startsWith("utm_")) {
      continue;
    }
    params.push([key, value]);
  }
  params.sort((a, b) => a[0].localeCompare(b[0]));

  // Rebuild URL
  const netloc = port ? `${host}:${port}` : host;
  const query = params.length > 0
    ? "?" + params.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&")
    : "";

  return `${scheme}://${netloc}${path}${query}`;
}

/**
 * Extract canonical URL from HTML document.
 * @param {Document} doc - DOM document
 * @param {string} baseUrl - Base URL for relative resolution
 * @returns {string|null} - Canonical URL or null
 */
export function extractCanonicalUrl(doc, baseUrl) {
  const link = doc.querySelector('link[rel="canonical"]');
  if (link && link.href) {
    try {
      return new URL(link.href, baseUrl).href;
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * Check if URL is HTTP or HTTPS.
 * @param {string} url - Input URL
 * @returns {boolean}
 */
export function isHttpUrl(url) {
  return url && (url.startsWith("http://") || url.startsWith("https://"));
}

/**
 * Extract and normalize domain from URL.
 * @param {string} url - Input URL
 * @returns {string} - Normalized domain
 */
export function normalizeDomain(url) {
  if (!url) return "";

  try {
    const parsed = new URL(url);
    let domain = parsed.hostname.toLowerCase();
    if (domain.startsWith("www.")) {
      domain = domain.slice(4);
    }
    return domain;
  } catch {
    return "";
  }
}

/**
 * Generate a unique ID for a tab based on URL and timestamp.
 * @param {string} url - Tab URL
 * @returns {string} - Unique ID
 */
export function generateTabId(url) {
  const timestamp = Date.now();
  const random = Math.random().toString(36).slice(2, 8);
  return `tab_${timestamp}_${random}`;
}
