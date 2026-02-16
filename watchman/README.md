# EC2 Watchman

An AWS Lambda function that automatically manages EC2 instance lifecycle by:
- Shutting down EC2 instances older than 24 hours (or after a custom keep period)
- Monitoring instances across **all AWS regions** automatically

## Features

- **Automatic Shutdown**: Shuts down EC2 instances that are older than 24 hours
- **Multi-Region Support**: Automatically checks and monitors instances across all AWS regions
- **Custom Keep Periods**: Use `keep-{days}` tags to extend the lifecycle (e.g., `keep-7` keeps instance for 7 days)
- **Slack Notifications**: Sends notifications to Slack when instances are about to be shut down
- **Scheduled Execution**: Runs on a configurable schedule (default: every hour)

## How It Works

1. **Region Discovery**:
   - Automatically discovers all available AWS regions
   - Iterates through each region to check for EC2 instances

2. **Instance Shutdown Logic**:
   - Checks all EC2 instances across all regions in the account
   - If an instance is older than 24 hours (or after keep period), it's shut down
   - Respects `keep-{days}` tags (e.g., `keep-7` = keep for 7 days)
   - Sends Slack notifications before shutting down instances (if configured)
   - Tags instances with `watchman-stopped-at` timestamp when shut down

## Tag Format

To keep an instance longer than the default 24 hours, add a tag with the format:
- Key: `keep-{number}` (e.g., `keep-7`, `keep-30`)
- Value: (any value, not used)

Examples:
- `keep-7` = Keep instance for 7 days before shutdown
- `keep-30` = Keep instance for 30 days before shutdown


## Deployment

### Prerequisites

- AWS CLI configured with appropriate credentials
- AWS SAM CLI installed (for local testing)
- Python 3.11+

### Using AWS SAM

1. **Build the application**:
   ```bash
   sam build
   ```

2. **Deploy to AWS**:
   ```bash
   sam deploy --guided
   ```

   This will prompt you for:
   - Stack name
   - AWS Region
   - Confirmation of parameter values

3. **Deploy with custom schedule**:
   ```bash
   sam deploy --parameter-overrides ScheduleExpression="rate(30 minutes)"
   ```

4. **Deploy with Slack notifications**:
   ```bash
   sam deploy --parameter-overrides SlackWebhookURL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
   ```

5. **Deploy with both custom schedule and Slack webhook**:
   ```bash
   sam deploy --parameter-overrides ScheduleExpression="rate(30 minutes)" SlackWebhookURL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
   ```

### Using CloudFormation directly

1. **Package the Lambda function**:
   ```bash
   zip -r function.zip lambda_function.py
   ```

2. **Upload to S3** (or use inline code for small functions)

3. **Create the stack**:
   ```bash
   aws cloudformation create-stack \
     --stack-name ec2-watchman \
     --template-body file://template.yaml \
     --capabilities CAPABILITY_IAM
   ```

## Configuration

### Schedule Expression

The default schedule is `rate(1 hour)`. You can customize it using:
- **Rate expressions**: `rate(30 minutes)`, `rate(2 hours)`, `rate(1 day)`
- **Cron expressions**: `cron(0 * * * ? *)` (every hour), `cron(0 0 * * ? *)` (daily at midnight)

### Lambda Settings

Default settings:
- Memory: 256 MB
- Timeout: 300 seconds (5 minutes)

Modify in `template.yaml` or via parameters.

### Slack Notifications

The function can send notifications to a Slack channel when instances are about to be shut down. Notifications include:
- Instance ID
- Instance Name (or indicates if no name tag is present)
- AWS Region
- Instance age in hours

**Setting up Slack notifications:**

1. **Create a Slack Incoming Webhook**:
   - Go to your Slack workspace settings
   - Navigate to Apps → Incoming Webhooks
   - Click "Add to Slack" and select the channel where you want notifications
   - Copy the webhook URL

2. **Deploy with the webhook URL**:
   ```bash
   sam deploy --parameter-overrides SlackWebhookURL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
   ```

