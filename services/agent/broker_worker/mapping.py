from vanessa.contracts.messages import TurnImage, TurnRequest
from vanessa.core.messages import ImageAttachment
from vanessa.core.turn import ChatTurnInput


def _attachment(image: TurnImage) -> ImageAttachment:
    return ImageAttachment(
        data_url=image.data_url,
        mime_type=image.mime_type,
        telegram_file_id=image.telegram_file_id,
    )


def _scene_attachment(source: TurnRequest) -> ImageAttachment | None:
    if source.scene_image is None:
        return None
    return _attachment(source.scene_image)


class TurnMapper:
    def to_turn(self, source: TurnRequest) -> ChatTurnInput:
        return ChatTurnInput(
            telegram_chat_id=source.telegram_chat_id,
            message=source.message,
            sender_telegram_id=source.sender_telegram_id,
            chat_title=source.chat_title,
            channel=source.channel,
            telegram_message_id=source.telegram_message_id,
            correlation_id=source.correlation_id,
            chat_type=source.chat_type,
            sender_username=source.sender_username,
            sender_first_name=source.sender_first_name,
            sender_last_name=source.sender_last_name,
            mentions_bot=source.mentions_bot,
            reply_to_bot=source.reply_to_bot,
            reply_to_other_user=source.reply_to_other_user,
            reply_to_sender_telegram_id=source.reply_to_sender_telegram_id,
            reply_to_message_id=source.reply_to_message_id,
            reply_to_text=source.reply_to_text,
            reply_to_sender_name=source.reply_to_sender_name,
            images=tuple(_attachment(image) for image in source.images),
            scene_image=_scene_attachment(source),
        )
