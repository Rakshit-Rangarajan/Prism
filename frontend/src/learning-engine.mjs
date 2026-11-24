export const LEARNING_TASKS = ['schema_mapping', 'exception_classification', 'sap_object_mapping', 'sql_conversion'];
export const TASK_LABELS = {
  schema_mapping: 'Schema / field mapping',
  exception_classification: 'Exception classification',
  sap_object_mapping: 'SAP object mapping',
  sql_conversion: 'SQL / query conversion',
};
export function compactTask(task) { return TASK_LABELS[task] || String(task).replace(/_/g, ' '); }
export function formatAccuracy(metrics) {
  if (!metrics || typeof metrics.accuracy !== 'number') return '—';
  return (metrics.accuracy * 100).toFixed(1) + '%';
}
export function validSlug(slug) { return /^[a-z0-9][a-z0-9-]{1,48}$/.test(String(slug)); }
export function summarizeExamples(examples) {
  const out = { total: examples.length, approved: 0, draft: 0, rejected: 0 };
  for (const example of examples) if (example.state in out) out[example.state] += 1;
  return out;
}
export function scoreLabel(score) {
  if (typeof score !== 'number') return '—';
  return score.toFixed(3);
}
