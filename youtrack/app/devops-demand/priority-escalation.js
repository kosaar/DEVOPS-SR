/**
 * P1/P2 requests notify the DevOps lead (e-mail via YouTrack notifications) when
 * they are submitted or when an open request is raised to P1/P2.
 * The request gets the 'lead-notified' tag + a comment so the escalation is visible.
 */
const entities = require('@jetbrains/youtrack-scripting-api/entities');

const HIGH = ['P1 Critical', 'P2 High'];

exports.rule = entities.Issue.onChange({
  title: 'Notify the DevOps lead about P1/P2 requests',
  guard: (ctx) => {
    const issue = ctx.issue;
    const p = issue.fields.Priority;
    if (!p || HIGH.indexOf(p.name) === -1 || issue.isResolved) {
      return false;
    }
    if (issue.becomesReported) {
      return true;
    }
    if (!issue.isReported || !issue.fields.isChanged(ctx.Priority)) {
      return false;
    }
    const old = issue.fields.oldValue(ctx.Priority);
    return !old || HIGH.indexOf(old.name) === -1;
  },
  action: (ctx) => {
    const issue = ctx.issue;
    const login = (ctx.settings && ctx.settings.devopsLeadLogin) || 'devops.lead';
    const lead = entities.User.findByLogin(login);
    const squad = issue.fields['Requester Squad'] ? issue.fields['Requester Squad'].name : 'unknown squad';
    const service = issue.fields.Service ? issue.fields.Service.name : 'unknown service';
    const subject = '[' + issue.fields.Priority.name + '] ' + issue.id + ' ' + issue.summary;
    const body = '<p>A <b>' + issue.fields.Priority.name + '</b> DevOps request needs attention.</p>' +
      '<p><b>' + issue.id + '</b>: ' + issue.summary + '<br/>Squad: ' + squad +
      '<br/>Service: ' + service + '</p><p><a href="' + issue.url + '">Open the request</a></p>';
    if (lead) {
      lead.notify(subject, body, true);
      issue.addComment('Escalation: ' + issue.fields.Priority.name + ' request, DevOps lead @' + login +
        ' has been notified.');
    } else {
      issue.addComment('Escalation: ' + issue.fields.Priority.name + ' request, but the DevOps lead login "' +
        login + '" was not found. Check the app settings.');
    }
    issue.addTag('lead-notified');
  },
  requirements: {
    Priority: { type: entities.EnumField.fieldType }
  }
});
