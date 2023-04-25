import datetime
import json
import os
import requests
import spotipy
import urllib.parse
from youtubesearchpython import VideosSearch
from flask_uploads import UploadSet, IMAGES, configure_uploads
from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    send_file,
    make_response,
)
from flask_session import Session
from functools import wraps
from tempfile import mkdtemp
from functools import *
import yt_dlp
import eyed3
from eyed3.id3.frames import ImageFrame


# import for future functionality
import shutil
import zipfile
from glob import glob
from io import BytesIO


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
photos = UploadSet("photos", IMAGES)

app.config["UPLOADS_DEFAULT_DEST"] = "static/img"
app.config["UPLOADS_DEFAULT_URL"] = "/static/img"

configure_uploads(app, photos)

app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


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
        for playlist in playlists["items"]:
            # if playlist["owner"]["id"] == user_id:
            all_playlists.append(playlist)
        if playlists["next"]:
            playlists = sp.next(playlists)
        else:
            playlists = None
    return all_playlists


def get_all_tracks():
    sp = spotipy.Spotify(auth=session["response_data"]["access_token"])
    playlists = get_playlists()
    all_tracks = []
    for playlist in playlists:
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


def get_urls_from_playlist(playlist_id):
    sp = spotipy.Spotify(auth=session["response_data"]["access_token"])
    all_yt_links = []
    limit = 100
    offset = 0
    results = None
    while True:
        results = sp.playlist_tracks(playlist_id, limit=limit, offset=offset)
        if not results["items"]:
            break
        for item in results["items"]:
            track = item["track"]
            if track and track["name"]:
                query = (
                    f'{track["name"]} by {track["artists"][0]["name"]}'
                    if track["artists"][0]["name"] != "Various Arists"
                    else f'{track["name"]}'
                )
                video_id, video_name = search_video(query)
                playable = "US" in track["available_markets"] or not track["id"]
                link = f"https://www.youtube.com/watch?v={video_id}"
                info = {
                    "link": link,
                    "name": track["name"],
                    "artist": track["artists"][0]["name"],
                    "playable": playable,
                    "album_art_url": track["album"]["images"][0]["url"],
                    "id": track["id"],
                }
                all_yt_links.append(info)
        offset += limit
    return all_yt_links


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
        for item in results["items"]:
            track = item["track"]
            if track and track["name"]:
                playable = "US" in track["available_markets"] or not track["id"]
                query = (
                    f'{track["name"]} by {track["artists"][0]["name"]}'
                    if track["artists"][0]["name"] != "Various Arists"
                    else f'{track["name"]}'
                )
                # video_id, video_name = search_video(query)
                info = {
                    "name": track["name"],
                    "artist": track["artists"][0]["name"],
                    "uri": track["uri"],
                    "id": track["id"],
                    "playable": playable,
                    # "video_id": video_id,
                    # "video_name": video_name,
                }
                all_tracks.append(info)

        offset += limit
    return render_template(
        "playlisttracks.html", playlist=playlist_id, tracks=all_tracks
    )


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


@app.route("/download/<song_id>")
@login_required
def download_video(song_id):
    sp = spotipy.Spotify(auth=session["response_data"]["access_token"])
    track = sp.track(song_id)

    query = (
        f'{track["name"]} {track["artists"][0]["name"]}'
        if track["artists"][0]["name"] != "Various Arists"
        else f'{track["name"]}'
    )
    video_id, video_name = search_video(query)
    video_url = f"https://www.youtube.com/watch?v={video_id}"
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
        ydl.extract_info(video_url, download=True)
    url = track["album"]["images"][0]["url"]
    response = requests.get(url)
    with open(f"static/img/{track['name']}tempimg.jpeg", "wb") as f:
        f.write(response.content)
    audiofile = eyed3.load("downloads/temp_audio.mp3")
    audiofile.tag.images.set(
        ImageFrame.FRONT_COVER,
        open(f"static/img/{track['name']}tempimg.jpeg", "rb").read(),
        "image/jpeg",
    )
    audiofile.tag.artist = track["artists"][0]["name"]
    audiofile.tag.album = track["album"]["name"]
    audiofile.tag.save()
    os.remove(f"static/img/{track['name']}tempimg.jpeg")
    return send_file(
        "downloads/temp_audio.mp3",
        as_attachment=True,
        download_name=(track["name"] + ".mp3"),
    )


@app.route("/megaplaylist")
@login_required
def megaplaylist():
    return render_template("megaplaylist.html")


#!THIS IS STILL IN ALPHA
@app.route("/downloadall/<playlist_id>")
@login_required
def downloadall(playlist_id):
    sp = spotipy.Spotify(auth=session["response_data"]["access_token"])
    link_list = get_urls_from_playlist(playlist_id)
    name = f"{sp.playlist(playlist_id)['name']}"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": name + "/%(title)s",
        "quiet": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    url_list = [url["link"] for url in link_list]
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(url_list)

    with zipfile.ZipFile(f"{name}.zip", "w") as zipf:
        for url in link_list:
            info = yt_dlp.YoutubeDL(ydl_opts).extract_info(url["link"], download=False)
            video_filename = yt_dlp.YoutubeDL(ydl_opts).prepare_filename(info) + ".mp3"
            zipf.write(video_filename)
    zipf.close()
    shutil.rmtree(name)
    response = make_response(send_file(f"{name}.zip", as_attachment=True))
    os.remove(f"{name}.zip")
    return response
