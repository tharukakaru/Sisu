"""Static Dev teacher-flow correction only; no migrations or service restarts."""
import hashlib,os,pwd,shutil,subprocess,tarfile
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone
ROOT=Path('/home/sisu/frappe-bench'); APP=ROOT/'apps/institute_lms'
ARCHIVE=Path('/tmp/sisu-dev-flow-audit.tgz')
def main():
 if os.geteuid()!=0:raise RuntimeError('Run as root')
 if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()!='6bc6ee20d655ea6b94a29296c013b1d3a4d076144eed6875b4b55c2ac0e5ec9f':raise RuntimeError('Checksum mismatch')
 import fcntl
 lock=open('/var/lock/sisu-merged-deployment.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 payload={}
 with tarfile.open(ARCHIVE) as t:
  for m in t.getmembers():
   n=m.name;p=PurePosixPath(n)
   if not m.isfile() or p.is_absolute() or '..' in p.parts or not(n.startswith('institute_lms/public/portal/') or n=='institute_lms/www/campus.html' or n=='frontend/src/native/ProviderFirstLogin.vue'):raise RuntimeError('Invalid file')
   dst=APP/n
   if any(x.is_symlink() for x in [dst,*dst.parents] if x!=Path('/')):raise RuntimeError('Symlink destination')
   payload[n]=t.extractfile(m).read()
 source=APP/'frontend/src/native/ProviderFirstLogin.vue'
 if hashlib.sha256(source.read_bytes().replace(b'\r\n',b'\n')).hexdigest() not in ('cc80c4681021108dba13211ef6a85f5554734cbd8c66444c89e9d115c0cf8691',hashlib.sha256(payload['frontend/src/native/ProviderFirstLogin.vue'].replace(b'\r\n',b'\n')).hexdigest()):raise RuntimeError('Teacher source changed; nothing installed')
 entry='institute_lms/www/campus.html'
 if entry not in payload:raise RuntimeError('Entry missing')
 os.umask(0o077);user=pwd.getpwnam('sisu')
 backup=Path('/home/sisu/.sisu-secrets')/('dev-flow-audit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
 backup.mkdir(mode=0o700)
 # Retain old chunks for already-open tabs; switch HTML only after assets exist.
 for n in sorted(payload,key=lambda n:n in (entry,'institute_lms/public/portal/index.html')):
  dst=APP/n
  if dst.exists():
   saved=backup/n;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dst,saved)
  dst.parent.mkdir(parents=True,exist_ok=True)
  temp=dst.with_name(dst.name+'.dialog-fix-tmp')
  with temp.open('xb') as f:f.write(payload[n])
  os.chown(temp,user.pw_uid,user.pw_gid);temp.chmod(0o644);os.replace(temp,dst)
 for site in ('staging.sisuacademylk.com','sisuacademylk.com','teen.sisuacademylk.com','platform.sisuacademylk.com'):
  subprocess.run(['sudo','-H','-u','sisu','/usr/local/bin/bench','--site',site,'clear-website-cache'],cwd=ROOT,check=True)
 print('DEPLOYED: Dev unified teacher automatic completion flow. No database migrations or service restarts. Backup: '+str(backup))
if __name__=='__main__':main()
