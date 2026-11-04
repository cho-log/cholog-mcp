"""차단 스위치. 호출 수 알람이 울리면 대상 함수의 동시 실행 수를 0으로 바꿔 모든 요청을 막는다.

다시 열기: aws lambda delete-function-concurrency --function-name <함수 이름>
"""

import json
import os

import boto3

lambda_client = boto3.client("lambda")


def handler(event, context):
    target = os.environ["TARGET_FUNCTION"]
    for record in event["Records"]:
        alarm = json.loads(record["Sns"]["Message"])
        if alarm.get("NewStateValue") != "ALARM":
            continue
        lambda_client.put_function_concurrency(FunctionName=target, ReservedConcurrentExecutions=0)
        print(f"차단함: {target} ({alarm.get('AlarmName')}: {alarm.get('NewStateReason')})")
