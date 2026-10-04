/**
 * Shared helpers for the DevOps Demand Management workflow rules.
 * Everything that encodes a "process decision" lives here so it is easy to review.
 */

const DAY = 24 * 60 * 60 * 1000;

// Placeholder prefix used in the request templates. A section still starting with it
// is considered "not filled in".
const TODO = 'TODO:';

// Request templates = the "request forms". Sections marked (required) are validated
// when the request is submitted.
const TEMPLATES = {
  Demand: [
    '### Description (required)',
    TODO + ' what do you need from DevOps? (new pipeline, environment, access, tooling...)',
    '',
    '### Business / technical impact (required)',
    TODO + ' who is affected, what is blocked or at risk if this is not delivered by the Target Date?',
    '',
    '### Acceptance criteria (optional)',
    '- ',
    ''
  ].join('\n'),
  Bug: [
    '### Description (required)',
    TODO + ' what is broken? (pipeline, runner, deployment, cluster, repository...)',
    '',
    '### Expected behavior (required)',
    TODO + ' what should happen?',
    '',
    '### Actual behavior (required)',
    TODO + ' what happens instead? Include the error message.',
    '',
    '### Evidence (required)',
    TODO + ' links to the failing pipeline/job/log. Attach screenshots or log files to this request.',
    ''
  ].join('\n'),
  Improvement: [
    '### Description (required)',
    TODO + ' what should be improved in the current DevOps service?',
    '',
    '### Expected benefit (required)',
    TODO + ' time saved, risk reduced, developer experience... Quantify if you can.',
    ''
  ].join('\n')
};

function sections(text) {
  const result = {};
  let current = null;
  (text || '').split('\n').forEach(function (line) {
    const m = /^#{2,4}\s+(.*?)\s*$/.exec(line);
    if (m) {
      current = m[1];
      result[current] = '';
    } else if (current !== null) {
      result[current] += line + '\n';
    }
  });
  return result;
}

/** Names of the "(required)" sections of the template that are missing or unfilled. */
function missingSections(type, description) {
  const template = TEMPLATES[type];
  if (!template) {
    return [];
  }
  const required = Object.keys(sections(template)).filter(function (h) {
    return h.indexOf('(required)') !== -1;
  });
  const actual = sections(description);
  return required.filter(function (heading) {
    const body = (actual[heading] || '').trim();
    return !body || body.indexOf(TODO) === 0;
  }).map(function (h) {
    return h.replace(' (required)', '');
  });
}

function isUntouchedTemplate(description) {
  const d = (description || '').trim();
  return !d || Object.keys(TEMPLATES).some(function (t) {
    return TEMPLATES[t].trim() === d;
  });
}

const AGING_BUCKETS = [
  { max: 7, name: '0-7 days' },
  { max: 14, name: '8-14 days' },
  { max: 30, name: '15-30 days' },
  { max: 60, name: '31-60 days' },
  { max: Infinity, name: '60+ days' }
];

/** Age of a request = time since "Requested On" (set on submit; may be earlier for migrated backlog). */
function requestedOn(issue) {
  return issue.fields['Requested On'] || issue.created;
}

function ageInDays(issue) {
  return Math.floor((Date.now() - requestedOn(issue)) / DAY);
}

function agingBucket(days) {
  for (let i = 0; i < AGING_BUCKETS.length; i++) {
    if (days <= AGING_BUCKETS[i].max) {
      return AGING_BUCKETS[i].name;
    }
  }
  return AGING_BUCKETS[AGING_BUCKETS.length - 1].name;
}

function threshold(settings) {
  const v = settings && parseInt(settings.agingThresholdDays, 10);
  return v > 0 ? v : 14;
}

/**
 * Recompute the Aging bucket and the 'aging' tag of one request.
 * Only writes when something actually changes (keeps the issue history clean).
 */
function refreshAging(issue, settings) {
  if (issue.isResolved) {
    if (issue.hasTag('aging')) {
      issue.removeTag('aging');
    }
    return;
  }
  const days = ageInDays(issue);
  const bucketName = agingBucket(days);
  const current = issue.fields.Aging;
  if (!current || current.name !== bucketName) {
    const field = issue.project.findFieldByName('Aging');
    const value = field && field.findValueByName(bucketName);
    if (value) {
      issue.fields.Aging = value;
    }
  }
  const old = days > threshold(settings);
  if (old && !issue.hasTag('aging')) {
    issue.addTag('aging');
  } else if (!old && issue.hasTag('aging')) {
    issue.removeTag('aging');
  }
}

module.exports = {
  DAY: DAY,
  TEMPLATES: TEMPLATES,
  missingSections: missingSections,
  isUntouchedTemplate: isUntouchedTemplate,
  requestedOn: requestedOn,
  ageInDays: ageInDays,
  agingBucket: agingBucket,
  refreshAging: refreshAging,
  threshold: threshold
};
