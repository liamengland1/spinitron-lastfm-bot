# coding=utf-8

import json
from pathlib import Path
import requests
import re
import pylast
import pendulum
import html
import os

ROOT = Path(__file__).resolve().parents[0]


def spotify_search_api_songs(isrc, query=None, token=None):
    if isrc:
        print('searching by isrc')
        url = f'https://api-partner.spotify.com/pathfinder/v1/query?operationName=searchTracks&variables=%7B%22searchTerm%22%3A%22isrc:{isrc}%22%2C%22offset%22%3A0%2C%22limit%22%3A10%2C%22numberOfTopResults%22%3A20%2C%22includeAudiobooks%22%3Afalse%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%221d021289df50166c61630e02f002ec91182b518e56bcd681ac6b0640390c0245%22%7D%7D'
    elif query:
        print('searching by query')
        url = f'https://api-partner.spotify.com/pathfinder/v1/query?operationName=searchTracks&variables=%7B%22searchTerm%22%3A%22{query}%22%2C%22offset%22%3A0%2C%22limit%22%3A10%2C%22numberOfTopResults%22%3A20%2C%22includeAudiobooks%22%3Afalse%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%221d021289df50166c61630e02f002ec91182b518e56bcd681ac6b0640390c0245%22%7D%7D'
    #token = requests.get('https://open.spotify.com/get_access_token?reason=transport&productType=web-player', headers=headers).json()['accessToken']
    spotifySearch = requests.get(url, headers={'Authorization': 'Bearer ' + token})
    x = spotifySearch.json()
    #if len(x['data']['searchV2']['tracksV2']['items']) > 0:
    return x
    #if isrc and len(x['data']['searchV2']['tracksV2']['items']) == 0:
    #    return spotify_search_api_songs(False, query, token)

def spotify_search_api_album(uri, token=None):
    print('searching spotify album')
    aURI = uri.replace(":", "%3A")
    url = f'https://api-partner.spotify.com/pathfinder/v1/query?operationName=getAlbumMetadata&variables=%7B%22uri%22%3A%22{aURI}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%223632de5a7622918df3594ef3b7919a3980a0c015331ef677fd1ceaf3d9997710%22%7D%7D'
    spotifySearch = requests.get(url, headers={'Authorization': 'Bearer ' + token})
    return spotifySearch.json()

def lambda_handler(event, context):

    network = pylast.LastFMNetwork(
        api_key=os.getenv('LASTFM_API_KEY'),
        api_secret=os.getenv('LASTFM_API_SECRET'),
        username=os.getenv('LASTFM_USERNAME'),
        password_hash=os.getenv('LASTFM_PASSWORD_HASH')
    )

    myHeaders = {
        'User-agent': 'Mozilla/5.0 (Windows NT 10.0; rv:105.0) Gecko/20100101 Firefox/105.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br'
    }
    spinitronWidget = requests.get("https://widgets.spinitron.com/widget/now-playing-v2?station=wuog&meta=0&player=0&sharing=0", headers=myHeaders)
    spinRegex = r'(?:data-spin=")({.+})'
    aHtml = spinitronWidget.content.decode('utf-8')
    match = re.search(spinRegex, aHtml)
    useSpotify = True
    if match:
        data = json.loads(html.unescape(match.group(1)))
        artist = data['a']
        song = data['s']
        album = data['r']
        isrc = data['i'] if data['i'] != '' else False
        q = f'{song} {artist}'
        print(data)
        spotToken = requests.get('https://open.spotify.com/get_access_token?reason=transport&productType=web-player', headers=myHeaders).json()['accessToken']
        songs = spotify_search_api_songs(isrc, q, spotToken)['data']['searchV2']['tracksV2']['items']
        chosenSongIdx = 0  # pick the first result by default
        if not isrc or len(songs) == 0:
            '''if album:
                for x in len(songs):
                    if songs[x]['item']['data']['name'] == song:
                        if songs[x]['item']['data']['albumOfTrack']['name'] == album:
                            chosenSongIdx = x
                            break
            else:
                if songs[chosenSongIdx]['item']['data']['name'].lower() != song.lower():
                    print('song name mismatch')
                    useSpotify = False'''
            useSpotify = False

        if useSpotify:
            songObj = songs[chosenSongIdx]['item']['data']
            albumObj = spotify_search_api_album(songObj['albumOfTrack']['uri'], spotToken)['data']['album']  # need to get album artist, in case it's not  the same as the track artist
        # check if last scrobbled song is the same as the current song
        lastScrobbled = network.get_user('wuog-athens').get_recent_tracks(limit=1)[0]
        aCondition = ((lastScrobbled.track.title == songObj['name'] and lastScrobbled.track.artist.name == songObj['artists']['items'][0]['profile']['name']) or (lastScrobbled.track.title == songObj['name'] and lastScrobbled.album == albumObj['name'])) if useSpotify else ((lastScrobbled.track.title == song and lastScrobbled.track.artist.name == artist) or (lastScrobbled.track.title == song and lastScrobbled.album == album))
        if (aCondition):
            print('already scrobbled')
            return
        else:
            timeRegex = r'(?:<a href=".+">)(\d{1,2}:\d{2}.+)(?:<\/a>)'
            match = re.search(timeRegex, aHtml)
            time = match.group(1)
            ts = pendulum.from_format(time, 'h:mm A', tz='America/New_York')
            # today's date
            today = pendulum.today('America/New_York')
            # 
            print(ts)
            print(today)
            if (ts.day != today.day & ts.hour > 20):
                print('ts day is not today, subtracting a day')
                ts = ts.subtract(days=1)
            #ts = ts.subtract(days=1)
            unix_timestamp = ts.timestamp()
            if useSpotify:
                print(f'scrobbling {song} - {artist} - {album} as {songObj["name"]} - {songObj["artists"]["items"][0]["profile"]["name"]} - {albumObj["name"]}')
                network.scrobble(
                    artist=songObj['artists']['items'][0]['profile']['name'],
                    title=songObj['name'],
                    album=albumObj['name'],
                    album_artist=albumObj['artists']['items'][0]['profile']['name'],
                    timestamp=unix_timestamp
                )
            else:
                print(f'scrobbling {song} - {artist} - {album} directly from spinitron')
                network.scrobble(
                    artist=artist,
                    title=song,
                    album=album,
                    timestamp=unix_timestamp
                )
    else:
        print('non-music track playing')