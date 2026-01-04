/**
 * Background service worker for Weft extension.
 * Handles tab tracking, navigation events, and content script communication.
 */

import { canonicalizeUrl, normalizeDomain, generateTabId, isHttpUrl } from "./lib/url.js";
import { extractKeywords, tokenize, simhashFromTokens } from "./lib/text.js";
import {
  openDB,
  saveTab,
  getTab,
  getTabByChromeId,
  getTabByCanonicalUrl,
  getAllTabs,
  saveNavigation,
  getAllNavigations,
  getAllEdges,
  getAllGroups,
  saveEdges,
  saveGroups,
  clearEdges,
  clearGroups,
  getGraphData
} from "./lib/storage.js";

// Track per-tab navigation sessions to avoid duplicate edges
// Key: chromeTabId, Value: { visitedUrls: Set, lastUrl: string }
const tabSessions = new Map();
import {
  buildSimilarityMatrix,
  buildEdges,
  buildNavigationEdges,
  buildGroups,
  dedupeTabs,
  computeIdf,
  labelGroup,
  DEFAULT_OPTIONS
} from "./lib/clustering.js";

// Initialize database and capture existing tabs on startup
openDB().then(async () => {
  console.log("[Weft] Database initialized");
  await captureExistingTabs();
});

// ============ CAPTURE EXISTING TABS ============

/**
 * Get or create a tab entry, deduping by canonical URL.
 * If a tab with the same canonical URL exists, update it with the new chrome tab ID.
 * @param {string} url - Tab URL
 * @param {number} chromeTabId - Chrome tab ID
 * @param {string} title - Tab title
 * @returns {Promise<Object>} - Tab entry
 */
async function getOrCreateTab(url, chromeTabId, title = "") {
  const canonical = canonicalizeUrl(url);

  // First check if we already have a tab with this canonical URL
  let existing = await getTabByCanonicalUrl(canonical);
  if (existing) {
    // Update with new chrome tab ID (this page is now open in this tab)
    existing.chromeTabId = chromeTabId;
    existing.closedAt = null; // Re-opened
    if (title) existing.title = title;
    await saveTab(existing);
    return existing;
  }

  // Check if this chrome tab was previously tracking a different URL
  const previousTab = await getTabByChromeId(chromeTabId);
  if (previousTab && previousTab.canonicalUrl !== canonical) {
    // Clear chromeTabId from old entry - that page is no longer open in this tab
    previousTab.chromeTabId = null;
    await saveTab(previousTab);
  }

  // Create new tab entry for this URL
  const tabData = {
    id: generateTabId(url),
    url: url,
    canonicalUrl: canonical,
    title: title,
    domain: normalizeDomain(url),
    keywords: [],
    simhash: null,
    text: "",
    createdAt: Date.now(),
    closedAt: null,
    source: "live",
    chromeTabId: chromeTabId,
    groupId: null
  };

  await saveTab(tabData);
  return tabData;
}

/**
 * Capture all currently open tabs on extension startup/install.
 */
async function captureExistingTabs() {
  try {
    const tabs = await chrome.tabs.query({});
    console.log(`[Weft] Capturing ${tabs.length} existing tabs...`);

    for (const tab of tabs) {
      if (!tab.url || !isHttpUrl(tab.url)) continue;

      // Get or create tab entry (deduped by canonical URL)
      const tabData = await getOrCreateTab(tab.url, tab.id, tab.title);

      // Initialize tab session for navigation tracking
      const canonical = canonicalizeUrl(tab.url);
      tabSessions.set(tab.id, {
        visitedUrls: new Set([canonical]),
        lastUrl: canonical
      });

      // Try to extract content from the tab
      try {
        await chrome.tabs.sendMessage(tab.id, { type: "EXTRACT_CONTENT" });
      } catch (e) {
        // Content script may not be injected yet, inject it manually
        try {
          await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: ["content.js"]
          });
          // Give it a moment to run, then request extraction
          setTimeout(() => {
            chrome.tabs.sendMessage(tab.id, { type: "EXTRACT_CONTENT" }).catch(() => {});
          }, 500);
        } catch (injectErr) {
          // Can't inject into this tab (chrome://, etc.)
        }
      }
    }

    console.log("[Weft] Existing tabs captured");
  } catch (e) {
    console.error("[Weft] Failed to capture existing tabs:", e);
  }
}

