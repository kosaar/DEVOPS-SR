/**
 * Every hour: recompute the Aging bucket of every open request and tag requests
 * older than the configured threshold (app setting "Aging threshold (days)") with 'aging'.
 */
const entities = require('@jetbrains/youtrack-scripting-api/entities');
const C = require('./common');

exports.rule = entities.Issue.onSchedule({
  title: 'Flag aging requests (hourly)',
  search: '#Unresolved',
  cron: '0 0 * * * ?',
  action: (ctx) => {
    C.refreshAging(ctx.issue, ctx.settings);
  },
  requirements: {
    Aging: { type: entities.EnumField.fieldType },
    RequestedOn: { type: entities.Field.dateType, name: 'Requested On' }
  }
});
