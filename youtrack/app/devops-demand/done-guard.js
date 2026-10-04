/**
 * Moving a request to Done requires a reference to the implementation in GitLab
 * ("GitLab Issue/MR reference", e.g. platform/ci-templates!12) unless the request
 * is tagged 'no-code-change' (advice, access grant, question answered...).
 */
const entities = require('@jetbrains/youtrack-scripting-api/entities');
const workflow = require('@jetbrains/youtrack-scripting-api/workflow');

exports.rule = entities.Issue.onChange({
  title: 'Done requires the GitLab implementation reference (when applicable)',
  guard: (ctx) => ctx.issue.isReported && ctx.issue.fields.becomes(ctx.State, ctx.State.Done),
  action: (ctx) => {
    const issue = ctx.issue;
    const ref = issue.fields['GitLab Issue/MR reference'];
    workflow.check((ref && ref.trim().length > 0) || issue.hasTag('no-code-change'),
      'Before closing, link the implementation: set "GitLab Issue/MR reference" ' +
      '(e.g. platform/ci-templates!12), or add the tag "no-code-change" if nothing was implemented in GitLab.');
    if (issue.hasTag('aging')) {
      issue.removeTag('aging');
    }
  },
  requirements: {
    State: { type: entities.State.fieldType, Done: {} },
    GitLabRef: { type: entities.Field.stringType, name: 'GitLab Issue/MR reference' }
  }
});
