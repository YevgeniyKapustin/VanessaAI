# [Ванесса](https://vk.com/vanessakapustovna "Группа бота в ВК")
### Хэндлер
Чтобы добавить свою команду боту, вам понадобится зайти в `src/handlers` и 
добавить туда новый модуль, в который вы добавите команду или же использовать 
существующий, при условии, что он подходит по смыслу.

Для написания хэндлера используется следующий синтаксис:

```python
from src.utils.decorators import handle_message
from src.rules.rules import Text
from src.services.events import Event


@handle_message(Text('Текст, на которой ответит ванесса'))
def handler_test_command(event: Event):
    event.text_answer('Можно ответить например таким образом.')
```
В декоратор пробрасываем правило, правило можно написать самому или посмотреть
существующие в `src/rules/rules`.

Сама функция не должна принимать что-то кроме event.<br>
Название обязательно должно начинаться с `handler_`, чтобы контроллер опознал
ее как хэндлер<br>
В теле функции делаем все нужные действия, а сам ответ отправляем через метод
объекта `Event`, например `text_answer` или `attachment_answer`, можете 
попробовать добавить туда свой, если нет нужного.

### Правила

Правила нужны, чтобы понять, что хэндлер сработал и нужно выполнить код в нем.<br>

Ниже будет пример правила, которое срабатывает всегда:
```python
from src.rules.base import BaseRule


class Any(BaseRule):
    def check(self) -> bool:
        return True
```
Главное в правиле это создать класс, наследующийся от `BaseRule` и определить
метод `check`, который вернет `bool`, писать свой `__init__` или что-то еще так же
можно, главное не переопределять метод `set_event`. Пример с пробросом аргумента
в обычном правиле на совпадение текста можно посмотреть ниже:
```python
from src.rules.base import BaseRule


class Text(BaseRule):
    def __init__(self, message: str = None):
        self._user_msg: str = message

    def check(self) -> bool:
        return True if not self._user_msg else self._message == self._user_msg
```
Поля `self._event` и `self._message` всегда есть во всех правилах, первый это объект 
ивента, а второй это сообщение юзера из того-же ивента.

А теперь то, как выглядит хэндлер для такого правила:

```python
from random import choice

from src.utils.constants import zmiys_phrases
from src.rules.rules import Text
from src.services.events import Event
from src.utils.decorators import handle_message


@handle_message(Text('абоба'))
def handler_random_zmiys_phrases(event: Event):
    event.text_answer(f'{choice(zmiys_phrases)}')
```

Здесь мы пробрасываем аргумент в правило, и если оно вернуло `True`, то
отвечаем случайной фразой из `zmiys_phrases`

### Деплой
Вы можете развернуть ванессу у себя, все что вам для этого нужно это положить
в одну с src папку конфигурационный файл, вот его пример:
```dotenv
COMMUNITY_TOKEN=токен от вашего сообщества
ADMIN_TOKEN=токен от вашего юзера
GROUP_ID=айдишник группы
SERVER_URI=URI, с которым вы будете работать
DEBUG=true или false, в зависимости от того что сейчас будете делать
```


### Как внести изменения в репозиторий
Ну, тут ничего уникального нет, можете посмотреть статью на тему:<br>
https://habr.com/ru/articles/125999/

![изображение_2023-01-27_141308807_waifu2x_art_noise1 (1)_20230127112230_Cartoon_x4](https://user-images.githubusercontent.com/106178214/215074764-2a59dbf8-ea81-4ad9-b58b-52ed37507764.png)
