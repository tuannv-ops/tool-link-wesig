/**
 * ==============================================================================
 * GOOGLE APPS SCRIPT WEB APP - BACKEND SERVER (Code.gs)
 * Tool Lấy Link Hợp Đồng Lao Động Nhanh (MISA WeSign)
 * ==============================================================================
 */

// 1. PHỤC VỤ GIAO DIỆN WEB (WEB APP ENTRY POINT)
function doGet(e) {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Tool Lấy Link Hợp Đồng Lao Động Nhanh')
    .setFaviconUrl('https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQYF62M8Z-nllVbmMgMX28dApj7L_4NEWxOlZIb0PUozw&s=10')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// 2. LẤY CẤU HÌNH TOKEN & COOKIE
function apiGetConfig() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('WESIGN_TOKEN') || 'eyJhbGciOiJSUzI1NiIsImtpZCI6IjRhNTc3ZWE3OWVmZDI3YzA0MmE2YjUyODljZDdlMjRlIiwidHlwIjoiYXQrand0In0...';
  const cookie = props.getProperty('WESIGN_COOKIE') || 'deviceId=f4007158-f14d-48f2-bae2-0e73c4e046a4; ...';
  const tenantId = props.getProperty('WESIGN_TENANT_ID') || 'c4e3c4ef-a722-40cd-96ed-6aa20a86ee94';
  const batchId = props.getProperty('WESIGN_BATCH_ID') || 'ff7b7049-83c1-4339-a5f7-9b5a7051adce';

  return {
    token: token,
    cookie: cookie,
    tenant_id: tenantId,
    document_batch_id: batchId
  };
}

// 3. LƯU CẤU HÌNH TOKEN & COOKIE MỚI
function apiSaveConfig(newConfig) {
  try {
    const props = PropertiesService.getScriptProperties();
    if (newConfig.token) props.setProperty('WESIGN_TOKEN', newConfig.token.replace(/^Bearer\s+/i, '').trim());
    if (newConfig.cookie) props.setProperty('WESIGN_COOKIE', newConfig.cookie.trim());
    if (newConfig.tenant_id) props.setProperty('WESIGN_TENANT_ID', newConfig.tenant_id.trim());
    if (newConfig.document_batch_id) props.setProperty('WESIGN_BATCH_ID', newConfig.document_batch_id.trim());
    return { success: true, message: 'Đã lưu cấu hình thành công vào hệ thống!' };
  } catch (err) {
    return { success: false, message: err.toString() };
  }
}

