#!/usr/bin/env bash
set -e

PYBIN="/opt/python/$INPUT_TAG/bin"
if [[ ! -d "$PYBIN" ]]; then
  echo "invalid python tag: $INPUT_TAG"
  exit 1
fi

export PATH="${PYBIN}:${PATH}"

pip install --upgrade pipenv
pipenv install --deploy --dev
pipenv run -- build_nuitka --dist-dir linux_dist
auditwheel repair linux_dist/*.whl --wheel-dir dist/
