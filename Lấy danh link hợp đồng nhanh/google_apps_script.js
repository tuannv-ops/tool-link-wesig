/**
 * ==============================================================================
 * AMIS WESIGN - GOOGLE APPS SCRIPT LẤY LINK KÝ HỢP ĐỒNG HÀNG LOẠT THEO CCCD
 * Hỗ trợ tra cứu tất cả các đợt/lô, lấy link ký, kiểm tra lịch sử ký (Đã ký, Đã xem)
 * ==============================================================================
 */

// 1. TẠO MENU TRÊN THANH CÔNG CỤ GOOGLE SHEETS
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('⚡ MISA WeSign')
    .addItem('▶️ 1. Lấy Link Ký Hàng Loạt', 'runBatchLookup')
    .addItem('🔄 2. Cập Nhật Tiến Độ Ký Mới Nhất', 'runBatchLookup')
    .addSeparator()
    .addItem('🔌 3. Kiểm Tra Kết Nối Token & Cookie', 'checkConnection')
    .addItem('📋 4. Tạo Mẫu Bảng Tự Động (Setup Sheets)', 'setupSheetTemplate')
    .addToUi();
}

// 2. ĐỌC CẤU HÌNH TỪ TAB "Cài Đặt" HOẶC SCRIPTPERPERTIES
function getWeSignConfig() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let settingSheet = ss.getSheetByName('Cài Đặt');
  
  let token = '';
  let cookie = '';
  let tenantId = 'c4e3c4ef-a722-40cd-96ed-6aa20a86ee94';

  if (settingSheet) {
    token = String(settingSheet.getRange('B2').getValue() || '').trim();
    cookie = String(settingSheet.getRange('B3').getValue() || '').trim();
    const tId = String(settingSheet.getRange('B4').getValue() || '').trim();
    if (tId) tenantId = tId;
  }

  const props = PropertiesService.getScriptProperties();
  if (!token) token = props.getProperty('WESIGN_TOKEN') || '';
  if (!cookie) cookie = props.getProperty('WESIGN_COOKIE') || '';

  return { token: token.replace(/^Bearer\s+/i, ''), cookie, tenantId };
}

// 3. TẠO TỰ ĐỘNG BẢNG MẪU CHO GOOGLE SHEETS
function setupSheetTemplate() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ui = SpreadsheetApp.getUi();

  let sheet = ss.getSheetByName('Tra Cứu');
  if (!sheet) {
    sheet = ss.insertSheet('Tra Cứu', 0);
  }

  const headers = [
    'STT', 
    'Số CCCD', 
    'Họ và Tên NLĐ', 
    'Đợt / Lô Ký', 
    'Tiến Độ Ký (Lịch Sử)', 
    'Thời Gian NLĐ Ký / Xem', 
    'Tên Hợp Đồng', 
    'Link Ký Hợp Đồng (Click)', 
    'Trạng Thái Tra Cứu'
  ];

  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  const headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setBackground('#1E40AF')
             .setFontColor('#FFFFFF')
             .setFontWeight('bold')
             .setHorizontalAlignment('center')
             .setVerticalAlignment('middle');
  sheet.setRowHeight(1, 35);

  sheet.setColumnWidth(1, 50);
  sheet.setColumnWidth(2, 130);
  sheet.setColumnWidth(3, 160);
  sheet.setColumnWidth(4, 150);
  sheet.setColumnWidth(5, 140);
  sheet.setColumnWidth(6, 170);
  sheet.setColumnWidth(7, 220);
  sheet.setColumnWidth(8, 250);
  sheet.setColumnWidth(9, 130);

  let settingSheet = ss.getSheetByName('Cài Đặt');
  if (!settingSheet) {
    settingSheet = ss.insertSheet('Cài Đặt');
    settingSheet.getRange('A1:B1').setValues([['TÊN CẤU HÌNH', 'GIÁ TRỊ CẤU HÌNH']]);
    settingSheet.getRange('A1:B1').setBackground('#047857').setFontColor('#FFFFFF').setFontWeight('bold');
    
    settingSheet.getRange('A2').setValue('Bearer Token');
    settingSheet.getRange('A3').setValue('Cookie');
    settingSheet.getRange('A4').setValue('Tenant ID');

    settingSheet.setColumnWidth(1, 160);
    settingSheet.setColumnWidth(2, 600);
  }

  ui.alert('Thiết lập thành công!', 'Đã tạo 2 tab: "Tra Cứu" và "Cài Đặt".\nHãy sang tab "Cài Đặt" dán Token & Cookie vào ô B2, B3!', ui.ButtonSet.OK);
}

