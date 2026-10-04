/**
 * When a blocked request becomes active again (any state other than Blocked),
 * write an audit comment (how long + why) and clear the blocked metadata.
 */
const entities = require('@jetbrains/youtrack-scripting-api/entities');
const C = require('./common');

exports.rule = entities.Issue.onChange({
  title: 'Clear blocked metadata when a request is unblocked',
  guard: (ctx) => {
    const issue = ctx.issue;
    if (!issue.isReported || !issue.fields.isChanged(ctx.State)) {
      return false;
    }
    const old = issue.fields.oldValue(ctx.State);
    return old && old.name === 'Blocked' && !issue.fields.is(ctx.State, ctx.State.Blocked);
  },
  action: (ctx) => {
    const issue = ctx.issue;
    const since = issue.fields['Blocked Since'];
    const reason = issue.fields['Blocked Reason'];
    const days = since ? Math.max(0, Math.round((Date.now() - since) / C.DAY * 10) / 10) : null;
    issue.addComment('Unblocked' + (days !== null ? ' after ' + days + ' day(s)' : '') +
      (reason ? '. Blocked reason was: ' + reason : '.'));
    issue.fields['Blocked Reason'] = null;
    issue.fields['Blocked Since'] = null;
  },
  requirements: {
    State: { type: entities.State.fieldType, Blocked: {} },
    BlockedReason: { type: entities.Field.stringType, name: 'Blocked Reason' },
    BlockedSince: { type: entities.Field.dateTimeType, name: 'Blocked Since' }
  }
});
