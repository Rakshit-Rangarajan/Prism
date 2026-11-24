import test from 'node:test';
import assert from 'node:assert/strict';
import {compactTask,formatAccuracy,validSlug,summarizeExamples,scoreLabel,LEARNING_TASKS} from '../src/learning-engine.mjs';

test('task labels stay readable and complete', () => {
  assert.equal(LEARNING_TASKS.length, 4);
  assert.equal(compactTask('schema_mapping'), 'Schema / field mapping');
  assert.equal(compactTask('custom_task'), 'custom task');
});
test('accuracy is formatted only when present', () => {
  assert.equal(formatAccuracy({accuracy:0.875}), '87.5%');
  assert.equal(formatAccuracy({}), '—');
  assert.equal(formatAccuracy(null), '—');
});
test('slug validation mirrors the API contract', () => {
  assert.equal(validSlug('acme-corp'), true);
  assert.equal(validSlug('Acme Corp'), false);
  assert.equal(validSlug('a'), false);
});
test('example summary counts each state', () => {
  const out = summarizeExamples([{state:'approved'},{state:'draft'},{state:'draft'},{state:'unknown'}]);
  assert.deepEqual(out, {total:4,approved:1,draft:2,rejected:0});
});
test('scores display deterministically', () => {
  assert.equal(scoreLabel(0.12345), '0.123');
  assert.equal(scoreLabel(undefined), '—');
});
