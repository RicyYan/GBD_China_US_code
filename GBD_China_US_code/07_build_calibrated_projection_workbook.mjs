import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

// Set GBD_PROJECT_ROOT or GBD_CALIBRATION_OUTPUT_DIR when the files are stored
// somewhere other than the current working directory. No local user path is embedded.
const projectRoot = process.env.GBD_PROJECT_ROOT ?? process.cwd();
const outDir = process.env.GBD_CALIBRATION_OUTPUT_DIR
  ?? path.join(projectRoot, "outputs", "gbd_neuro_calibration");
const data = JSON.parse(await fs.readFile(path.join(outDir, "calibration_data.json"), "utf8"));
const wb = Workbook.create();
const intro = wb.worksheets.add("Overview and QA");
const coef = wb.worksheets.add("Coefficient QA");
const result = wb.worksheets.add("Calibrated results");
const pct = wb.worksheets.add("Percentage change");

const isOutsideReviewRange = value =>
  Number.isFinite(Number(value)) && (Number(value) < 0.3 || Number(value) > 3);

const coefficientQa = row => {
  const flagged = [
    ["mean factor", row.mean_factor],
    ["upper-distance factor", row.upper_distance_factor],
    ["lower-distance factor", row.lower_distance_factor],
  ].filter(([, value]) => isOutsideReviewRange(value)).map(([label]) => label);
  return flagged.length === 0
    ? "Pass"
    : `Review: ${flagged.join(", ")} outside 0.3-3`;
};

const sourceLabel = value => value ? path.win32.basename(String(value)) : "";

const navy = "#17365D", blue = "#D9EAF7", pale = "#F3F6F9", red = "#FCE4E4", amber = "#FFF2CC", green = "#E2F0D9";
for (const s of [intro, coef, result, pct]) { s.showGridLines = false; }

intro.getRange("A1:B1").merge();
intro.getRange("A1").values = [["GBD 2023-Anchored DALY Projections for 20 Neurological Conditions in China and the United States"]];
intro.getRange("A1:B1").format = { fill: navy, font: { bold: true, color: "#FFFFFF", size: 16 }, rowHeight: 30 };
intro.getRange("A3:B10").values = [
  ["Item", "Description"],
  ["Scope", "China and the United States; 20 conditions; both sexes combined; five future scenarios; 2024-2050"],
  ["Metrics", "DALY number and age-standardized DALY rate, calibrated separately"],
  ["Scenarios", "Reference plus four alternative or combined scenarios; Past is excluded because it has no future values"],
  ["Anchor", "2023: GBD 2023 estimate divided by the corresponding GBD forecast estimate"],
  ["Mean formula", "Calibrated mean = forecast mean x mean calibration factor"],
  ["Interval formula", "Distances from the mean to the lower and upper bounds are scaled separately; the lower bound is truncated at zero"],
  ["Key limitation", "Forecast files contain both sexes combined only; the Reference-derived factor is applied to every scenario"],
];
intro.getRange("A3:B3").format = { fill: blue, font: { bold: true, color: navy } };
intro.getRange("A4:A10").format = { fill: pale, font: { bold: true } };
intro.getRange("A3:B10").format.borders = { preset: "outside", style: "thin", color: "#9EADBA" };
intro.getRange("A12:B17").values = [
  ["QA metric", "Result"],
  ["Coefficient combinations", data.counts.coefficients],
  ["Rows across five scenarios", data.counts.projections],
  ["Coefficient combinations flagged for review", data.coefficients.filter(x => coefficientQa(x) !== "Pass").length],
  ["Anchor-matching errors", data.issues.filter(x => x.severity === "error").length],
  ["Sex coverage", "Both sexes combined only"],
];
intro.getRange("A12:B12").format = { fill: blue, font: { bold: true, color: navy } };
intro.getRange("A13:A17").format = { fill: pale, font: { bold: true } };
intro.getRange("A19:B24").values = [
  ["Source", "Reference"],
  ["Methods article", "https://pmc.ncbi.nlm.nih.gov/articles/PMC12687902/"],
  ["GBD forecast: age-standardized rate", "GBD forecast input: raw ASR"],
  ["GBD forecast: number", "GBD forecast input: raw number"],
  ["GBD 2023 historical estimates", "China DALY.csv; US DALY.csv"],
  ["Review rule", "Flag any mean or interval-distance factor below 0.3 or above 3; do not cap automatically"],
];
intro.getRange("A19:B19").format = { fill: blue, font: { bold: true, color: navy } };
intro.getRange("A20:A24").format = { fill: pale, font: { bold: true } };
intro.getRange("A1:B24").format.wrapText = true;
intro.getRange("A:A").format.columnWidth = 22;
intro.getRange("B:B").format.columnWidth = 85;

