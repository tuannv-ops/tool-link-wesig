// WeSign Auto Sync - Popup Script

document.addEventListener("DOMContentLoaded", () => {
  const badgeToken = document.getElementById("badge-token");
  const txtLastSync = document.getElementById("txt-last-sync");
  const txtCount = document.getElementById("txt-count");

  const chkRender = document.getElementById("chk-render");
  const txtRender = document.getElementById("txt-render");
  const chkLocal = document.getElementById("chk-local");
  const txtLocal = document.getElementById("txt-local");

  const btnOpenMisa = document.getElementById("btn-open-misa");
  const btnManualSync = document.getElementById("btn-manual-sync");
  const btnOpenTool = document.getElementById("btn-open-tool");
  const toast = document.getElementById("toast");

  function showToast(msg, type = "success") {
    toast.textContent = msg;
    toast.className = `toast toast-${type}`;
    toast.style.display = "block";
    setTimeout(() => { toast.style.display = "none"; }, 3500);
  }

  // Nạp trạng thái từ Storage
  chrome.storage.local.get({
    renderUrl: "https://tool-link-wesig.onrender.com",
    localUrl: "http://localhost:5050",
    syncToRender: true,
    syncToLocal: true,
    lastSyncTime: null,
    totalSyncCount: 0
  }, (data) => {
    txtRender.value = data.renderUrl;
    txtLocal.value = data.localUrl;
    chkRender.checked = data.syncToRender;
    chkLocal.checked = data.syncToLocal;

    if (data.lastSyncTime) {
      badgeToken.className = "status-badge badge-success";
      badgeToken.textContent = "🟢 Đã kết nối tự động";
      txtLastSync.textContent = data.lastSyncTime;
    } else {
      badgeToken.className = "status-badge badge-waiting";
      badgeToken.textContent = "⏳ Chờ đăng nhập MISA";
      txtLastSync.textContent = "Chưa có";
    }

    txtCount.textContent = (data.totalSyncCount || 0) + " lần";
  });

  // Tự động lưu cấu hình khi người dùng sửa
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

  // Mở MISA WeSign để đăng nhập
  btnOpenMisa.addEventListener("click", () => {
    chrome.tabs.create({ url: "https://amisapp.misa.vn/login/?ReturnUrl=%2Fwesign%2Fhome" });
  });

  // Mở Web Tool
  btnOpenTool.addEventListener("click", () => {
    const url = txtRender.value.trim() || "https://tool-link-wesig.onrender.com";
    chrome.tabs.create({ url: url });
  });

  // Kích hoạt đồng bộ ngay
  btnManualSync.addEventListener("click", () => {
    btnManualSync.disabled = true;
    btnManualSync.textContent = "⏳ Đang kiểm tra...";

    chrome.runtime.sendMessage({ action: "manual_sync" }, (response) => {
      btnManualSync.disabled = false;
      btnManualSync.textContent = "🔄 Kích Hoạt Đồng Bộ Ngay";

      if (response && response.success) {
        showToast(response.message, "success");
      } else {
        showToast((response && response.message) || "Vui lòng mở tab MISA WeSign và đăng nhập trước", "error");
      }
    });
  });
});
