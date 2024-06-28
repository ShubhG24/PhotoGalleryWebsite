import json
import boto3  

REGION="RETRACTED"
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table('PhotoGallery')

def lambda_handler(event, context):
    response = table.scan()
    items = response['Items']

    return {
        "statusCode": 200,
        "body": items
    }
