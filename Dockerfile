FROM python:3.11.3

WORKDIR /bot/

RUN pip install 'poetry==1.0.0'
COPY poetry.lock pyproject.toml /bot/

RUN poetry config virtualenvs.create false &&  \
    poetry install --no-interaction --no-ansi --no-dev

COPY . .

CMD python run.py
