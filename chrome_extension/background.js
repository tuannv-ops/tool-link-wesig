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
  totalSyncCount: 0
};

// Khởi tạo cài đặt ban đầu
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(DEFAULT_SETTINGS, (items) => {
    chrome.storage.local.set(items);
  });
  console.log("[WeSign Auto Sync] Đã cài đặt extension thành công!");
});

// Lắng nghe các request API thực tế của WeSign
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

      // Nếu bắt được Bearer Token hợp lệ
      if (token) {
        handleCapturedToken(token, tenantId, deviceId, headerCookie, folderId);
      }
    } catch (e) {
      console.error("[WeSign Auto Sync] Lỗi xử lý headers:", e);
    }
  },
  { 
    urls: [
      "*://amisapp.misa.vn/wesign/g2/api/*",
      "*://amisapp.misa.vn/wesign/api/*"
    ] 
  },
  ["requestHeaders", "extraHeaders"]
);

// Khóa chống gửi trùng lặp khi nhiều request diễn ra đồng thời
let isSyncing = false;

// Xử lý và gửi Token & Cookie về Tool
function handleCapturedToken(token, tenantId, deviceId, headerCookie, folderId) {
  if (isSyncing) return;

  chrome.storage.local.get(DEFAULT_SETTINGS, async (settings) => {
    const now = Date.now();
    const storedToken = settings.lastSyncedToken || "";
    const storedCookie = settings.lastSyncedCookie || "";
    const lastTimestamp = settings.lastSyncTimestamp || 0;

    isSyncing = true;

    try {
      // 1. Thu thập TOÀN BỘ cookie từ trình duyệt (kết hợp cả url và domain .misa.vn)
      let cookieMap = new Map();

      // Nạp cookie từ header trước
      if (headerCookie) {
        headerCookie.split(";").forEach(pair => {
          const idx = pair.indexOf("=");
          if (idx > 0) {
            const k = pair.substring(0, idx).trim();
            const v = pair.substring(idx + 1).trim();
            if (k && v) cookieMap.set(k, v);
          }
        });
      }

      // Lấy cookie chính xác qua chrome.cookies API
      try {
        const urlCookies = await chrome.cookies.getAll({ url: "https://amisapp.misa.vn" });
        if (urlCookies && urlCookies.length > 0) {
          urlCookies.forEach(c => cookieMap.set(c.name, c.value));
        }
      } catch (err) {}

      try {
        const domainCookies = await chrome.cookies.getAll({ domain: ".misa.vn" });
        if (domainCookies && domainCookies.length > 0) {
          domainCookies.forEach(c => {
            if (!cookieMap.has(c.name)) cookieMap.set(c.name, c.value);
          });
        }
      } catch (err) {}

      let fullCookieStr = Array.from(cookieMap.entries())
        .map(([k, v]) => `${k}=${v}`)
        .join("; ");

      // Nếu cả token và cookie đều không đổi và vừa đồng bộ dưới 10 phút trước -> bỏ qua để tránh spam
      if (token === storedToken && fullCookieStr === storedCookie && (now - lastTimestamp < 10 * 60 * 1000)) {
        return;
      }

      // 2. Tự động giải mã tenant_id từ JWT nếu chưa có
      if (!tenantId && token) {
        try {
          const parts = token.split(".");
          if (parts.length >= 2) {
            const padded = parts[1] + "=".repeat((4 - (parts[1].length % 4)) % 4);
            const decoded = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
            const payloadJson = JSON.parse(decoded);
            if (payloadJson.tenantid) tenantId = payloadJson.tenantid;
          }
        } catch (e) {}
      }

      // Trích xuất deviceId từ cookie nếu header chưa có
      if (!deviceId && cookieMap.has("deviceId")) {
        deviceId = cookieMap.get("deviceId");
      }

      const payload = {
        token: token,
        cookie: fullCookieStr,
        source: "extension"
      };
      if (tenantId) payload.tenant_id = tenantId;
      if (deviceId) payload.device_id = deviceId;
      if (folderId) payload.folder_id = folderId;

      let successCount = 0;

      // Đồng bộ về máy tính cục bộ (Localhost)
      if (settings.syncToLocal && settings.localUrl) {
        const ok = await postConfigToTool(settings.localUrl, payload);
        if (ok) successCount++;
      }

      // Đồng bộ lên Render (nếu bật)
      if (settings.syncToRender && settings.renderUrl) {
        const ok = await postConfigToTool(settings.renderUrl, payload);
        if (ok) successCount++;
      }

      if (successCount > 0) {
        // Lưu Token, Cookie và thời gian vào Storage
        chrome.storage.local.set({
          lastSyncedToken: token,
          lastSyncedCookie: fullCookieStr,
          lastSyncTimestamp: now,
          lastSyncTime: new Date().toLocaleTimeString("vi-VN") + " " + new Date().toLocaleDateString("vi-VN"),
          totalSyncCount: (settings.totalSyncCount || 0) + 1
        });

        // Đổi màu huy hiệu icon thành OK
        chrome.action.setBadgeText({ text: "OK" });
        chrome.action.setBadgeBackgroundColor({ color: "#10B981" });

        // Thông báo khi token mới được cập nhật
        if (token !== storedToken) {
          try {
            chrome.notifications.create({
              type: "basic",
              iconUrl: "icon48.png",
              title: "WeSign Auto Sync",
              message: "🎉 Đã tự động cập nhật Token & Cookie WeSign mới thành công!"
            });
          } catch (e) {}
        }

        console.log("[WeSign Auto Sync] Đã đồng bộ Token & Cookie mới thành công lúc:", new Date().toLocaleTimeString());
      }
    } finally {
      isSyncing = false;
    }
  });
}

// Hàm gửi cấu hình qua API
async function postConfigToTool(baseUrl, payload) {
  try {
    const cleanUrl = baseUrl.replace(/\/+$/, "") + "/api/config";
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 6000);

    const res = await fetch(cleanUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    if (res.ok) {
      const data = await res.json();
      return data.success === true;
    }
    return false;
  } catch (err) {
    return false;
  }
}

// Lắng nghe yêu cầu kiểm tra hoặc đồng bộ thủ công từ Popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "manual_sync") {
    // Reset thời gian để cho phép đồng bộ cưỡng bức khi người dùng bấm nút
    chrome.storage.local.set({ lastSyncTimestamp: 0, lastSyncedToken: "" }, () => {
      chrome.tabs.query({ url: "*://amisapp.misa.vn/*" }, (tabs) => {
        if (!tabs || tabs.length === 0) {
          sendResponse({ success: false, message: "Bạn chưa mở tab MISA WeSign nào. Vui lòng bấm 'Mở MISA WeSign' trước." });
          return;
        }
        chrome.tabs.reload(tabs[0].id);
        sendResponse({ success: true, message: "Đang tải lại trang WeSign để đồng bộ lại ngay..." });
      });
    });
    return true;
  }
});
