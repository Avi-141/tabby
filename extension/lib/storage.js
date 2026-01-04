/**
 * IndexedDB storage layer for tabs, edges, groups, and navigations.
 */

const DB_NAME = "weft";
const DB_VERSION = 1;

let dbPromise = null;

/**
 * Open and initialize the IndexedDB database.
 * @returns {Promise<IDBDatabase>}
 */
export async function openDB() {
  if (dbPromise) return dbPromise;

  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => reject(request.error);

    request.onsuccess = () => resolve(request.result);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;

      // Tabs store
      if (!db.objectStoreNames.contains("tabs")) {
        const tabStore = db.createObjectStore("tabs", { keyPath: "id" });
        tabStore.createIndex("url", "url", { unique: false });
        tabStore.createIndex("canonicalUrl", "canonicalUrl", { unique: false });
        tabStore.createIndex("domain", "domain", { unique: false });
        tabStore.createIndex("chromeTabId", "chromeTabId", { unique: false });
        tabStore.createIndex("groupId", "groupId", { unique: false });
        tabStore.createIndex("createdAt", "createdAt", { unique: false });
        tabStore.createIndex("source", "source", { unique: false });
      }

      // Edges store
      if (!db.objectStoreNames.contains("edges")) {
        const edgeStore = db.createObjectStore("edges", { keyPath: "id", autoIncrement: true });
        edgeStore.createIndex("source", "source", { unique: false });
        edgeStore.createIndex("target", "target", { unique: false });
        edgeStore.createIndex("reason", "reason", { unique: false });
      }

      // Groups store
      if (!db.objectStoreNames.contains("groups")) {
        const groupStore = db.createObjectStore("groups", { keyPath: "id" });
        groupStore.createIndex("label", "label", { unique: false });
      }

      // Navigations store (for tracking link clicks)
      if (!db.objectStoreNames.contains("navigations")) {
        const navStore = db.createObjectStore("navigations", { keyPath: "id", autoIncrement: true });
        navStore.createIndex("sourceTabId", "sourceTabId", { unique: false });
        navStore.createIndex("targetUrl", "targetUrl", { unique: false });
        navStore.createIndex("timestamp", "timestamp", { unique: false });
      }

      // Settings store
      if (!db.objectStoreNames.contains("settings")) {
        db.createObjectStore("settings", { keyPath: "key" });
      }
    };
  });

  return dbPromise;
}

/**
 * Generic transaction helper.
 * @param {string} storeName - Object store name
 * @param {string} mode - "readonly" or "readwrite"
 * @param {Function} callback - Function receiving the object store
 * @returns {Promise<any>}
 */
async function withStore(storeName, mode, callback) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, mode);
    const store = tx.objectStore(storeName);
    const result = callback(store);

    tx.oncomplete = () => resolve(result);
    tx.onerror = () => reject(tx.error);
  });
}

/**
 * Generic get-all-from-store helper.
 * @param {string} storeName - Object store name
 * @returns {Promise<any[]>}
 */
async function getAll(storeName) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readonly");
    const store = tx.objectStore(storeName);
    const request = store.getAll();

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

// ============ TABS ============

/**
 * Save a tab to the database.
 * @param {Object} tab - Tab object
 * @returns {Promise<void>}
 */
export async function saveTab(tab) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("tabs", "readwrite");
    const store = tx.objectStore("tabs");
    store.put(tab);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/**
 * Get a tab by ID.
 * @param {string} id - Tab ID
 * @returns {Promise<Object|null>}
 */
