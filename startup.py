import os

from code_generator import generate_code
from utilities.config_util import ConfigUtil

from flask import flash, Response, jsonify
from flask import render_template, Flask, request, redirect, url_for, send_from_directory, session
from flask_login import login_user, logout_user, login_required, LoginManager, current_user, UserMixin

from werkzeug.utils import secure_filename
from uml_parser.parse_dm_file import Analyzer as p

from flask_pymongo import PyMongo
import bcrypt
import datetime as dt
import uuid
import base64
from bson import binary
from bson.objectid import ObjectId
import pytz


class User(UserMixin):
    def __init__(self, mongodbengine, username):
        self.username = username
        self.dbengine = mongodbengine
        self.key = -1
        self.validtill = dt.datetime.now(pytz.utc) - dt.timedelta(days=30)
        authentcol = self.dbengine.db.authentication
        findresult = authentcol.find_one({"username": self.username})
        if findresult is not None:
            if findresult["validtill"] is not None:
                tempvalidtill = findresult["validtill"]
                delta = tempvalidtill-dt.datetime.now(pytz.utc)
                if not delta >= dt.timedelta():
                    self.refreshToken(self.username, self.dbengine)
                newfind = authentcol.find_one({"username": self.username})
                self.validtill = newfind["validtill"]
                self.key = newfind["key"]
        else:
            self.key = User.create_random_key()
            self.validtill = User.create_expiry_object()
            authentcol.insert({
                "username": self.username,
                "key": self.key,
                "validtill": self.validtill
            })

        findresult = mongodbengine.db.history.find_one({
            "username":
            self.username
        })
        if findresult is None:
            mongodbengine.db.history.insert({
                "username": self.username,
                "uploads": []
            })

    @staticmethod
    def create_random_key():
        return str(uuid.uuid4())

    @staticmethod
    def create_expiry_object():
        return dt.datetime.now(pytz.utc) + dt.timedelta(days=30)

    @staticmethod
    def refreshToken(username, dbengine):
        authentcol = dbengine.db.authentication
        userprofile = authentcol.find_one({"username": username})
        if userprofile is not None:
            newkey = User.create_random_key()
            newvalidtill = User.create_expiry_object()
            updateresult = authentcol.update(
                {
                    "username": username
                }, {"$set": {
                    "key": newkey,
                    "validtill": newvalidtill
                }},
                upsert=False)
            if updateresult.modified_count > 0:
                return True

        return False

    def is_authenticated(self):
        delta = dt.datetime.now(pytz.utc) - self.validtill
        if not delta >= dt.timedelta():
            User.refreshToken(self.username, self.dbengine)
            authentcol = self.dbengine.db.authentication
            newfind = authentcol.find_one({"username": self.username})
            self.validtill = newfind["validtill"]
            self.key = newfind["key"]
        return True

    def get_id(self):
        tempusername = self.username
        return tempusername.decode('utf-8')

    def is_active(self):
        return True

    def is_anonymous(self):
        return False


ana = p()
config = ConfigUtil()

UPLOAD_FOLDER = 'input'
ALLOWED_EXTENSIONS = set(['xml'])

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# set MongoDB details
app.config['MONGO_DBNAME'] = config.get('Mongo_DB', 'db_name')
app.config['MONGO_URI'] = config.get('Mongo_DB', 'mongo_db_uri')
app.config['LOGIN_DISABLED']=False
mongo = PyMongo(app)

login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'login'
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    if user_id is not None:
        newusername = user_id.encode('utf-8')
        findres = mongo.db.users.find_one({"username":newusername})
        if findres is not None:
            return User(mongo, newusername)
    
    return None


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    if 'username' in session:
        return render_template('user_profile.html')
    return render_template('homepage.html')


@app.route('/login', methods=['POST'])
def login():
    users = mongo.db.users
    findresult = users.find_one({'username': request.form['uname']})

    if findresult:
        if bcrypt.hashpw(request.form['psw'].encode('utf-8'),
                         findresult['password'].encode('utf-8')) == findresult[
                             'password'].encode('utf-8'):
            session['username'] = request.form['uname']
            newuser = User(mongo, request.form['uname'])
            login_user(newuser)
            return redirect(url_for('index'))
    return 'Invalid username/password combination'


@app.route('/register', methods=['POST'])
def register():
    users = mongo.db.users
    username = request.form['uname']
    existing_user = users.find_one({'username': request.form['uname']})

    if existing_user is None:
        hashpass = bcrypt.hashpw(request.form['psw'].encode('utf-8'),
                                 bcrypt.gensalt())
        users.insert({
            'username': request.form['uname'],
            'password': hashpass,
            'email': request.form['email']
        })
        session['username'] = request.form['uname']

        key = User.create_random_key()
        validtill = User.create_expiry_object()
        userprofile = {
            "username": username,
            "key": key,
            "validtill": validtill
        }
        mongo.db.authentication.insert(userprofile)
        mongo.db.history.insert({"username": username, "uploads": []})

        return redirect(url_for('index'))

    return 'That username already exists!'


@app.route('/upload')
@login_required
def upload_xml():
    return render_template('xml_upload.html')


