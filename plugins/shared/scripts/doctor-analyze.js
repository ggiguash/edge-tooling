export const meta = {
  name: 'doctor-analyze',
  description: 'Analyze CI jobs in parallel via per-job prow-job skill invocations',
  phases: [
    { title: 'Analyze', detail: 'Per-job root cause analysis' },
  ],
}

// args: {
//   jobs: [{ artifacts_dir: string, output_path: string, label: string, status?: string }],
//   prow_job_skill: string,      // e.g. "/lvms-ci:prow-job" or "/microshift-ci:prow-job"
// }

// Defend against the model passing args as a JSON string instead of an object
const a = typeof args === 'string' ? JSON.parse(args) : args

phase('Analyze')
const failedJobs = a.jobs.filter(function(job) {
  return !job.status || job.status.toUpperCase() === 'FAILURE'
})
log('Analyzing ' + failedJobs.length + ' jobs in parallel...')

const results = await parallel(failedJobs.map(function(job) {
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

const analyzed = results.filter(function(r) { return r !== null }).length
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
