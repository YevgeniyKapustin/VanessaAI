FROM python:3.11.3

WORKDIR /app/

RUN pip install 'poetry==1.0.0'
COPY poetry.lock pyproject.toml /app/

RUN poetry config virtualenvs.create false &&  \
    poetry install --no-interaction --no-ansi --no-dev

COPY . .

CMD python src/main.py
