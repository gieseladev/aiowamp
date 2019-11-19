#!/usr/bin/env bash
set -e

ls -R ${pythonLocation}

PATH="${pythonLocation}/bin:${PATH}"

python setup.py bdist_nuitka --dist-dir linux_dist
auditwheel repair linux_dist/*.whl --wheel-dir dist/