const cHeaders = ["Key", "Country", "Cause", "Sex", "Metric", "Forecast 2023 mean", "Forecast 2023 lower", "Forecast 2023 upper", "GBD 2023 mean", "GBD 2023 lower", "GBD 2023 upper", "Mean factor", "Upper-distance factor", "Lower-distance factor", "QA flag", "Forecast source", "History source"];
coef.getRangeByIndexes(0, 0, 1, cHeaders.length).values = [cHeaders];
coef.getRangeByIndexes(1, 0, data.coefficients.length, cHeaders.length).values = data.coefficients.map(x => [x.key,x.country,x.cause,x.sex,x.metric,x.forecast_2023_mean,x.forecast_2023_lower,x.forecast_2023_upper,x.gbd2023_mean,x.gbd2023_lower,x.gbd2023_upper,x.mean_factor,x.upper_distance_factor,x.lower_distance_factor,coefficientQa(x),sourceLabel(x.source_forecast),sourceLabel(x.source_history)]);
coef.getRangeByIndexes(0,0,1,cHeaders.length).format = { fill: navy, font: { bold:true, color:"#FFFFFF" }, wrapText:true, rowHeight:32 };
coef.freezePanes.freezeRows(1); coef.freezePanes.freezeColumns(5);
coef.getRange(`F2:N${data.coefficients.length+1}`).format.numberFormat = "0.0000";
coef.getRange(`A1:Q${data.coefficients.length+1}`).format.rowHeight = 20;
for (let i=0;i<data.coefficients.length;i++) if(coefficientQa(data.coefficients[i])!=="Pass") coef.getRange(`A${i+2}:Q${i+2}`).format.fill = amber;
coef.getRange("A:A").format.columnWidth=42; coef.getRange("B:B").format.columnWidth=22; coef.getRange("C:C").format.columnWidth=42; coef.getRange("D:E").format.columnWidth=16; coef.getRange("F:N").format.columnWidth=18; coef.getRange("O:O").format.columnWidth=38; coef.getRange("P:Q").format.columnWidth=70;

const rHeaders = ["Key","Country","Cause","Sex","Metric","Scenario","Year","Forecast mean","Forecast lower","Forecast upper","Mean factor","Upper-distance factor","Lower-distance factor","Calibrated mean","Calibrated lower","Calibrated upper","Lower truncated?","Coefficient QA"];
result.getRangeByIndexes(0,0,1,rHeaders.length).values=[rHeaders];
result.getRangeByIndexes(1,0,data.projections.length,13).values=data.projections.map(x=>[x.key,x.country,x.cause,x.sex,x.metric,x.scenario,x.year,x.forecast_mean,x.forecast_lower,x.forecast_upper,x.mean_factor,x.upper_distance_factor,x.lower_distance_factor]);
result.getRangeByIndexes(1,17,data.projections.length,1).values=data.projections.map(x=>[coefficientQa(x)]);
for(let i=0;i<data.projections.length;i++){
  const row=i+2;
  result.getRange(`N${row}:Q${row}`).formulas=[[
    `=H${row}*K${row}`,
    `=MAX(0,N${row}-(H${row}-I${row})*M${row})`,
    `=N${row}+(J${row}-H${row})*L${row}`,
    `=IF(N${row}-(H${row}-I${row})*M${row}<0,"Yes","No")`
  ]];
}
result.getRangeByIndexes(0,0,1,rHeaders.length).format={fill:navy,font:{bold:true,color:"#FFFFFF"},wrapText:true,rowHeight:32};
result.freezePanes.freezeRows(1); result.freezePanes.freezeColumns(7);
result.getRange(`H2:P${data.projections.length+1}`).format.numberFormat="0.0000";
result.getRange("A:A").format.columnWidth=42; result.getRange("B:B").format.columnWidth=22; result.getRange("C:C").format.columnWidth=42; result.getRange("D:E").format.columnWidth=15; result.getRange("F:F").format.columnWidth=46; result.getRange("G:G").format.columnWidth=12; result.getRange("H:P").format.columnWidth=18; result.getRange("Q:R").format.columnWidth=34;

