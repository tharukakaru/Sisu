"""Enable the local campus scheduler without touching production configuration."""
import json
from pathlib import Path
from urllib.parse import urlsplit

import frappe

SITES = Path('/home/frappe/workspace/frappe-bench/sites')
SITE = 'sisuacademylk.com'


def configure():
    # This file belongs to the local Docker launcher, never a production migration.
    if not Path('/.dockerenv').exists() or not Path('/home/frappe/deploy/dev-serve.sh').exists():
        raise RuntimeError('Run only inside the SISU local Docker bench')
    path = SITES / SITE / 'site_config.json'
    config = json.loads(path.read_text())
    if urlsplit(config.get('host_name', '')).hostname not in ('127.0.0.1', 'localhost', 'checkout.localhost'):
        raise RuntimeError('Refusing to change a non-local site')
    config.update(pause_scheduler=0, disable_scheduler=0)
    path.write_text(json.dumps(config, indent=2) + '\n')
    common_path = SITES / 'common_site_config.json'
    common = json.loads(common_path.read_text())
    common['scheduler_tick_interval'] = 15
    common_path.write_text(json.dumps(common, indent=2) + '\n')
    frappe.init(site=SITE, sites_path=str(SITES))
    frappe.connect()
    try:
        frappe.db.set_single_value('System Settings', 'enable_scheduler', 1)
        from frappe.core.doctype.scheduled_job_type.scheduled_job_type import sync_jobs
        sync_jobs()
        job_name = frappe.db.get_value('Scheduled Job Type',
            {'method': 'institute_lms.session_reminders.dispatch'}, 'name')
        if not job_name:
            raise RuntimeError('Class reminder scheduler hook is missing')
        job = frappe.get_doc('Scheduled Job Type', job_name)
        job.queue = 'short'
        job.stopped = 0
        job.create_log = 1
        job.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.clear_cache()
        print('Local campus scheduler enabled; 15-second tick; scheduled jobs synced.')
    finally:
        frappe.destroy()


if __name__ == '__main__':
    configure()
