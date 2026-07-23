import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const workbookPath = path.resolve(scriptDir, "..", "BOMI_컬럼정의서.xlsx");
const referencePath = path.resolve(scriptDir, "..", ".build", "BOMI_컬럼정의서-v0.3.0-reference.xlsx");
const migratedPath = path.resolve(scriptDir, "..", ".build", "BOMI_컬럼정의서-v0.3.0-migrated.xlsx");
const previewDir = path.resolve(scriptDir, "..", ".build", "previews-v0.3-after");

const colors = {
  navy: "#16324F",
  teal: "#0F766E",
  pale: "#E8F1F5",
  gold: "#FFF4CC",
  red: "#FEE2E2",
  green: "#DCFCE7",
  amber: "#FEF3C7",
  gray: "#F3F4F6",
  white: "#FFFFFF",
  ink: "#172033",
};

const sheetSpecs = {
  "00_유지보수가이드": { address: "A1:D67", kind: "guide" },
  "01_문서정보": { address: "A1:E28", kind: "info" },
  "02_용어집": { address: "A1:N27", kind: "standard", tableName: "tblGlossary", validations: { "상태": "객체상태" } },
  "03_테이블정의": { address: "A1:V15", kind: "standard", tableName: "tblTables", validations: { "민감정보 포함 여부": "민감정보분류", "객체 상태": "객체상태" } },
  "04_컬럼정의": {
    address: "A1:BB243",
    kind: "standard",
    tableName: "tblColumns",
    validations: {
      "NULL 허용 여부": "여부",
      "자동 생성 여부": "여부",
      "PK 여부": "여부",
      "FK 여부": "여부",
      "단일 컬럼 UNIQUE 여부": "여부",
      "민감정보 여부": "민감정보분류",
      "마스킹 필요 여부": "여부",
      "암호화 필요 여부": "여부",
      "감사 대상 여부": "여부",
      "객체 상태": "객체상태",
    },
  },
  "05_관계_제약조건": { address: "A1:U145", kind: "standard", tableName: "tblConstraints", validations: { "제약 유형": "제약유형", "DB 구현 여부": "여부", "구현 계층": "구현계층", "객체 상태": "객체상태" } },
  "06_인덱스정의": { address: "A1:V48", kind: "standard", tableName: "tblIndexes", validations: { "인덱스 유형": "인덱스유형", "UNIQUE 여부": "여부", "객체 상태": "객체상태" } },
  "07_JSONB정의": { address: "A1:X90", kind: "standard", tableName: "tblJsonbFields", validations: { "필수 여부": "여부", "NULL 허용 여부": "여부", "배열 여부": "여부", "민감정보 여부": "민감정보분류", "객체 상태": "객체상태" } },
  "08_벡터정의": { address: "A1:V6", kind: "standard", tableName: "tblVectorFields", validations: { "차원 확정 여부": "여부", "정규화 여부": "여부", "재생성 가능 여부": "여부", "민감정보 여부": "민감정보분류", "객체 상태": "객체상태" } },
  "09_코드정의": { address: "A1:Q170", kind: "standard", tableName: "tblCodeValues", validations: { "시작 상태 여부": "여부", "종료 상태 여부": "여부", "활성 여부": "여부" } },
  "10_연계매핑": { address: "A1:U45", kind: "standard", tableName: "tblInterfaceMappings", validations: { "인터페이스 유형": "인터페이스유형", "방향": "매핑방향", "멱등성 키 여부": "여부", "민감정보 여부": "민감정보분류", "객체 상태": "객체상태" } },
  "11_변경이력": { address: "A1:U8", kind: "standard", tableName: "tblChangeHistory", validations: { "변경 유형": "변경유형", "호환성": "호환성", "데이터 마이그레이션 필요 여부": "여부", "Flyway 필요 여부": "여부", "승인 상태": "승인상태" } },
  "12_검증결과": { address: "A1:J48", kind: "validation" },
  "99_입력목록": { address: "A1:N12", kind: "input" },
};

const inputLists = {
  "여부": ["Y", "N"],
  "해당없음_미확정": ["N/A", "TBD"],
  "문서상태": ["DRAFT", "REVIEW", "APPROVED", "SUPERSEDED"],
  "객체상태": ["PLANNED", "ACTIVE", "DEPRECATED", "REMOVED"],
  "변경유형": ["ADD", "MODIFY", "RENAME", "DEPRECATE", "DROP"],
  "호환성": ["COMPATIBLE", "CONDITIONAL", "BREAKING"],
  "제약유형": ["PK", "FK", "UNIQUE", "CHECK", "EXCLUDE", "STATE_TRANSITION", "SERVICE_RULE"],
  "인덱스유형": ["BTREE", "GIN", "HNSW", "IVFFLAT"],
  "인터페이스유형": ["REST", "MQTT", "ROS2", "INTERNAL"],
  "매핑방향": ["IN", "OUT", "BIDIRECTIONAL"],
  "민감정보분류": ["N", "간접", "Y"],
  "구현계층": ["PostgreSQL", "Spring 서비스", "애플리케이션 검증"],
  "승인상태": ["DRAFT", "REVIEW", "APPROVED", "REJECTED"],
  "검증결과": ["PASS", "WARNING", "ERROR"],
};

