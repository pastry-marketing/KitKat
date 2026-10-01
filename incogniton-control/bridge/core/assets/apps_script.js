/**
 * Google Apps Script for Automation Tool Integration (DYNAMIC VERSION)
 * 
 * INSTRUCTIONS:
 * 1. Open your Google Sheet.
 * 2. Click on "Extensions" > "Apps Script".
 * 3. Delete any code in the editor and paste this entire script.
 * 4. Click the "Deploy" button (top right) > "New deployment" (or "Manage deployments" -> Edit -> New version).
 * 5. Select type "Web app".
 * 6. Set "Execute as" to "Me".
 * 7. Set "Who has access" to "Anyone".
 * 8. Click "Deploy" (you may need to authorize permissions).
 * 9. Copy the generated "Web app URL" and save it in the Desktop App Settings.
 */

const SHEET_PROFILES = "Incog Profile Creation";
const SHEET_ND_ACC = "ND Acc Creation";

function setupSheets() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const requiredSheets = [SHEET_PROFILES, SHEET_ND_ACC, "Auto Posting", "Auto Listing", "Auto Warmup", "Auto Random Posting"];

  requiredSheets.forEach(sheetName => {
    let sheet = ss.getSheetByName(sheetName);
    if (!sheet) {
      sheet = ss.insertSheet(sheetName);
      if (sheetName === SHEET_PROFILES) {
        sheet.appendRow(["ID", "Profile Name", "Group", "Proxy", "Lat/Long", "Status"]);
        sheet.getRange("A1:F1").setFontWeight("bold");
        sheet.setFrozenRows(1);
      }
      if (sheetName === SHEET_ND_ACC) {
        sheet.appendRow(["ID", "Profile Name", "Full Name", "Email", "Password", "Status"]);
        sheet.getRange("A1:F1").setFontWeight("bold");
        sheet.setFrozenRows(1);
      }
    }
  });
}

function doGet(e) {
  const action = e.parameter.action;
  
  if (action === "getPendingProfiles") {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(SHEET_PROFILES);
    if (!sheet) return ContentService.createTextOutput(JSON.stringify({error: "Sheet not found"})).setMimeType(ContentService.MimeType.JSON);
    
    const dataRange = sheet.getDataRange();
    const data = dataRange.getValues();
    const richTextData = dataRange.getRichTextValues();
    if (data.length < 2) return ContentService.createTextOutput(JSON.stringify({success: true, data: []})).setMimeType(ContentService.MimeType.JSON);
    
    const headers = data[0].map(h => h.toString().trim());
    const pendingProfiles = [];
    
    // Find status and ID columns
    const statusIdx = headers.findIndex(h => h.toLowerCase() === "status");
    const idIdx = headers.findIndex(h => h.toLowerCase() === "id");
    
    if (statusIdx === -1) return ContentService.createTextOutput(JSON.stringify({error: "Status column not found"})).setMimeType(ContentService.MimeType.JSON);
    
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      if (row[statusIdx] === "") {
        
        // Auto-generate ID if empty
        if (idIdx !== -1 && row[idIdx] === "") {
           const newId = Utilities.getUuid();
           sheet.getRange(i + 1, idIdx + 1).setValue(newId);
           row[idIdx] = newId;
        }
        
        // Dynamically map all columns to JSON!
        const profileObj = { rowNumber: i + 1 };
        for (let c = 0; c < headers.length; c++) {
            if (headers[c]) {
                const key = headers[c]; // exact header name
                profileObj[key] = row[c];
            }
        }
        
        // For backwards compatibility with standard expectations if using separated columns
        profileObj.name = profileObj["Profile Name"] || profileObj["Name"] || "";
        
        pendingProfiles.push(profileObj);
      }
    }
    
    return ContentService.createTextOutput(JSON.stringify({success: true, data: pendingProfiles})).setMimeType(ContentService.MimeType.JSON);
  }
  
  if (action === "getPendingNDAccounts") {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(SHEET_ND_ACC);
    if (!sheet) return ContentService.createTextOutput(JSON.stringify({error: "Sheet not found"})).setMimeType(ContentService.MimeType.JSON);
    
    const dataRange = sheet.getDataRange();
    const data = dataRange.getValues();
    const richTextData = dataRange.getRichTextValues();
    if (data.length < 2) return ContentService.createTextOutput(JSON.stringify({success: true, data: []})).setMimeType(ContentService.MimeType.JSON);
    
    const headers = data[0].map(h => h.toString().trim());
    const pendingAccounts = [];
    
    const statusIdx = headers.findIndex(h => h.toLowerCase() === "status");
    
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      if (statusIdx !== -1 && row[statusIdx] === "") {
          
        const accountObj = { rowNumber: i + 1 };
        for (let c = 0; c < headers.length; c++) {
            if (headers[c]) {
                accountObj[headers[c]] = row[c];
            }
        }
        // Force these specifically for ND accounts
        accountObj.id = accountObj["ID"] || "";
        accountObj.profileName = accountObj["Profile Name"] || accountObj["Name"] || "";
        accountObj.fullName = accountObj["Full Name"] || "";
        accountObj.email = accountObj["Email"] || "";
        accountObj.password = accountObj["Password"] || "";
        
        pendingAccounts.push(accountObj);
      }
    }
    
    return ContentService.createTextOutput(JSON.stringify({success: true, data: pendingAccounts})).setMimeType(ContentService.MimeType.JSON);
  }
  
  if (action === "getPendingRows") {
    const sheetName = e.parameter.sheetName;
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(sheetName);
    if (!sheet) return ContentService.createTextOutput(JSON.stringify({error: "Sheet not found"})).setMimeType(ContentService.MimeType.JSON);
    
    const dataRange = sheet.getDataRange();
    const data = dataRange.getValues();
    const richTextData = dataRange.getRichTextValues();
    if (data.length < 2) return ContentService.createTextOutput(JSON.stringify({success: true, data: []})).setMimeType(ContentService.MimeType.JSON);
    
    const headers = data[0].map(h => h.toString().trim());
    const pendingRows = [];
    
    const statusIdx = headers.findIndex(h => h.toLowerCase() === "status");
    
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      if (statusIdx !== -1 && row[statusIdx] === "") {
          
        const rowObj = { rowNumber: i + 1 };
        for (let c = 0; c < headers.length; c++) {
            if (headers[c]) {
                let cellVal = row[c];
                const lowerHeader = headers[c].toLowerCase();
                if (lowerHeader.includes("picture") || lowerHeader.includes("image")) {
                    const richText = richTextData[i][c];
                    if (richText) {
                        const runs = richText.getRuns();
                        const links = [];
                        for(let r=0; r<runs.length; r++) {
                            const l = runs[r].getLinkUrl();
                            if(l) links.push(l);
                        }
                        if(links.length > 0) {
                            cellVal = links.join(",");
                        }
                    }
                }
                rowObj[headers[c]] = cellVal;
            }
        }
        
        // Auto-mappings for convenience
        rowObj.id = rowObj["ID"] || rowObj["Profile Name"] || rowObj["Name"] || "";
        rowObj.profileName = rowObj["Profile Name"] || rowObj["Name"] || "";
        
        pendingRows.push(rowObj);
      }
    }
    
    return ContentService.createTextOutput(JSON.stringify({success: true, data: pendingRows})).setMimeType(ContentService.MimeType.JSON);
  }

  return ContentService.createTextOutput(JSON.stringify({error: "Invalid action"})).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);
    const action = payload.action;
    
    if (action === "updateStatus" || action === "updateNDStatus" || action === "updateRowStatus") {
      let targetSheetName = payload.sheetName;
      if (!targetSheetName) {
        targetSheetName = action === "updateStatus" ? SHEET_PROFILES : SHEET_ND_ACC;
      }
      
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const sheet = ss.getSheetByName(targetSheetName);
      if(!sheet) return ContentService.createTextOutput(JSON.stringify({error: "Sheet not found"})).setMimeType(ContentService.MimeType.JSON);
      
      const rowNumber = payload.rowNumber;
      const newStatus = payload.status;
      
      const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      const statusIdx = headers.findIndex(h => h.toString().trim().toLowerCase() === "status");
      if (statusIdx === -1) return ContentService.createTextOutput(JSON.stringify({error: "Status column not found"})).setMimeType(ContentService.MimeType.JSON);
      
      sheet.getRange(rowNumber, statusIdx + 1).setValue(newStatus);
      
      return ContentService.createTextOutput(JSON.stringify({success: true})).setMimeType(ContentService.MimeType.JSON);
    }
    
    if (action === "updateColumnValue") {
      const targetSheetName = payload.sheetName;
      const rowNumber = payload.rowNumber;
      const columnName = payload.columnName;
      const newValue = payload.value;
      
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const sheet = ss.getSheetByName(targetSheetName);
      if(!sheet) return ContentService.createTextOutput(JSON.stringify({error: "Sheet not found"})).setMimeType(ContentService.MimeType.JSON);
      
      const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      const colIdx = headers.findIndex(h => h.toString().trim().toLowerCase() === columnName.toLowerCase());
      
      if (colIdx !== -1) {
          sheet.getRange(rowNumber, colIdx + 1).setValue(newValue);
          return ContentService.createTextOutput(JSON.stringify({success: true})).setMimeType(ContentService.MimeType.JSON);
      } else {
          return ContentService.createTextOutput(JSON.stringify({error: "Column not found"})).setMimeType(ContentService.MimeType.JSON);
      }
    }
    
    if (action === "claimRow") {
      const targetSheetName = payload.sheetName;
      const rowNumber = payload.rowNumber;
      
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const sheet = ss.getSheetByName(targetSheetName);
      if(!sheet) return ContentService.createTextOutput(JSON.stringify({error: "Sheet not found"})).setMimeType(ContentService.MimeType.JSON);
      
      const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      const statusIdx = headers.findIndex(h => h.toString().trim().toLowerCase() === "status");
      if (statusIdx === -1) return ContentService.createTextOutput(JSON.stringify({error: "Status column not found"})).setMimeType(ContentService.MimeType.JSON);
      
      const currentStatus = sheet.getRange(rowNumber, statusIdx + 1).getValue().toString().trim().toLowerCase();
      
      // Atomic claim: only claim if it is currently empty or pending
      if (currentStatus === "" || currentStatus === "pending") {
          sheet.getRange(rowNumber, statusIdx + 1).setValue("CLAIMED");
          return ContentService.createTextOutput(JSON.stringify({success: true, claimed: true})).setMimeType(ContentService.MimeType.JSON);
      } else {
          return ContentService.createTextOutput(JSON.stringify({success: true, claimed: false, currentStatus: currentStatus})).setMimeType(ContentService.MimeType.JSON);
      }
    }
    
  } catch(err) {
    return ContentService.createTextOutput(JSON.stringify({error: err.message})).setMimeType(ContentService.MimeType.JSON);
  }
}

