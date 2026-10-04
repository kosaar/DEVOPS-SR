/**
 * "Request forms": when a developer picks the request Type on a new (draft) request,
 * insert the matching description template. Untouched templates are swapped if the
 * Type is changed; anything the user already typed is never overwritten.
 */
const entities = require('@jetbrains/youtrack-scripting-api/entities');
const C = require('./common');

exports.rule = entities.Issue.onChange({
  title: 'Insert the request template for the selected Type (draft only)',
  guard: (ctx) => {
    const issue = ctx.issue;
    return !issue.isReported && !issue.becomesReported && issue.fields.Type &&
      C.TEMPLATES[issue.fields.Type.name] && C.isUntouchedTemplate(issue.description) &&
      issue.description !== C.TEMPLATES[issue.fields.Type.name];
  },
  action: (ctx) => {
    ctx.issue.description = C.TEMPLATES[ctx.issue.fields.Type.name];
  },
  requirements: {
    Type: { type: entities.EnumField.fieldType }
  }
});
