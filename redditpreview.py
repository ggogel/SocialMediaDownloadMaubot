import re, json, mimetypes
from typing import Type
from urllib.request import Request, urlopen
from urllib.parse import quote, urlparse
from mautrix.types import ImageInfo, EventType, MessageType
from mautrix.types.event.message import BaseFileInfo, Format, TextMessageEventContent
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import event

class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("appid")
        helper.copy("source")
        helper.copy("response_type")


reddit_pattern = re.compile(r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:reddit\.com|redd.it))(\/r\/.*\/comments\/.*)(\/)?$")

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
        for url_tup in reddit_pattern.findall(evt.content.body):
            
            await evt.mark_read()
            url = ''.join(url_tup).split('?')[0]
            query_url = quote(url).replace('%3A', ':') + ".json" + "?limit=1"
            headers = {
                'User-Agent': 'ggogel/RedditPreviewMaubot'
            }
            req = Request(query_url, headers=headers)
            response = urlopen(req)

            if response.status != 200:
                self.log.warning(f"Unexpected status fetching reddit listing {query_url}: {response.status}")
                return None
            
            response_text = response.read()
            data = json.loads(response_text.decode())

            sub = data[0]['data']['children'][0]['data']['subreddit_name_prefixed']
            title = data[0]['data']['children'][0]['data']['title']
            name = data[0]['data']['children'][0]['data']['name']
            
            await evt.respond(TextMessageEventContent(msgtype=MessageType.TEXT, format=Format.HTML, body=f"{sub}: {title}", formatted_body=f"""<p><a href="{url}"><b>{sub}: {title}</b></a></p>"""))
            
            # We assume that when this condition is true, the post is either an image or video
            if 'url_overridden_by_dest' in  data[0]['data']['children'][0]['data']:
                media_url = data[0]['data']['children'][0]['data']['url_overridden_by_dest']
                mime_type = mimetypes.guess_type(media_url)[0]

                # Use video preview fallback URL if original URL has non-standard or no file extension. This is typically the case for "gifs" on imgur and gfycat, which are actually videos.
                if mime_type == None:
                    media_url = data[0]['data']['children'][0]['data']['preview']['reddit_video_preview']['fallback_url']
                    mime_type = mimetypes.guess_type(media_url)[0]

                response = await self.http.get(media_url)

                if response.status != 200:
                    self.log.warning(f"Unexpected status fetching media {media_url}: {response.status}")
                    return None

                file_extension = mimetypes.guess_extension(mime_type)
                file_name = name + file_extension
                media = await response.read()

                if "image" in mime_type:
                    uri = await self.client.upload_media(media, mime_type=mime_type, filename=file_name)
                    await self.client.send_image(evt.room_id, url=uri, file_name=file_name, info=ImageInfo(mimetype='image/jpg'))
                elif "video" in mime_type:
                    uri = await self.client.upload_media(media, mime_type=mime_type, filename=file_name)
                    await self.client.send_file(evt.room_id, url=uri, info=BaseFileInfo(mimetype=mime_type, size=len(media)), file_name=file_name,file_type=MessageType.VIDEO)
                else:
                    self.log.warning(f"Unknown media type {query_url}: {mime_type}")
                    return None