// 4. KIỂM TRA KẾT NỐI WEISIGN
function checkConnection() {
  const ui = SpreadsheetApp.getUi();
  const cfg = getWeSignConfig();

  if (!cfg.token) {
    ui.alert('Chưa có Token', 'Vui lòng sang tab "Cài Đặt" và dán Bearer Token vào ô B2!', ui.ButtonSet.OK);
    return;
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
    const code = res.getResponseCode();
    if (code === 200) {
      const data = JSON.parse(res.getContentText());
      const batches = data.data || [];
      ui.alert('Kết nối thành công!', 'Đã kết nối thành công đến MISA WeSign!\nTìm thấy ' + batches.length + ' đợt tài liệu trên hệ thống.', ui.ButtonSet.OK);
    } else {
      ui.alert('Lỗi kết nối (' + code + ')', 'Token hoặc Cookie có thể đã hết hạn. Vui lòng kiểm tra lại ô B2, B3 trong tab Cài Đặt!', ui.ButtonSet.OK);
    }
  } catch (err) {
    ui.alert('Lỗi', 'Chi tiết: ' + err.toString(), ui.ButtonSet.OK);
  }
}

// 5. TRA CỨU HÀNG LOẠT VÀ ĐIỀN LINK VÀO SHEET
function runBatchLookup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName('Tra Cứu') || ss.getActiveSheet();
  const ui = SpreadsheetApp.getUi();
  const cfg = getWeSignConfig();

  if (!cfg.token) {
    ui.alert('Chưa có Token', 'Vui lòng sang tab "Cài Đặt" điền Token vào ô B2 trước!', ui.ButtonSet.OK);
    return;
  }

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    ui.alert('Chưa có dữ liệu', 'Hãy dán danh sách số CCCD vào cột B (bắt đầu từ dòng 2)!', ui.ButtonSet.OK);
    return;
  }

  const cccdValues = sheet.getRange(2, 2, lastRow - 1, 1).getValues();
  let countFound = 0;
  let countTotal = 0;

  SpreadsheetApp.getActiveSpreadsheet().toast('Đang bắt đầu tra cứu WeSign...', 'MISA WeSign', 5);

  for (let i = 0; i < cccdValues.length; i++) {
    const rowNum = i + 2;
    const cccdRaw = String(cccdValues[i][0] || '').trim();
    if (!cccdRaw) continue;

    countTotal++;
    sheet.getRange(rowNum, 1).setValue(countTotal);
    sheet.getRange(rowNum, 9).setValue('Đang tìm...');

    const info = lookupSingleCCCD(cccdRaw, cfg);

    if (info.status === 'success') {
      countFound++;
      sheet.getRange(rowNum, 3).setValue(info.workerName);
      sheet.getRange(rowNum, 4).setValue(info.batchName);
      sheet.getRange(rowNum, 5).setValue(info.signingState);
      sheet.getRange(rowNum, 6).setValue(info.signedTime || info.viewedTime || '-');
      sheet.getRange(rowNum, 7).setValue(info.docName);
      
      if (info.signLink) {
        sheet.getRange(rowNum, 8).setFormula(`=HYPERLINK("${info.signLink}", "Mở Link Ký")`);
      } else {
        sheet.getRange(rowNum, 8).setValue('-');
      }

      sheet.getRange(rowNum, 9).setValue('Thành công');

      const stateCell = sheet.getRange(rowNum, 5);
      if (info.signingState === 'Đã hoàn thành') {
        stateCell.setBackground('#D1FAE5').setFontColor('#065F46').setFontWeight('bold');
      } else if (info.signingState === 'NLĐ đã ký') {
        stateCell.setBackground('#DBEAFE').setFontColor('#1E40AF').setFontWeight('bold');
      } else if (info.signingState === 'Đã xem (Chưa ký)') {
        stateCell.setBackground('#FEF3C7').setFontColor('#92400E');
      } else {
        stateCell.setBackground('#F1F5F9').setFontColor('#475569');
      }

    } else if (info.status === 'not_found') {
      sheet.getRange(rowNum, 3).setValue('-');
      sheet.getRange(rowNum, 4).setValue('-');
      sheet.getRange(rowNum, 5).setValue('-');
      sheet.getRange(rowNum, 6).setValue('-');
      sheet.getRange(rowNum, 7).setValue('-');
      sheet.getRange(rowNum, 8).setValue('-');
      sheet.getRange(rowNum, 9).setValue('Không tìm thấy');
      sheet.getRange(rowNum, 9).setBackground('#FEE2E2').setFontColor('#991B1B');
    } else {
      sheet.getRange(rowNum, 9).setValue(info.message || 'Lỗi');
    }

    if (i % 3 === 0) {
      SpreadsheetApp.flush();
    }
  }

  SpreadsheetApp.flush();
  ui.alert('Hoàn thành tra cứu!', `Đã tra cứu xong ${countTotal} số CCCD.\nTìm thấy thành công: ${countFound} hợp đồng.`, ui.ButtonSet.OK);
}

