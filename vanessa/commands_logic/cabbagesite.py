"""Module to represent the class "Cabbagesite" for working with the site
https://kapusta.eu.pythonanywhere.com
"""
import requests


def get_winrate(request: str = 'players') -> str:
    """Makes a request to the site api and returns html for vk.
    :param str request: 'players' or 'fractions'
    :returns: html string, by default returns players
    """
    request = f'https://kapusta.eu.pythonanywhere.com/api/{request}_stats'
    data = requests.get(request).json()
    lst = [f"{item['name']}: {item['winrate']}%" for item in data]
    return '<br>'.join(lst)
