#!flask/bin/python
import sys, os
sys.path.append(os.path.abspath(os.path.join('..', 'utils')))
from env import AWS_ACCESS_KEY, AWS_SECRET_ACCESS_KEY, AWS_REGION, PHOTOGALLERY_S3_BUCKET_NAME, DYNAMODB_TABLE
from flask import Flask, jsonify, abort, request, make_response, url_for
from flask import render_template, redirect
import time
import exifread
import json
import boto3  
from boto3.dynamodb.conditions import Key, Attr
import pymysql.cursors
from datetime import datetime,timedelta
import pytz



"""
    INSERT NEW LIBRARIES HERE (IF NEEDED)
"""
import uuid
import bcrypt
from bcrypt import hashpw, gensalt
from flask import flash,session
from botocore.exceptions import ClientError
from itsdangerous import URLSafeTimedSerializer

import secrets
import urllib.request


"""
"""

app = Flask(__name__, static_url_path="")
app.secret_key = uuid.uuid4().hex
# salts
secret_salt = "secretsalt"
secret_salt_user = "secretsaltuser"

dynamodb = boto3.resource('dynamodb', aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                            region_name=AWS_REGION)


table = dynamodb.Table(DYNAMODB_TABLE)
userTable = dynamodb.Table('PhotoGalleryUser')

serializer_key = str(uuid.uuid4())
serializer = URLSafeTimedSerializer(serializer_key)


UPLOAD_FOLDER = os.path.join(app.root_path,'static','media')
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def getExifData(path_name):
    f = open(path_name, 'rb')
    tags = exifread.process_file(f)
    ExifData={}
    for tag in tags.keys():
        if tag not in ('JPEGThumbnail', 'TIFFThumbnail', 'Filename', 'EXIF MakerNote'):
            key="%s"%(tag)
            val="%s"%(tags[tag])
            ExifData[key]=val
    return ExifData

def s3uploading(filename, filenameWithPath, uploadType="photos"):
    s3 = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
                       
    bucket = PHOTOGALLERY_S3_BUCKET_NAME
    path_filename = uploadType + "/" + filename

    s3.upload_file(filenameWithPath, bucket, path_filename)  
    s3.put_object_acl(ACL='public-read', Bucket=bucket, Key=path_filename)
    return f'''http://{PHOTOGALLERY_S3_BUCKET_NAME}.s3.amazonaws.com/{path_filename}'''


"""
    INSERT YOUR NEW FUNCTION HERE (IF NEEDED)
"""
# ses configuration for sending email.
ses = boto3.client('ses',
                    aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                            region_name=AWS_REGION)


# function to check session expiry.
def loggedTime():
    """Check if the session has expired."""
    if 'loggeduser' in session:
        try:
            email = serializer.loads(
                session['loggeduser'],
                salt=secret_salt_user,
                max_age=600  # 10 minutes
            )
        except Exception as e:
            print("Session expired!")
            session.pop('loggeduser', None)
            return -1
    else:
        print("no user logged in")
        return -1

    return email



"""
"""

"""
    INSERT YOUR NEW ROUTE HERE (IF NEEDED)
"""
@app.route('/signup', methods=['POST', 'GET'])
def signup_page():

    if request.method == 'POST':
        username = str(uuid.uuid4())
        # store username in session
        session['username'] = username
        email = request.form['email']
        # store email in session
        session['email'] = email
        name = request.form['name']
        password = request.form['password']
        #hashing password
        hashed_pswd = hashpw(password.encode('utf8'), gensalt())
        
        response = userTable.scan(FilterExpression=Key('userID').eq(username) | Attr('email').eq(email))

        if response['Items']:
            flash("Username or email already exists, try logging in.")
            return redirect('/login')
        else:
            userTable.put_item(
                Item={
                    "userID": username,
                    "email": email,
                    "name": name,
                    "password": hashed_pswd,
                    "confirmed": False
                }
            )

           # creating confirmation url
            token = serializer.dumps(username, salt=secret_salt)
            confirmation_url = f'RETRACTED'

            print(confirmation_url)
            

            SENDER = 'RETRACTED'
            
            # html formatting to send the link
            email_html = '''
                <html>
                <head></head>
                <body>
                <p> Click <a href="{}"> here</a> to confirm your email. </p>
                </body>
                </html>
            '''.format(confirmation_url)

            # sending email
            try:
                response = ses.send_email(
                    Destination={'ToAddresses': [email]},
                    Message={
                        'Body': {'Html': {'Charset': "UTF-8", 'Data': email_html}},
                        'Subject': {'Data': 'PhotoGallery Email Confirmation'}
                    },
                    Source=SENDER
                )
                print("Email sent! Message ID:", response['MessageId'])
            except ClientError as e:
                print("Email sending failed:", e.response['Error']['Message'])

            flash("Signup successful! Please check your email to confirm.")
            return redirect('/login')

    else:
        return render_template('signup.html')   