3. **Or update an existing deployment**:
   ```bash
   aws cloudformation update-stack \
     --stack-name ec2-watchman \
     --use-previous-template \
     --parameters ParameterKey=SlackWebhookURL,ParameterValue="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
   ```

**Note**: If no webhook URL is provided, the function will skip Slack notifications and continue normally. This is an optional feature.

## IAM Permissions

The Lambda function requires the following permissions:
- `ec2:DescribeRegions` (to discover all available regions)
- `ec2:DescribeInstances` (to list instances in each region)
- `ec2:DescribeInstanceStatus` (to check instance status)
- `ec2:StopInstances` (to shut down instances)
- `ec2:DescribeTags` (to read instance tags)
- `ec2:CreateTags` (to tag instances with stop timestamps)

These are automatically configured in the CloudFormation template. The function operates across all regions, so ensure your IAM role has permissions for all regions where you have EC2 instances.

## Testing

### Local Testing

1. **Test the Lambda function locally**:
   ```bash
   sam local invoke EC2WatchmanFunction
   ```

2. **Test with a test event**:
   ```bash
   sam local invoke EC2WatchmanFunction -e event.json
   ```

### Manual Invocation

You can manually invoke the function via AWS CLI:
```bash
aws lambda invoke \
  --function-name ec2-watchman \
  --payload '{}' \
  response.json
```

## Monitoring

- **CloudWatch Logs**: Check `/aws/lambda/ec2-watchman` for execution logs
- **CloudWatch Metrics**: Monitor Lambda invocations, errors, and duration
- **Function Output**: Returns JSON with counts of instances shut down per region

## Example Output

```json
{
  "statusCode": 200,
  "body": {
    "instances_shutdown": 5,
    "regions_checked": 18,
    "regions_with_shutdowns": {
      "us-east-1": 2,
      "us-west-2": 3
    },
    "total_regions": 18
  }
}
```

The function logs include region-specific information:
```
Checking 18 regions for EC2 instances...
[us-east-1] Instance i-1234567890abcdef0 marked for shutdown (age: 25.50 hours)
[us-west-2] Instance i-0987654321fedcba0 marked for shutdown (age: 30.25 hours)
[us-east-1] Shutting down 1 instances...
[us-west-2] Shutting down 1 instances...
```

## Limitations

1. **Shutdown Only**: The function only shuts down instances; it does not terminate them or their associated CloudFormation stacks. You'll need to manually terminate stopped instances if desired.

2. **Region Errors**: If the function encounters an error in a specific region (e.g., insufficient permissions), it will log the error and continue processing other regions. Check CloudWatch logs for region-specific issues.

3. **Execution Time**: With multi-region support, the function may take longer to execute. The default timeout is 300 seconds (5 minutes), which should be sufficient for most accounts. If you have a very large number of regions or instances, consider increasing the timeout.

## Troubleshooting

### Instances not shutting down
- Check CloudWatch logs for errors (look for region-specific error messages)
- Verify IAM permissions across all regions
- Check if instances have `keep-{days}` tags extending their lifecycle
- Ensure the Lambda function has permissions to describe regions

### Slack notifications not working
- Verify the webhook URL is correctly set in the Lambda environment variables
- Check CloudWatch logs for Slack notification errors (e.g., "Error sending Slack notification")
- Ensure the webhook URL is valid and the Slack app has permission to post to the channel
- Test the webhook URL manually using curl:
  ```bash
  curl -X POST -H 'Content-type: application/json' \
    --data '{"text":"Test message"}' \
    https://hooks.slack.com/services/YOUR/WEBHOOK/URL
  ```

### Function timing out
- Increase the Lambda timeout in `template.yaml` if you have many regions/instances
- Check CloudWatch logs to see which region was being processed when timeout occurred

### Region-specific errors
- Review CloudWatch logs for messages like `Error processing region {region}: ...`
- Verify IAM permissions are not region-restricted
- Some regions may be disabled in your account; the function will skip these gracefully

## License

MIT

