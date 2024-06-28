import json
import boto3

REGION = "RETRACTED"
s3 = boto3.resource('s3',region_name=REGION)
dynamodb = boto3.resource('dynamodb',region_name=REGION)
table = dynamodb.Table('PhotoGallery')


def lambda_handler(event, context):
  #  return {"data":event}
    photoID = event['body-json']['photoID']  # assuming the client sends the PhotoID of the image to be deleted
    
    table.delete_item(
            Key={
                'PhotoID': str(photoID), 'CreationTime':int(photoID)
            }
        )
        
    return {
            "statusCode": 200,
            "body": json.dumps("Photo deleted successfully.")
        }
    