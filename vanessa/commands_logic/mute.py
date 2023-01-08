import json
from vk_api import ApiError
from vanessa.actions import send_text, send_file
from vanessa.connection_to_vk.connection import vk
from vanessa.default_commands.links import img_no_power


class Mute:
    """class for working with mutes and unmutes"""

    def shut_up(self, chat_id: int, msg: str, peer_id: int, event):
        """allows conversation admins to mute a non-admin conversation participant"""
        members = self.__members_search(peer_id, chat_id)
        if self.__member_status_check(event, members):
            victim_id = self.__victim_id_search(msg, event)
            if victim_id == 'ub2121387' or victim_id == '-212138773':  # vanessa can't shut up
                return send_text(chat_id, 'я бы сказала, что это несколько возмутительно')
            found = False
            for member in members['items']:
                try:
                    if str(member['member_id']) == victim_id:
                        found = True
                        if member['is_admin']:
                            return send_file(chat_id, img_no_power)
                        break
                except KeyError:
                    pass
            if not found:
                return send_text(chat_id, 'жертвы нету в этой беседе')
            elif victim_id in self.get_shut_up_people_list():
                send_text(chat_id, f'наш [id{victim_id}|друг] уже отдыхает')
                return f'наш [id{victim_id}|друг] уже отдыхает'
            else:
                self.__supplement_shut_up_people_list(victim_id)
                send_text(chat_id, f'наш [id{victim_id}|друг] пока что отдохнет')
                return f'наш [id{victim_id}|друг] пока что отдохнет'
        else:
            return send_file(chat_id, img_no_power)

    def redemption(self, chat_id, msg, event, peer_id):
        """allows an admin to remove a member's mute"""
        members = self.__members_search(peer_id, chat_id)
        shut_up_people = self.get_shut_up_people_list()
        if self.__member_status_check(event, members):
            victim_id = self.__victim_id_search(msg, event)
            if victim_id in shut_up_people:
                self.__remove_from_shut_up_people_list(victim_id)
                send_text(chat_id, f'[id{victim_id}|друг], ты свободен, наслаждайся жизнью и хорошего тебе дня')
                return f'[id{victim_id}|друг], ты свободен, наслаждайся жизнью и хорошего тебе дня'
            else:
                send_text(chat_id, 'да не то чтобы он сильно замучен')
                return 'да не то чтобы он сильно замучен'
        else:
            send_file(chat_id, img_no_power)

    @staticmethod
    def get_shut_up_people_list():
        with open('shut_up_people.json', 'r') as f:
            shut_up_people = json.load(f)
        return shut_up_people

    def __supplement_shut_up_people_list(self, victim_id):
        shut_up_people = self.get_shut_up_people_list()
        shut_up_people.append(victim_id)
        return self.__dump_shut_up_people(shut_up_people)

    def __remove_from_shut_up_people_list(self, victim_id):
        shut_up_people = self.get_shut_up_people_list()
        shut_up_people.remove(victim_id)
        return self.__dump_shut_up_people(shut_up_people)

    def __victim_id_search(self, msg, event):
        if 'раз' in msg:
            msg = msg.replace('раз', '')
        msg = msg.replace('мут', '')
        if msg == '' and 'reply_message' in event.object.message:
            victim_id = str(event.object.message['reply_message']['from_id'])
        else:
            victim_id = self.__id_definition_by_mention(msg)
        return victim_id

    @staticmethod
    def __dump_shut_up_people(shut_up_people):
        with open('shut_up_people.json', 'w') as f:
            json.dump(shut_up_people, f, indent=4)
        return shut_up_people

    @staticmethod
    def __member_status_check(event, members) -> bool:
        """returns true if the requester is an administrator"""
        from_admin = False
        member_id = event.object.message['from_id']
        for member in members['items']:
            try:
                if member['member_id'] == member_id and member['is_admin']:
                    from_admin = True
                    return from_admin
            except KeyError:
                pass
        return from_admin

    @staticmethod
    def __members_search(peer_id, chat_id):
        try:
            members = vk.messages.getConversationMembers(peer_id=peer_id)
            return members
        except ApiError:
            send_text(chat_id, 'ну знаете, могли бы админку чтоле дать для начала')
            return

    @staticmethod
    def __id_definition_by_mention(mention):
        return mention.strip()[3:12]  # cut id from mention
