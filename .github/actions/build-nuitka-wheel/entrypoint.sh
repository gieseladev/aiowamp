#!/usr/bin/env bash

cd "$GITHUB_WORKSPACE" || exit 1
pipenv run build_nuitka --dist-dir linx_dist
auditwheel repair linux_dist/*.whl --wheel-dir dist/