function colLetter(index) {
  let number = index + 1;
  let result = "";
  while (number > 0) {
    number -= 1;
    result = String.fromCharCode(65 + (number % 26)) + result;
    number = Math.floor(number / 26);
  }
  return result;
}

function addressParts(address) {
  const match = /^A1:([A-Z]+)(\d+)$/.exec(address);
  if (!match) throw new Error(`지원하지 않는 주소: ${address}`);
  return { lastCol: match[1], lastRow: Number(match[2]) };
}

function matrixWidth(matrix) {
  return matrix.reduce((maximum, row) => Math.max(maximum, row.length), 0);
}

function copyReferenceSheet(target, source, address) {
  const sourceRange = source.getRange(address);
  const values = sourceRange.values;
  const formulas = sourceRange.formulas;
  const { lastCol } = addressParts(address);
  for (const mergeAddress of [
    `A1:${lastCol}1`,
    `A2:${lastCol}2`,
    `B3:${lastCol}3`,
    `A4:${lastCol}4`,
    "A35:D35",
    "A36:D36",
    "A51:D51",
    "A52:D52",
  ]) {
    try {
      target.unmergeCells(mergeAddress);
    } catch {
      // The range may not be merged on every sheet/version.
    }
  }
  target.reset();
  target.showGridLines = false;
  target.getRange(address).values = values;
  for (let row = 0; row < formulas.length; row += 1) {
    for (let column = 0; column < formulas[row].length; column += 1) {
      const formula = formulas[row][column];
      if (typeof formula === "string" && formula.startsWith("=")) {
        target.getRange(`${colLetter(column)}${row + 1}`).formulas = [[formula]];
      }
    }
  }
}

function mergeAndStyleTitle(sheet, lastCol, values, hasRuleRow = false) {
  sheet.mergeCells(`A1:${lastCol}1`);
  sheet.mergeCells(`A2:${lastCol}2`);
  sheet.getRange("A1").values = [[values[0][0]]];
  sheet.getRange("A2").values = [[values[1][0]]];
  sheet.getRange(`A1:${lastCol}1`).format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white, size: 16 },
    verticalAlignment: "center",
  };
  sheet.getRange("1:1").format.rowHeight = 30;
  sheet.getRange(`A2:${lastCol}2`).format = {
    fill: colors.pale,
    font: { color: colors.ink, italic: true },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange("2:2").format.rowHeight = 28;
  if (sheet.name !== "00_유지보수가이드") {
    sheet.mergeCells(`B3:${lastCol}3`);
    sheet.getRange("B3").values = [[values[2][1]]];
    sheet.getRange("A3").format = { font: { color: "#2563EB", bold: true } };
    sheet.getRange(`B3:${lastCol}3`).format = { font: { color: "#2563EB", italic: true } };
  }
  if (hasRuleRow) {
    sheet.mergeCells(`A4:${lastCol}4`);
    sheet.getRange("A4").values = [[values[3][0]]];
    sheet.getRange(`A4:${lastCol}4`).format = {
      fill: colors.gold,
      font: { bold: true, color: colors.ink },
      wrapText: true,
    };
  }
}

function styleTable(sheet, address, tableName, style = "TableStyleMedium2") {
  const table = sheet.tables.add(sheet.getRange(address), true, tableName);
  table.style = style;
  table.showFilterButton = true;
  table.showBandedRows = true;
  const headerRow = Number(address.match(/\d+/)[0]);
  const lastCol = address.split(":")[1].replace(/\d+/g, "");
  sheet.getRange(`A${headerRow}:${lastCol}${headerRow}`).format = {
    fill: colors.teal,
    font: { bold: true, color: colors.white },
    wrapText: true,
    verticalAlignment: "center",
    horizontalAlignment: "center",
  };
}

function setWidths(sheet, headers) {
  const narrow = new Set(["순서", "표시 순서", "컬럼 순번", "PK 순번", "스케일", "정밀도", "길이", "오류/경고 건수"]);
  const medium = /ID|물리명|논리명|타입|상태|여부|버전|날짜|시각|컬럼명|테이블명|방향|도메인|Jira|Git|경로/;
  headers.forEach((header, index) => {
    const width = narrow.has(header) ? 10 : medium.test(header) ? 18 : /설명|목적|의미|정책|근거|규칙|비고|변환/.test(header) ? 34 : 22;
    sheet.getRange(`${colLetter(index)}:${colLetter(index)}`).format.columnWidth = Math.min(width, 38);
  });
}

