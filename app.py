import datetime
import json
import os
import zipfile
import requests
import spotipy
import urllib.parse
from pprint import pprint
from tqdm import tqdm
from youtubesearchpython import VideosSearch
from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    send_file,
    # Response,
    # flash,
    # stream_with_context,
)
from flask_session import Session
from functools import wraps
from tempfile import mkdtemp
from functools import *
import yt_dlp

# import re
# import html
# import base64
# import tempfile
# from bs4 import BeautifulSoup
# import time
# from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
# from spotipy.oauth2 import SpotifyOAuth
# from requests.exceptions import ReadTimeout
# import subprocess


SPOTIFY_AUTH_URL = "https://accounts.spotify.com/en/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE_URL = "https://api.spotify.com"
API_VERSION = "v1"
SPOTIFY_API_URL = "{}/{}".format(SPOTIFY_API_BASE_URL, API_VERSION)
CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
YOUTUBE_API_KEY = os.environ.get("YT_API_KEY")

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


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Configure session to use filesystem (instead of signed cookies)
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

# if not os.environ.get("YT_API_KEY"):
#     raise RuntimeError("YouTube API Key not set")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login():
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
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    post_request = requests.post(SPOTIFY_TOKEN_URL, data=code_payload)

    response_data = json.loads(post_request.text)

    response_data["expire_datetime"] = datetime.datetime.now() + datetime.timedelta(
        seconds=max(response_data["expires_in"] - 100, 0)
    )
    session["status"] = "active"
    session["response_data"] = response_data

    return redirect("/")


@lru_cache
def get_playlists():
    """Returns a list of all tracks (with names on Spotify) that the user has added to a playlist they have created

    Returns:
        list: List of all tracks that the user has added to their playlists.
    """
    sp = spotipy.Spotify(auth=session["response_data"]["access_token"])
    playlists = sp.current_user_playlists(limit=50)
    all_playlists = []
    # user_id = sp.current_user()["id"]
    while playlists:
        for playlist in tqdm(playlists["items"]):
            # if playlist["owner"]["id"] == user_id:
            all_playlists.append(playlist)
        if playlists["next"]:
            playlists = sp.next(playlists)
        else:
            playlists = None
    return all_playlists


@lru_cache
def get_all_tracks():
    sp = spotipy.Spotify(auth=session["response_data"]["access_token"])
    playlists = get_playlists()
    all_tracks = []
    for playlist in tqdm(playlists):
        limit = 100
        offset = 0
        results = None
        while True:
            results = sp.playlist_tracks(playlist["id"], limit=limit, offset=offset)
            if not results["items"]:
                break
            for item in results["items"]:
                track = item["track"]
                if track and track["name"]:
                    playable = "US" in track["available_markets"] or not track["id"]
                    info = {
                        "name": track["name"],
                        "artist": track["artists"][0]["name"],
                        "uri": track["uri"],
                        "id": track["id"],
                        "playable": playable,
                    }
                    all_tracks.append(info)

            offset += limit
    return all_tracks


@lru_cache
def get_broken_tracks():
    broken_tracks = [track for track in get_all_tracks() if track["playable"] == False]
    return broken_tracks


@lru_cache
def search_video(query):
    result = VideosSearch(query, limit=1).result()
    return result["result"][0]["id"], result["result"][0]["title"]


@app.route("/info")
def info():
    return render_template("info.html")


@app.route("/showplaylists")
@login_required
def showplaylists():
    all_playlists = get_playlists()
    return render_template("showplaylists.html", playlists=all_playlists)


@app.route("/playlist/<playlist_id>")
@login_required
@lru_cache
def playlist_tracks(playlist_id):
    sp = spotipy.Spotify(auth=session["response_data"]["access_token"])
    all_tracks = []
    limit = 100
    offset = 0
    results = None
    while True:
        results = sp.playlist_tracks(playlist_id, limit=limit, offset=offset)
        if not results["items"]:
            break
        for item in tqdm(results["items"]):
            track = item["track"]
            if track and track["name"]:
                playable = "US" in track["available_markets"] or not track["id"]
                query = (
                    f'{track["name"]} by {track["artists"][0]["name"]}'
                    if track["artists"][0]["name"] != "Various Arists"
                    else f'{track["name"]}'
                )
                video_id, video_name = search_video(query)
                info = {
                    "name": track["name"],
                    "artist": track["artists"][0]["name"],
                    "uri": track["uri"],
                    "id": track["id"],
                    "playable": playable,
                    "video_id": video_id,
                    "video_name": video_name,
                }
                all_tracks.append(info)

        offset += limit
    return render_template("playlisttracks.html", tracks=all_tracks)


@app.route("/allsongs")
@login_required
def allsongs():
    all_tracks = get_all_tracks()
    return render_template("allsongs.html", all_tracks=all_tracks)


@app.route("/brokensongs")
@login_required
def brokensongs():
    broken_tracks = get_broken_tracks()
    return render_template("brokensongs.html", broken_tracks=broken_tracks)


@app.route("/songdownloader")
@login_required
def songdownloader():
    return render_template("songdownloader.html")


@app.route("/songfixer")
@login_required
def fix():
    return render_template("songfixer.html")


@app.route("/download/<video_id>")
def download_video(video_id):
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    video_title = VideosSearch(video_id, limit=1).result()["result"][0]["title"]
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": "downloads/temp_audio.%(ext)s",
        "quiet": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
    return send_file(
        "downloads/temp_audio.mp3",
        as_attachment=True,
        attachment_filename=(video_title + ".mp3"),
    )