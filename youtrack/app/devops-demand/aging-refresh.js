/**
 * Command "refresh-aging": recompute Aging immediately (used after imports,
 * or by anyone who does not want to wait for the hourly run).
 */
const entities = require('@jetbrains/youtrack-scripting-api/entities');
const C = require('./common');

exports.rule = entities.Issue.action({
  title: 'Refresh aging',
  command: 'refresh-aging',
  guard: () => true,
  action: (ctx) => {
    C.refreshAging(ctx.issue, ctx.settings);
  },
  requirements: {
    Aging: { type: entities.EnumField.fieldType },
    RequestedOn: { type: entities.Field.dateType, name: 'Requested On' }
  }
});
