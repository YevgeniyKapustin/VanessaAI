from vk_api import ApiError

from basic_actions.actions import send_text, send_file
from basic_actions.database import DataBase
from prepare.connection import Connection


class Mute(object):
    """Class for handling the request associated with the mute.

        :param event: object with information about the request

    Methods:
    shut_up()
    redemption()
    """

    def __init__(self, event):
        self.chat_id = event.chat_id
        self.text = event.msg.text
        self.peer_id = event.msg.peer_id
        self.vk = Connection().vk
        self.db = DataBase()
        self.event = event
        self.msg = event.msg

    def shut_up(self) -> str:
        """Added to mutes a non-admin conversation participant.

        Sends a command report.
        """
        members = self._members_search()

        if self._member_status_check(members):
            victim_id = self._victim_id_search()
            # vanessa can't shut up
            if victim_id == 'ub2121387' or victim_id == '-212138773':
                return self._send_response('mute_for_bot')

            found = self._founding_member(members, victim_id)

            if not found:
                if not found == bool:
                    return self._send_response('no_power')
                return self._send_response('no_found_victim')

            elif victim_id == self.db.get_shut_up_person(victim_id):
                return self._send_response('already_muted', victim_id)

            else:
                self.db.set_shut_up_person(victim_id)
                return self._send_response('muted', victim_id)

        else:
            return self._send_response('no_power')

    def redemption(self) -> str:
        """Allow an admin to remove a member's mute.

        Sends a command report.
        """
        members = self._members_search()

        if self._member_status_check(members):
            victim_id = self._victim_id_search()
            if int(victim_id) == self.db.get_shut_up_person(victim_id)[0]:
                self.db.remove_from_shut_up_people(victim_id)
                return self._send_response('redemption')
            else:
                return self._send_response('already_unmuted')
        else:
            return self._send_response('no_power')

    def _victim_id_search(self) -> str:
        text = self.text
        if 'раз' in text:
            text = text.replace('раз', '')
        text = text.replace('мут', '')
        if text == '' and self.msg.reply_message:
            victim_id = self.msg.reply_message['from_id']
        else:
            victim_id = self._id_definition_by_mention(text)

        return str(victim_id)

    def _member_status_check(self, members) -> bool:
        """Return true if the requester is an administrator."""
        from_admin = False
        member_id = self.msg.from_id

        for member in members['items']:
            try:
                if member['member_id'] == member_id and member['is_admin']:
                    from_admin = True
                    return from_admin
            except KeyError:
                pass

        return from_admin

    def _members_search(self):
        """Return object members or send about error."""
        try:
            return self.vk.messages.getConversationMembers(
                peer_id=self.peer_id
            )
        except ApiError:
            return self._send_response('no_admin')

    def _send_response(self, option: str, victim_id: str = '0') -> str:
        """Report status of commands.

        For the already_muted, muted, redemption, must be passed victim_id.
        Sends text except in the case of no_power.
        Options: mute_for_bot, no_found_victim, already_unmuted, already_muted,
        muted, redemption, no_power, no_admin.

        :param option: a string specifying the response choice
        :param victim_id: vk id the victim of mute
        """
        options = {
            'mute_for_bot': 'я бы сказала, что это несколько возмутительно',
            'no_found_victim': 'жертвы нету в этой беседе',
            'already_unmuted': 'да не то чтобы он сильно замучен',
            'already_muted': f'наш [id{victim_id}|друг] уже отдыхает',
            'muted': f'наш [id{victim_id}|друг] пока что отдохнет',
            'redemption': f'[id{victim_id}|друг], ты свободен, наслаждайся '
                          'жизнью и хорошего тебе дня',
            'no_power': 'photo-212138773_457239033',
            'no_admin': 'ну знаете, могли бы админку чтоле дать для начала',
        }
        if option == 'no_power':
            return send_file(self.chat_id, options[option])
        return send_text(self.chat_id, options[option])

    @staticmethod
    def _id_definition_by_mention(mention):
        """Cut id from mention."""
        return mention.strip()[3:12]

    @staticmethod
    def _founding_member(members, victim_id):
        found = False

        for member in members['items']:
            try:
                if str(member['member_id']) == victim_id:
                    found = True
                    if member['is_admin']:
                        return 'victim_admin'
                    break
            except KeyError:
                pass

        return found