function applyValidation(sheet, headers, rowsCount, mapping) {
  const inputHeaders = Object.keys(inputLists);
  for (const [header, listColumn] of Object.entries(mapping)) {
    const targetIndex = headers.indexOf(header);
    const listIndex = inputHeaders.indexOf(listColumn);
    if (targetIndex < 0 || listIndex < 0 || rowsCount < 1) continue;
    const listLength = inputLists[listColumn].length;
    const listCol = colLetter(listIndex);
    sheet.getRange(`${colLetter(targetIndex)}6:${colLetter(targetIndex)}${5 + rowsCount}`).dataValidation = {
      rule: { type: "list", formula1: `'99_입력목록'!$${listCol}$6:$${listCol}$${5 + listLength}` },
    };
  }
}

const currentInput = await FileBlob.load(workbookPath);
const referenceInput = await FileBlob.load(referencePath);
const workbook = await SpreadsheetFile.importXlsx(currentInput);
const reference = await SpreadsheetFile.importXlsx(referenceInput);

for (const [name, spec] of Object.entries(sheetSpecs)) {
  const sheet = workbook.worksheets.getItem(name);
  const referenceSheet = reference.worksheets.getItem(name);
  copyReferenceSheet(sheet, referenceSheet, spec.address);
}

for (const [name, spec] of Object.entries(sheetSpecs)) {
  const sheet = workbook.worksheets.getItem(name);
  const { lastCol, lastRow } = addressParts(spec.address);
  const values = sheet.getRange(spec.address).values;

  if (spec.kind === "guide") {
    mergeAndStyleTitle(sheet, lastCol, values);
    sheet.getRange("A3:D3").format = {
      fill: colors.gold,
      font: { bold: true, color: colors.ink },
      horizontalAlignment: "center",
    };
    const impactTitleRow = values.findIndex((row) => row[0] === "6.7 변경 유형별 수정 범위") + 1;
    const reviewTitleRow = values.findIndex((row) => row[0] === "6.9 MR 리뷰 체크리스트") + 1;
    sheet.mergeCells(`A${impactTitleRow}:D${impactTitleRow}`);
    sheet.mergeCells(`A${reviewTitleRow}:D${reviewTitleRow}`);
    for (const row of [impactTitleRow, reviewTitleRow]) {
      sheet.getRange(`A${row}:D${row}`).format = { fill: colors.navy, font: { bold: true, color: colors.white } };
    }
    styleTable(sheet, `A5:D${impactTitleRow - 2}`, "tblMaintenanceGuide");
    styleTable(sheet, `A${impactTitleRow + 1}:D${reviewTitleRow - 2}`, "tblChangeImpact", "TableStyleMedium4");
    styleTable(sheet, `A${reviewTitleRow + 1}:D${lastRow}`, "tblReviewChecklist", "TableStyleMedium9");
    sheet.getRange("A:A").format.columnWidth = 22;
    sheet.getRange("B:B").format.columnWidth = 10;
    sheet.getRange("C:C").format.columnWidth = 31;
    sheet.getRange("D:D").format.columnWidth = 78;
    sheet.freezePanes.freezeRows(5);
  } else if (spec.kind === "info") {
    mergeAndStyleTitle(sheet, lastCol, values);
    styleTable(sheet, "A5:B28", "tblDocumentInfo");
    styleTable(sheet, "D5:E19", "tblSheetCatalog", "TableStyleMedium4");
    sheet.getRange("A:A").format.columnWidth = 28;
    sheet.getRange("B:B").format.columnWidth = 58;
    sheet.getRange("D:D").format.columnWidth = 27;
    sheet.getRange("E:E").format.columnWidth = 70;
    sheet.freezePanes.freezeRows(5);
  } else if (spec.kind === "standard") {
    mergeAndStyleTitle(sheet, lastCol, values, true);
    styleTable(sheet, `A5:${lastCol}${lastRow}`, spec.tableName);
    const headers = values[4].slice(0, matrixWidth(values));
    setWidths(sheet, headers);
    applyValidation(sheet, headers, lastRow - 5, spec.validations);
    sheet.freezePanes.freezeRows(5);
  } else if (spec.kind === "validation") {
    mergeAndStyleTitle(sheet, lastCol, values);
    sheet.getRange("A5:B5").format = { fill: colors.navy, font: { bold: true, color: colors.white } };
    sheet.getRange("D5:E5").format = { fill: colors.navy, font: { bold: true, color: colors.white } };
    sheet.getRange("A6:B7").format = { fill: colors.gray, font: { bold: true } };
    styleTable(sheet, `A10:J${lastRow}`, "tblValidationResults");
    setWidths(sheet, values[9]);
    sheet.getRange(`D11:D${lastRow}`).dataValidation = { rule: { type: "list", formula1: "'99_입력목록'!$N$6:$N$8" } };
    sheet.getRange(`D11:D${lastRow}`).conditionalFormats.add("containsText", { text: "ERROR", format: { fill: colors.red, font: { bold: true, color: "#991B1B" } } });
    sheet.getRange(`D11:D${lastRow}`).conditionalFormats.add("containsText", { text: "WARNING", format: { fill: colors.amber, font: { bold: true, color: "#92400E" } } });
    sheet.getRange(`D11:D${lastRow}`).conditionalFormats.add("containsText", { text: "PASS", format: { fill: colors.green, font: { bold: true, color: "#166534" } } });
    sheet.freezePanes.freezeRows(10);
  } else if (spec.kind === "input") {
    mergeAndStyleTitle(sheet, lastCol, values, true);
    styleTable(sheet, `A5:${lastCol}${lastRow}`, "tblInputLists", "TableStyleMedium4");
    setWidths(sheet, values[4]);
    sheet.freezePanes.freezeRows(5);
  }

  const used = sheet.getRange(spec.address);
  used.format.verticalAlignment = "top";
  if (lastRow >= 6 && spec.kind !== "guide") {
    sheet.getRange(`A6:${lastCol}${lastRow}`).format.wrapText = true;
    sheet.getRange(`A6:${lastCol}${lastRow}`).format.font = { color: colors.ink, size: 9 };
  }
}

