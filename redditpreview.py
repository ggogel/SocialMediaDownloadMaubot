from ast import parse
from typing import Type
import urllib.parse, re, json
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
            url = ''.join(url_tup)
            query_url = url + ".json"
            response = urllib.request.urlopen(query_url)

            if response.status != 200:
                self.log.warning(f"Unexpected status fetching reddit listing {query_url}: {response.status}")
                return None
            
            response_text = response.read()
            data = json.loads(response_text.decode())

            sub = data[0]['data']['children'][0]['data']['subreddit_name_prefixed']
            title = data[0]['data']['children'][0]['data']['title']
            name = data[0]['data']['children'][0]['data']['name']
            isMedia = data[0]['data']['children'][0]['data']['is_reddit_media_domain']

            await evt.respond(TextMessageEventContent(msgtype=MessageType.TEXT, format=Format.HTML, body=f"{sub}: {title}", formatted_body=f"""<p><a href="{url}"><b>{sub}: {title}</b></a></p>"""))
            
            if (isMedia):
                media_type = data[0]['data']['children'][0]['data']['post_hint']

                if(media_type == "image"):
                    media_url = data[0]['data']['children'][0]['data']['url_overridden_by_dest']

                elif(media_type == "hosted:video"):
                    media_url = data[0]['data']['children'][0]['data']['media']['reddit_video']['fallback_url']

                else:
                    self.log.warning(f"Unknown media type {query_url}: {media_type}")
                    return None
                
                response = await self.http.get(media_url)

                if response.status != 200:
                    self.log.warning(f"Unexpected status fetching media {media_url}: {response.status}")
                    return None

                media = await response.read()

                if(media_type == "image"):
                    filename = name + ".jpg"
                    uri = await self.client.upload_media(media, mime_type='image/jpg', filename=filename)
                    await self.client.send_image(evt.room_id, url=uri, file_name=filename, info=ImageInfo(mimetype='image/jpg'))

                elif(media_type == "hosted:video"):
                    filename = name + ".mp4"
                    uri = await self.client.upload_media(media, mime_type='video/mp4', filename=filename)
                    await self.client.send_file(evt.room_id, url=uri, info=BaseFileInfo(mimetype='video/mp4', size=len(media)), file_name=filename,file_type=MessageType.VIDEO)
