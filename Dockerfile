FROM python:3.7

# prepare nuitka
RUN pip install nuitka

# prepare aiowamp
RUN pip install pipenv

WORKDIR /aiowamp

COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock
RUN pipenv install --system --deploy --dev

COPY aiowamp aiowamp

RUN python -m nuitka \
    --verbose \
    --lto \
    --module aiowamp --include-package=aiowamp

RUN rm --recursive aiowamp aiowamp.build

COPY examples/client/app.py app.py

# using shell form to have variable substitution
ENTRYPOINT python app.py --realm ${WAMP_REALM} ${WAMP_URI}
