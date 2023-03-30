import sqlite3 as sql
from sqlite3 import OperationalError, IntegrityError


class DataBase(object):
    """ORM for Vanessa.

    :Methods:
    set_command(cmd)
    update_command(cmd)
    remove_command(request)
    get_response_and_type(request)
    get_all_commands_for_strategy(strategy)
    get_all_commands_data()

    set_shut_up_person(user_id)
    get_all_shut_up_person()
    get_shut_up_person(user_id)
    remove_from_shut_up_people(user_id)
    """

    __instance = None

    def __new__(cls, *args, **kwargs):
        if not cls.__instance:
            cls.__instance = super(cls, cls).__new__(cls)
        return cls.__instance

    def __init__(self):
        self.__tables_validation()

    @staticmethod
    def open_db(func):
        def wrapper(*args, **kwargs):
            try:
                with sql.connect('vanessa.db') as connect:
                    cursor = connect.cursor()
                    return func(*args, **kwargs, cursor=cursor)
            except (IntegrityError, OperationalError):
                return False

        return wrapper

    @staticmethod
    @open_db
    def set_command(cmd, cursor) -> bool:
        """Add command to database.

        :param cmd: command object
        :param cursor: connection to db(taken from the decorator)
        """
        cursor.execute(f'''INSERT INTO commands(type, strategy, 
        request, response) VALUES ("{cmd.type}", "{cmd.strategy}", 
        "{cmd.request}", "{cmd.response}")''')
        return True

    @staticmethod
    @open_db
    def set_shut_up_person(user_id, cursor) -> bool:
        """Add person to database of muted.

        :param user_id: user ID
        :param cursor: connection to db(taken from the decorator)
        """
        cursor.execute(f'''INSERT INTO shut_up_people(user_id) 
        VALUES ("{user_id}")''')
        return True

    @staticmethod
    @open_db
    def update_command(cmd, cursor):
        """Update command to database.

        :param cmd: command object
        :param cursor: connection to db(taken from the decorator)
        """
        cursor.execute(f'''UPDATE commands SET type = "{cmd.type}", 
        strategy = "{cmd.strategy}", response = "{cmd.response}"
        WHERE request = "{cmd.request}"
        ''')
        return True

    @staticmethod
    @open_db
    def remove_command(request, cursor):
        """Remove command from database.

        :param request: a request made to invoke a command
        :param cursor: connection to db(taken from the decorator)
        """
        cursor.execute(f'''DELETE FROM commands
        WHERE request = "{request}"
        ''')
        return True

    @staticmethod
    @open_db
    def remove_from_shut_up_people(user_id, cursor):
        """Remove person from database of muted.

        :param user_id: user ID
        :param cursor: connection to db(taken from the decorator)
        """
        cursor.execute(f'''DELETE FROM shut_up_people
        WHERE user_id = {user_id}
        ''')
        return True

    @staticmethod
    @open_db
    def get_response_and_type(request, cursor):
        """Return command from database or None.

        :param request: a request made to invoke a command
        :param cursor: connection to db(taken from the decorator)
        """
        cursor.execute(f'''SELECT response, type FROM commands 
        WHERE request == "{request}" ''')
        return cursor.fetchone()

    @staticmethod
    @open_db
    def get_all_commands_for_strategy(strategy, cursor):
        """Return all commands from database.

        :param cursor: connection to db(taken from the decorator)
        :param strategy: 'contextual' or 'normal'
        """
        cursor.execute(f'''SELECT request, type, response
        FROM commands WHERE strategy == "{strategy}" ''')
        return cursor.fetchall()

    @staticmethod
    @open_db
    def get_all_commands_data(cursor):
        """Return all commands with full data about them.

        :param cursor: connection to db(taken from the decorator)
        """
        cursor.execute(f'''SELECT * FROM commands ORDER BY request''')
        return cursor.fetchall()

    @staticmethod
    @open_db
    def get_shut_up_person(user_id, cursor):
        """Return person data.

        :param user_id: user ID
        :param cursor: connection to db(taken from the decorator)
        """
        cursor.execute(f'''SELECT * FROM shut_up_people 
        WHERE user_id == "{user_id}"''')
        return cursor.fetchone()

    @staticmethod
    @open_db
    def get_all_shut_up_person(cursor):
        """Return all shut_up_person with full data about them.

        :param cursor: connection to db(taken from the decorator)
        """
        cursor.execute(f'''SELECT * FROM shut_up_people''')
        return cursor.fetchall()

    @staticmethod
    @open_db
    def __tables_validation(cursor):
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
        type TEXT NOT NULL,
        strategy TEXT NOT NULL,
        request TEXT NOT NULL UNIQUE,
        response TEXT NOT NULL)''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS shut_up_people (
        user_id INT NOT NULL UNIQUE)''')
