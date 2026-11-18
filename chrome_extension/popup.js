// WeSign Auto Sync - Popup Script v1.1.0

document.addEventListener("DOMContentLoaded", () => {
  const badgeToken = document.getElementById("badge-token");
  const badgeCookie = document.getElementById("badge-cookie");
  const rowUser = document.getElementById("row-user");
  const txtUser = document.getElementById("txt-user");
  const rowExp = document.getElementById("row-exp");
  const txtExp = document.getElementById("txt-exp");
  const txtLastSync = document.getElementById("txt-last-sync");
  const txtStatus = document.getElementById("txt-status");

  const chkRender = document.getElementById("chk-render");
  const txtRender = document.getElementById("txt-render");
  const chkLocal = document.getElementById("chk-local");
  const txtLocal = document.getElementById("txt-local");

  const btnForceSync = document.getElementById("btn-force-sync");
  const btnCopyCurl = document.getElementById("btn-copy-curl");
  const btnCopyCookie = document.getElementById("btn-copy-cookie");
  const btnOpenMisa = document.getElementById("btn-open-misa");
  const btnOpenTool = document.getElementById("btn-open-tool");
  const toast = document.getElementById("toast");

  let hideToastTimeout = null;
  function showToast(msg, type = "success", duration = 4000) {
    if (hideToastTimeout) clearTimeout(hideToastTimeout);
    toast.textContent = msg;
    toast.className = `toast toast-${type}`;
    toast.style.display = "block";
    hideToastTimeout = setTimeout(() => { toast.style.display = "none"; }, duration);
  }

  // Tải trạng thái từ Chrome Storage và cập nhật giao diện
  function refreshUI() {
    chrome.storage.local.get({
      renderUrl: "https://tool-link-wesig.onrender.com",
      localUrl: "http://localhost:5050",
      syncToRender: true,
      syncToLocal: false,
      lastSyncTime: null,
      lastSyncedToken: "",
      lastSyncedCookie: "",
      cookieCount: 0,
      cookieKeys: [],
      tokenUser: "",
      tokenExp: "",
      lastSyncStatus: ""
    }, (data) => {
      txtRender.value = data.renderUrl || "https://tool-link-wesig.onrender.com";
      txtLocal.value = data.localUrl || "http://localhost:5050";
      chkRender.checked = data.syncToRender !== false;
      chkLocal.checked = data.syncToLocal === true;

      // Cập nhật Badge Token
      if (data.lastSyncedToken) {
        badgeToken.className = "status-badge badge-success";
        badgeToken.textContent = "🟢 Đã có Token";

        if (data.tokenUser) {
          rowUser.style.display = "flex";
          txtUser.textContent = data.tokenUser;
        } else {
          rowUser.style.display = "none";
        }

        if (data.tokenExp) {
          rowExp.style.display = "flex";
          txtExp.textContent = data.tokenExp;
        } else {
          rowExp.style.display = "none";
        }
      } else {
        badgeToken.className = "status-badge badge-waiting";
        badgeToken.textContent = "⏳ Chưa có Token";
        rowUser.style.display = "none";
        rowExp.style.display = "none";
      }

      // Cập nhật Badge Cookie
      const count = data.cookieCount || 0;
      if (data.lastSyncedCookie && count > 0) {
        badgeCookie.className = "status-badge badge-success";
        badgeCookie.textContent = `🟢 Đã lấy ${count} cookies`;
      } else if (data.lastSyncedCookie) {
        badgeCookie.className = "status-badge badge-success";
        badgeCookie.textContent = "🟢 Đã có Cookie";
      } else {
        badgeCookie.className = "status-badge badge-waiting";
        badgeCookie.textContent = "⏳ Chưa lấy được";
      }

      txtLastSync.textContent = data.lastSyncTime || "Chưa có";
      txtStatus.textContent = data.lastSyncStatus || "-";
      txtStatus.title = data.lastSyncStatus || "";
    });
  }

  // Tự động lưu cài đặt
  function saveSettings() {
    chrome.storage.local.set({
      renderUrl: txtRender.value.trim(),
      localUrl: txtLocal.value.trim(),
      syncToRender: chkRender.checked,
      syncToLocal: chkLocal.checked
    });
  }

  chkRender.addEventListener("change", saveSettings);
  chkLocal.addEventListener("change", saveSettings);
  txtRender.addEventListener("change", saveSettings);
  txtLocal.addEventListener("change", saveSettings);

  // 1. Nút Đồng Bộ Ngay Cưỡng Bức
  btnForceSync.addEventListener("click", () => {
    btnForceSync.disabled = true;
    btnForceSync.textContent = "⏳ Đang kết nối máy chủ...";
    showToast("Đang quét tab MISA WeSign và gửi lên Render...", "info", 6000);

    chrome.runtime.sendMessage({ action: "force_sync_now" }, (response) => {
      btnForceSync.disabled = false;
      btnForceSync.textContent = "🚀 ĐỒNG BỘ TOKEN & COOKIE NGAY LÊN RENDER";

      if (response && response.success) {
        showToast(response.message || "🎉 Đồng bộ thành công lên Render!", "success", 5000);
      } else {
        const errMsg = (response && response.message) || "Không thể đồng bộ. Vui lòng mở trang MISA WeSign trước.";
        showToast(errMsg, "error", 6000);
      }
      refreshUI();
    });
  });

  // 2. Nút Tạo và Sao Chép cURL Đầy Đủ
  btnCopyCurl.addEventListener("click", () => {
    chrome.runtime.sendMessage({ action: "generate_curl" }, (response) => {
      if (response && response.success && response.curl) {
        navigator.clipboard.writeText(response.curl).then(() => {
          showToast("📋 Đã copy lệnh cURL đầy đủ vào Clipboard! Bạn có thể dán vào Web Tool Tab 3.", "success", 4000);
        }).catch(() => {
          showToast("Lỗi khi sao chép vào bộ nhớ tạm.", "error");
        });
      } else {
        showToast((response && response.message) || "Chưa có Token WeSign để tạo cURL. Hãy mở tab WeSign trước.", "error");
      }
    });
  });

  // 3. Nút Sao Chép Cookie Nhanh
  btnCopyCookie.addEventListener("click", () => {
    chrome.storage.local.get({ lastSyncedCookie: "" }, (data) => {
      if (data.lastSyncedCookie) {
        navigator.clipboard.writeText(data.lastSyncedCookie).then(() => {
          showToast("🍪 Đã sao chép chuỗi Cookie vào Clipboard!", "success", 3000);
        }).catch(() => {
          showToast("Lỗi khi sao chép Cookie.", "error");
        });
      } else {
        showToast("Chưa có Cookie nào được lưu. Hãy bấm 'Đồng Bộ Ngay'.", "error");
      }
    });
  });

  // 4. Mở tab MISA WeSign để đăng nhập
  btnOpenMisa.addEventListener("click", () => {
    chrome.tabs.create({ url: "https://amisapp.misa.vn/login/?ReturnUrl=%2Fwesign%2Fhome" });
  });

  // 5. Mở Web Tool
  btnOpenTool.addEventListener("click", () => {
    const url = txtRender.value.trim() || "https://tool-link-wesig.onrender.com";
    chrome.tabs.create({ url: url });
  });

  // Khởi tạo hiển thị lần đầu
  refreshUI();
});