// ============ TAB LIFECYCLE ============

/**
 * Handle tab creation.
 */
chrome.tabs.onCreated.addListener(async (tab) => {
  if (!tab.url || !isHttpUrl(tab.url)) return;

  // Get or create tab (deduped by canonical URL)
  const tabData = await getOrCreateTab(tab.url, tab.id, tab.title);

  // Initialize tab session
  const canonical = canonicalizeUrl(tab.url);
  tabSessions.set(tab.id, {
    visitedUrls: new Set([canonical]),
    lastUrl: canonical
  });

  console.log("[Weft] Tab created:", tabData.id);
});

/**
 * Handle tab updates (URL change, title change, page load).
 * This also handles SPA navigation where URLs change via History API.
 */
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  // Track URL changes (important for SPAs that use History API)
  if (changeInfo.url && isHttpUrl(changeInfo.url)) {
    const newCanonical = canonicalizeUrl(changeInfo.url);
    let session = tabSessions.get(tabId);

    if (session && session.lastUrl && session.lastUrl !== newCanonical) {
      // URL changed - this is a navigation (likely SPA)
      if (!session.visitedUrls.has(newCanonical)) {
        // New URL, create navigation edge
        await saveNavigation({
          sourceTabId: tabId,
          sourceUrl: session.lastUrl,
          targetUrl: newCanonical,
          timestamp: Date.now(),
          transitionType: "spa_navigation"
        });
        console.log("[Weft] SPA Navigation tracked:", session.lastUrl, "->", newCanonical);
      }
      session.visitedUrls.add(newCanonical);
      session.lastUrl = newCanonical;
    } else if (!session) {
      // Initialize session for this tab
      session = { visitedUrls: new Set([newCanonical]), lastUrl: newCanonical };
      tabSessions.set(tabId, session);
    }
  }

  // Only process tab data when page is complete
  if (changeInfo.status !== "complete") return;
  if (!tab.url || !isHttpUrl(tab.url)) return;

  const canonical = canonicalizeUrl(tab.url);

  // Get or create tab (deduped by canonical URL)
  const tabData = await getOrCreateTab(tab.url, tabId, tab.title);

  // Update tab data
  tabData.url = tab.url;
  tabData.canonicalUrl = canonical;
  tabData.title = tab.title || tabData.title;
  tabData.domain = normalizeDomain(tab.url);
  await saveTab(tabData);

  // Ensure session exists and is updated
  let session = tabSessions.get(tabId);
  if (!session) {
    session = { visitedUrls: new Set(), lastUrl: null };
    tabSessions.set(tabId, session);
  }
  session.visitedUrls.add(canonical);
  session.lastUrl = canonical;

  // Request content extraction from content script
  try {
    chrome.tabs.sendMessage(tabId, { type: "EXTRACT_CONTENT" });
  } catch (e) {
    // Content script may not be loaded yet
  }
});

/**
 * Handle tab closure.
 */
chrome.tabs.onRemoved.addListener(async (tabId) => {
  // Clean up tab session
  tabSessions.delete(tabId);

  const existingTab = await getTabByChromeId(tabId);
  if (existingTab) {
    existingTab.closedAt = Date.now();
    existingTab.chromeTabId = null; // Clear chrome ID since tab is closed
    await saveTab(existingTab);
    console.log("[Weft] Tab closed:", existingTab.id);
  }
});

// ============ NAVIGATION TRACKING ============

