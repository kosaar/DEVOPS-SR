/**
 * Intake: when a request is submitted, enforce the type-specific mandatory
 * information and route it to Triage.
 *  - all types: Requester Squad, Service, Priority (also required at field level)
 *  - Demand:    Target Date + "Business / technical impact"
 *  - Bug:       Environment + Expected/Actual behavior + Evidence
 *  - Improvement: "Expected benefit"
 */
const entities = require('@jetbrains/youtrack-scripting-api/entities');
const workflow = require('@jetbrains/youtrack-scripting-api/workflow');
const C = require('./common');

exports.rule = entities.Issue.onChange({
  title: 'Validate a new request and move it to Triage',
  guard: (ctx) => ctx.issue.becomesReported,
  action: (ctx) => {
    const issue = ctx.issue;
    const type = issue.fields.Type ? issue.fields.Type.name : null;
    workflow.check(issue.fields['Requester Squad'], 'Select your Requester Squad.');
    workflow.check(issue.fields.Service, 'Select the DevOps Service concerned.');
    workflow.check(issue.fields.Priority, 'Select a Priority.');
    if (type === 'Demand') {
      workflow.check(issue.fields['Target Date'], 'A Demand needs a Target Date.');
    }
    if (type === 'Bug') {
      workflow.check(issue.fields.Environment, 'A Bug needs the affected Environment.');
    }
    const missing = C.missingSections(type, issue.description);
    workflow.check(missing.length === 0,
      'Please complete these sections of the request description: ' + missing.join(', ') + '.');

    // Every request starts in Triage. Only the DevOps team may file a request
    // directly in another state (e.g. work they discovered themselves).
    const devops = ctx.currentUser && ctx.currentUser.isInGroup('DevOps Team');
    if (!issue.fields.State || issue.fields.State.name === 'New' || !devops) {
      issue.fields.State = ctx.State.Triage;
    }
    // The age clock starts now. The DevOps team may backdate it for migrated backlog items.
    if (!issue.fields['Requested On'] || !devops) {
      issue.fields['Requested On'] = Date.now();
    }
    C.refreshAging(issue, ctx.settings);
  },
  requirements: {
    Type: { type: entities.EnumField.fieldType },
    State: { type: entities.State.fieldType, Triage: {} },
    Aging: { type: entities.EnumField.fieldType },
    RequestedOn: { type: entities.Field.dateType, name: 'Requested On' }
  }
});
