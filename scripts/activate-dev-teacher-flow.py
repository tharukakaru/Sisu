"""Activate Dev's documented teacher flow on the existing public shared campus."""
from pathlib import Path
import os,json,pwd,shutil,subprocess,urllib.request,time
from datetime import datetime,timezone
BENCH=Path('/home/sisu/frappe-bench')
SITE='sisuacademylk.com'
URL='https://www.sisuacademylk.com/api/method/institute_lms.portal_policy.public'
def main():
 if os.geteuid()!=0:raise RuntimeError('Run as root')
 import fcntl
 lock=open('/var/lock/sisu-merged-deployment.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 os.umask(0o077)
 path=BENCH/'sites'/SITE/'site_config.json'
 if path.is_symlink():raise RuntimeError('Unexpected configuration symlink')
 original=path.read_bytes();config=json.loads(original)
 common=json.loads((BENCH/'sites/common_site_config.json').read_text());effective={**common,**config}
 for key in ('il_public_signup_enabled','il_shared_campus_enabled'):
  if effective.get(key)!=1:raise RuntimeError('Required existing public-campus setting is not enabled: '+key+'. Nothing changed.')
 if effective.get('il_control_plane') or effective.get('host_name')!='https://www.sisuacademylk.com':raise RuntimeError('Unexpected target site')
 for name in ('teacher_workspace.py','institute_coverage.py','signup_environment.py'):
  if not (BENCH/'apps/institute_lms/institute_lms'/name).is_file():raise RuntimeError('Required application code missing')
 backup=Path('/home/sisu/.sisu-secrets')/('teacher-flow-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));backup.mkdir(mode=0o700)
 (backup/'site_config.private.json').write_bytes(original)
 user=pwd.getpwnam('sisu')
 def write(data):
  temp=path.with_name('site_config.teacher-flow-tmp.json')
  with temp.open('xb') as f:f.write(data)
  temp.chmod(0o600);os.chown(temp,user.pw_uid,user.pw_gid);os.replace(temp,path)
 def clear():subprocess.run(['sudo','-H','-u','sisu','--','/usr/local/bin/bench','--site',SITE,'clear-cache'],cwd=BENCH,check=True)
 try:
  config.update(il_unified_teacher_signup=1,il_institute_teacher_coverage=1)
  write(json.dumps(config,indent=2).encode());clear()
  for attempt in range(6):
   try:
    with urllib.request.urlopen(URL,timeout=20) as r:policy=json.load(r)['message']
    if policy.get('unified_teacher_signup') is not True:raise RuntimeError('Live API still reports legacy teacher signup')
    if not policy.get('self_signup_enabled'):raise RuntimeError('Public signup is not available')
    break
   except Exception:
    if attempt==5:raise
    time.sleep(3)
 except Exception:
  write(original);clear();print('Previous site configuration restored. Backup:',backup);raise
 print('ACTIVATED: unified teacher signup and institute-workspace subscription coverage.')
 print('VERIFIED: public API reports unified_teacher_signup=true. Backup:',backup)
 print('No accounts approved, memberships changed, trial dates reset or payments submitted.')
if __name__=='__main__':main()
