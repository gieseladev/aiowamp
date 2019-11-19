FROM quay.io/pypa/manylinux2010_x86_64

ENV PYBIN "/opt/python/cp38-cp38/bin"
RUN ls "/opt/python/cp38-cp38"
RUN ls PYBIN

ENV PATH "${PYBIN}:${PATH}"

RUN pip install nuitka

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]