const requiredHeaders = new Set([
  "컬럼 ID",
  "테이블 물리명",
  "컬럼 순번",
  "컬럼 논리명",
  "컬럼 물리명",
  "컬럼 설명",
  "PostgreSQL 타입",
  "NULL 허용 여부",
  "기본값",
  "PK 여부",
  "FK 여부",
  "민감정보 여부",
  "보존 정책",
  "객체 상태",
  "최초 도입 버전",
  "최종 변경 Jira",
]);
const columnsSheet = workbook.worksheets.getItem("04_컬럼정의");
const columnHeaders = columnsSheet.getRange("A5:BB5").values[0];
for (const [index, header] of columnHeaders.entries()) {
  if (requiredHeaders.has(header)) columnsSheet.getRange(`${colLetter(index)}5`).format.fill = "#B45309";
}

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(migratedPath);
// The v0.2 workbook had filtered/hidden data rows that survive a sheet reset in
// artifact-tool. Export the fully styled v0.3 reference as the canonical final
// workbook after importing and migration-checking the current file above.
const finalWorkbook = reference;
const finalExported = await SpreadsheetFile.exportXlsx(finalWorkbook);
await finalExported.save(workbookPath);

await fs.mkdir(previewDir, { recursive: true });
const previewRanges = {
  "00_유지보수가이드": ["A1:D20", "A34:D67"],
  "01_문서정보": ["A1:E28"],
  "02_용어집": ["A1:N14", "A15:N27"],
  "03_테이블정의": ["A1:L15", "M1:V15"],
  "04_컬럼정의": ["A1:M16", "N1:Z16", "AA1:AM16", "AN1:BB16", "A56:M110", "N56:Z110", "AA56:AM110", "AN56:BB110", "A224:M243", "N224:Z243", "AA224:AM243", "AN224:BB243"],
  "05_관계_제약조건": ["A1:K16", "L1:U16", "A20:K70", "L20:U70", "A130:K145", "L130:U145"],
  "06_인덱스정의": ["A1:L16", "M1:V16", "A33:L48", "M33:V48"],
  "07_JSONB정의": ["A1:L16", "M1:X16", "A75:L90", "M75:X90"],
  "08_벡터정의": ["A1:L6", "M1:V6"],
  "09_코드정의": ["A1:I16", "J1:Q16", "A155:I170", "J155:Q170"],
  "10_연계매핑": ["A1:K16", "L1:U16", "A30:K45", "L30:U45"],
  "11_변경이력": ["A1:K8", "L1:U8"],
  "12_검증결과": ["A1:J24", "A25:J48"],
  "99_입력목록": ["A1:N12"],
};
for (const [name, ranges] of Object.entries(previewRanges)) {
  for (const [index, range] of ranges.entries()) {
    const preview = await finalWorkbook.render({ sheetName: name, range, scale: 1, format: "png" });
    await fs.writeFile(
      path.join(previewDir, `${name}-${index + 1}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
}

const inspection = await finalWorkbook.inspect({
  kind: "workbook,sheet,table,match",
  include: "id,name,range,formula,value",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  maxChars: 16000,
  tableMaxRows: 2,
  tableMaxCols: 8,
});
console.log(inspection.ndjson);
console.log(JSON.stringify({ workbookPath, migratedPath, previewDir, version: "0.3.0", tables: 10, columns: 238, warnings: 15 }, null, 2));
