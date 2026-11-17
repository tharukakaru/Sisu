"""Deploy only the hero artwork and its marketing references, with rollback."""
from pathlib import Path,PurePosixPath
import hashlib,json,os,re,shutil,subprocess,tarfile
from datetime import datetime,timezone
ARCHIVE=Path('/tmp/sisu-hero-clean.tgz')
DIGEST='8471969ded00ac78e9874d48779f6dea6a0d3f3f70eaef27b81e2398bdad4970'
def main():
 if os.geteuid()!=0:raise RuntimeError('Run as root')
 import fcntl
 lock=open('/var/lock/sisu-merged-deployment.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()!=DIGEST:raise RuntimeError('Archive mismatch')
 config=Path('/etc/nginx/conf.d/sisu-main-public.conf').read_text()
 roots=set(re.findall(r'(?:root|alias)\s+(/var/www/sisu-marketing-releases/[^;\s]+)',config))
 roots={r.rstrip('/') for r in roots}
 if len(roots)!=1:raise RuntimeError('Unexpected marketing routes')
 root=Path(roots.pop())
 if root.is_symlink() or root.resolve().parent!=Path('/var/www/sisu-marketing-releases'):raise RuntimeError('Unexpected release directory')
 with tarfile.open(ARCHIVE) as t:
  payload={}
  for m in t.getmembers():
   if not m.isfile() or m.name in payload or PurePosixPath(m.name).is_absolute() or '..' in PurePosixPath(m.name).parts:raise RuntimeError('Unsafe archive')
   payload[m.name]=t.extractfile(m).read()
 manifest=json.loads(payload.pop('manifest.json'))
 if set(payload)!=set(manifest):raise RuntimeError('Manifest mismatch')
 for n,d in payload.items():
  target=root/n
  if any(p.is_symlink() for p in [target,*target.parents]):raise RuntimeError('Symlink destination')
  if hashlib.sha256(d).hexdigest()!=manifest[n]['after']:raise RuntimeError('Payload mismatch')
  actual=hashlib.sha256(target.read_bytes().replace(b'\r\n',b'\n')).hexdigest() if target.exists() else None
  if actual not in (manifest[n]['before'],manifest[n]['after']):raise RuntimeError('Live file differs: '+n)
 backup=Path('/home/sisu/.sisu-secrets')/('hero-clean-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
 backup.mkdir(mode=0o700);existed=[]
 for n in payload:
  if (root/n).exists():
   dst=backup/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/n,dst);existed.append(n)
 try:
  for n in sorted(payload,key=lambda n:(not n.startswith('assets/'),n.endswith('.html'))):
   target=root/n;temp=target.with_name(target.name+'.hero-tmp')
   with temp.open('xb') as f:f.write(payload[n])
   temp.chmod(0o644);os.replace(temp,target)
  for n,d in payload.items():
   url='https://www.sisuacademylk.com'+('/' if n=='index.html' else '/marketing/'+n)
   result=subprocess.run(['curl','--noproxy','*','--resolve','www.sisuacademylk.com:443:127.0.0.1','-fsS','--max-time','30',url],capture_output=True,check=True)
   if result.stdout!=d:raise RuntimeError('Served content mismatch: '+n)
 except Exception:
  for n in existed:shutil.copy2(backup/n,root/n)
  print('Previous marketing files restored. Backup:',backup);raise
 print('DEPLOYED: clean hero image; HTTPS checks passed. No migrations or restarts. Backup:',backup)
if __name__=='__main__':main()