@app.route('/login', methods=['GET', 'POST'])
def login_page():
    """ Login page route.
    get:
        description: Endpoint to return sign in page.
    """
    if request.method == 'POST':
        email = request.form['email']
        session['email'] = email

        password = request.form['password']
        # getting the response from the dynamodb table for the particular email
        response = userTable.scan(FilterExpression=Attr('email').eq(email))

        results = response['Items']
        # checking user password,if confirmed, if user exists
        if results:
            hashed_pwd = results[0]['password']
            if hashpw(password.encode("utf-8"),hashed_pwd.value) == hashed_pwd:
                print("Pass matches")

                confirmed_value = results[0]['confirmed']
                if confirmed_value:
                    print("user confirmed")
                    user_token = serializer.dumps(email,salt = secret_salt_user)
                    session['loggeduser'] = user_token
                    return redirect('/')

                else:
                    flash("User not confirmed yet!")
                    return redirect('/login')

            else:
                print("incorrect password")
                flash("Incorrect password!")
                return redirect('/login')
        else:
            flash("No user with the given email!")
            return redirect('/login')
        
    else: 
        return render_template('login.html')

@app.route('/confirm/<string:emailtoken>')
def confirm_email(emailtoken):
    try:
       userID = serializer.loads(
           emailtoken,
           salt=secret_salt,
           max_age=600
       )
    except Exception as e:
        print("Token expired!")
    # updating confirm attribute to true when confirmed
    response = userTable.update_item(
        Key={
            "userID":userID,
        },
        UpdateExpression = "SET confirmed = :val1",
        ExpressionAttributeValues={':val1': True}
    )

    return redirect('/login')

@app.route('/album/<string:albumID>/photo/<string:photoID>/delete', methods=['POST'])
def delete_photo(albumID, photoID):
    """ Delete photo route.

    delete:
        description: Endpoint to delete a photo.
        responses: Deletes the specified photo and redirects user to album page.
    """ 
    try:
        # Delete photo from DynamoDB table
        table.delete_item(
            Key={
                'albumID': albumID,
                'photoID': photoID
            }
        )
        return redirect(f'/album/{albumID}')
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 500)

@app.route('/album/<string:albumID>/delete', methods=['POST'])
def delete_album(albumID):
    """ Delete album route.

    post:
        description: Endpoint to delete an album.
        responses: Deletes the specified album and redirects user to home page.
    """ 
    try:
        # Delete album and associated photos from DynamoDB table
        response = table.query(
            KeyConditionExpression=Key('albumID').eq(albumID)
        )
        items = response['Items']
        for item in items:
            table.delete_item(
                Key={
                    'albumID': albumID,
                    'photoID': item['photoID']
                }
            )
        
        # Redirect user to home page
        return redirect('/')
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 500)

@app.route('/album/<string:albumID>/photo/<string:photoID>/update', methods=['POST'])
def update_photo(albumID, photoID):
    """ Update photo route.

    post:
        description: Endpoint to update photo details.
        responses: Updates the specified photo details and redirects user to photo detail page.
    """ 
    try:
        # Fetch the photo item from DynamoDB
        response = table.get_item(
            Key={
                'albumID': albumID,
                'photoID': photoID
            }
        )
        photo_item = response['Item']
        
        # Update the photo details 
        data = request.json
        if 'title' in data:
            photo_item['title'] = data['title']
        if 'description' in data:
            photo_item['description'] = data['description']
        if 'tags' in data:
            photo_item['tags'] = data['tags']
        
        # Save the updated photo back to DynamoDB
        table.put_item(Item=photo_item)

        return redirect(f'/album/{albumID}/photo/{photoID}')
        
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 500)

@app.route('/cancel', methods=['POST', 'GET'])
def cancel_account():
    email = session.get('email')
    if not email:
        flash("Email not found in session.")
        return redirect('/login')

    user_response = userTable.scan(FilterExpression=Attr('email').eq(email))
    items = user_response['Items']
    if not items:
        flash("No user found with the given email.")
        return redirect('/login')
    # get the userID for the row containing the given email.
    userID = items[0]['userID']
    # delete the user entry
    userTable.delete_item(
        Key={
            'userID': userID
        }
    )
    # delete the albums and photos
    gallery_response = table.scan(FilterExpression=Attr('createdBy').eq(email))
    gallery_items = gallery_response['Items']
    for album in gallery_items:
        table.delete_item(
            Key={
                'albumID': album['albumID'],
                'photoID': album['photoID']
            }
        )
    flash("Account canceled successfully!")
    return redirect('/login')




