// WeSign Auto Sync - Background Service Worker (Manifest V3)

const DEFAULT_SETTINGS = {
  renderUrl: "https://tool-link-wesig.onrender.com",
  localUrl: "http://localhost:5050",
  syncToRender: true,
  syncToLocal: true,
  lastSyncTime: null,
  lastSyncedToken: "",
  lastSyncedCookie: "",
  lastSyncTimestamp: 0,
  totalSyncCount: 0,
  cookieCount: 0,
  cookieKeys: [],
  tokenUser: "",
  tokenExp: "",
  lastSyncStatus: ""
};

// Khởi tạo cài đặt ban đầu
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(DEFAULT_SETTINGS, (items) => {
    chrome.storage.local.set(items);
  });
  console.log("[WeSign Auto Sync] Đã cài đặt extension v1.1.0 thành công!");
});

// Hàm thu thập TOÀN BỘ cookie liên quan đến MISA từ mọi URL và Domain
async function getAllMisaCookies() {
  const cookieMap = new Map();

  // 1. Quét theo các URL chính của WeSign và MISA
  const urlsToScan = [
    "https://amisapp.misa.vn/",
    "https://amisapp.misa.vn/wesign/",
    "https://amisapp.misa.vn/wesign/home",
    "https://id.misa.vn/",
    "https://misa.vn/"
  ];

  for (const u of urlsToScan) {
    try {
      const list = await chrome.cookies.getAll({ url: u });
      if (list && list.length > 0) {
        list.forEach(c => {
          if (c.name && c.value) cookieMap.set(c.name, c.value);
        });
      }
    } catch (e) {
      console.warn("[WeSign Auto Sync] Lỗi quét cookie URL:", u, e);
    }
  }

  // 2. Quét theo các Domain và Subdomain của MISA
  const domainsToScan = [
    "amisapp.misa.vn",
    ".amisapp.misa.vn",
    "misa.vn",
    ".misa.vn",
    "id.misa.vn",
    ".id.misa.vn"
  ];

  for (const d of domainsToScan) {
    try {
      const list = await chrome.cookies.getAll({ domain: d });
      if (list && list.length > 0) {
        list.forEach(c => {
          if (c.name && c.value && !cookieMap.has(c.name)) {
            cookieMap.set(c.name, c.value);
          }
        });
      }
    } catch (e) {
      console.warn("[WeSign Auto Sync] Lỗi quét cookie Domain:", d, e);
    }
  }

  return cookieMap;
}

// Giải mã thông tin từ JWT Token
function decodeJwt(token) {
  if (!token) return {};
  try {
    const parts = token.split(".");
    if (parts.length >= 2) {
      const padded = parts[1] + "=".repeat((4 - (parts[1].length % 4)) % 4);
      const decoded = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
      return JSON.parse(decoded);
    }
  } catch (e) {}
  return {};
}

// Trích xuất Token và Cookie từ tab MISA WeSign đang mở
async function extractFromMisaTab(tabId) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: () => {
        let token = null;
        let tenantId = null;

        // 1. Quét localStorage
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          const val = localStorage.getItem(key);
          if (!val) continue;

          if (typeof val === "string" && val.startsWith("eyJ") && val.includes(".")) {
            token = val;
            break;
          }

          if (typeof val === "string" && val.startsWith("{") && val.includes("access_token")) {
            try {
              const obj = JSON.parse(val);
              if (obj.access_token && typeof obj.access_token === "string" && obj.access_token.startsWith("eyJ")) {
                token = obj.access_token;
                break;
              }
            } catch (e) {}
          }
        }

        // 2. Quét sessionStorage
        if (!token) {
          for (let i = 0; i < sessionStorage.length; i++) {
            const key = sessionStorage.key(i);
            const val = sessionStorage.getItem(key);
            if (!val) continue;

            if (typeof val === "string" && val.startsWith("eyJ") && val.includes(".")) {
              token = val;
              break;
            }

            if (typeof val === "string" && val.startsWith("{") && val.includes("access_token")) {
              try {
                const obj = JSON.parse(val);
                if (obj.access_token && typeof obj.access_token === "string" && obj.access_token.startsWith("eyJ")) {
                  token = obj.access_token;
                  break;
                }
              } catch (e) {}
            }
          }
        }

        return {
          token: token,
          docCookie: document.cookie || ""
        };
      }
    });

    if (results && results[0] && results[0].result) {
      return results[0].result;
    }
  } catch (e) {
    console.warn("[WeSign Auto Sync] Lỗi script injection:", e);
  }
  return { token: null, docCookie: "" };
}

// Gửi cấu hình về Web Tool (Render hoặc Localhost)
// Timeout 40 giây để xử lý Render cold-start khi đang ngủ
async function postConfigToTool(baseUrl, payload) {
  try {
    const cleanUrl = baseUrl.replace(/\/+$/, "") + "/api/config";
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 40000);

    const res = await fetch(cleanUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    if (res.ok) {
      const data = await res.json();
      return { success: data.success === true, message: data.message || "OK" };
    }
    return { success: false, message: `Lỗi HTTP ${res.status}` };
  } catch (err) {
    const isTimeout = err.name === "AbortError";
    return { 
      success: false, 
      message: isTimeout ? "Quá thời gian chờ (Server Render đang thức dậy, vui lòng thử lại)" : err.message 
    };
  }
}

