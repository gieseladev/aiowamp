#!/usr/bin/env bash
set -e

python setup.py bdist_nuitka --dist-dir linux_dist
auditwheel repair linux_dist/*.whl --wheel-dir dist/
