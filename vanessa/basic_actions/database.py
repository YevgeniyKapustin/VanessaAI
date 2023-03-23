import sqlite3 as sql
from sqlite3 import OperationalError


class DataBase(object):

    def __init__(self):
        with sql.connect('vanessa.db') as connect:
            self.cursor = connect.cursor()
            self.__tables_validation()

    def set_command(self, _type, strategy, request, response):
        self.cursor.execute(f'''INSERT INTO commands
        (type, strategy, request, response)
        VALUES ("{_type}", "{strategy}", "{request}", "{response}")''')
        return self.cursor.fetchone()

    def set_shut_up_person(self, user_id):
        self.cursor.execute(f'''INSERT INTO commands(user_id) 
        VALUES ("{user_id}")''')
        return self.cursor.fetchone()

    def update_command(self, _type, strategy, request, response):
        self.cursor.execute(f'''UPDATE commands SET 
        type = "{_type}", strategy = "{strategy}", response = "{response}"
        WHERE request = "{request}"
        ''')
        return self.cursor.fetchone()

    def remove_command(self, request):
        self.cursor.execute(f'''DELETE FROM commands
        WHERE request = "{request}"
        ''')
        return self.cursor.fetchone()

    def remove_from_shut_up_people(self, user_id):
        self.cursor.execute(f'''DELETE FROM shut_up_people
        WHERE user_id = "{user_id}"
        ''')
        return self.cursor.fetchone()

    def get_response(self, request):
        try:
            self.cursor.execute(f'''SELECT response, type FROM commands 
            WHERE request == "{request}" ''')
            return self.cursor.fetchone()
        except OperationalError:
            return None

    def get_all_commands(self, strategy='contextual'):
        self.cursor.execute(f'''SELECT response, type FROM commands 
        WHERE strategy == "{strategy}" ''')
        return self.cursor.fetchall()

    def get_all_commands_data(self):
        self.cursor.execute(f'''SELECT * FROM commands''')
        return self.cursor.fetchall()

    def get_shut_up_person(self, user_id):
        try:
            self.cursor.execute(f'''SELECT user_id FROM shut_up_people 
            WHERE user_id == "{user_id}"''')
            return self.cursor.fetchall()
        except OperationalError:
            return None

    def __tables_validation(self):
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
        type TEXT NOT NULL,
        strategy TEXT NOT NULL,
        request TEXT NOT NULL UNIQUE,
        response TEXT NOT NULL)''')
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS shut_up_people (
        user_id INT NOT NULL UNIQUE)''')
