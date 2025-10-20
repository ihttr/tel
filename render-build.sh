#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. تثبيت مكتبات البايثون
pip install -r requirements.txt

# 2. تثبيت ffmpeg على الخادم
apt-get update && apt-get install -y ffmpeg