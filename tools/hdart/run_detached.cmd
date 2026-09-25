@echo off
rem Detached launcher for the LoRA batch supervisor.
rem
rem Started with Start-Process, this runs as an independent Windows process: it survives
rem closing or restarting the agent session, and the background-task reaper cannot touch it.
rem Arguments live here, in a file, on purpose - PowerShell 5.1 mangles arguments that
rem contain spaces or quotes on the way to an external program (rake R-045).
rem
rem Both logs are APPENDED, never truncated: keep_batch.log holds the restarts,
rem gen_batch2.log holds the run itself.

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d E:\OpenXCom
rem Через очередь видеокарты (tools\gpuq.py): прогон дождётся своей очереди, его вывод -
rem в .gpuq\logs\<номер>.log, а не в keep_batch.log.
py -3 tools\gpuq.py add --name lora-batch -- py -3 tools\hdart\keep_batch.py --lora E:/train/lora/oxcehd/step-2540.safetensors --hours 48 --gap 60 --extra "--max-plan 100000"
