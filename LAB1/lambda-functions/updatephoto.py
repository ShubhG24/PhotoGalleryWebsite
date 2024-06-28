import json
import boto3
from boto3.dynamodb.conditions import Key,Attr

REGION = "RETRACTED"
s3 = boto3.resource('s3',region_name=REGION)
dynamodb = boto3.resource('dynamodb',region_name=REGION)
table = dynamodb.Table('PhotoGallery')


def lambda_handler(event, context):
    photoID = event['body-json']['photoID']  
    title = event['body-json']['title']
    description = event['body-json']['description']
    tags = event['body-json']['tags']

    table.update_item(
            Key={
                'PhotoID': str(photoID), 'CreationTime':int(photoID)
            },
            UpdateExpression = "SET Title = :nt, Description = nd, Tags = :ng",
            ExpressionAttributeValues = {
                ':nt' : title,
                ':nd' : description,
                ':ng' :tags
            }
        )
    response = {
        "statusCode": 200,
        "body": json.dumps(title)
    }
        
    return response
  