export async function getTab(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("tabs", "readonly");
    const store = tx.objectStore("tabs");
    const request = store.get(id);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Get a tab by Chrome tab ID.
 * @param {number} chromeTabId - Chrome's tab ID
 * @returns {Promise<Object|null>}
 */
export async function getTabByChromeId(chromeTabId) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("tabs", "readonly");
    const store = tx.objectStore("tabs");
    const index = store.index("chromeTabId");
    const request = index.get(chromeTabId);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Get a tab by canonical URL.
 * @param {string} canonicalUrl - Canonical URL
 * @returns {Promise<Object|null>}
 */
export async function getTabByCanonicalUrl(canonicalUrl) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("tabs", "readonly");
    const store = tx.objectStore("tabs");
    const index = store.index("canonicalUrl");
    const request = index.get(canonicalUrl);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Get all tabs.
 * @returns {Promise<Object[]>}
 */
export async function getAllTabs() {
  return getAll("tabs");
}

/**
 * Get tabs by source (live or import).
 * @param {string} source - "live" or "import"
 * @returns {Promise<Object[]>}
 */
export async function getTabsBySource(source) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("tabs", "readonly");
    const store = tx.objectStore("tabs");
    const index = store.index("source");
    const request = index.getAll(source);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Delete a tab by ID.
 * @param {string} id - Tab ID
 * @returns {Promise<void>}
 */
export async function deleteTab(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("tabs", "readwrite");
    const store = tx.objectStore("tabs");
    store.delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/**
 * Update tab's group assignment.
 * @param {string} tabId - Tab ID
 * @param {string} groupId - Group ID
 * @returns {Promise<void>}
 */
export async function updateTabGroup(tabId, groupId) {
  const tab = await getTab(tabId);
  if (tab) {
    tab.groupId = groupId;
    await saveTab(tab);
  }
}

// ============ EDGES ============

/**
 * Save an edge to the database.
 * @param {Object} edge - Edge object
 * @returns {Promise<void>}
 */
export async function saveEdge(edge) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("edges", "readwrite");
    const store = tx.objectStore("edges");
    store.put(edge);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/**
 * Save multiple edges at once.
 * @param {Object[]} edges - Array of edge objects
 * @returns {Promise<void>}
 */
export async function saveEdges(edges) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("edges", "readwrite");
    const store = tx.objectStore("edges");
    for (const edge of edges) {
      store.put(edge);
    }
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/**
 * Get all edges.
 * @returns {Promise<Object[]>}
 */
export async function getAllEdges() {
  return getAll("edges");
}

/**
 * Clear all edges.
 * @returns {Promise<void>}
 */
export async function clearEdges() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("edges", "readwrite");
    const store = tx.objectStore("edges");
    store.clear();
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// ============ GROUPS ============

/**
 * Save a group to the database.
 * @param {Object} group - Group object
 * @returns {Promise<void>}
 */
export async function saveGroup(group) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("groups", "readwrite");
    const store = tx.objectStore("groups");
    store.put(group);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/**
 * Save multiple groups at once.
 * @param {Object[]} groups - Array of group objects
 * @returns {Promise<void>}
 */
export async function saveGroups(groups) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("groups", "readwrite");
    const store = tx.objectStore("groups");
    for (const group of groups) {
      store.put(group);
    }
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/**
 * Get all groups.
 * @returns {Promise<Object[]>}
 */
export async function getAllGroups() {
  return getAll("groups");
}

/**
 * Clear all groups.
 * @returns {Promise<void>}
 */
export async function clearGroups() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("groups", "readwrite");
    const store = tx.objectStore("groups");
    store.clear();
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// ============ NAVIGATIONS ============

/**
 * Save a navigation event.
 * @param {Object} nav - Navigation object {sourceTabId, targetUrl, timestamp}
 * @returns {Promise<void>}
 */
export async function saveNavigation(nav) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("navigations", "readwrite");
    const store = tx.objectStore("navigations");
    store.put(nav);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/**
 * Get all navigations.
 * @returns {Promise<Object[]>}
 */
export async function getAllNavigations() {
  return getAll("navigations");
}

/**
 * Clear all navigations.
 * @returns {Promise<void>}
 */
export async function clearNavigations() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("navigations", "readwrite");
    const store = tx.objectStore("navigations");
    store.clear();
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// ============ SETTINGS ============

/**
 * Get a setting value.
 * @param {string} key - Setting key
 * @param {any} defaultValue - Default value if not found
 * @returns {Promise<any>}
 */
export async function getSetting(key, defaultValue = null) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("settings", "readonly");
    const store = tx.objectStore("settings");
    const request = store.get(key);
    request.onsuccess = () => {
      const result = request.result;
      resolve(result ? result.value : defaultValue);
    };
    request.onerror = () => reject(request.error);
  });
}

/**
 * Set a setting value.
 * @param {string} key - Setting key
 * @param {any} value - Setting value
 * @returns {Promise<void>}
 */
export async function setSetting(key, value) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("settings", "readwrite");
    const store = tx.objectStore("settings");
    store.put({ key, value });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// ============ BULK OPERATIONS ============

/**
 * Clear all data from the database.
 * @returns {Promise<void>}
 */
export async function clearAll() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const stores = ["tabs", "edges", "groups", "navigations"];
    const tx = db.transaction(stores, "readwrite");

    for (const storeName of stores) {
      tx.objectStore(storeName).clear();
    }

    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/**
 * Get full graph data (tabs, edges, groups).
 * @returns {Promise<{tabs: Object[], edges: Object[], groups: Object[]}>}
 */
export async function getGraphData() {
  const [tabs, edges, groups] = await Promise.all([
    getAllTabs(),
    getAllEdges(),
    getAllGroups()
  ]);
  return { tabs, edges, groups };
}
