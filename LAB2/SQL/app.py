#!flask/bin/python
import sys, os
sys.path.append(os.path.abspath(os.path.join('..', 'utils')))
from env import AWS_ACCESS_KEY, AWS_SECRET_ACCESS_KEY, AWS_REGION, PHOTOGALLERY_S3_BUCKET_NAME, RDS_DB_HOSTNAME, RDS_DB_USERNAME, RDS_DB_PASSWORD, RDS_DB_NAME
from flask import Flask, jsonify, abort, request, make_response, url_for
from flask import render_template, redirect
import time
import exifread
import json
import uuid
import boto3  
import pymysql.cursors
from datetime import datetime
from pytz import timezone

"""
    INSERT NEW LIBRARIES HERE (IF NEEDED)
"""
import uuid
import bcrypt
from bcrypt import hashpw, gensalt,checkpw
from flask import flash,session
from botocore.exceptions import ClientError
from itsdangerous import URLSafeTimedSerializer

import secrets
import urllib.request

## Same code as NoSQL, just the code for adding/updating/deleting elements
## from database is different. Rest all is same. Already added comments
## in NoSQL, hence didn't add comments here.

"""
"""

app = Flask(__name__, static_url_path="")
app.secret_key = uuid.uuid4().hex

secret_salt = "secretsalt"
secret_salt_user = "secretsaltuser"

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

def get_database_connection():
    conn = pymysql.connect(host=RDS_DB_HOSTNAME,
                             user=RDS_DB_USERNAME,
                             password=RDS_DB_PASSWORD,
                             db=RDS_DB_NAME,
                             charset='utf8mb4',
                             cursorclass=pymysql.cursors.DictCursor)
    return conn



"""
    INSERT YOUR NEW FUNCTION HERE (IF NEEDED)
"""
ses = boto3.client('ses',
                    aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                            region_name=AWS_REGION)
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
        session['userID'] = username
        email = request.form['email']
        session['email'] = email
        name = request.form['name']
        password = request.form['password']
        
        hashed_pswd = hashpw(password.encode('utf8'), gensalt())
        decoded_pass = hashed_pswd.decode('utf-8')


        conn=get_database_connection()
        cursor = conn.cursor ()
        statement = f'''SELECT * FROM photogallerydb.User WHERE email="{email}";'''
        cursor.execute(statement)
        userMeta = cursor.fetchall()
        conn.close()


        if userMeta:
            flash("UserID exists, try different username/logging in!")
            return redirect('/signup')
        
        else:
            conn=get_database_connection()
            cursor = conn.cursor()
            statement = f'''INSERT INTO photogallerydb.User (userID,email,name,password) 
            VALUES("{username}","{email}","{name}","{decoded_pass}");'''
            results = cursor.execute(statement)
            conn.commit()
            conn.close()


            token = serializer.dumps(username, salt=secret_salt)
            confirmation_url = f'RETRACTED'

            print(confirmation_url)
            SENDER = 'RETRACTED'
            

            email_html = '''
                <html>
                <head></head>
                <body>
                <p> Click <a href="{}"> here</a> to confirm your email. </p>
                </body>
                </html>
            '''.format(confirmation_url)


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

        conn=get_database_connection()
        cursor = conn.cursor ()
        statement = f'''SELECT * FROM photogallerydb.User WHERE email="{email}";'''
        cursor.execute(statement)
        userMeta = cursor.fetchall()
        conn.close()

        if userMeta:
            hashed_pw = userMeta[0]['password']
            if checkpw(password.encode('utf-8'),hashed_pw.encode('utf-8')):
                print('pass matches')
                confirmed = userMeta[0]['confirmed']
                confirmed_value = int.from_bytes(confirmed,"big")

                if confirmed_value:
                        user_token = serializer.dumps(email,salt=secret_salt)

                        session['loggeduser'] = user_token
                        return redirect('/')

                else:
                    flash("User not confirmed!")
                    return redirect('/login')
            else:
                flash("Incorrect Password!")
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
           max_age=1000
       )
    except Exception as e:
        print("Token expired!")

    conn=get_database_connection()
    cursor = conn.cursor ()
    statement = f'''UPDATE photogallerydb.User SET confirmed=1 WHERE userID = "{userID}";'''
    cursor.execute(statement)
    conn.commit()
    conn.close()
    
    return redirect('/login')