// Khóa chống gửi trùng lặp
let isSyncing = false;

// Xử lý và gửi Token & Cookie về Tool
async function processAndSync(token, tenantId, deviceId, extraCookies, folderId, isForced = false) {
  if (isSyncing && !isForced) return { success: false, message: "Đang đồng bộ..." };

  isSyncing = true;
  try {
    const settings = await chrome.storage.local.get(DEFAULT_SETTINGS);
    const now = Date.now();
    const storedToken = settings.lastSyncedToken || "";
    const storedCookie = settings.lastSyncedCookie || "";
    const lastTimestamp = settings.lastSyncTimestamp || 0;

    // 1. Quét cookie toàn diện
    const cookieMap = await getAllMisaCookies();

    // Bổ sung cookie từ header hoặc document.cookie nếu có
    if (extraCookies) {
      extraCookies.split(";").forEach(pair => {
        const idx = pair.indexOf("=");
        if (idx > 0) {
          const k = pair.substring(0, idx).trim();
          const v = pair.substring(idx + 1).trim();
          if (k && v && !cookieMap.has(k)) cookieMap.set(k, v);
        }
      });
    }

    let fullCookieStr = Array.from(cookieMap.entries())
      .map(([k, v]) => `${k}=${v}`)
      .join("; ");

    // Nếu không lấy được cookie mới, giữ lại cookie cũ đang hoạt động
    if (!fullCookieStr && storedCookie) {
      fullCookieStr = storedCookie;
    }

    const currentToken = token || storedToken;
    if (!currentToken) {
      return { success: false, message: "Chưa tìm thấy Token đăng nhập MISA WeSign." };
    }

    // Nếu không cưỡng bức và cả token & cookie đều không đổi và vừa sync dưới 5 phút -> bỏ qua
    if (!isForced && currentToken === storedToken && fullCookieStr === storedCookie && (now - lastTimestamp < 5 * 60 * 1000)) {
      return { success: true, message: "Dữ liệu Token & Cookie đã được đồng bộ gần đây." };
    }

    // 2. Tự động giải mã tenant_id và thông tin người dùng từ JWT
    const jwtData = decodeJwt(currentToken);
    if (!tenantId && jwtData.tenantid) tenantId = jwtData.tenantid;
    if (!deviceId && cookieMap.has("deviceId")) deviceId = cookieMap.get("deviceId");
    if (!deviceId && jwtData.sessionid) deviceId = jwtData.sessionid;

    let tokenUser = jwtData.name || jwtData.username || "";
    let tokenExpStr = "";
    if (jwtData.exp) {
      const expDate = new Date(jwtData.exp * 1000);
      tokenExpStr = expDate.toLocaleTimeString("vi-VN") + " " + expDate.toLocaleDateString("vi-VN");
    }

    const payload = {
      token: currentToken,
      cookie: fullCookieStr,
      source: "extension"
    };
    if (tenantId) payload.tenant_id = tenantId;
    if (deviceId) payload.device_id = deviceId;
    if (folderId) payload.folder_id = folderId;

    let statusLogs = [];
    let successCount = 0;

    // Đồng bộ lên Render
    if (settings.syncToRender && settings.renderUrl) {
      const resRender = await postConfigToTool(settings.renderUrl, payload);
      if (resRender.success) {
        successCount++;
        statusLogs.push("Render: OK");
      } else {
        statusLogs.push(`Render: ${resRender.message}`);
      }
    }

    // Đồng bộ về Localhost
    if (settings.syncToLocal && settings.localUrl) {
      const resLocal = await postConfigToTool(settings.localUrl, payload);
      if (resLocal.success) {
        successCount++;
        statusLogs.push("Local: OK");
      } else {
        statusLogs.push(`Local: ${resLocal.message}`);
      }
    }

    const cookieKeyList = Array.from(cookieMap.keys());

    // Cập nhật trạng thái vào Storage
    const updateData = {
      lastSyncedToken: currentToken,
      lastSyncedCookie: fullCookieStr,
      lastSyncTimestamp: now,
      lastSyncTime: new Date().toLocaleTimeString("vi-VN") + " " + new Date().toLocaleDateString("vi-VN"),
      totalSyncCount: (settings.totalSyncCount || 0) + (successCount > 0 ? 1 : 0),
      cookieCount: cookieKeyList.length,
      cookieKeys: cookieKeyList,
      tokenUser: tokenUser,
      tokenExp: tokenExpStr,
      lastSyncStatus: statusLogs.join(" | ")
    };
    if (tenantId) updateData.tenantId = tenantId;
    if (deviceId) updateData.deviceId = deviceId;

    await chrome.storage.local.set(updateData);

    if (successCount > 0) {
      chrome.action.setBadgeText({ text: "OK" });
      chrome.action.setBadgeBackgroundColor({ color: "#10B981" });

      if (currentToken !== storedToken) {
        try {
          chrome.notifications.create({
            type: "basic",
            iconUrl: "icon48.png",
            title: "WeSign Auto Sync",
            message: `🎉 Đã đồng bộ Token & Cookie WeSign (${cookieKeyList.length} cookies) lên Server thành công!`
          });
        } catch (e) {}
      }

      return {
        success: true,
        message: `Đã đồng bộ thành công (${cookieKeyList.length} cookies)! [${statusLogs.join(" | ")}]`,
        cookieCount: cookieKeyList.length,
        user: tokenUser,
        exp: tokenExpStr
      };
    } else {
      chrome.action.setBadgeText({ text: "ERR" });
      chrome.action.setBadgeBackgroundColor({ color: "#EF4444" });
      return {
        success: false,
        message: `Không thể kết nối đến máy chủ: ${statusLogs.join(" | ")}`
      };
    }
  } finally {
    isSyncing = false;
  }
}