/**
 * Capture source URL before navigation happens.
 * This is crucial because by the time onCommitted fires, the tab URL has already changed.
 */
chrome.webNavigation.onBeforeNavigate.addListener(async (details) => {
  if (details.frameId !== 0) return;

  try {
    const tab = await chrome.tabs.get(details.tabId);
    if (tab && tab.url && isHttpUrl(tab.url)) {
      const canonical = canonicalizeUrl(tab.url);
      let session = tabSessions.get(details.tabId);
      if (!session) {
        session = { visitedUrls: new Set([canonical]), lastUrl: canonical };
        tabSessions.set(details.tabId, session);
      } else if (!session.lastUrl) {
        // Update lastUrl if it wasn't set
        session.lastUrl = canonical;
        session.visitedUrls.add(canonical);
      }
      console.log("[Weft] onBeforeNavigate - captured source:", canonical);
    }
  } catch (e) {
    // Tab might not exist
  }
});

/**
 * Track navigation events to create navigation edges.
 * Skips back/forward navigations and already-visited URLs in session.
 */
chrome.webNavigation.onCommitted.addListener(async (details) => {
  // Only track main frame navigations
  if (details.frameId !== 0) return;

  console.log("[Weft] onCommitted:", details.url, "transition:", details.transitionType, "qualifiers:", details.transitionQualifiers);

  // Skip back/forward navigations
  if (details.transitionQualifiers && details.transitionQualifiers.includes("forward_back")) {
    console.log("[Weft] Skipping back/forward navigation");
    return;
  }

  // Track user-initiated navigations (link clicks, typed URLs, form submissions, JS navigations)
  const trackableTypes = ["link", "typed", "form_submit", "auto_bookmark", "generated"];
  if (!trackableTypes.includes(details.transitionType)) {
    console.log("[Weft] Skipping non-trackable transition type:", details.transitionType);
    return;
  }

  if (!isHttpUrl(details.url)) return;

  const canonical = canonicalizeUrl(details.url);

  // Get session (should have been initialized by onBeforeNavigate)
  let session = tabSessions.get(details.tabId);
  if (!session) {
    session = { visitedUrls: new Set(), lastUrl: null };
    tabSessions.set(details.tabId, session);
  }

  // Skip if we've already visited this URL in this session
  if (session.visitedUrls.has(canonical)) {
    console.log("[Weft] Already visited:", canonical);
    session.lastUrl = canonical;
    return;
  }

  // Get the source URL from session
  const sourceUrl = session.lastUrl;
  console.log("[Weft] Source URL:", sourceUrl, "-> Target:", canonical);

  if (sourceUrl && sourceUrl !== canonical) {
    // This is a genuine new navigation
    await saveNavigation({
      sourceTabId: details.tabId,
      sourceUrl: sourceUrl,
      targetUrl: canonical,
      timestamp: Date.now(),
      transitionType: details.transitionType
    });
    console.log("[Weft] Navigation tracked:", sourceUrl, "->", canonical);
  }

  // Update session
  session.visitedUrls.add(canonical);
  session.lastUrl = canonical;
});

// ============ CONTENT SCRIPT COMMUNICATION ============

/**
 * Handle messages from content scripts.
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "CONTENT_EXTRACTED") {
    handleContentExtracted(sender.tab?.id, message.data);
    sendResponse({ success: true });
    return false;
  } else if (message.type === "REBUILD_GRAPH") {
    rebuildGraph().then((result) => sendResponse(result)).catch(e => sendResponse({ success: false, error: e.message }));
    return true; // Keep channel open for async response
  } else if (message.type === "GET_GRAPH_DATA") {
    getSerializableGraphData().then((data) => sendResponse(data)).catch(e => sendResponse({ tabs: [], edges: [], groups: [] }));
    return true;
  } else if (message.type === "IMPORT_GRAPH") {
    importGraph(message.data).then((result) => sendResponse(result)).catch(e => sendResponse({ success: false, error: e.message }));
    return true;
  } else if (message.type === "EXPORT_GRAPH") {
    exportGraph().then((data) => sendResponse(data)).catch(e => sendResponse(null));
    return true;
  }
  return false;
});

/**
 * Get graph data with BigInt converted to strings for serialization.
 */
