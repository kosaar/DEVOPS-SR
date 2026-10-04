/**
 * Action "Mark as blocked": asks for the reason and sets Blocked Reason + State in one go.
 * Available in the issue "..." menu and as the command: block
 */
const entities = require('@jetbrains/youtrack-scripting-api/entities');

exports.rule = entities.Issue.action({
  title: 'Mark as blocked',
  command: 'block',
  userInput: {
    type: entities.Field.stringType,
    description: 'Why is this request blocked? (waiting for whom / what)'
  },
  guard: (ctx) => ctx.issue.isReported && !ctx.issue.isResolved,
  action: (ctx) => {
    ctx.issue.fields['Blocked Reason'] = ctx.userInput;
    ctx.issue.fields.State = ctx.State.Blocked;
  },
  requirements: {
    State: { type: entities.State.fieldType, Blocked: {} },
    BlockedReason: { type: entities.Field.stringType, name: 'Blocked Reason' }
  }
});
