/**
 * Moving a request to Blocked requires a Blocked Reason and records Blocked Since.
 * Tip: use the "Mark as blocked" action (issue menu, or command "block <reason>")
 * to set both at once.
 */
const entities = require('@jetbrains/youtrack-scripting-api/entities');
const workflow = require('@jetbrains/youtrack-scripting-api/workflow');

exports.rule = entities.Issue.onChange({
  title: 'Blocked requires a Blocked Reason and records Blocked Since',
  guard: (ctx) => ctx.issue.isReported && ctx.issue.fields.becomes(ctx.State, ctx.State.Blocked),
  action: (ctx) => {
    const issue = ctx.issue;
    const reason = issue.fields['Blocked Reason'];
    workflow.check(reason && reason.trim().length > 0,
      'Fill in "Blocked Reason" before moving the request to Blocked ' +
      '(or use the "Mark as blocked" action, which asks for the reason).');
    issue.fields['Blocked Since'] = Date.now();
  },
  requirements: {
    State: { type: entities.State.fieldType, Blocked: {} },
    BlockedReason: { type: entities.Field.stringType, name: 'Blocked Reason' },
    BlockedSince: { type: entities.Field.dateTimeType, name: 'Blocked Since' }
  }
});
