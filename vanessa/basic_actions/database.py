import sqlite3 as sql
from os import path
from sqlite3 import OperationalError


class DataBase(object):

    def __init__(self):
        with sql.connect('vanessa.db') as connect:
            self.cursor = connect.cursor()

            if not path.isfile('vanessa.db'):
                self.__create_database()

    def set_command(self, _type, strategy, request, response):
        self.cursor.execute(f'''INSERT INTO 'commands' (
        type, strategy, request, response
        VALUES {_type}, {strategy}, {request}, {response})''')
        return True

    def get_response(self, request):
        try:
            self.cursor.execute(f'''SELECT response, type, strategy FROM 
            commands WHERE request == "{request}"''')
            return self.cursor.fetchone()
        except OperationalError:
            return None

    def __create_database(self):
        self.cursor.execute('''
        CREATE TABLE commands (
        type TEXT NOT NULL,
        strategy TEXT NOT NULL,
        request TEXT NOT NULL UNIQUE,
        response TEXT NOT NULL)''')