async function getSerializableGraphData() {
  const { tabs, edges, groups } = await getGraphData();

  // Convert BigInt simhash to string for serialization
  const serializableTabs = tabs.map(tab => ({
    ...tab,
    simhash: tab.simhash !== null && tab.simhash !== undefined ? tab.simhash.toString() : null
  }));

  return { tabs: serializableTabs, edges, groups };
}

/**
 * Handle extracted content from content script.
 */
async function handleContentExtracted(chromeTabId, data) {
  if (!chromeTabId) return;

  const tab = await getTabByChromeId(chromeTabId);
  if (!tab) return;

  const { title, text, canonicalUrl } = data;

  // Update tab with extracted content
  tab.title = title || tab.title;
  tab.text = text?.slice(0, 5000) || ""; // Limit stored text

  if (canonicalUrl) {
    tab.canonicalUrl = canonicalizeUrl(canonicalUrl);
  }

  // Extract keywords from title + text
  const inputText = `${tab.title} ${tab.text}`;
  tab.keywords = extractKeywords(inputText, 8);

  // Compute tokens and simhash
  const tokens = tokenize(inputText);
  tab.simhash = simhashFromTokens(tokens);

  await saveTab(tab);
  console.log("[Weft] Content processed for:", tab.id, "keywords:", tab.keywords);
}

// ============ GRAPH BUILDING ============

/**
 * Rebuild the entire graph from stored tabs.
 */
async function rebuildGraph() {
  console.log("[Weft] Rebuilding graph...");

  const tabs = await getAllTabs();
  const navigations = await getAllNavigations();

  if (tabs.length === 0) {
    return { success: true, stats: { tabs: 0, groups: 0, edges: 0 } };
  }

  // Filter to non-duplicate tabs
  const { primaryMap, duplicates } = dedupeTabs(tabs, DEFAULT_OPTIONS.dedupeHamming);
  const primaryTabs = tabs.filter(t => !t.duplicateOf);

  // Build similarity matrix
  const matrix = buildSimilarityMatrix(primaryTabs, DEFAULT_OPTIONS.domainBonus);

  // Build similarity edges
  const similarityEdges = buildEdges(primaryTabs, matrix, DEFAULT_OPTIONS.edgeThreshold);

  // Build navigation edges
  const navEdges = buildNavigationEdges(navigations, tabs);

  // Combine edges (dedupe by source+target)
  const edgeMap = new Map();
  for (const edge of [...similarityEdges, ...navEdges]) {
    const key = `${edge.source}-${edge.target}`;
    const reverseKey = `${edge.target}-${edge.source}`;
    if (!edgeMap.has(key) && !edgeMap.has(reverseKey)) {
      edgeMap.set(key, edge);
    } else {
      // If navigation edge exists, prefer it (stronger signal)
      const existing = edgeMap.get(key) || edgeMap.get(reverseKey);
      if (edge.reason === "navigation" && existing.reason !== "navigation") {
        edgeMap.set(key, edge);
      }
    }
  }
  const allEdges = Array.from(edgeMap.values());

  // Build groups
  const { groups, tabToGroup } = buildGroups(primaryTabs, matrix, DEFAULT_OPTIONS);

  // Compute IDF for labeling
  const docs = primaryTabs.map(t => t.keywords || []);
  const idf = computeIdf(docs);

  // Label groups
  for (const group of groups) {
    const groupTabs = group.tabIds.map(id => tabs.find(t => t.id === id)).filter(Boolean);
    group.label = labelGroup(groupTabs, idf);
  }

  // Update tab group assignments
  for (const tab of tabs) {
    const primaryId = primaryMap.get(tab.id) || tab.id;
    tab.groupId = tabToGroup.get(primaryId) || null;
    await saveTab(tab);
  }

  // Clear and save edges
  await clearEdges();
  await saveEdges(allEdges);

  // Clear and save groups
  await clearGroups();
  await saveGroups(groups);

  const stats = {
    tabs: tabs.length,
    primaryTabs: primaryTabs.length,
    duplicates,
    groups: groups.length,
    edges: allEdges.length,
    navigationEdges: navEdges.length,
    similarityEdges: similarityEdges.length
  };

  console.log("[Weft] Graph rebuilt:", stats);
  return { success: true, stats };
}