@app.route('/album/<string:albumID>/photo/<string:photoID>/delete', methods=['POST'])
def delete_photo(albumID, photoID):
    """ Delete photo route.

    post:
        description: Endpoint to delete a photo.
        responses: Deletes the specified photo and redirects user to album page.
    """
    try:
        conn = get_database_connection()
        cursor = conn.cursor()

        sql = "DELETE FROM photogallerydb.Photo WHERE albumID = %s AND photoID = %s"
        cursor.execute(sql, (albumID, photoID))
        conn.commit()
        conn.close()

        return redirect(f'/album/{albumID}')
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 500)
    
@app.route('/album/<string:albumID>/delete', methods=['POST'])
def delete_album(albumID):
    """ Delete album route.

    get:
        description: Endpoint to delete an album and its associated photos.
        responses: Deletes the album and redirects to the home page.
    """
    conn = get_database_connection()
    cursor = conn.cursor()

    delete_photos_query = f'DELETE FROM photogallerydb.Photo WHERE albumID = "{albumID}";'
    cursor.execute(delete_photos_query)

    delete_album_query = f'DELETE FROM photogallerydb.Album WHERE albumID = "{albumID}";'
    cursor.execute(delete_album_query)
    conn.commit()
    conn.close()

    return redirect('/')
    

