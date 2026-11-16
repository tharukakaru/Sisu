#!/usr/bin/env bash
# Web server, realtime, workers and scheduler inside the bench container. Re-run after Python changes.
cd /home/frappe/workspace/frappe-bench/sites || exit 1
# Imported site backups can contain pause_scheduler=1. Repair only the local campus.
../env/bin/python /home/frappe/deploy/configure_scheduler.py || exit 1
pkill -f '[b]ench_helper frappe serve'
pkill -f '[b]ench_helper frappe worker'
pkill -f '[b]ench_helper frappe schedule'
pkill -f '[s]ocketio.js'
sleep 1
cd /home/frappe/workspace/frappe-bench/sites || exit 1
# Local Nginx supplies the original scheme/host, including the HTTPS card-test proxy.
nohup ../env/bin/python -m frappe.utils.bench_helper frappe serve --host 0.0.0.0 --port 8000 --noreload --proxy >/tmp/serve.log 2>&1 &
disown
nohup node ../apps/frappe/socketio.js >/tmp/socketio.log 2>&1 &
disown
nohup ../env/bin/python -m frappe.utils.bench_helper frappe worker --queue short,default,long >/tmp/worker.log 2>&1 &
disown
# Keep time-sensitive reminders moving while the normal worker handles slow jobs.
nohup ../env/bin/python -m frappe.utils.bench_helper frappe worker --queue short >/tmp/short-worker.log 2>&1 &
disown
nohup ../env/bin/python -m frappe.utils.bench_helper frappe schedule >/tmp/scheduler.log 2>&1 &
disown
echo "Bench started (sites on ports 5400-5403)"