// 6. HÀM TRA CỨU ĐƠN LẺ 1 SỐ CCCD QUA API
function lookupSingleCCCD(cccd, cfg) {
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
      return { status: 'error', message: 'HTTP ' + res.getResponseCode() };
    }

    const data = JSON.parse(res.getContentText());
    const docs = data.data || [];
    if (!docs.length) {
      return { status: 'not_found' };
    }

    let matchDoc = null;
    let matchPart = null;

    for (let i = 0; i < docs.length; i++) {
      const d = docs[i];
      const dName = d.name || '';
      const parts = d.documentParticipants || [];

      if (dName.indexOf(cccd) !== -1 || (cccd.startsWith('0') && dName.indexOf(cccd.substring(1)) !== -1)) {
        matchDoc = d;
        matchPart = extractWorker(parts, dName);
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
      matchPart = extractWorker(matchDoc.documentParticipants || [], matchDoc.name || '');
    }

    const docId = matchDoc.id;
    const partId = matchPart ? (matchPart.documentParticipantID || matchPart.id) : null;
    const workerName = matchPart ? (matchPart.name || '') : '';
    const docName = matchDoc.name || '';
    const batchName = matchDoc.batchName || 'Hợp đồng lao động';

    let signLink = '';
    if (docId && partId) {
      signLink = getSignLink(docId, partId, cfg);
    }

    const historyInfo = getDocHistory(docId, workerName, cfg);

    return {
      status: 'success',
      docId: docId,
      docName: docName,
      workerName: workerName,
      batchName: batchName,
      signLink: signLink,
      signingState: historyInfo.signingState,
      signedTime: historyInfo.signedTime,
      viewedTime: historyInfo.viewedTime
    };

  } catch (err) {
    return { status: 'error', message: err.toString() };
  }
}

// 7. LẤY LINK KÝ CHO NGƯỜI LAO ĐỘNG
function getSignLink(docId, partId, cfg) {
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

// 8. LẤY LỊCH SỬ KÝ CHI TIẾT
function getDocHistory(docId, workerName, cfg) {
  let signingState = 'Chưa xem';
  let signedTime = '';
  let viewedTime = '';

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

        if (action === 6) {
          isCompleted = true;
          signedTime = t;
        } else if (action === 5) {
          if (!normWorker || uName.indexOf(normWorker) !== -1 || normWorker.indexOf(uName) !== -1) {
            workerSigned = true;
            signedTime = t;
          }
        } else if (action === 4) {
          if (!normWorker || uName.indexOf(normWorker) !== -1 || normWorker.indexOf(uName) !== -1) {
            workerViewed = true;
            viewedTime = t;
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

  return { signingState, signedTime, viewedTime };
}

// 9. TRÍCH XUẤT NGƯỜI LAO ĐỘNG
function extractWorker(participants, docName) {
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
