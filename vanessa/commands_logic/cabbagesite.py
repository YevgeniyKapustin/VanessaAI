"""Module to represent the class "Cabbagesite" for working with the site
https://kapusta.eu.pythonanywhere.com
"""
import requests


def get_players_winrate():
    """Returns html string with winrate of players"""
    players_data = requests.get(
        'https://kapusta.eu.pythonanywhere.com/api/players_stats'
    ).json()
    return '<br>'.join([f"{player['name']}: {player['winrate']}%"
                        for player in players_data])


def get_fractions_winrate():
    """Returns html string with winrate of fractions"""
    fractions_data = requests.get(
        'https://kapusta.eu.pythonanywhere.com/api/fractions_stats'
    ).json()
    return '<br>'.join([f"{fraction['name']}: {fraction['winrate']}%"
                        for fraction in fractions_data])
