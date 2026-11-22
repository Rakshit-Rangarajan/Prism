export interface ParsedCSV {headers:string[];rows:string[][]}
export interface CSVField {name:string;index:number;type:string;missing:number;unique:number;examples:string[]}
export interface CSVReport {rows:number;columns:number;missingCells:number;duplicateRows:number;distinctRows:number;fields:CSVField[];duplicateIndexes:number[];warning:string}
export interface CleanOptions {trim?:boolean;dropExactDuplicates?:boolean;normalizeEmpty?:boolean}
export interface CleanResult extends ParsedCSV {removed:number;changed:number}
export function parseCSV(text:string,maxRows?:number,maxColumns?:number):ParsedCSV;
export function profileCSV(parsed:ParsedCSV):CSVReport;
export function cleanCSV(parsed:ParsedCSV,options?:CleanOptions):CleanResult;
export function serializeCSV(parsed:ParsedCSV):string;