// ============ IMPORT/EXPORT ============

/**
 * Import a weft graph JSON file.
 */
async function importGraph(data) {
  try {
    const { tabs, groups, edges } = data;

    // Import tabs
    for (const tab of tabs || []) {
      const importedTab = {
        id: `import_${tab.id}`,
        url: tab.url,
        canonicalUrl: tab.canonical_url || canonicalizeUrl(tab.url),
        title: tab.title,
        domain: tab.domain || normalizeDomain(tab.url),
        keywords: tab.keywords || [],
        simhash: tab.simhash ? BigInt(tab.simhash) : null,
        text: tab.text_excerpt || "",
        createdAt: Date.now(),
        closedAt: null,
        source: "import",
        chromeTabId: null,
        groupId: tab.group_id != null ? `import_group_${tab.group_id}` : null
      };
      await saveTab(importedTab);
    }

    // Import groups
    for (const group of groups || []) {
      const importedGroup = {
        id: `import_group_${group.id}`,
        label: group.label,
        tabIds: (group.tab_ids || []).map(id => `import_${id}`),
        size: group.size
      };
      await saveGroups([importedGroup]);
    }

    // Import edges
    const importedEdges = (edges || []).map(edge => ({
      source: `import_${edge.source}`,
      target: `import_${edge.target}`,
      weight: edge.weight,
      reason: edge.reason
    }));
    await saveEdges(importedEdges);

    return { success: true, imported: { tabs: tabs?.length || 0, groups: groups?.length || 0, edges: edges?.length || 0 } };
  } catch (e) {
    console.error("[Weft] Import failed:", e);
    return { success: false, error: e.message };
  }
}

/**
 * Export graph to weft-compatible JSON format.
 */
async function exportGraph() {
  const { tabs, edges, groups } = await getGraphData();

  // Convert to weft format
  const exportData = {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    source: "weft-extension",
    stats: {
      tab_count: tabs.length,
      group_count: groups.length,
      edge_count: edges.length
    },
    tabs: tabs.map((t, idx) => ({
      id: idx,
      url: t.url,
      title: t.title,
      domain: t.domain,
      canonical_url: t.canonicalUrl,
      keywords: t.keywords,
      simhash: t.simhash ? t.simhash.toString() : null,
      group_id: t.groupId ? parseInt(t.groupId.replace(/\D/g, "")) : null,
      source: t.source
    })),
    groups: groups.map((g, idx) => ({
      id: idx,
      label: g.label,
      tab_ids: g.tabIds.map(id => tabs.findIndex(t => t.id === id)).filter(i => i >= 0),
      size: g.size
    })),
    edges: edges.map(e => ({
      source: tabs.findIndex(t => t.id === e.source),
      target: tabs.findIndex(t => t.id === e.target),
      weight: e.weight,
      reason: e.reason
    })).filter(e => e.source >= 0 && e.target >= 0)
  };

  return exportData;
}

// ============ SIDE PANEL ============

/**
 * Open side panel when extension icon is clicked.
 */
chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ tabId: tab.id });
});

// Enable side panel on all tabs
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });

console.log("[Weft] Background service worker started");
