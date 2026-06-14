export const meta = {
  name: 'doctor-analyze',
  description: 'Analyze CI jobs in parallel via per-job prow-job skill invocations',
  phases: [
    { title: 'Analyze', detail: 'Per-job root cause analysis' },
  ],
}

// args: {
//   jobs: [{ artifacts_dir: string, output_path: string, label: string }],
//   prow_job_skill: string,      // e.g. "/lvms-ci:prow-job" or "/microshift-ci:prow-job"
// }

// Defend against the model passing args as a JSON string instead of an object
const a = typeof args === 'string' ? JSON.parse(args) : args

if (!a || !Array.isArray(a.jobs)) {
  log('ERROR: args.jobs is missing or not an array')
  return { analyzed: 0, failed: 0, total: 0, error: 'args.jobs is missing or not an array' }
}
if (!a.prow_job_skill) {
  log('ERROR: args.prow_job_skill is missing')
  return { analyzed: 0, failed: 0, total: 0, error: 'args.prow_job_skill is missing' }
}

phase('Analyze')
log('Analyzing ' + a.jobs.length + ' jobs in parallel...')

const results = await parallel(a.jobs.map(function(job) {
  return function() {
    return agent(
      'Analyze this Prow job and save the report:\n' +
      '1. Run ' + a.prow_job_skill + ' ' + job.artifacts_dir + '\n' +
      '2. After the analysis completes, save the FULL report output' +
      ' (including the --- STRUCTURED SUMMARY --- block) to:\n' +
      '   ' + job.output_path + '\n' +
      '   Use the Write tool to save the file.' +
      ' The file must contain the complete analysis report.',
      { label: job.label, phase: 'Analyze' }
    )
  }
}))

const analyzed = results.filter(function(r) { return r != null }).length
const failed = results.length - analyzed
if (failed > 0) {
  log('Analysis complete: ' + analyzed + '/' + results.length + ' jobs analyzed, ' + failed + ' failed')
} else {
  log('Analysis complete: all ' + analyzed + ' jobs analyzed')
}

return {
  analyzed: analyzed,
  failed: failed,
  total: results.length,
}
