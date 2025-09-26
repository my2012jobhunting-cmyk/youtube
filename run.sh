#!/bin/bash
set -ex
cd `dirname $0`

# 可以类似官方示例代码，加入 output 文件夹

export RUNTIME_LOGDIR=/opt/tiger/toutiao/log
export PYTHONPATH=./site-packages


exec python3 ./main.py