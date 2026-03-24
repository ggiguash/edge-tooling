import boto3
import json
import os
import re
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, List

def parse_keep_days(tags: List[Dict]) -> Optional[int]:
    """
    Parse the 'keep-{days}' tag from EC2 instance tags.
    Returns the number of days if found, None otherwise.
    """
    if not tags:
        return None
    
    for tag in tags:
        if tag.get('Key', '').startswith('keep-'):
            try:
                # Extract number from 'keep-{days}' format
                match = re.search(r'keep-(\d+)', tag.get('Key', ''), re.IGNORECASE)
                if match:
                    return int(match.group(1))
            except (ValueError, AttributeError):
                continue
    return None

def get_instance_age_hours(instance: Dict) -> float:
    """Calculate the age of an instance in hours."""
    launch_time = instance['LaunchTime']
    if launch_time.tzinfo is None:
        launch_time = launch_time.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    age = now - launch_time
    return age.total_seconds() / 3600


def should_shutdown_instance(instance: Dict) -> bool:
    """Determine if an instance should be shut down."""
    state = instance.get('State', {}).get('Name', '')
    
    # Don't shutdown if already stopped or terminated
    if state in ['stopped', 'stopping', 'terminated', 'terminating']:
        return False
    
    # Get instance age
    age_hours = get_instance_age_hours(instance)
    
    # Check for keep tag
    tags = instance.get('Tags', [])
    keep_days = parse_keep_days(tags)
    
    if keep_days:
        # Keep instance for specified days before shutdown
        keep_hours = keep_days * 24
        if age_hours < keep_hours:
            return False
    
    # Shutdown if older than 12 hours (or after keep period)
    return age_hours >= 12


def get_all_regions() -> List[str]:
    """Get all available AWS regions."""
    ec2_global = boto3.client('ec2', region_name='us-east-1')
    response = ec2_global.describe_regions()
    return [region['RegionName'] for region in response['Regions']]


def get_instance_name(instance: Dict) -> str:
    """Extract the Name tag from an instance, or return instance ID if no name."""
    tags = instance.get('Tags', [])
    for tag in tags:
        if tag.get('Key') == 'Name':
            return tag.get('Value', '')
    return instance.get('InstanceId', 'unknown')


def send_slack_notification(instance_id: str, instance_name: str, region: str, age_hours: float) -> bool:
    """
    Send a Slack notification about an instance being shut down.
    Returns True if successful, False otherwise.
    """
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
    
    if not webhook_url:
        print("SLACK_WEBHOOK_URL not configured, skipping Slack notification")
        return False
    
    try:
        # Format instance name for display
        display_name = instance_name if instance_name != instance_id else f"*{instance_id}* (no name tag)"
        
        message = {
            "text": "EC2 Instance Shutdown Notification",
            "blocks": [
                {
                      "type": "rich_text",
                      "elements": [
                          {
                              "type": "rich_text_section",
                              "elements": [
                                  {
                                      "type": "emoji",
                                      "name": "warning"
                                  },
                                  {
                                      "type": "link",
                                      "url": "https://github.com/openshift-eng/edge-tooling/tree/main/watchman",
                                      "text": "EC2 Watchman"
                                  },
                                  {
                                      "type": "text",
                                      "text": " (Shutdown): "
                                  },
                                  {
                                      "type": "text",
                                      "style": {
                                          "bold": true
                                      },
                                      "text": f"{display_name}"
                                  },
                                  {
                                      "type": "text",
                                      "text": f" after {age_hours:.2f} hours ("
                                  },
                                  {
                                      "type": "text",
                                      "style": {
                                          "code": true
                                      },
                                      "text": f"{instance_id} @ {region}"
                                  },
                                  {
                                      "type": "text",
                                      "text": ")"
                                  }
                              ]
                          }
                      ]
                }
            ]
        }
        
        response = requests.post(webhook_url, json=message, timeout=5)
        response.raise_for_status()
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Error sending Slack notification for {instance_id}: {str(e)}")
        return False
    except Exception as e:
        print(f"Unexpected error sending Slack notification for {instance_id}: {str(e)}")
        return False


def lambda_handler(event, context):
    """
    Main Lambda handler function.
    Monitors EC2 instances across all regions and performs shutdown actions.
    """
    try:
        # Get all available regions
        regions = get_all_regions()
        print(f"Checking {len(regions)} regions for EC2 instances...")
        
        all_instances_to_shutdown = []
        region_summary = {}
        
        # Check each region
        for region in regions:
            try:
                ec2 = boto3.client('ec2', region_name=region)
                response = ec2.describe_instances()
                
                instances_to_shutdown = []
                instance_details = {}  # Store instance details for notifications
                
                for reservation in response['Reservations']:
                    for instance in reservation['Instances']:
                        instance_id = instance['InstanceId']
                        state = instance.get('State', {}).get('Name', '')
                        
                        # Skip terminated instances
                        if state in ['terminated', 'terminating']:
                            continue
                        
                        # Check if instance should be shut down
                        if should_shutdown_instance(instance):
                            instances_to_shutdown.append(instance_id)
                            age_hours = get_instance_age_hours(instance)
                            instance_name = get_instance_name(instance)
                            instance_details[instance_id] = {
                                'name': instance_name,
                                'age_hours': age_hours
                            }
                            print(f"[{region}] Instance {instance_id} ({instance_name}) marked for shutdown (age: {age_hours:.2f} hours)")
                
                if instances_to_shutdown:
                    region_summary[region] = len(instances_to_shutdown)
                    all_instances_to_shutdown.append((region, instances_to_shutdown, instance_details))
                else:
                    print(f"[{region}] No instances to shutdown")
                    
            except Exception as e:
                print(f"Error processing region {region}: {str(e)}")
                continue
        
        # Shutdown instances in each region
        total_shutdown = 0
        current_time = datetime.now(timezone.utc).isoformat()
        
        for region, instance_ids, instance_details in all_instances_to_shutdown:
            try:
                ec2 = boto3.client('ec2', region_name=region)
                print(f"[{region}] Shutting down {len(instance_ids)} instances...")
                
                # Send Slack notifications before shutting down
                for instance_id in instance_ids:
                    details = instance_details.get(instance_id, {})
                    instance_name = details.get('name', instance_id)
                    age_hours = details.get('age_hours', 0)
                    send_slack_notification(instance_id, instance_name, region, age_hours)
                
                ec2.stop_instances(InstanceIds=instance_ids)
                
                # Tag instances with stop timestamp for tracking
                for instance_id in instance_ids:
                    try:
                        ec2.create_tags(
                            Resources=[instance_id],
                            Tags=[{
                                'Key': 'watchman-stopped-at',
                                'Value': current_time
                            }]
                        )
                    except Exception as e:
                        print(f"Warning: Could not tag instance {instance_id} in {region} with stop time: {str(e)}")
                
                total_shutdown += len(instance_ids)
                
            except Exception as e:
                print(f"Error shutting down instances in {region}: {str(e)}")
                continue
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'instances_shutdown': total_shutdown,
                'regions_checked': len(regions),
                'regions_with_shutdowns': region_summary,
                'total_regions': len(regions)
            })
        }
    
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }

