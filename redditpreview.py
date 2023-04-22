import re, json, mimetypes, instaloader, urllib
from typing import Type
from urllib.parse import quote
from mautrix.types import ImageInfo, EventType, MessageType
from mautrix.types.event.message import BaseFileInfo, Format, TextMessageEventContent
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import event


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("reddit.enabled")
        helper.copy("reddit.info")
        helper.copy("reddit.image")
        helper.copy("reddit.video")
        helper.copy("instagram.enabled")
        helper.copy("instagram.info")
        helper.copy("instagram.image")
        helper.copy("instagram.thumbnail")
        helper.copy("instagram.video")
        helper.copy("youtube.enabled")
        helper.copy("youtube.info")
        helper.copy("youtube.thumbnail")


reddit_pattern = re.compile(r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:reddit\.com|redd.it))(\/r\/.*\/comments\/.*)(\/)?$")
instagram_pattern = re.compile(r"/(?:https?:\/\/)?(?:www.)?instagram.com\/?([a-zA-Z0-9\.\_\-]+)?\/([p]+)?([reel]+)?([tv]+)?([stories]+)?\/([a-zA-Z0-9\-\_\.]+)\/?([0-9]+)?/")
youtube_pattern = re.compile(r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$")

class RedditPreviewPlugin(Plugin):
    async def start(self) -> None:
        await super().start()

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    @event.on(EventType.ROOM_MESSAGE)
    async def on_message(self, evt: MessageEvent) -> None:
        if evt.content.msgtype != MessageType.TEXT or evt.content.body.startswith("!"):
            return
        for url_tup in youtube_pattern.findall(evt.content.body):
            await evt.mark_read()
            if self.config["youtube.enabled"]:
                url = ''.join(url_tup)
                if "youtu.be" in url:
                    video_id = url.split("youtu.be/")[1]
                else:
                    video_id = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)['v'][0]
                video_id = video_id.split("?", 1)[0]

                params = {"format": "json", "url": url}
                query_url = "https://www.youtube.com/oembed"
                query_string = urllib.parse.urlencode(params)
                query_url = query_url + "?" + query_string
                response = await self.http.get(query_url)
                if response.status != 200:
                    self.log.warning(f"Unexpected status fetching video title {query_url}: {response.status}")
                    return None
                response_text = await response.read()
                data = json.loads(response_text.decode())

                if self.config["youtube.info"]:
                    await evt.reply(data['title'])

                if self.config["youtube.thumbnail"]:
                    thumbnail_link = "https://img.youtube.com/vi/" + video_id + "/hqdefault.jpg"
                    response = await self.http.get(thumbnail_link)
                    if response.status != 200:
                        self.log.warning(f"Unexpected status fetching image {thumbnail_link}: {response.status}")
                        return None
                    thumbnail = await response.read()
                    filename = video_id + ".jpg"
                    uri = await self.client.upload_media(thumbnail, mime_type='image/jpg', filename=filename)
                    await self.client.send_image(evt.room_id, url=uri, file_name=filename, info=ImageInfo(mimetype='image/jpg'))
        for url_tup in instagram_pattern.findall(evt.content.body):
            await evt.mark_read()
            if self.config["instagram.enabled"] and url_tup[5]:
                L = instaloader.Instaloader()
                shortcode = url_tup[5]
                self.log.warning(shortcode)
                post = instaloader.Post.from_shortcode(L.context, shortcode)
                if(self.config["instagram.info"]):
                    await evt.reply(TextMessageEventContent(msgtype=MessageType.TEXT, format=Format.HTML, formatted_body=f"""<p>Username: {post.owner_username}<br>Caption: {post.pcaption}<br>Hashtags: {post.caption_hashtags}<br>Mentions: {post.caption_mentions}<br>Likes: {post.likes}<br>Comments: {post.comments}</p>"""))
                if((post.is_video and self.config["instagram.thumbnail"]) or (not post.is_video and self.config["instagram.image"])):
                    response = await self.http.get(post.url)
                    if response.status != 200:
                        self.log.warning(f"Unexpected status fetching instagram image {post.url}: {response.status}")
                        return None
                    media = await response.read()
                    mime_type='image/jpg'
                    file_extension = ".jpg"
                    file_name = shortcode + file_extension
                    uri = await self.client.upload_media(media, mime_type=mime_type, filename=file_name)
                    self.log.warning(f"{mime_type} {file_name}")
                    await self.client.send_image(evt.room_id, url=uri, file_name=file_name, info=ImageInfo(mimetype='image/jpg'))
                if(post.is_video and self.config["instagram.video"]):
                    response = await self.http.get(post.video_url)
                    if response.status != 200:
                        self.log.warning(f"Unexpected status fetching instagram video {post.video_url}: {response.status}")
                        return None
                    media = await response.read()
                    mime_type='video/mp4'
                    file_extension = ".mp4"
                    file_name = shortcode + file_extension
                    uri = await self.client.upload_media(media, mime_type=mime_type, filename=file_name)
                    await self.client.send_file(evt.room_id, url=uri, info=BaseFileInfo(mimetype=mime_type, size=len(media)), file_name=file_name,file_type=MessageType.VIDEO)
        for url_tup in reddit_pattern.findall(evt.content.body):
            await evt.mark_read()
            if self.config["reddit.enabled"]:
                url = ''.join(url_tup).split('?')[0]
                query_url = quote(url).replace('%3A', ':') + ".json" + "?limit=1"
                headers = {
                    'User-Agent': 'ggogel/RedditPreviewMaubot'
                }
                response = await self.http.request('GET', query_url, headers=headers)

                if response.status != 200:
                    self.log.warning(f"Unexpected status fetching reddit listing {query_url}: {response.status}")
                    return None
                
                response_text = await response.read()
                data = json.loads(response_text.decode())

                sub = data[0]['data']['children'][0]['data']['subreddit_name_prefixed']
                title = data[0]['data']['children'][0]['data']['title']
                name = data[0]['data']['children'][0]['data']['name']
                
                if self.config["reddit.info"]:
                    await evt.reply(TextMessageEventContent(msgtype=MessageType.TEXT, format=Format.HTML, body=f"{sub}: {title}", formatted_body=f"""<p><b>{sub}: {title}</b></p>"""))
                
                # We assume that when this condition is true, the post is either an image or video
                if 'url_overridden_by_dest' in  data[0]['data']['children'][0]['data']:
                    media_url = data[0]['data']['children'][0]['data']['url_overridden_by_dest']
                    mime_type = mimetypes.guess_type(media_url)[0]

                    # Use video fallback URL if original URL has non-standard or no file extension. This is typically the case for "gifs" on imgur and gfycat, which are actually videos.
                    if mime_type == None:
                        if 'reddit_video' in data[0]['data']['children'][0]['data']['secure_media']:
                            media_url = data[0]['data']['children'][0]['data']['secure_media']['reddit_video']['fallback_url'].split('?')[0]
                        else:
                            media_url = data[0]['data']['children'][0]['data']['preview']['reddit_video_preview']['fallback_url'].split('?')[0]
                        mime_type = mimetypes.guess_type(media_url)[0]

                    file_extension = mimetypes.guess_extension(mime_type)
                    file_name = name + file_extension
                    
                    if "image" in mime_type and self.config["reddit.image"]:
                        response = await self.http.get(media_url)

                        if response.status != 200:
                            self.log.warning(f"Unexpected status fetching media {media_url}: {response.status}")
                            return None

                        media = await response.read()
                        uri = await self.client.upload_media(media, mime_type=mime_type, filename=file_name)
                        await self.client.send_image(evt.room_id, url=uri, file_name=file_name, info=ImageInfo(mimetype='image/jpg'))
                    elif "video" in mime_type and self.config["reddit.video"]:
                        audio_url = media_url.replace("DASH_720","DASH_audio")
                        media_url = "https://sd.rapidsave.com/download.php?permalink={}&video_url={}?source=fallback&audio_url={}?source=fallback".format(url, media_url, audio_url)
                        response = await self.http.get(media_url)

                        if response.status != 200:
                            self.log.warning(f"Unexpected status fetching media {media_url}: {response.status}")
                            return None

                        media = await response.read()
                        uri = await self.client.upload_media(media, mime_type=mime_type, filename=file_name)
                        await self.client.send_file(evt.room_id, url=uri, info=BaseFileInfo(mimetype=mime_type, size=len(media)), file_name=file_name,file_type=MessageType.VIDEO)
                    elif self.config["reddit.image"] or self.config["reddit.video"]:
                        self.log.warning(f"Unknown media type {query_url}: {mime_type}")
                        return None