import os
from PIL import Image, ImageDraw, ImageFont
from vanessa.connection_to_vk.connection import upload, vk_admin
from pickle import dump, load
from vanessas_config import get_vanessas_config
config = get_vanessas_config()


class VanessaAvatar:
    """a class for changing the avatar in the community of vanessa every time a new instance of vanessa is created"""
    def __init__(self):
        self.version, self.serial_number = self.__init_sn_and_version()
        if not config.get("settings", "debug"):
            self.font = ImageFont.truetype("arial.ttf", 25)
            self.line_height = sum(self.font.getmetrics())
            self.upload = upload

    def refresh_avatar(self):
        """replaces the old avatar with a new one and cleaning up all traces"""
        if not config.get("settings", "debug"):
            self.__delete_avatar()
            self.__post_avatar()
        else:
            raise Exception('Debug mode is true')

    @staticmethod
    def __init_sn_and_version() -> tuple:
        try:
            with open('serial_number.data', 'rb') as f:
                serial_number = load(f)
        except FileNotFoundError:
            serial_number = 0
        with open('serial_number.data', 'wb') as f:
            serial_number += 1
            dump(serial_number, f)
        return f"V.SN{serial_number}", serial_number

    def __create_avatar(self):
        fontimage = self.__drawing_fontimage()
        image = Image.open("vanessas_avatar/exemplar.jpg")
        image.paste(fontimage, box=(330, 440), mask=fontimage)
        image.save(f'vanessas_avatar/vanessa_avatar{self.serial_number}.jpg')

    def __drawing_fontimage(self):
        fontimage = Image.new('L', (self.font.getsize(self.version)[0], self.line_height))
        ImageDraw.Draw(fontimage).text((0, 0), self.version, fill=255, font=self.font)
        return fontimage.rotate(25, resample=Image.BICUBIC, expand=True)

    def __post_avatar(self):
        self.__create_avatar()
        upload.photo_profile(f'vanessas_avatar/vanessa_avatar{self.serial_number}.jpg', owner_id=-212138773)
        last_post = vk_admin.wall.get(owner_id=-212138773, count=1)
        if last_post['items']:
            vk_admin.wall.delete(owner_id=-212138773, post_id=last_post['items'][0]['id'])

    def __delete_avatar(self):
        try:
            os.remove(f'vanessas_avatar/vanessa_avatar{self.serial_number - 1}.jpg')
            last_avatar = vk_admin.photos.get(owner_id=-212138773, album_id='profile', rev=1, count=1)
            if last_avatar['items']:
                vk_admin.photos.delete(owner_id=-212138773, photo_id=last_avatar['items'][0]['id'])
        except FileNotFoundError:
            return
