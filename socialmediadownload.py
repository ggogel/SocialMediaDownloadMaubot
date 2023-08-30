import re
import json
import mimetypes
import instaloader
import urllib

from typing import Type
from urllib.parse import quote
from mautrix.types import ImageInfo, EventType, MessageType
from mautrix.types.event.message import BaseFileInfo, Format, TextMessageEventContent
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import event


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        for prefix in ["reddit", "instagram", "youtube"]:
            for suffix in ["enabled", "info", "image", "video", "thumbnail"]:
                helper.copy(f"{prefix}.{suffix}")

reddit_pattern = re.compile(r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:reddit\.com|redd.it))(\/r\/.*\/comments\/.*)(\/)?$")
instagram_pattern = re.compile(r"/(?:https?:\/\/)?(?:www.)?instagram.com\/?([a-zA-Z0-9\.\_\-]+)?\/([p]+)?([reel]+)?([tv]+)?([stories]+)?\/([a-zA-Z0-9\-\_\.]+)\/?([0-9]+)?/")
youtube_pattern = re.compile(r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$")

class SocialMediaDownloadPlugin(Plugin):
    async def start(self) -> None:
        self.config.load_and_update()

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
                await self.handle_youtube(evt, url_tup)

        for url_tup in instagram_pattern.findall(evt.content.body):
            await evt.mark_read()
            if self.config["instagram.enabled"] and url_tup[5]:
                await self.handle_instagram(evt, url_tup)

        for url_tup in reddit_pattern.findall(evt.content.body):
            await evt.mark_read()
            if self.config["reddit.enabled"]:
                await self.handle_reddit(evt, url_tup)

    async def get_youtube_video_id(self, url):
        if "youtu.be" in url:
            video_id = url.split("youtu.be/")[1]
        else:
            video_id = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)['v'][0]
        return video_id.split("?", 1)[0]

    async def generate_youtube_query_url(self, url):
        params = {"format": "json", "url": url}
        query_url = "https://www.youtube.com/oembed"
        query_string = urllib.parse.urlencode(params)
        return f"{query_url}?{query_string}"

    async def handle_youtube(self, evt, url_tup):
        url = ''.join(url_tup)
        video_id = await self.get_youtube_video_id(url)

        query_url = await self.generate_youtube_query_url(url)
        response = await self.http.get(query_url)
        if response.status != 200:
            self.log.warning(f"Unexpected status fetching video title {query_url}: {response.status}")
            return

        response_text = await response.read()
        data = json.loads(response_text.decode())

        if self.config["youtube.info"]:
            await evt.reply(data['title'])

        if self.config["youtube.thumbnail"]:
            thumbnail_link = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            response = await self.http.get(thumbnail_link)
            if response.status != 200:
                self.log.warning(f"Unexpected status fetching image {thumbnail_link}: {response.status}")
                return
            thumbnail = await response.read()
            filename = f"{video_id}.jpg"
            uri = await self.client.upload_media(thumbnail, mime_type='image/jpeg', filename=filename)
            await self.client.send_image(evt.room_id, url=uri, file_name=filename, info=ImageInfo(mimetype='image/jpeg'))

    async def handle_instagram(self, evt, url_tup):
        L = instaloader.Instaloader()
        shortcode = url_tup[5]
        self.log.warning(shortcode)
        post = instaloader.Post.from_shortcode(L.context, shortcode)

        if self.config["instagram.info"]:
            await evt.reply(TextMessageEventContent(msgtype=MessageType.TEXT, format=Format.HTML, formatted_body=f"""<p>Username: {post.owner_username}<br>Caption: {post.caption}<br>Hashtags: {post.caption_hashtags}<br>Mentions: {post.caption_mentions}<br>Likes: {post.likes}<br>Comments: {post.comments}</p>"""))

        if (post.is_video and self.config["instagram.thumbnail"]) or (not post.is_video and self.config["instagram.image"]):
            response = await self.http.get(post.url)
            if response.status != 200:
                self.log.warning(f"Unexpected status fetching instagram image {post.url}: {response.status}")
                return

            media = await response.read()
            mime_type = 'image/jpeg'
            file_extension = ".jpg"
            file_name = shortcode + file_extension
            uri = await self.client.upload_media(media, mime_type=mime_type, filename=file_name)
            self.log.warning(f"{mime_type} {file_name}")
            await self.client.send_image(evt.room_id, url=uri, file_name=file_name, info=ImageInfo(mimetype='image/jpeg'))

        if post.is_video and self.config["instagram.video"]:
            response = await self.http.get(post.video_url)
            if response.status != 200:
                self.log.warning(f"Unexpected status fetching instagram video {post.video_url}: {response.status}")
                return

            media = await response.read()
            mime_type = 'video/mp4'
            file_extension = ".mp4"
            file_name = shortcode + file_extension
            uri = await self.client.upload_media(media, mime_type=mime_type, filename=file_name)
            await self.client.send_file(evt.room_id, url=uri, info=BaseFileInfo(mimetype=mime_type, size=len(media)), file_name=file_name, file_type=MessageType.VIDEO)

    async def handle_reddit(self, evt, url_tup):
        url = ''.join(url_tup).split('?')[0]
        query_url = quote(url).replace('%3A', ':') + ".json" + "?limit=1"
        headers = {'User-Agent': 'ggogel/SocialMediaDownloadMaubot'}
        response = await self.http.request('GET', query_url, headers=headers)

        if response.status != 200:
            self.log.warning(f"Unexpected status fetching reddit listing {query_url}: {response.status}")
            return

        response_text = await response.read()
        data = json.loads(response_text.decode())
        post_data = data[0]['data']['children'][0]['data']
        sub, title, name = post_data['subreddit_name_prefixed'], post_data['title'], post_data['name']

        if self.config["reddit.info"]:
            await evt.reply(TextMessageEventContent(msgtype=MessageType.TEXT, format=Format.HTML, body=f"{sub}: {title}", formatted_body=f"""<p><b>{sub}: {title}</b></p>"""))

        if 'url_overridden_by_dest' in post_data:
            media_url = post_data['url_overridden_by_dest']
            mime_type = mimetypes.guess_type(media_url)[0]

            if mime_type is None:
                if 'reddit_video' in post_data['secure_media']:
                    fallback_url = post_data['secure_media']['reddit_video']['fallback_url']
                else:
                    fallback_url = post_data['preview']['reddit_video_preview']['fallback_url']
                media_url = fallback_url.split('?')[0]
                mime_type = mimetypes.guess_type(media_url)[0]

            file_extension = mimetypes.guess_extension(mime_type)
            file_name = name + file_extension

            if "image" in mime_type and self.config["reddit.image"]:
                response = await self.http.get(media_url)

                if response.status != 200:
                    self.log.warning(f"Unexpected status fetching media {media_url}: {response.status}")
                    return

                media = await response.read()
                uri = await self.client.upload_media(media, mime_type=mime_type, filename=file_name)
                await self.client.send_image(evt.room_id, url=uri, file_name=file_name, info=ImageInfo(mimetype='image/jpeg'))

            elif "video" in mime_type and self.config["reddit.video"]:
                audio_url = media_url.replace("DASH_720", "DASH_audio")
                download_url = f"https://sd.rapidsave.com/download.php?permalink={url}&video_url={media_url}?source=fallback&audio_url={audio_url}?source=fallback"
                response = await self.http.get(download_url)

                if response.status != 200:
                    self.log.warning(f"Unexpected status fetching media {download_url}: {response.status}")
                    return

                media = await response.read()
                uri = await self.client.upload_media(media, mime_type=mime_type, filename=file_name)
                await self.client.send_file(evt.room_id, url=uri, info=BaseFileInfo(mimetype=mime_type, size=len(media)), file_name=file_name, file_type=MessageType.VIDEO)

            elif self.config["reddit.image"] or self.config["reddit.video"]:
                self.log.warning(f"Unknown media type {query_url}: {mime_type}")
                return