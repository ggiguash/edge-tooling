export const meta = {
  name: 'doctor-analyze',
  description: 'Analyze CI jobs in parallel via prow-job-analyzer agents',
  phases: [
    { title: 'Analyze', detail: 'Per-job root cause analysis via prow-job-analyzer' },
  ],
}

phase('Analyze')
log('Analyzing ' + args.jobs.length + ' jobs in parallel...')

var promises = args.jobs.map(function (job) {
  return agent(job.prompt, {
    label: job.label,
    phase: 'Analyze',
    agentType: args.agentType,
  }).catch(function () { log('Agent failed: ' + job.label); return null })
})
var results = await Promise.all(promises)

var succeeded = results.filter(Boolean).length
log('Analysis complete: ' + succeeded + '/' + args.jobs.length + ' jobs analyzed')

return { analyzed: succeeded, failed: args.jobs.length - succeeded, total: args.jobs.length }