@app.route('/uploadtodb', methods=['POST'])
@login_required
def uploadtodb():
    username = request.form['username']
    dmname = request.form['dmname']

    response = {}

    if username == None or dmname == None or len(username) == 0 or len(
            dmname) == 0:
        response["status"] = "fail"
        response["response"] = "Insufficient parameters"
        return jsonify(response)

    if 'modelfile' not in request.files:
        response["status"] = "fail"
        response["response"] = "model file not exist"
        return jsonify(response)
    f = request.files['modelfile']
    if f.filename == '':
        response["status"] = "fail"
        response["response"] = "file not selected"
        return jsonify(response)

    allcontent = ''
    with f.open(mode='r') as textfile:
        allcontent = textfile.read()
    b64content = base64.standard_b64encode(allcontent)
    bincontent = binary.Binary(b64content)
    fileid = mongo.db.filedb.insert({"file": bincontent})

    userresult = mongo.db.history.find_one({"username": username})
    if userresult == None:
        mongo.db.history.insert({"username": username, "uploads": []})

    domainresult = mongo.db.history.find_one({
        "username": username,
        "uploads": {
            "$elemMatch": {
                "domainModeName": dmname
            }
        }
    })

    if domainresult == None:
        mongo.db["history"].update({
            "username": username
        }, {
            "$push": {
                "uploads": {
                    "domainModeName": dmname,
                    "files": []
                }
            }
        })

    mongo.db["history"].update({
        "username": username,
        "uploads.domainModeName": dmname
    }, {
        "$push": {
            "uploads.$.files": {
                "file": fileid,
                "date": dt.datetime.now(pytz.utc)
            }
        }
    })

    response["status"] = "success"
    response["response"] = "successfully upload model file"
    return jsonify(response)


@app.route('/result', methods=['GET', 'POST'])
@login_required
def result():
    filename_str = ""
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        # if user does not select file, browser also
        # submit a empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filename_str = filename.split(".")[0]
            #!!!
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    #Parse XML and generate JSON
    ana.DM_File_Analyze('input', {'DM_Input_type': "Simple_XML"}, filename_str)

    # NOTE the code below have changed and not compatible with old html files
    #Parse JSON and generate code
    server_url, model_display_data = generate_code.generate_all(filename_str)

    print server_url

    #Pass required data to the template
    description_data = {
        "model_display_data": model_display_data,
        "db_name": filename_str,
        "server_url": server_url
    }

    #Render the template
    # XXX need test
    return render_template('reference.html', **description_data)


@app.route('/generated_code/<path:path>')
@login_required
def generated_code(path):
    return send_from_directory('generated_code', path)


@app.route('/logout')
def logout():
    # remove the username from the session if it is there
    session.pop('username', None)
    logout_user()
    return redirect(url_for('index'))


@app.route('/filelist')
@login_required
def filelist():
    response = {}
    findresult = mongo.db.history.find_one({
        "username": current_user.username,
    },{"username":0,"uploads":1,"_id":0})

    if findresult is None:
        response["message"] = "no such user"
    else:
        for i, imode in enumerate(findresult["uploads"]):
            for j, jfile in enumerate(imode["files"]):
                fileid = jfile["file"]
                prefix = "/downloadfile/" + current_user.username + "/"
                findresult["uploads"][i]["files"][j]["file"]=str(fileid)
                findresult["uploads"][i]["files"][j]["fileurl"] = prefix + str(fileid)

        response = findresult

    return jsonify(response)


@app.route('/downloadfile',methods=['GET'])
@login_required
def downloadfile():
    response = {}
    username = request.args.get('username')
    fileid = request.args.get('fileid')
    if current_user.username != username:
        response["message"] = "file not belong to this user"
        return response

    historycol = mongo.db.history
    findresult = historycol.find_one({
        "username": username,
    })
    if findresult is None:
        response["message"] = "no such user"
    else:
        for imode in findresult["uploads"]:
            for jfile in imode["files"]:
                if fileid == jfile["file"]:
                    newfind = mongo.db.filedb.find_one({"_id": fileid})
                    if newfind is not None:
                        xmlfile = base64.standard_b64decode(newfind["file"])
                        return Response(xmlfile, mimetype='text/xml')

        response["message"] = "no such file"

    return response


@app.route('/requesttoken')
@login_required
def requesttoken():
    userprofile=load_user(current_user.get_id())
    response = {}
    response['key'] = userprofile.key
    return jsonify(response)


@app.route('/verifykey', methods=['POST'])
def verifykeyapi():
    response = {}
    username = request.form['username']
    usertoken = request.form['key']
    if verifykey(username, usertoken, mongo) is True:
        response["valid"] = True
    else:
        response["valid"] = False

    return jsonify(response)


def verifykey(username, usertoken, dbengine):
    authentcol = dbengine.db.authentication
    findresult = authentcol.find_one({"username": username})
    if findresult == None:
        return False

    validtill = findresult["validtill"]
    delta = dt.datetime.now(pytz.utc) - validtill
    if not delta >= dt.timedelta():
        User.refreshToken(username, dbengine)
        findresult = authentcol.find_one({"username": username})
    if findresult["key"] == usertoken:
        return True

    return False


if __name__ == '__main__':

    host = config.get('Application', 'host')
    port = config.getInt('Application', 'port')
    app.secret_key = 'mysecret'
    app.run(host=host, port=port)