// 4. KIỂM TRA KẾT NỐI WEISIGN
function apiTestConnection() {
  const cfg = apiGetConfig();
  if (!cfg.token) {
    return { success: false, message: 'Chưa cấu hình Bearer Token!' };
  }

  try {
    const url = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v2/documents/paging/data';
    const payload = {
      "status": [],
      "limit": 20,
      "pageNumber": 1,
      "keyword": "",
      "filterField": 1,
      "isMine": false,
      "isParticipated": false,
      "isTrash": false,
      "sourceDocuments": ["Task", "CRM", "Accounting", "AMISProcess", "EmployeesProfile", "Other", "AMISWesign"],
      "draftType": 0,
      "relatedUsers": []
    };

    const options = {
      method: 'post',
      contentType: 'application/json',
      headers: {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': 'Bearer ' + cfg.token,
        'Cookie': cfg.cookie
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };

    const res = UrlFetchApp.fetch(url, options);
    if (res.getResponseCode() === 200) {
      const data = JSON.parse(res.getContentText());
      const batches = data.data || [];
      return {
        success: true,
        message: `Kết nối thành công! Đang có ${batches.length} đợt tài liệu trên WeSign.`,
        batchName: `Tất cả ${batches.length} đợt tài liệu`,
        total: batches.length
      };
    } else {
      return { success: false, message: `Lỗi kết nối (Mã HTTP: ${res.getResponseCode()}). Vui lòng kiểm tra lại Token & Cookie!` };
    }
  } catch (err) {
    return { success: false, message: err.toString() };
  }
}

// 5. TRA CỨU ĐƠN LẺ 1 SỐ CCCD
function apiLookupSingle(cccd) {
  const cfg = apiGetConfig();
  if (!cfg.token) {
    return { status: 'error', message: 'Chưa cấu hình Token WeSign!' };
  }

  try {
    const url = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v2/documents/paging/data';
    const payload = {
      "status": [],
      "limit": 50,
      "pageNumber": 1,
      "keyword": cccd,
      "filterField": 1,
      "isMine": false,
      "isParticipated": false,
      "isTrash": false,
      "sourceDocuments": ["Task", "CRM", "Accounting", "AMISProcess", "EmployeesProfile", "Other", "AMISWesign"],
      "draftType": 0,
      "relatedUsers": []
    };

    const options = {
      method: 'post',
      contentType: 'application/json',
      headers: {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': 'Bearer ' + cfg.token,
        'Cookie': cfg.cookie
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };

    const res = UrlFetchApp.fetch(url, options);
    if (res.getResponseCode() !== 200) {
      return { status: 'error', cccd: cccd, message: 'Lỗi máy chủ MISA HTTP ' + res.getResponseCode() };
    }

    const json = JSON.parse(res.getContentText());
    const docs = json.data || [];
    if (!docs.length) {
      return { status: 'not_found', cccd: cccd, message: 'Không tìm thấy hợp đồng' };
    }

    let matchDoc = null;
    let matchPart = null;

    for (let i = 0; i < docs.length; i++) {
      const d = docs[i];
      const dName = d.name || '';
      const parts = d.documentParticipants || [];

      if (dName.indexOf(cccd) !== -1 || (cccd.startsWith('0') && dName.indexOf(cccd.substring(1)) !== -1)) {
        matchDoc = d;
        matchPart = extractWorkerPart(parts, dName);
        break;
      }
      for (let j = 0; j < parts.length; j++) {
        const p = parts[j];
        if (p.legalCode === cccd || (p.name && dName.indexOf(p.name) !== -1)) {
          matchDoc = d;
          matchPart = p;
          break;
        }
      }
      if (matchDoc) break;
    }

    if (!matchDoc) {
      matchDoc = docs[0];
      matchPart = extractWorkerPart(matchDoc.documentParticipants || [], matchDoc.name || '');
    }

    const docId = matchDoc.id;
    const partId = matchPart ? (matchPart.documentParticipantID || matchPart.id) : null;
    const workerName = matchPart ? (matchPart.name || '') : '';
    const jobPosition = matchPart ? (matchPart.jobPosition || 'Người lao động') : 'Người lao động';
    const docName = matchDoc.name || '';
    const batchName = matchDoc.batchName || 'Hợp đồng lao động';

    // Lấy Sign Link
    let signLink = '';
    if (docId && partId) {
      signLink = fetchSignLink(docId, partId, cfg);
    }

    // Lấy History
    const hist = fetchDocHistory(docId, workerName, cfg);

    return {
      status: 'success',
      cccd: cccd,
      doc_id: docId,
      doc_name: docName,
      worker_name: workerName,
      job_position: jobPosition,
      batch_name: batchName,
      doc_status: matchDoc.status === 7 ? 'Hoàn thành' : 'Chờ ký',
      sign_link: signLink,
      signing_state: hist.signingState,
      worker_signed_time: hist.workerSignedTime,
      worker_viewed_time: hist.workerViewedTime,
      completed_time: hist.completedTime
    };

  } catch (err) {
    return { status: 'error', cccd: cccd, message: err.toString() };
  }
}

// 6. LẤY LINK KÝ
function fetchSignLink(docId, partId, cfg) {
  try {
    const url = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v2/documents/sign-link';
    const payload = { "documentId": docId, "participantId": partId };
    const options = {
      method: 'post',
      contentType: 'application/json',
      headers: {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': 'Bearer ' + cfg.token,
        'Cookie': cfg.cookie
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };
    const res = UrlFetchApp.fetch(url, options);
    if (res.getResponseCode() === 200) {
      const data = JSON.parse(res.getContentText());
      return data.data || '';
    }
  } catch (e) {}
  return '';
}

// 7. LẤY LỊCH SỬ KÝ CHI TIẾT
function fetchDocHistory(docId, workerName, cfg) {
  let signingState = 'Chưa xem';
  let workerSignedTime = '';
  let workerViewedTime = '';
  let completedTime = '';
  let eventsList = [];

  try {
    const url = `https://amisapp.misa.vn/wesign/g2/api/v1/documents/${docId}/histories`;
    const options = {
      method: 'get',
      headers: {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': 'Bearer ' + cfg.token,
        'Cookie': cfg.cookie
      },
      muteHttpExceptions: true
    };
    const res = UrlFetchApp.fetch(url, options);
    if (res.getResponseCode() === 200) {
      const json = JSON.parse(res.getContentText());
      const events = json.data || [];

      let isCompleted = false;
      let workerSigned = false;
      let workerViewed = false;
      const normWorker = (workerName || '').trim().toLowerCase();

      for (let i = 0; i < events.length; i++) {
        const ev = events[i];
        const action = ev.action;
        const uName = (ev.name || '').trim().toLowerCase();
        const t = ev.createdDate ? Utilities.formatDate(new Date(ev.createdDate), "GMT+7", "dd/MM/yyyy HH:mm") : '';

        let actText = 'Hành động khác';
        if (action === 0) actText = 'Tạo và gửi văn bản';
        else if (action === 4) actText = 'Mở xem văn bản';
        else if (action === 5) actText = 'Đã ký văn bản';
        else if (action === 6) actText = 'Văn bản đã hoàn tất';

        eventsList.push({
          action: action,
          action_text: actText,
          time: t,
          user_name: ev.name || 'Người dùng',
          user_email: ev.email || ''
        });

        if (action === 6) {
          isCompleted = true;
          completedTime = t;
        } else if (action === 5) {
          if (!normWorker || uName.indexOf(normWorker) !== -1 || normWorker.indexOf(uName) !== -1) {
            workerSigned = true;
            workerSignedTime = t;
          }
        } else if (action === 4) {
          if (!normWorker || uName.indexOf(normWorker) !== -1 || normWorker.indexOf(uName) !== -1) {
            workerViewed = true;
            workerViewedTime = t;
          }
        }
      }

      if (isCompleted) {
        signingState = 'Đã hoàn thành';
      } else if (workerSigned) {
        signingState = 'NLĐ đã ký';
      } else if (workerViewed) {
        signingState = 'Đã xem (Chưa ký)';
      }
    }
  } catch (e) {}

  return {
    signingState: signingState,
    workerSignedTime: workerSignedTime,
    workerViewedTime: workerViewedTime,
    completedTime: completedTime,
    events: eventsList
  };
}

// 8. API LẤY LỊCH SỬ KÝ PHỤC VỤ POPUP MODAL
function apiGetDocumentHistory(docId, workerName) {
  const cfg = apiGetConfig();
  const hist = fetchDocHistory(docId, workerName, cfg);
  return {
    is_completed: hist.signingState === 'Đã hoàn thành',
    worker_signed: hist.signingState === 'NLĐ đã ký' || hist.signingState === 'Đã hoàn thành',
    worker_viewed: hist.signingState !== 'Chưa xem',
    events: hist.events
  };
}

// 9. TRÍCH XUẤT NGƯỜI THAM GIA LÀ NGƯỜI LAO ĐỘNG
function extractWorkerPart(participants, docName) {
  if (!participants || !participants.length) return null;
  for (let i = 0; i < participants.length; i++) {
    const job = (participants[i].jobPosition || '').toLowerCase();
    if (job.indexOf('lao động') !== -1) return participants[i];
  }
  for (let i = 0; i < participants.length; i++) {
    const name = (participants[i].name || '').trim().toUpperCase();
    if (name && docName.toUpperCase().indexOf(name) !== -1) return participants[i];
  }
  for (let i = 0; i < participants.length; i++) {
    const job = (participants[i].jobPosition || '').toLowerCase();
    if (job.indexOf('giám đốc') === -1 && job.indexOf('trưởng phòng') === -1 && job.indexOf('đại diện') === -1) {
      return participants[i];
    }
  }
  return participants[0];
}

// 10. GỬI LẠI HỢP ĐỒNG CHO NLĐ QUA AMIS WESIGN
function apiResendDocuments(docIds) {
  if (typeof docIds === 'string') docIds = [docIds];
  if (!docIds || !docIds.length) {
    return { success: false, message: 'Không có documentId để gửi lại' };
  }

  const cfg = getConfig();
  const url = 'https://amisapp.misa.vn/wesign/g2/api/file-management/api/v3/documents/resend-all';
  const headers = getHeaders(cfg);
  
  const payload = {
    documents: docIds.map(function(id) {
      return { documentId: id, tenantId: cfg.tenant_id };
    }),
    Device: {
      deviceName: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/156.0.0.0 Safari/537.36',
      location: ''
    }
  };

  try {
    const res = UrlFetchApp.fetch(url, {
      method: 'post',
      headers: headers,
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
    const code = res.getResponseCode();
    if (code === 200) {
      return { success: true, count: docIds.length, message: 'Đã gửi lại thành công cho ' + docIds.length + ' hợp đồng!' };
    } else {
      return { success: false, message: 'Lỗi từ máy chủ MISA (Mã: ' + code + '): ' + res.getContentText() };
    }
  } catch (err) {
    return { success: false, message: 'Lỗi kết nối khi gửi lại: ' + err.toString() };
  }
}
