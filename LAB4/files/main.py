#!flask/bin/python3
import sys, os

sys.path.append(os.path.abspath(os.path.join("utils")))
from env import (
    BUCKET_NAME,
    ACCESS_KEY_USERNAME,
    SECRET_KEY_PASSWORD,
    STORAGE_HOST,
    STORAGE_HOST_PORT,
    STORAGE_HOST_EXT,
    STORAGE_PORT_EXT,
    DB_HOSTNAME,
    DB_USERNAME,
    DB_PASSWORD,
    DB_NAME,
    DB_PORT,
    DB_TABLE,
)
from flask import (
    Flask,
    jsonify,
    abort,
    request,
    make_response,
    render_template,
    redirect,
)
import time
import exifread
import json
import uuid
import boto3
import pymysql.cursors
from datetime import datetime
from pytz import timezone


app = Flask(__name__, static_url_path="")

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "media")
ALLOWED_EXTENSIONS = set(["png", "jpg", "jpeg"])


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def getExifData(path_name):
    f = open(path_name, "rb")
    tags = exifread.process_file(f)
    ExifData = {}
    for tag in tags.keys():
        if tag not in ("JPEGThumbnail", "TIFFThumbnail", "Filename", "EXIF MakerNote"):
            key = "%s" % (tag)
            val = "%s" % (tags[tag])
            ExifData[key] = val
    return ExifData


def s3uploading(filename, filenameWithPath, uploadType="photos"):
    storage_endpoint = f"""http://{STORAGE_HOST}:{STORAGE_HOST_PORT}"""
    s3 = boto3.client(
        "s3",
        endpoint_url=storage_endpoint,
        aws_access_key_id=ACCESS_KEY_USERNAME,
        aws_secret_access_key=SECRET_KEY_PASSWORD,
    )

    bucket = BUCKET_NAME
    path_filename = uploadType + "/" + filename

    s3.upload_file(filenameWithPath, bucket, path_filename)
    return f"""http://{STORAGE_HOST_EXT}:{STORAGE_PORT_EXT}/{BUCKET_NAME}/{path_filename}"""


def get_database_connection():
    conn = pymysql.connect(
        host=DB_HOSTNAME,
        user=DB_USERNAME,
        password=DB_PASSWORD,
        db=DB_NAME,
        port=DB_PORT,
        cursorclass=pymysql.cursors.DictCursor,
    )
    return conn


@app.errorhandler(400)
def bad_request(error):
    """400 page route.

    get:
        description: Endpoint to return a bad request 400 page.
        responses: Returns 400 object.
    """
    return make_response(jsonify({"error": "Bad request"}), 400)


@app.errorhandler(404)
def not_found(error):
    """404 page route.

    get:
        description: Endpoint to return a not found 404 page.
        responses: Returns 404 object.
    """
    return make_response(jsonify({"error": "Not found"}), 404)


@app.route("/", methods=["GET", "POST"])
def home_page():
    """Home page route.

    get:
        description: Endpoint to return home page.
        responses: Returns all the Photos.
    """
    conn = get_database_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {DB_NAME}.{DB_TABLE};")
    results = cursor.fetchall()
    conn.close()

    items = []
    for item in results:
        photo = {}
        photo["PhotoID"] = item["PhotoID"]
        photo["Title"] = item["Title"]
        photo["Description"] = item["Description"]
        photo["Tags"] = item["Tags"]
        photo["URL"] = item["URL"]

        createdAt = datetime.strptime(str(item["CreationTime"]), "%Y-%m-%d %H:%M:%S")

        createdAt_UTC = timezone("UTC").localize(createdAt)

        photo["CreationTime"] = createdAt_UTC.astimezone(
            timezone("US/Eastern")
        ).strftime("%B %d, %Y at %-I:%M:%S %p")

        items.append(photo)

    return render_template("index.html", photos=items)


