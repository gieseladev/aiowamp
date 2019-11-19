#!/usr/bin/env bash
set -e

PATH="/opt/python/$1/bin:${PATH}"

pip install --upgrade pipenv
pipenv install --deploy --dev
pipenv run -- build_nuitka --dist-dir linux_dist
auditwheel repair linux_dist/*.whl --wheel-dir dist/
