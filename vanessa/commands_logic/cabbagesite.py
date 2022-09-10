import requests


class Cabbagesite:

    @staticmethod
    def get_players_winrate():
        players_data = requests.get('https://kapusta.eu.pythonanywhere.com/api/players_stats').json()
        return '<br>'.join([f"{player['name']}: {player['winrate']}%" for player in players_data])

    @staticmethod
    def get_fractions_winrate():
        fractions_data = requests.get('https://kapusta.eu.pythonanywhere.com/fractions_stats').json()
        return '<br>'.join([f"{fraction['name']}: {fraction['winrate']}%" for fraction in fractions_data])
