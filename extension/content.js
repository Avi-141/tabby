/**
 * Content script for Weft extension.
 * Extracts page content and sends it to the background service worker.
 */

/**
 * Extract readable text from the page.
 * @returns {string} - Extracted text content
 */
function extractPageText() {
  // Get main content areas first
  const mainSelectors = [
    "main",
    "article",
    '[role="main"]',
    "#content",
    "#main",
    ".content",
    ".main",
    ".post",
    ".article"
  ];

  let mainContent = null;
  for (const selector of mainSelectors) {
    const el = document.querySelector(selector);
    if (el && el.innerText.length > 200) {
      mainContent = el;
      break;
    }
  }

  // Fall back to body if no main content found
  const contentElement = mainContent || document.body;

  // Clone and clean up
  const clone = contentElement.cloneNode(true);

  // Remove non-content elements
  const removeSelectors = [
    "script",
    "style",
    "noscript",
    "iframe",
    "nav",
    "header",
    "footer",
    "aside",
    ".sidebar",
    ".navigation",
    ".menu",
    ".advertisement",
    ".ads",
    ".ad",
    ".social",
    ".share",
    ".comments",
    ".comment",
    '[role="navigation"]',
    '[role="banner"]',
    '[role="contentinfo"]',
    '[aria-hidden="true"]'
  ];

  for (const selector of removeSelectors) {
    const elements = clone.querySelectorAll(selector);
    for (const el of elements) {
      el.remove();
    }
  }

  // Get text content
  let text = clone.innerText || clone.textContent || "";

  // Clean up whitespace
  text = text
    .replace(/\s+/g, " ")
    .replace(/\n\s*\n/g, "\n")
    .trim();

  return text;
}

/**
 * Extract canonical URL from the page.
 * @returns {string|null} - Canonical URL or null
 */
function extractCanonicalUrl() {
  const link = document.querySelector('link[rel="canonical"]');
  if (link && link.href) {
    return link.href;
  }

  // Check Open Graph URL
  const ogUrl = document.querySelector('meta[property="og:url"]');
  if (ogUrl && ogUrl.content) {
    return ogUrl.content;
  }

  return null;
}

/**
 * Extract page description from meta tags.
 * @returns {string} - Description or empty string
 */
function extractDescription() {
  // Try Open Graph description first (usually best for social sites)
  const ogDesc = document.querySelector('meta[property="og:description"]');
  if (ogDesc && ogDesc.content) {
    return ogDesc.content;
  }

  // Try Twitter description
  const twitterDesc = document.querySelector('meta[name="twitter:description"]');
  if (twitterDesc && twitterDesc.content) {
    return twitterDesc.content;
  }

  // Try standard meta description
  const metaDesc = document.querySelector('meta[name="description"]');
  if (metaDesc && metaDesc.content) {
    return metaDesc.content;
  }

  return "";
}

/**
 * Extract YouTube-specific metadata.
 * @returns {object|null} - YouTube metadata or null
 */
function extractYouTubeMetadata() {
  if (!window.location.hostname.includes("youtube.com")) {
    return null;
  }

  const metadata = {};

  // Get video title from og:title (cleaner than document.title)
  const ogTitle = document.querySelector('meta[property="og:title"]');
  if (ogTitle && ogTitle.content) {
    metadata.title = ogTitle.content;
  }

  // Get channel name
  const channelLink = document.querySelector('#channel-name a, [itemprop="author"] [itemprop="name"]');
  if (channelLink) {
    metadata.channel = channelLink.textContent?.trim();
  }

  // Get video description from meta
  const ogDesc = document.querySelector('meta[property="og:description"]');
  if (ogDesc && ogDesc.content) {
    metadata.description = ogDesc.content;
  }

  // Try to get full description from the page
  const expandedDesc = document.querySelector('#description-inline-expander, #description .content, ytd-text-inline-expander');
  if (expandedDesc) {
    const fullDesc = expandedDesc.textContent?.trim();
    if (fullDesc && fullDesc.length > (metadata.description?.length || 0)) {
      metadata.description = fullDesc.slice(0, 2000); // Limit size
    }
  }

  // Get keywords from meta
  const keywords = document.querySelector('meta[name="keywords"]');
  if (keywords && keywords.content) {
    metadata.keywords = keywords.content;
  }

  return metadata;
}

/**
 * Extract metadata for other common sites.
 * @returns {object|null} - Site-specific metadata or null
 */
function extractSiteMetadata() {
  const hostname = window.location.hostname;

  // GitHub
  if (hostname.includes("github.com")) {
    const repoDesc = document.querySelector('[itemprop="about"], .f4.my-3');
    const topics = Array.from(document.querySelectorAll('.topic-tag')).map(t => t.textContent?.trim()).filter(Boolean);
    return {
      description: repoDesc?.textContent?.trim() || "",
      topics: topics.join(" ")
    };
  }

  // Twitter/X
  if (hostname.includes("twitter.com") || hostname.includes("x.com")) {
    const tweetText = document.querySelector('[data-testid="tweetText"]');
    return {
      text: tweetText?.textContent?.trim() || ""
    };
  }

  // Reddit
  if (hostname.includes("reddit.com")) {
    const postTitle = document.querySelector('h1');
    const postContent = document.querySelector('[data-click-id="text"]');
    return {
      title: postTitle?.textContent?.trim() || "",
      text: postContent?.textContent?.trim() || ""
    };
  }

  return null;
}

/**
 * Extract and send page content to background script.
 */
function extractAndSendContent() {
  // Get base content
  let title = document.title;
  let text = extractPageText();
  const description = extractDescription();
  const canonicalUrl = extractCanonicalUrl();

  // Check for YouTube-specific metadata
  const ytMetadata = extractYouTubeMetadata();
  if (ytMetadata) {
    // Use cleaner YouTube title
    if (ytMetadata.title) {
      title = ytMetadata.title;
    }
    // Build rich text from YouTube metadata
    const parts = [];
    if (ytMetadata.title) parts.push(ytMetadata.title);
    if (ytMetadata.channel) parts.push(`Channel: ${ytMetadata.channel}`);
    if (ytMetadata.description) parts.push(ytMetadata.description);
    if (ytMetadata.keywords) parts.push(ytMetadata.keywords);
    text = parts.join(" | ");
  } else {
    // Check for other site-specific metadata
    const siteMetadata = extractSiteMetadata();
    if (siteMetadata) {
      const parts = [title];
      if (siteMetadata.description) parts.push(siteMetadata.description);
      if (siteMetadata.topics) parts.push(siteMetadata.topics);
      if (siteMetadata.text) parts.push(siteMetadata.text);
      if (siteMetadata.title && siteMetadata.title !== title) {
        parts.unshift(siteMetadata.title);
      }
      // Prepend metadata to extracted text
      text = parts.join(" | ") + " " + text;
    } else if (description) {
      // Prepend description to text for better keyword extraction
      text = description + " " + text;
    }
  }

  const data = {
    title,
    text,
    description,
    canonicalUrl,
    url: window.location.href
  };

  // Limit text size
  if (data.text.length > 10000) {
    data.text = data.text.slice(0, 10000);
  }

  chrome.runtime.sendMessage({
    type: "CONTENT_EXTRACTED",
    data
  }).catch(() => {
    // Extension context may be invalidated
  });
}

// Listen for extraction requests from background
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "EXTRACT_CONTENT") {
    extractAndSendContent();
    sendResponse({ success: true });
  }
});

// Extract content when page is fully loaded
if (document.readyState === "complete") {
  extractAndSendContent();
} else {
  window.addEventListener("load", extractAndSendContent);
}
