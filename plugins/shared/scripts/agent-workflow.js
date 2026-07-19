export const meta = {
  name: 'parallel-agents',
  description: 'Run agents in parallel and report success counts',
  phases: [
    { title: 'Analyze', detail: 'Per-job agent execution' },
  ],
}

phase('Analyze')
log('Running ' + args.jobs.length + ' agents in parallel...')

var promises = args.jobs.map(function (job) {
  return agent(job.prompt, {
    label: job.label,
    phase: 'Analyze',
    agentType: args.agentType,
  }).catch(function () { log('Agent failed: ' + job.label); return null })
})
var results = await Promise.all(promises)

var succeeded = results.filter(Boolean).length
log('Complete: ' + succeeded + '/' + args.jobs.length + ' agents succeeded')

return { analyzed: succeeded, failed: args.jobs.length - succeeded, total: args.jobs.length }
