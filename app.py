import base64
import datetime
import html
import json
import os
import re
import requests
import spotipy
import time
import urllib.parse
import pprint
from tqdm import tqdm


from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    Response,
    request,
    session,
    stream_with_context,
)
from flask_session import Session
from functools import wraps
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from tempfile import mkdtemp
from time import sleep


SPOTIFY_AUTH_URL = "https://accounts.spotify.com/en/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE_URL = "https://api.spotify.com"
API_VERSION = "v1"
SPOTIFY_API_URL = "{}/{}".format(SPOTIFY_API_BASE_URL, API_VERSION)


REDIRECT_URI = f"{os.environ.get('SPOTIPY_REDIRECT_URL')}/callback/wb"
SCOPE = "user-library-read user-library-modify playlist-modify-private playlist-modify-public ugc-image-upload playlist-read-collaborative playlist-read-private"
SHOW_DIALOG_bool = True

auth_query_parameters = {
    "client_id": os.environ.get("SPOTIPY_CLIENT_ID"),
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPE,
    "show_dialog": SHOW_DIALOG_bool,
}


app = Flask(__name__)


app.config["TEMPLATES_AUTO_RELOAD"] = True


# @app.after_request
# def after_request(response):
#     response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
#     response.headers["Expires"] = 0
#     response.headers["Pragma"] = "no-cache"
#     return response


app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

if not os.environ.get("SPOTIPY_CLIENT_ID"):
    raise RuntimeError("SPOTIPY_CLIENT_ID not set")

if not os.environ.get("SPOTIPY_CLIENT_SECRET"):
    raise RuntimeError("SPOTIPY_CLIENT_SECRET not set")

if not os.environ.get("SPOTIPY_REDIRECT_URL"):
    raise RuntimeError("SPOTIPY_REDIRECT_URL not set")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login():
    # Auth Step 1: Authorization
    auth_url = f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(auth_query_parameters)}"
    return redirect(auth_url)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


def login_required(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if session.get("response_data") is None:
            return redirect("/")
        elif datetime.datetime.now() >= session.get("response_data").get(
            "expire_datetime"
        ):
            session["status"] = "expired"
            return redirect("/")
        return func(*args, **kwargs)

    return decorated_function


@app.route("/callback/wb")
def callback():
    auth_token = request.args["code"]
    code_payload = {
        "grant_type": "authorization_code",
        "code": str(auth_token),
        "redirect_uri": REDIRECT_URI,
        "client_id": os.environ.get("SPOTIPY_CLIENT_ID"),
        "client_secret": os.environ.get("SPOTIPY_CLIENT_SECRET"),
    }
    post_request = requests.post(SPOTIFY_TOKEN_URL, data=code_payload)

    response_data = json.loads(post_request.text)

    response_data["expire_datetime"] = datetime.datetime.now() + datetime.timedelta(
        seconds=max(response_data["expires_in"] - 100, 0)
    )
    session["status"] = "active"
    session["response_data"] = response_data

    return redirect("/")


@app.route("/brokensongs")
@login_required
def brokensongs():
    sp = spotipy.Spotify(auth=session["response_data"]["access_token"])
    # client_credentials_manager = SpotifyClientCredentials(
    #     os.environ.get("SPOTIPY_CLIENT_ID"), os.environ.get("SPOTIPY_CLIENT_SECRET")
    # )
    # sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
    playlists = sp.current_user_playlists(limit=50)
    playlist_ids = []
    all_tracks = []
    broken_tracks = []
    while playlists:
        for playlist in playlists["items"]:
            playlist_ids.append(
                # {
                # "name": playlist["name"],
                # "id": playlist["id"],
                # "tracks": playlist["tracks"]["total"],
                # }
                playlist["id"]
            )
        if playlists["next"]:
            playlists = sp.next(playlists)
        else:
            playlists = None
    print("god dammit")
    for playlist_id in tqdm(playlist_ids):
        results = sp.playlist_tracks(playlist_id)
        for item in results["items"]:
            track = item["track"]
            if track:
                info = {
                    "name": track["name"],
                    "artist": track["artists"][0]["name"],
                    "uri": track["uri"],
                    "id": track["id"],
                }
            if info not in all_tracks:
                all_tracks.append(info)
    print("Got here!")

    # for track in (all_tracks):
    #     if track["id"] == None:
    #         continue
    #     else:
    #         track_id = track["id"]
    #         print(sp.track(track_id)["available_markets"])
    #         if "US" not in sp.track(track_id)["available_markets"]:
    #             broken_tracks.append(track)

    for track in all_tracks[:1]:
        track_id = track["id"]
        test_track = sp.track(track_id)
        if "US" not in test_track["available_markets"]:
            broken_tracks.append(track)
    print(len(all_tracks))
    for i in all_tracks[:1]:
        pprint.pprint(d := i["id"])
        pprint.pprint(e := sp.track(d))
        print("US" in e["available_markets"])
        print()
    pprint.pprint(f := sp.track("5uaIbU3oHHcSOK6WFNK5nj"))
    print("US" in f["available_markets"])

    return render_template(
        "brokensongs.html", all_tracks=all_tracks, broken_tracks=broken_tracks
    )


@app.route("/info")
def info():
    return render_template("info.html")
