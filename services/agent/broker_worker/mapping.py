from vanessa.core.messages import ImageAttachment
from vanessa.core.turn import ChatTurnInput


class TurnMapper:
    def to_turn(self, source) -> ChatTurnInput:
        return ChatTurnInput(
            telegram_chat_id=source.telegram_chat_id,
            message=source.message,
            sender_telegram_id=source.sender_telegram_id,
            chat_title=source.chat_title,
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
            images=tuple(
                ImageAttachment(
                    data_url=image.data_url,
                    mime_type=image.mime_type,
                    telegram_file_id=image.telegram_file_id,
                )
                for image in source.images
            ),
        )
