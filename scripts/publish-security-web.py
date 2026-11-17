"""Publish the reviewed marketing snapshot and enable public-campus CAPTCHA."""
from pathlib import Path, PurePosixPath
import hashlib, json, os, pwd, re, shutil, subprocess, tarfile, time, urllib.request
from datetime import datetime,timezone
ARCHIVE=Path('/tmp/sisu-security-marketing.tgz')
DIGEST='692555e966718327912620b341c48f8fd2fc623f57b0cd2397711c7e7bdc4421'
OLD='/var/www/sisu-marketing-releases/main-69031d8-20261114T022408257798Z'
CONFIG=Path('/etc/nginx/conf.d/sisu-main-public.conf')
BENCH=Path('/home/sisu/frappe-bench')
SITE='sisuacademylk.com'
PRIVATE=Path('/root/SISU-reCAPTCHA-HANDOVER.private.txt')
def main():
 if os.geteuid()!=0:raise RuntimeError('Run as root')
 import fcntl
 lock=open('/var/lock/sisu-merged-deployment.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 os.umask(0o077)
 if ARCHIVE.is_symlink() or hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()!=DIGEST:raise RuntimeError('Archive mismatch')
 if PRIVATE.is_symlink() or PRIVATE.stat().st_uid!=0:raise RuntimeError('Private handover must be root-owned')
 PRIVATE.chmod(0o600)
 text=PRIVATE.read_text(encoding='utf-8-sig')
 keys={name:re.findall(r'"'+name+r'"\s*:\s*"([^"\n]+)"',text) for name in ('site_key','secret_key')}
 if any(len(v)!=1 or len(v[0])<20 for v in keys.values()):raise RuntimeError('Invalid private handover')
 if CONFIG.is_symlink():raise RuntimeError('Unexpected nginx config symlink')
 old=CONFIG.read_text()
 if OLD not in old:raise RuntimeError('Marketing routing changed; inspect before publishing')
 site_path=BENCH/'sites'/SITE/'site_config.json'
 original=site_path.read_bytes();site=json.loads(original)
 if site.get('host_name')!='https://www.sisuacademylk.com':raise RuntimeError('Public site hostname changed')
 if not (BENCH/'apps/institute_lms/institute_lms/checkout_captcha.py').is_file():raise RuntimeError('Deploy application first')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 backup=Path('/home/sisu/.sisu-secrets')/('security-web-'+stamp);backup.mkdir(mode=0o700)
 shutil.copy2(CONFIG,backup/'nginx.conf');(backup/'site_config.private.json').write_bytes(original)
 release=Path('/var/www/sisu-marketing-releases')/('security-5938b1a-'+stamp)
 release.mkdir(mode=0o755)
 # The private-backup umask also affects mkdir; explicitly open the public directory.
 release.chmod(0o755)
 with tarfile.open(ARCHIVE) as t:
  seen=set()
  for m in t.getmembers():
   path=PurePosixPath(m.name)
   if path.is_absolute() or '..' in path.parts or not m.isfile() or m.name in seen:raise RuntimeError('Unexpected marketing archive entry')
   seen.add(m.name);dst=release/m.name;dst.parent.mkdir(parents=True,exist_ok=True)
   dst.write_bytes(t.extractfile(m).read());dst.chmod(0o644)
   for parent in dst.parents:
    if parent==release:break
    parent.chmod(0o755)
 for name in ('index.html','app.js','theme.css','config.js'):
  if not (release/name).is_file():raise RuntimeError('Required marketing file missing')
 # Verify the actual nginx worker can read the release before switching routing.
 nginx_user=re.search(r'^\s*user\s+([^;\s]+)',Path('/etc/nginx/nginx.conf').read_text(),re.M)
 if not nginx_user:raise RuntimeError('Cannot identify nginx worker user')
 for name in seen:
  subprocess.run(['sudo','-u',nginx_user.group(1),'--','test','-r',str(release/name)],check=True)
 user=pwd.getpwnam('sisu')
 def cache():
  subprocess.run(['sudo','-H','-u','sisu','--','/usr/local/bin/bench','--site',SITE,'clear-cache'],cwd=BENCH,check=True)
 try:
  site['il_checkout_recaptcha']={'enabled':True,'site_key':keys['site_key'][0],'secret_key':keys['secret_key'][0],'hostnames':['sisuacademylk.com','www.sisuacademylk.com']}
  tmp=site_path.with_name('site_config.security-tmp.json')
  if tmp.exists():raise RuntimeError('Temporary config already exists')
  tmp.write_text(json.dumps(site,indent=2));tmp.chmod(0o600);os.chown(tmp,user.pw_uid,user.pw_gid);os.replace(tmp,site_path)
  CONFIG.write_text(old.replace(OLD,str(release)));CONFIG.chmod(0o644)
  subprocess.run(['nginx','-t'],check=True)
  cache()
  subprocess.run(['systemctl','reload','nginx'],check=True)
  for attempt in range(6):
   try:
    for path,file in (('/', 'index.html'),('/marketing/app.js','app.js'),('/marketing/theme.css','theme.css')):
     print('Checking marketing URL: '+path,flush=True)
     with urllib.request.urlopen('https://www.sisuacademylk.com'+path,timeout=20) as r:data=r.read()
     if data!=(release/file).read_bytes():raise RuntimeError('Published marketing content mismatch')
    break
   except Exception:
    if attempt==5:raise
    time.sleep(3)
 except Exception:
  CONFIG.write_text(old);site_path.write_bytes(original);os.chown(site_path,user.pw_uid,user.pw_gid)
  cache();subprocess.run(['nginx','-t'],check=True);subprocess.run(['systemctl','reload','nginx'],check=True)
  print('Previous marketing routing and CAPTCHA config restored. Private backup:',backup)
  raise
 print('PUBLISHED: marketing release and public-campus CAPTCHA. Private backup:',backup)
 print('Complete a real checkbox in public checkout to verify Google domain registration. Do not submit a payment for this check.')
 PRIVATE.unlink()
if __name__=='__main__':main()