"""
"""

@app.errorhandler(400)
def bad_request(error):
    """ 400 page route.

    get:
        description: Endpoint to return a bad request 400 page.
        responses: Returns 400 object.
    """
    return make_response(jsonify({'error': 'Bad request'}), 400)



@app.errorhandler(404)
def not_found(error):
    """ 404 page route.

    get:
        description: Endpoint to return a not found 404 page.
        responses: Returns 404 object.
    """
    return make_response(jsonify({'error': 'Not found'}), 404)


@app.route('/', methods=['GET'])
def home_page():
    """ Home page route.

    get:
        description: Endpoint to return home page.
        responses: Returns all the albums.
    """
    # checking if the session has expired or not
    # if expired redirect to login page
    username = loggedTime()
    if username == -1:
        return redirect('/login')
    
    response = table.scan(FilterExpression=Attr('photoID').eq("thumbnail"))
    results = response['Items']

    if len(results) > 0:
        for index, value in enumerate(results):
            createdAt = datetime.strptime(str(results[index]['createdAt']), "%Y-%m-%d %H:%M:%S")
            createdAt_UTC = pytz.timezone("UTC").localize(createdAt)
            results[index]['createdAt'] = createdAt_UTC.astimezone(pytz.timezone("US/Eastern")).strftime("%B %d, %Y")

    return render_template('index.html', albums=results)



@app.route('/createAlbum', methods=['GET', 'POST'])
def add_album():
    """ Create new album route.

    get:
        description: Endpoint to return form to create a new album.
        responses: Returns all the fields needed to store new album.

    post:
        description: Endpoint to send new album.
        responses: Returns user to home page.
    """
    username = loggedTime()
    if username == -1:
        return redirect('/login')
    
    if request.method == 'POST':
        uploadedFileURL=''
        file = request.files['imagefile']
        name = request.form['name']
        description = request.form['description']

        if file and allowed_file(file.filename):
            albumID = uuid.uuid4()
            
            filename = file.filename
            filenameWithPath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filenameWithPath)
            
            uploadedFileURL = s3uploading(str(albumID), filenameWithPath, "thumbnails");

            createdAtlocalTime = datetime.now().astimezone()
            createdAtUTCTime = createdAtlocalTime.astimezone(pytz.utc)

            # username = session.get('username')

            table.put_item(
                Item={
                    "albumID": str(albumID),
                    "photoID": "thumbnail",
                    "name": name,
                    "description": description,
                    "thumbnailURL": uploadedFileURL,
                    "createdAt": createdAtUTCTime.strftime("%Y-%m-%d %H:%M:%S"),
                    "createdBy": username     # Add createdBy attribute
                }
            )

        return redirect('/')
    else:
        return render_template('albumForm.html')



@app.route('/album/<string:albumID>', methods=['GET'])
def view_photos(albumID):
    """ Album page route.

    get:
        description: Endpoint to return an album.
        responses: Returns all the photos of a particular album.
    """
    username = loggedTime()
    if username == -1:
        return redirect('/login')
    
    albumResponse = table.query(KeyConditionExpression=Key('albumID').eq(albumID) & Key('photoID').eq('thumbnail'))
    albumMeta = albumResponse['Items']

    response = table.scan(FilterExpression=Attr('albumID').eq(albumID) & Attr('photoID').ne('thumbnail'))
    items = response['Items']

    return render_template('viewphotos.html', photos=items, albumID=albumID, albumName=albumMeta[0]['name'])



@app.route('/album/<string:albumID>/addPhoto', methods=['GET', 'POST'])
def add_photo(albumID):
    """ Create new photo under album route.

    get:
        description: Endpoint to return form to create a new photo.
        responses: Returns all the fields needed to store a new photo.

    post:
        description: Endpoint to send new photo.
        responses: Returns user to album page.
    """
    username = loggedTime()
    if username == -1:
        return redirect('/login')
    

    if request.method == 'POST':    
        uploadedFileURL=''
        file = request.files['imagefile']
        title = request.form['title']
        description = request.form['description']
        tags = request.form['tags']
        if file and allowed_file(file.filename):
            photoID = uuid.uuid4()
            filename = file.filename
            filenameWithPath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filenameWithPath)            
            
            uploadedFileURL = s3uploading(filename, filenameWithPath);
            
            ExifData=getExifData(filenameWithPath)
            ExifDataStr = json.dumps(ExifData)

            createdAtlocalTime = datetime.now().astimezone()
            updatedAtlocalTime = datetime.now().astimezone()

            createdAtUTCTime = createdAtlocalTime.astimezone(pytz.utc)
            updatedAtUTCTime = updatedAtlocalTime.astimezone(pytz.utc)

            table.put_item(
                Item={
                    "albumID": str(albumID),
                    "photoID": str(photoID),
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "photoURL": uploadedFileURL,
                    "EXIF": ExifDataStr,
                    "createdAt": createdAtUTCTime.strftime("%Y-%m-%d %H:%M:%S"),
                    "updatedAt": updatedAtUTCTime.strftime("%Y-%m-%d %H:%M:%S"),
                    "createdBy": username
                }
            )

        return redirect(f'''/album/{albumID}''')

    else:

        albumResponse = table.query(KeyConditionExpression=Key('albumID').eq(albumID) & Key('photoID').eq('thumbnail'))
        albumMeta = albumResponse['Items']

        return render_template('photoForm.html', albumID=albumID, albumName=albumMeta[0]['name'])



