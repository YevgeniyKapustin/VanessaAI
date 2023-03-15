import sqlite3 as sql
from os import path
from sqlite3 import OperationalError


class DataBase(object):

    def __init__(self):
        new = False
        if not path.isfile('vanessa.db'):
            new = True

        with sql.connect('vanessa.db') as connect:
            self.cursor = connect.cursor()

            if new:
                self.__create_database()

    def add_command(self, command_type, request, response):
        self.cursor.execute(f'''INSERT INTO '{command_type}' (
        request, response VALUES {request}, {response})''')

        return True

    def get_response_and_type(self, request) -> tuple:
        try:
            self.cursor.execute(f'''SELECT response, type FROM 
            commands WHERE request == "{request}" LIMIT 1''')
            return self.cursor.fetchone()
        except OperationalError:
            self.cursor.execute(f'''SELECT response, type FROM 
            contextual_commands WHERE request == "{request}" LIMIT 1''')
            return self.cursor.fetchone()

    def __create_database(self):

        self.cursor.execute('''
        CREATE TABLE commands (
        type TEXT NOT NULL,
        request TEXT NOT NULL,
        response TEXT NOT NULL)''')

        self.cursor.execute('''
        CREATE TABLE contextual_commands (
        type TEXT NOT NULL,
        request TEXT NOT NULL,
        response TEXT NOT NULL)''')

# with sql.connect('vanessa.db') as connect:
#     cursor = connect.cursor()
#     cursor.execute(f'''SELECT response FROM commands WHERE request == "хм"''')
#     result = cursor.fetchone()
