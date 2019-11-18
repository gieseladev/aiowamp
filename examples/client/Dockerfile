FROM python:3.7

# prepare nuitka
RUN pip install nuitka pipenv

WORKDIR /aiowamp

COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock
RUN pipenv install --system --deploy --dev

COPY aiowamp aiowamp

RUN python -m nuitka \
    --warn-unusual-code \
    --show-scons --show-progress --show-modules \
    --lto \
    --module aiowamp --include-package aiowamp --include-package aiobservable

RUN rm --recursive aiowamp

COPY examples/client/app.py app.py

# using shell form to have variable substitution
ENTRYPOINT python app.py --realm ${WAMP_REALM} ${WAMP_URI}
#ENTRYPOINT bash