export const LEARNING_TASKS:string[];
export const TASK_LABELS:Record<string,string>;
export function compactTask(task:string):string;
export function formatAccuracy(metrics:Record<string,unknown>|null|undefined):string;
export function validSlug(slug:string):boolean;
export function summarizeExamples(examples:Array<{state:string}>):{total:number;approved:number;draft:number;rejected:number};
export function scoreLabel(score:unknown):string;
