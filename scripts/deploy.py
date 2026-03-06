#!/usr/bin/env python

import sys
import time

import boto3

ECR_REPOSITORY_NAME = "nocfo-mcp"
ECR_REPOSITORY_REGION = "eu-west-1"

if len(sys.argv) < 3:
    print("Usage: python script.py <pipeline_name> <tag_to_deploy>")
    sys.exit(1)

pipeline_name = sys.argv[1]
tag_to_deploy = sys.argv[2].split("/")[-1]

print("Getting image digest from ECR ...")
ecr_client = boto3.client("ecr", region_name=ECR_REPOSITORY_REGION)
ecr_response = ecr_client.describe_images(
    repositoryName=ECR_REPOSITORY_NAME,
    imageIds=[{"imageTag": tag_to_deploy}],
)
image_digest = ecr_response["imageDetails"][0]["imageDigest"]

print("Starting CodePipeline execution ...")
codepipeline_client = boto3.client("codepipeline", region_name=ECR_REPOSITORY_REGION)
execution_response = codepipeline_client.start_pipeline_execution(
    name=pipeline_name,
    sourceRevisions=[
        {
            "actionName": "Source",
            "revisionType": "IMAGE_DIGEST",
            "revisionValue": image_digest,
        }
    ],
)
pipeline_execution_id = execution_response["pipelineExecutionId"]

statuses_success = ["Succeeded"]
terminal_statuses = statuses_success + [
    "Failed",
    "Stopped",
    "Cancelled",
    "Superseded",
]

current_status = None
start_time = time.time()
while current_status not in terminal_statuses:
    time.sleep(10)
    execution_response = codepipeline_client.get_pipeline_execution(
        pipelineName=pipeline_name,
        pipelineExecutionId=pipeline_execution_id,
    )
    current_status = execution_response["pipelineExecution"]["status"]
    minutes_elapsed, seconds_elapsed = divmod(time.time() - start_time, 60)
    print(
        f"{pipeline_name}: Still running... [{current_status}, "
        f"{int(minutes_elapsed)}m{int(seconds_elapsed)}s elapsed]"
    )

if current_status in statuses_success:
    print("Pipeline execution succeeded")
    sys.exit(0)

print("Pipeline execution failed!")
sys.exit(1)
