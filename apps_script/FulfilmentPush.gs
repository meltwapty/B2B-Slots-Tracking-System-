/**
 * B2B Slots Tracking — Google Apps Script
 * =========================================
 * This script runs inside Google Sheets.
 *
 * TWO functions:
 *  1. doPost(e)         — Web App endpoint that receives fulfilment data from Django
 *                         and writes it to the "Dashboard" tab.
 *  2. triggerDjangoSync() — Calls the Django /api/sync/ endpoint to kick off a fresh pull.
 *
 * SETUP:
 *   1. Open your Google Sheet → Extensions → Apps Script
 *   2. Paste this entire file
 *   3. Deploy → New deployment → Web app (Execute as: Me, Access: Anyone)
 *   4. Copy the Web App URL → set APPS_SCRIPT_PUSH_URL in Django .env
 *   5. (Optional) Set up a time-based trigger on triggerDjangoSync() for auto-sync
 */

// ── Config ───────────────────────────────────────────────────────────────────
var DJANGO_SYNC_URL   = "https://YOUR_DJANGO_HOST/api/sync/";  // ← update
var DASHBOARD_TAB     = "Dashboard";   // Sheet tab to write results into
var HISTORY_TAB       = "Sync History";
var HEADER_ROW        = 1;
var DATA_START_ROW    = 3;

// ── 1. Receive fulfilment push from Django ───────────────────────────────────
function doPost(e) {
  try {
    var payload = JSON.parse(e.postData.contents);
    writeDashboard(payload);
    appendHistory(payload);
    return ContentService
      .createTextOutput(JSON.stringify({ status: "ok" }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: "error", message: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// ── Write to Dashboard tab ───────────────────────────────────────────────────
function writeDashboard(payload) {
  var ss   = SpreadsheetApp.getActiveSpreadsheet();
  var tab  = ss.getSheetByName(DASHBOARD_TAB);
  if (!tab) tab = ss.insertSheet(DASHBOARD_TAB);

  tab.clearContents();

  // Title
  tab.getRange("A1").setValue("B2B Slots Fulfilment Dashboard");
  tab.getRange("A1").setFontSize(16).setFontWeight("bold");
  tab.getRange("B1").setValue("Last synced: " + payload.synced_at);

  // Summary block
  var summary = payload;
  tab.getRange("A3:B3").setValues([["Total Slots",     summary.total_slots     || 0]]);
  tab.getRange("A4:B4").setValues([["Fulfilled Slots",  summary.fulfilled_slots || 0]]);
  tab.getRange("A5:B5").setValues([["Fulfilment Rate",  (summary.fulfilment_pct || 0) + "%"]]);

  // Style summary
  tab.getRange("A3:A5").setFontWeight("bold").setBackground("#4285F4").setFontColor("white");
  tab.getRange("B3:B5").setBackground("#EAF0FB");

  // Fulfilment rate — big visual cell
  var rateCell = tab.getRange("D3:E5");
  rateCell.merge();
  rateCell.setValue((summary.fulfilment_pct || 0) + "%");
  rateCell.setFontSize(36).setFontWeight("bold").setHorizontalAlignment("center").setVerticalAlignment("middle");
  var rate = summary.fulfilment_pct || 0;
  rateCell.setBackground(rate >= 80 ? "#34A853" : rate >= 50 ? "#FBBC04" : "#EA4335");
  rateCell.setFontColor("white");

  // Product breakdown table
  var byProduct = payload.by_product || {};
  var products  = Object.keys(byProduct);
  if (products.length > 0) {
    tab.getRange("A7").setValue("Product Breakdown").setFontWeight("bold").setFontSize(12);
    tab.getRange("A8:D8").setValues([["Product", "Total Slots", "Fulfilled", "Fulfilment %"]]);
    tab.getRange("A8:D8").setFontWeight("bold").setBackground("#E8F0FE");

    var rows = products.map(function(prod) {
      var p = byProduct[prod];
      return [prod, p.total_slots || 0, p.fulfilled_slots || 0, (p.fulfilment_pct || 0) + "%"];
    });
    tab.getRange(9, 1, rows.length, 4).setValues(rows);

    // Alternating row colors
    rows.forEach(function(_, i) {
      var color = i % 2 === 0 ? "#FFFFFF" : "#F8F9FA";
      tab.getRange(9 + i, 1, 1, 4).setBackground(color);
    });
  }

  // Auto-resize columns
  tab.autoResizeColumns(1, 5);
  SpreadsheetApp.flush();
}

// ── Append to Sync History tab ───────────────────────────────────────────────
function appendHistory(payload) {
  var ss  = SpreadsheetApp.getActiveSpreadsheet();
  var tab = ss.getSheetByName(HISTORY_TAB);
  if (!tab) {
    tab = ss.insertSheet(HISTORY_TAB);
    tab.getRange("A1:E1").setValues([["Synced At", "Total Slots", "Fulfilled", "Fulfilment %", "Source"]]);
    tab.getRange("A1:E1").setFontWeight("bold").setBackground("#E8F0FE");
  }
  tab.appendRow([
    payload.synced_at,
    payload.total_slots     || 0,
    payload.fulfilled_slots || 0,
    (payload.fulfilment_pct || 0) + "%",
    "Django Sync",
  ]);
}

// ── 2. Trigger Django sync from Sheets (manual or scheduled) ─────────────────
function triggerDjangoSync() {
  if (!DJANGO_SYNC_URL || DJANGO_SYNC_URL.includes("YOUR_DJANGO_HOST")) {
    Logger.log("Set DJANGO_SYNC_URL before calling triggerDjangoSync()");
    return;
  }
  var options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({}),
    muteHttpExceptions: true,
  };
  var resp   = UrlFetchApp.fetch(DJANGO_SYNC_URL, options);
  var result = JSON.parse(resp.getContentText());
  Logger.log("Sync triggered: " + JSON.stringify(result));
  SpreadsheetApp.getActiveSpreadsheet().toast(
    "Sync complete! Fulfilment: " + (result.dashboard?.summary?.fulfilment_pct || "?") + "%",
    "Django Sync",
    5
  );
}

// ── 3. Add a custom menu in the Sheet ────────────────────────────────────────
function onOpen() {
  SpreadsheetApp.getActiveSpreadsheet().addMenu("B2B Sync", [
    { name: "Trigger Sync Now", functionName: "triggerDjangoSync" },
    { name: "View Dashboard Tab", functionName: "openDashboardTab" },
  ]);
}

function openDashboardTab() {
  var tab = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(DASHBOARD_TAB);
  if (tab) tab.activate();
}