@app.route('/album/<string:albumID>/photo/<string:photoID>', methods=['GET'])
def view_photo(albumID, photoID):
    """ photo page route.

    get:
        description: Endpoint to return a photo.
        responses: Returns a photo from a particular album.
    """ 
    username = loggedTime()
    if username == -1:
        return redirect('/login')
    
    albumResponse = table.query(KeyConditionExpression=Key('albumID').eq(albumID) & Key('photoID').eq('thumbnail'))
    albumMeta = albumResponse['Items']

    response = table.query( KeyConditionExpression=Key('albumID').eq(albumID) & Key('photoID').eq(photoID))
    results = response['Items']

    if len(results) > 0:
        photo={}
        photo['photoID'] = results[0]['photoID']
        photo['title'] = results[0]['title']
        photo['description'] = results[0]['description']
        photo['tags'] = results[0]['tags']
        photo['photoURL'] = results[0]['photoURL']
        photo['EXIF']=json.loads(results[0]['EXIF'])

        createdAt = datetime.strptime(str(results[0]['createdAt']), "%Y-%m-%d %H:%M:%S")
        updatedAt = datetime.strptime(str(results[0]['updatedAt']), "%Y-%m-%d %H:%M:%S")

        createdAt_UTC = pytz.timezone("UTC").localize(createdAt)
        updatedAt_UTC = pytz.timezone("UTC").localize(updatedAt)

        photo['createdAt']=createdAt_UTC.astimezone(pytz.timezone("US/Eastern")).strftime("%B %d, %Y")
        photo['updatedAt']=updatedAt_UTC.astimezone(pytz.timezone("US/Eastern")).strftime("%B %d, %Y")
        
        tags=photo['tags'].split(',')
        exifdata=photo['EXIF']
        
        return render_template('photodetail.html', photo=photo, tags=tags, exifdata=exifdata, albumID=albumID, albumName=albumMeta[0]['name'])
    else:
        return render_template('photodetail.html', photo={}, tags=[], exifdata={}, albumID=albumID, albumName="")



@app.route('/album/search', methods=['GET'])
def search_album_page():
    """ search album page route.

    get:
        description: Endpoint to return all the matching albums.
        responses: Returns all the albums based on a particular query.
    """ 
    username = loggedTime()
    if username == -1:
        return redirect('/login')
    
    query = request.args.get('query', None)    

    response = table.scan(FilterExpression=Attr('name').contains(query) | Attr('description').contains(query))
    results = response['Items']

    items=[]
    for item in results:
        if item['photoID'] == 'thumbnail':
            album={}
            album['albumID'] = item['albumID']
            album['name'] = item['name']
            album['description'] = item['description']
            album['thumbnailURL'] = item['thumbnailURL']
            items.append(album)

    return render_template('searchAlbum.html', albums=items, searchquery=query)



@app.route('/album/<string:albumID>/search', methods=['GET'])
def search_photo_page(albumID):
    """ search photo page route.

    get:
        description: Endpoint to return all the matching photos.
        responses: Returns all the photos from an album based on a particular query.
    """ 
    username = loggedTime()
    if username == -1:
        return redirect('/login')
    
    query = request.args.get('query', None)    

    response = table.scan(FilterExpression=Attr('title').contains(query) | Attr('description').contains(query) | Attr('tags').contains(query) | Attr('EXIF').contains(query))
    results = response['Items']

    items=[]
    for item in results:
        if item['photoID'] != 'thumbnail' and item['albumID'] == albumID:
            photo={}
            photo['photoID'] = item['photoID']
            photo['albumID'] = item['albumID']
            photo['title'] = item['title']
            photo['description'] = item['description']
            photo['photoURL'] = item['photoURL']
            items.append(photo)

    return render_template('searchPhoto.html', photos=items, searchquery=query, albumID=albumID)



if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