@app.route('/album/<string:albumID>/photo/<string:photoID>/update', methods=['POST'])
def update_photo(albumID, photoID):
    """ Update photo details route.

    post:
        description: Endpoint to update photo details.
        responses: Updates the specified photo details and redirects user to photo page.
    """
    try:
        data = json.loads(request.data)

        new_title = data.get('title')
        new_description = data.get('description')
        new_tags = data.get('tags')

        conn = get_database_connection()
        cursor = conn.cursor()

        sql = "UPDATE photogallerydb.Photo SET title = %s, description = %s, tags = %s, updatedAt = %s WHERE albumID = %s AND photoID = %s"
        cursor.execute(sql, (new_title, new_description, new_tags, datetime.now(), albumID, photoID))
        conn.commit()
        conn.close()

        return jsonify({'message': 'Photo details updated successfully.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/cancel', methods=['POST', 'GET'])
def cancel_account():

    print(session)
    email = session.get('email')

    conn = get_database_connection()
    cursor = conn.cursor()


    cursor.execute("SELECT userID FROM photogallerydb.User WHERE email = %s", (email,))
    user = cursor.fetchone()

    userID = user['userID']

    
    # Delete albums created by the user
    delete_albums_query = "DELETE FROM photogallerydb.Album WHERE createdBy = %s"
    cursor.execute(delete_albums_query, (userID,))

    # Delete photos associated with albums created by the user
    delete_photos_query = """
        DELETE FROM photogallerydb.Photo
        WHERE albumID IN (SELECT albumID FROM photogallerydb.Album WHERE createdBy = %s)
    """
    cursor.execute(delete_photos_query, (userID,))

    # Delete user from User table
    delete_user_query = "DELETE FROM photogallerydb.User WHERE userID = %s"
    cursor.execute(delete_user_query, (userID,))
    conn.commit()
    conn.close()

    flash("Account canceled successfully.")
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
    
    conn=get_database_connection()
    cursor = conn.cursor ()
    cursor.execute("SELECT * FROM photogallerydb.Album;")
    results = cursor.fetchall()
    conn.close()
    
    items=[]
    for item in results:
        album={}
        album['albumID'] = item['albumID']
        album['name'] = item['name']
        album['description'] = item['description']
        album['thumbnailURL'] = item['thumbnailURL']

        createdAt = datetime.strptime(str(item['createdAt']), "%Y-%m-%d %H:%M:%S")
        createdAt_UTC = timezone("UTC").localize(createdAt)
        album['createdAt']=createdAt_UTC.astimezone(timezone("US/Eastern")).strftime("%B %d, %Y")

        items.append(album)

    return render_template('index.html', albums=items)



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

        email = session.get('email')
        conn = get_database_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT userID FROM photogallerydb.User WHERE email = %s", (email,))
        user = cursor.fetchone()
        userID = user['userID']
        conn.close()


        if file and allowed_file(file.filename):
            albumID = uuid.uuid4()
            
            filename = file.filename
            filenameWithPath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filenameWithPath)
            
            uploadedFileURL = s3uploading(str(albumID), filenameWithPath, "thumbnails");

            conn=get_database_connection()
            cursor = conn.cursor ()
            statement = f'''INSERT INTO photogallerydb.Album (albumID, name, description, thumbnailURL,createdBy) VALUES ("{albumID}", "{name}", "{description}", "{uploadedFileURL}","{userID}");'''
            
            result = cursor.execute(statement)
            conn.commit()
            conn.close()

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
     
    conn=get_database_connection()
    cursor = conn.cursor ()
    # Get title
    statement = f'''SELECT * FROM photogallerydb.Album WHERE albumID="{albumID}";'''
    cursor.execute(statement)
    albumMeta = cursor.fetchall()
    
    # Photos
    statement = f'''SELECT photoID, albumID, title, description, photoURL FROM photogallerydb.Photo WHERE albumID="{albumID}";'''
    cursor.execute(statement)
    results = cursor.fetchall()
    conn.close() 
    
    items=[]
    for item in results:
        photos={}
        photos['photoID'] = item['photoID']
        photos['albumID'] = item['albumID']
        photos['title'] = item['title']
        photos['description'] = item['description']
        photos['photoURL'] = item['photoURL']
        items.append(photos)

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

            conn=get_database_connection()
            cursor = conn.cursor ()
            ExifDataStr = json.dumps(ExifData)
            statement = f'''INSERT INTO photogallerydb.Photo (PhotoID, albumID, title, description, tags, photoURL, EXIF) VALUES ("{photoID}", "{albumID}", "{title}", "{description}", "{tags}", "{uploadedFileURL}", %s);'''
            
            result = cursor.execute(statement, (ExifDataStr,))
            conn.commit()
            conn.close()

        return redirect(f'''/album/{albumID}''')
    else:
        conn=get_database_connection()
        cursor = conn.cursor ()
        # Get title
        statement = f'''SELECT * FROM photogallerydb.Album WHERE albumID="{albumID}";'''
        cursor.execute(statement)
        albumMeta = cursor.fetchall()
        conn.close()

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
    
    conn=get_database_connection()
    cursor = conn.cursor ()

    # Get title
    statement = f'''SELECT * FROM photogallerydb.Album WHERE albumID="{albumID}";'''
    cursor.execute(statement)
    albumMeta = cursor.fetchall()

    statement = f'''SELECT * FROM photogallerydb.Photo WHERE albumID="{albumID}" and photoID="{photoID}";'''
    cursor.execute(statement)
    results = cursor.fetchall()
    conn.close()

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

        createdAt_UTC = timezone("UTC").localize(createdAt)
        updatedAt_UTC = timezone("UTC").localize(updatedAt)

        photo['createdAt']=createdAt_UTC.astimezone(timezone("US/Eastern")).strftime("%B %d, %Y")
        photo['updatedAt']=updatedAt_UTC.astimezone(timezone("US/Eastern")).strftime("%B %d, %Y")
        
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

    conn=get_database_connection()
    cursor = conn.cursor ()
    statement = f'''SELECT * FROM photogallerydb.Album WHERE name LIKE '%{query}%' UNION SELECT * FROM photogallerydb.Album WHERE description LIKE '%{query}%';'''
    cursor.execute(statement)

    results = cursor.fetchall()
    conn.close()

    items=[]
    for item in results:
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

    conn=get_database_connection()
    cursor = conn.cursor ()
    statement = f'''SELECT * FROM photogallerydb.Photo WHERE title LIKE '%{query}%' AND albumID="{albumID}" UNION SELECT * FROM photogallerydb.Photo WHERE description LIKE '%{query}%' AND albumID="{albumID}" UNION SELECT * FROM photogallerydb.Photo WHERE tags LIKE '%{query}%' AND albumID="{albumID}" UNION SELECT * FROM photogallerydb.Photo WHERE EXIF LIKE '%{query}%' AND albumID="{albumID}";'''
    cursor.execute(statement)

    results = cursor.fetchall()
    conn.close()

    items=[]
    for item in results:
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

                    