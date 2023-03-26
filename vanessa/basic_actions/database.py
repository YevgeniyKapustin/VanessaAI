import sqlite3 as sql
from sqlite3 import OperationalError


class DataBase(object):
    __instance = None

    def __new__(cls, *args, **kwargs):
        if not cls.__instance:
            cls.__instance = super(DataBase, cls).__new__(cls)
        return cls.__instance

    def __init__(self):
        self.__tables_validation()

    @staticmethod
    def set_command(cmd):
        with sql.connect('vanessa.db') as connect:
            cursor = connect.cursor()
            cursor.execute(f'''INSERT INTO commands(type, strategy, 
            request, response) VALUES ("{cmd.type}", "{cmd.strategy}", 
            "{cmd.request}", "{cmd.response}")''')
        return cursor.fetchone()

    @staticmethod
    def set_shut_up_person(user_id):
        with sql.connect('vanessa.db') as connect:
            cursor = connect.cursor()
            cursor.execute(f'''INSERT INTO shut_up_people(user_id) 
            VALUES ("{user_id}")''')
        return cursor.fetchone()

    @staticmethod
    def update_command(cmd):
        with sql.connect('vanessa.db') as connect:
            cursor = connect.cursor()
            cursor.execute(f'''UPDATE commands SET type = "{cmd.type}", 
            strategy = "{cmd.strategy}", response = "{cmd.response}"
            WHERE request = "{cmd.request}"
            ''')
        return cursor.fetchone()

    @staticmethod
    def remove_command(request):
        with sql.connect('vanessa.db') as connect:
            cursor = connect.cursor()
            cursor.execute(f'''DELETE FROM commands
            WHERE request = {request}
            ''')
        return cursor.fetchone()

    @staticmethod
    def remove_from_shut_up_people(user_id):
        with sql.connect('vanessa.db') as connect:
            cursor = connect.cursor()
            cursor.execute(f'''DELETE FROM shut_up_people
            WHERE user_id = {user_id}
            ''')
        return cursor.fetchone()

    @staticmethod
    def get_response_and_type(request):
        try:
            with sql.connect('vanessa.db') as connect:
                cursor = connect.cursor()
                cursor.execute(f'''SELECT response, type FROM commands 
                WHERE request == "{request}" ''')
            return cursor.fetchone()
        except OperationalError:
            return None

    @staticmethod
    def get_all_commands(strategy='contextual'):
        with sql.connect('vanessa.db') as connect:
            cursor = connect.cursor()
            cursor.execute(f'''SELECT request, type, response
            FROM commands WHERE strategy == "{strategy}" ''')
        return cursor.fetchall()

    @staticmethod
    def get_all_commands_data():
        with sql.connect('vanessa.db') as connect:
            cursor = connect.cursor()
            cursor.execute(f'''SELECT * FROM commands''')
        return cursor.fetchall()

    @staticmethod
    def get_shut_up_person(user_id):
        try:
            with sql.connect('vanessa.db') as connect:
                cursor = connect.cursor()
                cursor.execute(f'''SELECT user_id FROM shut_up_people 
                WHERE user_id == "{user_id}"''')
            return cursor.fetchone()
        except OperationalError:
            return None

    @staticmethod
    def get_all_shut_up_person():
        with sql.connect('vanessa.db') as connect:
            cursor = connect.cursor()
            cursor.execute(f'''SELECT user_id FROM shut_up_people''')
        return cursor.fetchall()

    @staticmethod
    def __tables_validation():
        with sql.connect('vanessa.db') as connect:
            cursor = connect.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS commands (
            type TEXT NOT NULL,
            strategy TEXT NOT NULL,
            request TEXT NOT NULL UNIQUE,
            response TEXT NOT NULL)''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS shut_up_people (
            user_id INT NOT NULL UNIQUE)''')
