#!/bin/sh
. /home/alessio9567/nft_project/venv/bin/activate
export PYTHONPATH=/home/alessio9567/nft_project:$PYTHONPATH
python3.11 -m scripts.import_social_hype