// Lắng nghe các request API thực tế của WeSign để tự động bắt Token
chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    try {
      if (!details.requestHeaders) return;

      let token = null;
      let tenantId = null;
      let deviceId = null;
      let headerCookie = null;
      let folderId = null;

      for (const h of details.requestHeaders) {
        const name = h.name.toLowerCase();
        if (name === "authorization" && h.value && h.value.startsWith("Bearer eyJ")) {
          token = h.value.replace(/^Bearer\s+/i, "").trim();
        } else if (name === "x-tenantid" || name === "tenantid" || name === "x-misa-ws-database-tenantid") {
          tenantId = h.value.trim();
        } else if (name === "deviceid" || name === "x-deviceid") {
          deviceId = h.value.trim();
        } else if (name === "cookie") {
          headerCookie = h.value.trim();
        } else if (name === "referer") {
          const fm = h.value.match(/\/documents\/(\d{3,10})/);
          if (fm) {
            folderId = parseInt(fm[1]);
          }
        }
      }

      if (token) {
        processAndSync(token, tenantId, deviceId, headerCookie, folderId, false);
      }
    } catch (e) {
      console.error("[WeSign Auto Sync] Lỗi xử lý headers:", e);
    }
  },
  { 
    urls: [
      "*://amisapp.misa.vn/*",
      "*://*.misa.vn/*"
    ] 
  },
  ["requestHeaders", "extraHeaders"]
);

// Xử lý các thông điệp từ giao diện Popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "force_sync_now") {
    (async () => {
      try {
        // 1. Tìm các tab WeSign đang mở
        const tabs = await chrome.tabs.query({ url: "*://amisapp.misa.vn/*" });
        let extractedToken = null;
        let extractedDocCookie = "";

        if (tabs && tabs.length > 0) {
          const extracted = await extractFromMisaTab(tabs[0].id);
          extractedToken = extracted.token;
          extractedDocCookie = extracted.docCookie;
        }

        // 2. Thực hiện đồng bộ cưỡng bức
        const res = await processAndSync(extractedToken, null, null, extractedDocCookie, null, true);

        // Nếu chưa có token trong tab hoặc storage, tải lại tab WeSign để kích hoạt mạng
        if (!res.success && (!tabs || tabs.length === 0)) {
          sendResponse({
            success: false,
            message: "Bạn chưa mở tab MISA WeSign nào. Vui lòng bấm '🔑 Mở MISA WeSign' để đăng nhập trước."
          });
          return;
        }

        if (!extractedToken && tabs && tabs.length > 0) {
          chrome.tabs.reload(tabs[0].id);
        }

        sendResponse(res);
      } catch (err) {
        sendResponse({ success: false, message: `Lỗi đồng bộ: ${err.message}` });
      }
    })();
    return true; // Cho phép async response
  }

  if (request.action === "generate_curl") {
    (async () => {
      const data = await chrome.storage.local.get(DEFAULT_SETTINGS);
      const token = data.lastSyncedToken || "";
      const cookie = data.lastSyncedCookie || "";
      const tenantId = data.tenantId || "c4e3c4ef-a722-40cd-96ed-6aa20a86ee94";

      if (!token) {
        sendResponse({ success: false, message: "Chưa có Token WeSign để tạo cURL." });
        return;
      }

      const curl = `curl --url 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v1/documents/paging/data' \\
  -H 'accept: application/json, text/plain, */*' \\
  -H 'authorization: Bearer ${token}' \\
  -H 'content-type: application/json' \\
  -H 'x-tenantid: ${tenantId}' \\
  -b '${cookie}' \\
  --data-raw '{"folderID":"all","pageIndex":1,"pageSize":10}'`;

      sendResponse({ success: true, curl: curl, cookie: cookie, token: token });
    })();
    return true;
  }
});