const groups = new Map();
data.projections.forEach((x,i)=>{
  const k=[x.country,x.cause,x.sex,x.metric,x.scenario].join("|");
  if(!groups.has(k)) groups.set(k,{country:x.country,cause:x.cause,sex:x.sex,metric:x.metric,scenario:x.scenario});
  if(x.year===2024) groups.get(k).row2024=i+2;
  if(x.year===2050) groups.get(k).row2050=i+2;
});
const pctRows=[...groups.values()].sort((a,b)=>[a.country,a.cause,a.metric,a.scenario].join("|").localeCompare([b.country,b.cause,b.metric,b.scenario].join("|")));
const pHeaders=["Country","Cause","Sex","Metric","Scenario","Start year","End year","2024 calibrated mean","2050 calibrated mean","Mean percentage change","2024 calibrated lower","2050 calibrated lower","Lower percentage change","2024 calibrated upper","2050 calibrated upper","Upper percentage change","QA"];
pct.getRangeByIndexes(0,0,1,pHeaders.length).values=[pHeaders];
pct.getRangeByIndexes(1,0,pctRows.length,7).values=pctRows.map(x=>[x.country,x.cause,x.sex,x.metric,x.scenario,2024,2050]);
pct.getRangeByIndexes(1,16,pctRows.length,1).values=pctRows.map(x=>[x.row2024&&x.row2050?"Pass":"Missing endpoint year"]);
for(let i=0;i<pctRows.length;i++){
  const r=i+2,x=pctRows[i];
  pct.getRange(`H${r}:P${r}`).formulas=[[
    `='Calibrated results'!N${x.row2024}`,`='Calibrated results'!N${x.row2050}`,`=IF(H${r}=0,"",I${r}/H${r}-1)`,
    `='Calibrated results'!O${x.row2024}`,`='Calibrated results'!O${x.row2050}`,`=IF(K${r}=0,"",L${r}/K${r}-1)`,
    `='Calibrated results'!P${x.row2024}`,`='Calibrated results'!P${x.row2050}`,`=IF(N${r}=0,"",O${r}/N${r}-1)`
  ]];
}
pct.getRangeByIndexes(0,0,1,pHeaders.length).format={fill:navy,font:{bold:true,color:"#FFFFFF"},wrapText:true,rowHeight:34};
pct.freezePanes.freezeRows(1); pct.freezePanes.freezeColumns(5);
pct.getRange(`H2:I${pctRows.length+1}`).format.numberFormat="0.0000";
pct.getRange(`K2:L${pctRows.length+1}`).format.numberFormat="0.0000";
pct.getRange(`N2:O${pctRows.length+1}`).format.numberFormat="0.0000";
pct.getRange(`J2:J${pctRows.length+1}`).format.numberFormat="0.00%";
pct.getRange(`M2:M${pctRows.length+1}`).format.numberFormat="0.00%";
pct.getRange(`P2:P${pctRows.length+1}`).format.numberFormat="0.00%";
pct.getRange(`J2:J${pctRows.length+1}`).conditionalFormats.add("cellIs",{operator:"greaterThanOrEqual",formula:0,format:{fill:green}});
pct.getRange(`J2:J${pctRows.length+1}`).conditionalFormats.add("cellIs",{operator:"lessThan",formula:0,format:{fill:red}});
pct.getRange(`M2:M${pctRows.length+1}`).conditionalFormats.add("cellIs",{operator:"greaterThanOrEqual",formula:0,format:{fill:green}});
pct.getRange(`M2:M${pctRows.length+1}`).conditionalFormats.add("cellIs",{operator:"lessThan",formula:0,format:{fill:red}});
pct.getRange(`P2:P${pctRows.length+1}`).conditionalFormats.add("cellIs",{operator:"greaterThanOrEqual",formula:0,format:{fill:green}});
pct.getRange(`P2:P${pctRows.length+1}`).conditionalFormats.add("cellIs",{operator:"lessThan",formula:0,format:{fill:red}});
pct.getRange("A:A").format.columnWidth=22; pct.getRange("B:B").format.columnWidth=42; pct.getRange("C:D").format.columnWidth=15; pct.getRange("E:E").format.columnWidth=46; pct.getRange("F:G").format.columnWidth=12; pct.getRange("H:P").format.columnWidth=22; pct.getRange("Q:Q").format.columnWidth=18;

const errorScan = await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",options:{useRegex:true,maxResults:100},summary:"final formula error scan"});
console.log(errorScan.ndjson);
console.log((await wb.inspect({kind:"table",range:"Overview and QA!A1:B24",include:"values,formulas",tableMaxRows:24,tableMaxCols:2})).ndjson);
const preview = await wb.render({sheetName:"Overview and QA",range:"A1:B24",scale:1.4,format:"png"});
await fs.writeFile(path.join(outDir,"preview.png"),new Uint8Array(await preview.arrayBuffer()));
const coefPreview = await wb.render({sheetName:"Coefficient QA",range:"A1:Q16",scale:0.8,format:"png"});
await fs.writeFile(path.join(outDir,"preview_coefficients.png"),new Uint8Array(await coefPreview.arrayBuffer()));
const resultPreview = await wb.render({sheetName:"Calibrated results",range:"A1:R16",scale:0.8,format:"png"});
await fs.writeFile(path.join(outDir,"preview_results.png"),new Uint8Array(await resultPreview.arrayBuffer()));
const pctPreview = await wb.render({sheetName:"Percentage change",range:"A1:Q18",scale:0.8,format:"png"});
await fs.writeFile(path.join(outDir,"preview_percentage_change.png"),new Uint8Array(await pctPreview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(path.join(outDir,"GBD2023_anchored_DALY_projections_China_US_2024-2050.xlsx"));
console.log("EXPORTED");
