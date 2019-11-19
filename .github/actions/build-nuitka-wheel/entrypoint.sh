#!/usr/bin/env bash
set -e

pipenv install --deploy --dev
pipenv run -- build_nuitka --dist-dir linux_dist
auditwheel repair linux_dist/*.whl --wheel-dir dist/

ls -R dist
