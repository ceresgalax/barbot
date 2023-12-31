#!/usr/bin/env python3
import argparse
import os
import shutil
import sys

argparser = argparse.ArgumentParser()
argparser.add_argument('--skip-libs', action='store_true')
args = argparser.parse_args()
include_libs = not args.skip_libs

os.chdir(os.path.normpath(os.path.join(__file__, '..')))

if include_libs:
    os.system('pip install -r requirements.txt --target ./build/libs/python --upgrade --only-binary=:all: --platform manylinux2014_aarch64')

os.makedirs('build/lambda_stage', exist_ok=True)
shutil.copytree('barbot', 'build/lambda_stage/barbot', dirs_exist_ok=True)
