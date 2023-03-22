import sqlite3 as sql
from sqlite3 import OperationalError


class DataBase(object):

    def __init__(self):
        with sql.connect('vanessa.db') as connect:
            self.cursor = connect.cursor()

            self.__tables_validation()

    def set_command(self, _type, strategy, request, response):
        self.cursor.execute(f'''INSERT INTO commands (
        type, strategy, request, response
        VALUES {_type}, {strategy}, {request}, {response})''')
        return self.cursor.fetchone()

    def get_response(self, request):
        try:
            self.cursor.execute(f'''SELECT response, type FROM commands 
            WHERE request == "{request}"''')
            return self.cursor.fetchone()
        except OperationalError:
            return None

    def get_all_contextual(self):
        self.cursor.execute('''SELECT response, type FROM commands 
        WHERE strategy == "контекстный"''')
        return self.cursor.fetchall()

    def __tables_validation(self):
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
        type TEXT NOT NULL,
        strategy TEXT NOT NULL,
        request TEXT NOT NULL UNIQUE,
        response TEXT NOT NULL)''')