@app.route("/add", methods=["GET", "POST"])
def add_photo():
    """Create new photo under album route.

    get:
        description: Endpoint to return form to create a new photo.
        responses: Returns all the fields needed to store a new photo.

    post:
        description: Endpoint to send new photo.
        responses: Returns user to home page.
    """
    if request.method == "POST":
        uploadedFileURL = ""
        file = request.files["imagefile"]
        title = request.form["title"]
        description = request.form["description"]
        tags = request.form["tags"]

        if file and allowed_file(file.filename):
            filename = file.filename
            filenameWithPath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filenameWithPath)

            uploadedFileURL = s3uploading(filename, filenameWithPath)
            ExifData = getExifData(filenameWithPath)

            conn = get_database_connection()
            cursor = conn.cursor()
            ExifDataStr = json.dumps(ExifData)
            statement = f"""INSERT INTO {DB_NAME}.{DB_TABLE} (Title, Description, Tags, URL, EXIF) VALUES ("{title}", "{description}", "{tags}", "{uploadedFileURL}", %s);"""

            result = cursor.execute(statement, (ExifDataStr,))
            conn.commit()
            conn.close()

        return redirect("/")

    else:
        return render_template("form.html")


@app.route("/<int:photoID>", methods=["GET"])
def view_photo(photoID):
    """photo page route.

    get:
        description: Endpoint to return a photo.
        responses: Returns a photo.
    """
    conn = get_database_connection()
    cursor = conn.cursor()

    # Get title
    statement = f"""SELECT * FROM {DB_NAME}.{DB_TABLE} WHERE PhotoID="{photoID}";"""
    cursor.execute(statement)
    results = cursor.fetchall()
    conn.close()

    photo = {}
    tags = []
    exifdata = {}

    if len(results) > 0:
        photo = {}
        photo["PhotoID"] = results[0]["PhotoID"]
        photo["Title"] = results[0]["Title"]
        photo["Description"] = results[0]["Description"]
        photo["Tags"] = results[0]["Tags"]
        photo["URL"] = results[0]["URL"]
        photo["ExifData"] = json.loads(results[0]["EXIF"])

        createdAt = datetime.strptime(str(results[0]["CreationTime"]), "%Y-%m-%d %H:%M:%S")

        createdAt_UTC = timezone("UTC").localize(createdAt)

        photo["CreationTime"] = createdAt_UTC.astimezone(
            timezone("US/Eastern")
        ).strftime("%B %d, %Y at %-I:%M:%S %p")

        tags = photo["Tags"].split(",")
        exifdata = photo["ExifData"]

    return render_template(
        "photodetail.html", photo=photo, tags=tags, exifdata=exifdata
    )


@app.route("/search", methods=["GET"])
def search_photo():
    """search photo page route.

    get:
        description: Endpoint to return all the matching photos.
        responses: Returns all the photos based on a particular query.
    """
    query = request.args.get("query", None)

    conn = get_database_connection()
    cursor = conn.cursor()
    statement = f"""SELECT * FROM {DB_NAME}.{DB_TABLE} WHERE Title LIKE '%{query}%' UNION SELECT * FROM {DB_NAME}.{DB_TABLE} WHERE Description LIKE '%{query}%' UNION SELECT * FROM {DB_NAME}.{DB_TABLE} WHERE Tags LIKE '%{query}%' UNION SELECT * FROM {DB_NAME}.{DB_TABLE} WHERE EXIF LIKE '%{query}%';"""
    print(statement)
    cursor.execute(statement)

    results = cursor.fetchall()
    conn.close()

    items = []
    for item in results:
        photo = {}
        photo["PhotoID"] = item["PhotoID"]
        photo["CreationTime"] = item["CreationTime"]
        photo["Title"] = item["Title"]
        photo["Description"] = item["Description"]
        photo["Tags"] = item["Tags"]
        photo["URL"] = item["URL"]
        photo["ExifData"] = item["EXIF"]
        items.append(photo)

    return render_template("search.html", photos=items, searchquery=query)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
